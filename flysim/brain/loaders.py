"""Real connectome loaders: FlyWire/Codex tables -> :class:`Connectome`.

This is the adapter that makes the promise in ``docs/ARCHITECTURE.md`` real. Whatever the
source, the output is the same object :class:`~flysim.brain.lif.LIFBrain` already takes,
so a real connectome runs through the unchanged environment, encoder, decoder, runner and
dashboard.

Not on the Starter Phase code path
----------------------------------
This module imports pandas and SciPy. Nothing imports it unless you ask for a real
connectome (``--connectome flywire``), so ``python main.py`` still runs on NumPy and
Matplotlib alone. :func:`flysim.brain.builders.build` imports it lazily.

Getting the data (no credentials required)
------------------------------------------
1. Go to ``codex.flywire.ai`` -> Downloads, pick **FAFB v783**, and fetch:

   * **Connections (Filtered)** (~68 MB) -- the edge list. Essential.
   * **Cell Types** (~900 KB) -- what makes LC4 / LPLC2 / DNp01 findable. Essential.
   * **Neurotransmitter Type Predictions** (~1.7 MB) -- signs each edge. Essential.
   * *Classification / Hierarchical Annotations* (~930 KB) -- optional, adds side.
   * *Visual Neuron Annotations* (~630 KB) -- optional, adds LC4 subtypes.

   Skip the Synapse Table (2.7 GB) and Neuron Skeletons (13 GB) unless you specifically
   need per-synapse coordinates or morphology.

2. Drop them all in one directory, under a cache root that is NOT inside this repo::

       E:\\FlyConnectome\\cache\\flywire\\v783\\

   Keep the original filenames. This module identifies each file by content, so it does
   not matter what Codex called them or what order you downloaded them in.

3. ``setx FLYSIM_CACHE_DIR "E:\\FlyConnectome\\cache"``
4. ``python main.py --connectome flywire``

Every annotation file found in that directory is merged on the root-id column, so cell
types and neurotransmitter predictions arriving as separate downloads is handled
automatically. The first load converts each CSV to Parquet beside it; later loads use
those and are roughly an order of magnitude faster.

The CAVE/`caveclient` route produces the same two dataframes and feeds the same functions;
see ``docs/CONNECTOME_ACCESS.md`` §4B.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover - depends on local environment
    raise ImportError(
        "Real connectome loading needs pandas. Install it with `pip install pandas "
        "pyarrow scipy`, or use --connectome mock12 / synthetic120, which need neither."
    ) from exc

from flysim.brain.connectome import PARAM_OVERRIDES, Connectome
from flysim.brain.credentials import get_token

# ---------------------------------------------------------------------------
# Schema tolerance
# ---------------------------------------------------------------------------
# Column names drift between FlyWire releases and differ again for NeuPrint exports.
# Rather than hardcoding one release's spelling and failing cryptically on another, each
# logical field lists the spellings seen in the wild, in preference order.

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "pre": ("pre_root_id", "pre_pt_root_id", "bodyId_pre", "pre", "source"),
    "post": ("post_root_id", "post_pt_root_id", "bodyId_post", "post", "target"),
    "weight": ("syn_count", "weight", "synapses", "n_syn", "count"),
    "nt": ("nt_type", "neurotransmitter", "nt", "top_nt"),
    "root_id": ("root_id", "bodyId", "pt_root_id", "id"),
    # `primary_type` (Codex's consolidated_cell_types) must outrank `type`
    # (visual_neuron_types). The visual table covers only the optic system, so DNp01 --
    # the Giant Fiber, a descending neuron -- is absent from it. Resolving to `type`
    # therefore finds 0 Giant Fibers while still finding all 104 LC4, which fails in the
    # most confusing way possible: a plausible-looking network with no output cell.
    "cell_type": ("primary_type", "cell_type", "type", "hemibrain_type", "cell_class"),
    "side": ("side", "hemisphere"),
}


def _resolve(frame: pd.DataFrame, field: str, required: bool = True) -> str | None:
    """Find which spelling of a logical column this table actually uses."""
    for candidate in COLUMN_ALIASES[field]:
        if candidate in frame.columns:
            return candidate
    if not required:
        return None
    raise KeyError(
        f"Could not find a '{field}' column. Tried {COLUMN_ALIASES[field]}; "
        f"the table has {list(frame.columns)[:12]}. Add the correct spelling to "
        "COLUMN_ALIASES in flysim/brain/loaders.py."
    )


# ---------------------------------------------------------------------------
# Neurotransmitter -> sign
# ---------------------------------------------------------------------------
# A connectome gives you a synapse COUNT, which is unsigned. The sign has to come from the
# neurotransmitter prediction.
#
# In Drosophila, acetylcholine is the main fast excitatory transmitter, while both GABA and
# glutamate are typically inhibitory (glutamate acts largely through the GluCl chloride
# channel, unlike the vertebrate case). The aminergic transmitters are modulatory and are
# not meaningfully represented by a fast synaptic current at all.
#
# Two honest caveats: these are per-neuron ML predictions with real error rates, not
# measurements, and a neuron classified aminergic here contributes nothing rather than
# something slow and diffuse, which is a modelling failure rather than an accuracy claim.

NT_SIGN: dict[str, float] = {
    "ACH": +1.0,
    "ACETYLCHOLINE": +1.0,
    "GABA": -1.0,
    "GLUT": -1.0,
    "GLUTAMATE": -1.0,
    "DA": 0.0,       # dopamine    - modulatory, not modelled
    "SER": 0.0,      # serotonin   - modulatory, not modelled
    "OCT": 0.0,      # octopamine  - modulatory, not modelled
    "UNK": +1.0,     # unknown: assume excitatory, the commonest case
}

DEFAULT_NT_SIGN = +1.0

# Synapse count -> picoamps per presynaptic spike. This is THE constant a connectome
# cannot give you, and it is not a free parameter: it decides whether the circuit is a
# reflex or an amplifier.
#
# Calibrated with tools/calibrate_pa.py against the real FlyWire LC4/LPLC2 -> DNp01
# subnetwork (15,452 neurons, one hop) under the SHIU_2024 uniform parameters. Measured
# escape threshold, and whether a slow, non-threatening approach is correctly ignored:
#
#     pA/syn   escape theta   slow approach
#     0.02         14.5 deg   FIRES   <- ungated: escapes from a harmless object
#     0.01         19.7 deg   ignored
#     0.007        --         (chosen: mid-window)
#     0.005        28.0 deg   ignored
#     0.002        no escape  ignored <- too weak: GF never reaches threshold
#     0.001        no escape  ignored
#
# The usable window is roughly 0.005-0.01 -- far narrower than under the earlier
# hand-tuned per-population parameters, where everything from 0.005 to 0.2 worked. That
# apparent robustness was an artefact of parameters I invented; with published uniform
# biophysics the model is genuinely sensitive to this constant, which is the more honest
# result and a reason to distrust any conclusion that depends on its exact value.
#
# 0.007 is the middle of the passing window on a log scale. It is NOT a physiological
# measurement: a connectome gives anatomy, not synaptic strength. Fit it against real
# electrophysiology before claiming anything quantitative from this model.
DEFAULT_PA_PER_SYNAPSE = 0.007

# Field-conventional floor for calling a pair "connected". Below ~5 synapses the edge is
# dominated by segmentation and detection error.
DEFAULT_MIN_SYNAPSES = 5

# Cap on the anatomical backdrop. Purely a rendering budget.
CONTEXT_MAX_POINTS = 25_000


# ---------------------------------------------------------------------------
# Functional population mapping
# ---------------------------------------------------------------------------
# The engine's populations are functional roles (LC4 / PMN / INH / GF), while a real
# connectome carries hundreds of anatomical cell types. This maps one onto the other so
# the existing encoder, decoder, runner and dashboard work unchanged on real data.
#
# This is a deliberate coarsening for pipeline compatibility. The true per-neuron cell type
# is preserved in `Connectome.labels`, so nothing is lost -- a real study would group by
# those instead of by these four roles.

VISUAL_TYPES: tuple[str, ...] = ("LC4", "LPLC2")
"""Looming-selective visual projection neurons that drive the Giant Fiber."""

COMMAND_TYPES: tuple[str, ...] = ("DNP01", "DNp01", "GF", "GIANT FIBER")
"""The Giant Fiber. DNp01 is its designation in the descending-neuron nomenclature."""


def assign_population(cell_type: str, nt: str) -> str:
    """Map an anatomical cell type onto one of the engine's four functional roles."""
    upper = str(cell_type).upper().strip()

    if any(upper == t.upper() or upper.startswith(t.upper() + "_") for t in COMMAND_TYPES):
        return "GF"
    if any(upper.startswith(t.upper()) for t in VISUAL_TYPES):
        return "LC4"
    # Everything else splits on sign: inhibitory cells become the gating population,
    # excitatory ones the premotor relay.
    if NT_SIGN.get(str(nt).upper(), DEFAULT_NT_SIGN) < 0:
        return "INH"
    return "PMN"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def cache_root() -> Path:
    """Resolve the cache directory, which must live outside this repo.

    Falls back to the registry for the same reason token lookup does: a shell started
    before ``setx FLYSIM_CACHE_DIR ...`` ran never sees the value, and would silently
    fall back to the home directory instead -- putting a multi-gigabyte connectome cache
    somewhere nobody asked for.
    """
    env = (os.environ.get("FLYSIM_CACHE_DIR") or "").strip()
    if not env:
        env = get_token("FLYSIM_CACHE_DIR", required=False) or ""
    if env:
        return Path(env)
    return Path.home() / ".flysim-cache"


# Codex hands you one download per annotation kind, with names like
# "cell_types.csv.gz" or "neurotransmitter_type_predictions.csv". Rather than demanding a
# fixed filename, files are identified by what is in them. These hints only decide which
# bucket a file goes in; the actual column detection is done by _resolve().

_CONNECTION_HINTS = ("connection",)

# Files that are large, per-synapse, or otherwise not per-neuron annotations. Merging
# these would be slow and pointless, so they are skipped with a note.
_SKIP_HINTS = (
    "synapse", "skeleton", "column", "size", "community", "tag",
)

# Coordinates are per-neuron but are NOT merged into the annotation table: the position
# column is a bracketed string that would survive the merge as useless text. Handled
# separately by _load_positions.
_COORDINATE_HINTS = ("coordinate", "position")


def _read_any(path: Path) -> pd.DataFrame:
    """Read a CSV/CSV.GZ/Parquet table, caching a Parquet copy beside it on first use."""
    if path.suffix == ".parquet":
        return pd.read_parquet(path)

    # Strip .csv or .csv.gz to build the cache name.
    stem = path.name.split(".")[0]
    parquet = path.with_name(f"{stem}.parquet")
    if parquet.exists():
        return pd.read_parquet(parquet)

    frame = pd.read_csv(path)
    try:
        frame.to_parquet(parquet, index=False)
        print(f"  cached {parquet.name} ({parquet.stat().st_size / 2**20:.1f} MiB)")
    except (ImportError, OSError, ValueError) as exc:
        # Parquet is an optimisation, not a requirement -- a failure here must not stop
        # the load.
        print(f"  (could not write {parquet.name}: {exc})")
    return frame


def _discover(directory: Path) -> tuple[Path, list[Path]]:
    """Sort the files in a download directory into (connections, annotations)."""
    if not directory.is_dir():
        raise FileNotFoundError(
            f"{directory} does not exist.\n"
            "Download the FAFB v783 tables from codex.flywire.ai -> Downloads "
            "(Connections (Filtered), Cell Types, Neurotransmitter Type Predictions) and "
            f"place them in that directory. No account or API token is required."
        )

    candidates = [
        p for p in sorted(directory.iterdir())
        if p.suffix in (".csv", ".gz", ".parquet") and p.is_file()
    ]

    connection_files: list[Path] = []
    annotations: list[Path] = []
    coordinate_files: list[Path] = []
    for path in candidates:
        name = path.name.lower()
        if any(h in name for h in _CONNECTION_HINTS):
            connection_files.append(path)
        elif any(h in name for h in _COORDINATE_HINTS):
            coordinate_files.append(path)
        elif any(h in name for h in _SKIP_HINTS):
            print(f"  skipping {path.name} (not a per-neuron annotation)")
        else:
            annotations.append(path)

    if not connection_files:
        raise FileNotFoundError(
            f"No connections table found in {directory}. Expected a file with "
            f"'connection' in its name; the directory contains: "
            f"{[p.name for p in candidates][:10]}"
        )

    # Prefer the thresholded edge list. The unfiltered one carries sub-threshold pairs
    # dominated by segmentation error, and is four times the size.
    filtered = [p for p in connection_files if "unfiltered" not in p.name.lower()]
    chosen = min(filtered or connection_files, key=lambda p: p.stat().st_size)
    if len(connection_files) > 1:
        print(f"  using {chosen.name} for connections")

    # A Parquet cache written by a previous run sits beside its CSV; do not read both.
    seen_stems: set[str] = set()
    deduped: list[Path] = []
    for path in annotations:
        stem = path.name.split(".")[0]
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        deduped.append(path)

    return chosen, deduped, coordinate_files


def _load_positions(paths: list[Path]) -> pd.DataFrame | None:
    """Parse marked-point coordinates into a root_id-indexed frame, in micrometres.

    Codex stores the position as a bracketed string, ``"[352484 175164 229040]"``, in
    nanometres. Several rows may exist per neuron -- roughly 1.7 on average for FAFB v783
    -- so they are averaged into one representative point.

    Sanity check on the units: the resulting extent is ~815 x 392 x 278 um, which matches
    an adult Drosophila brain (roughly 600 x 350 x 250 um). Reading the same numbers as
    4x4x40 nm voxels would give ~3261 x 1566 x 11139 um, which is absurd -- a useful guard
    if a future release changes the convention.
    """
    if not paths:
        return None

    frame = _read_any(paths[0])
    id_col = _resolve(frame, "root_id", required=False)
    if id_col is None or "position" not in frame.columns:
        print(f"  skipping {paths[0].name} (no recognisable position column)")
        return None

    parts = frame["position"].astype(str).str.strip("[]").str.split()
    xyz = np.array([[float(v) for v in row] for row in parts], dtype=np.float64) / 1000.0

    out = pd.DataFrame(
        {"root_id": frame[id_col].to_numpy(), "x": xyz[:, 0],
         "y": xyz[:, 1], "z": xyz[:, 2]}
    )
    averaged = out.groupby("root_id")[["x", "y", "z"]].mean()
    print(f"  positions for {len(averaged):,} neurons ({paths[0].name})")
    return averaged


def load_codex_tables(directory: str | Path | None = None, version: str = "v783"):
    """Load a FlyWire Codex download directory.

    Files are identified by content rather than by exact filename, and every per-neuron
    annotation table found is merged on the root-id column -- so Codex splitting cell
    types and neurotransmitter predictions into separate downloads needs no special
    handling from you.

    Returns:
        ``(connections, annotations, positions)``. ``positions`` is None when no
        coordinate table was downloaded -- everything still works, the anatomical view
        simply has nothing to draw.
    """
    directory = Path(directory) if directory else cache_root() / "flywire" / version
    print(f"Loading FlyWire tables from {directory}")

    connection_path, annotation_paths, coordinate_paths = _discover(directory)
    connections = _read_any(connection_path)

    if not annotation_paths:
        raise FileNotFoundError(
            f"No annotation tables found in {directory}. At minimum you need the "
            "'Cell Types' download, or nothing can be identified as LC4 or DNp01."
        )

    merged: pd.DataFrame | None = None
    for path in annotation_paths:
        frame = _read_any(path)
        id_col = _resolve(frame, "root_id", required=False)
        if id_col is None:
            print(f"  skipping {path.name} (no root-id column)")
            continue

        frame = frame.rename(columns={id_col: "root_id"}).drop_duplicates("root_id")
        if merged is None:
            merged = frame
        else:
            # Only bring in columns we do not already have, so the first file supplying
            # a field wins and there are no _x/_y suffix collisions.
            new_cols = [c for c in frame.columns if c not in merged.columns]
            if new_cols:
                merged = merged.merge(
                    frame[["root_id", *new_cols]], on="root_id", how="outer"
                )
        print(f"  merged {path.name} ({len(frame):,} rows)")

    if merged is None:
        raise ValueError(
            f"None of the annotation files in {directory} had a recognisable root-id "
            "column. Add the correct spelling to COLUMN_ALIASES in this module."
        )

    positions = _load_positions(coordinate_paths)
    print(f"  {len(connections):,} raw edges, {len(merged):,} annotated neurons")
    return connections, merged, positions


# ---------------------------------------------------------------------------
# Pathway extraction
# ---------------------------------------------------------------------------


def select_pathway(
    connections: pd.DataFrame,
    classification: pd.DataFrame,
    seed_types: tuple[str, ...] = VISUAL_TYPES + ("DNp01",),
    hops: int = 1,
    min_synapses: int = DEFAULT_MIN_SYNAPSES,
    max_neurons: int = 4000,
) -> set:
    """Grow a subnetwork outward from a set of seed cell types.

    Whole-brain simulation is rarely what you want first (see ``docs/ARCHITECTURE.md``
    §6). This pulls out the neurons that actually matter for a pathway: the seeds, plus
    everything within ``hops`` synapses of them.

    Args:
        seed_types: cell types to start from, e.g. ``("LC4", "LPLC2", "DNp01")``.
        hops: how many synaptic steps to expand. 0 returns only the seeds.
        min_synapses: edges below this are ignored during expansion.
        max_neurons: safety cap. Expansion stops and warns rather than pulling in the
            whole brain, which one hop from a well-connected descending neuron can do.

    Returns:
        The set of root ids in the subnetwork.
    """
    id_col = _resolve(classification, "root_id")
    type_col = _resolve(classification, "cell_type")
    pre_col = _resolve(connections, "pre")
    post_col = _resolve(connections, "post")
    weight_col = _resolve(connections, "weight")

    wanted = {t.upper() for t in seed_types}
    types_upper = classification[type_col].astype(str).str.upper()
    seed_mask = types_upper.isin(wanted)
    # Also catch subtype spellings such as "LC4_a" or "LPLC2_R".
    for t in wanted:
        seed_mask |= types_upper.str.startswith(t + "_")

    selected = set(classification.loc[seed_mask, id_col])
    if not selected:
        available = sorted(types_upper.dropna().unique())[:15]
        raise ValueError(
            f"No neurons matched seed types {sorted(wanted)}. "
            f"The classification table's types look like: {available}"
        )
    print(f"  seeds: {len(selected):,} neurons matching {sorted(wanted)}")

    strong = connections[connections[weight_col] >= min_synapses]

    for hop in range(hops):
        touching = strong[
            strong[pre_col].isin(selected) | strong[post_col].isin(selected)
        ]
        grown = selected | set(touching[pre_col]) | set(touching[post_col])

        if len(grown) > max_neurons:
            print(
                f"  hop {hop + 1} would reach {len(grown):,} neurons (cap {max_neurons:,}); "
                "stopping expansion. Raise max_neurons or lower hops to go further."
            )
            break
        selected = grown
        print(f"  hop {hop + 1}: {len(selected):,} neurons")

    return selected


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------


def connectome_from_tables(
    connections: pd.DataFrame,
    classification: pd.DataFrame,
    keep_ids: set | None = None,
    name: str = "flywire",
    min_synapses: int = DEFAULT_MIN_SYNAPSES,
    pa_per_synapse: float = DEFAULT_PA_PER_SYNAPSE,
    sparse: bool | None = None,
    positions: "pd.DataFrame | None" = None,
) -> Connectome:
    """Convert FlyWire-shaped tables into a :class:`Connectome`.

    Args:
        keep_ids: restrict to this subnetwork. None uses every neuron in the tables,
            which at whole-brain scale forces a sparse matrix.
        sparse: force dense/sparse. None picks automatically (sparse above 3000 neurons,
            where a dense float32 matrix passes ~36 MB and keeps growing quadratically).
    """
    pre_col = _resolve(connections, "pre")
    post_col = _resolve(connections, "post")
    weight_col = _resolve(connections, "weight")
    nt_col = _resolve(connections, "nt", required=False)
    id_col = _resolve(classification, "root_id")
    type_col = _resolve(classification, "cell_type")

    edges = connections[connections[weight_col] >= min_synapses]
    if keep_ids is not None:
        edges = edges[edges[pre_col].isin(keep_ids) & edges[post_col].isin(keep_ids)]
    if edges.empty:
        raise ValueError(
            f"No edges survived filtering (min_synapses={min_synapses}"
            f"{', restricted to a subnetwork' if keep_ids is not None else ''})."
        )

    # Per-neuron annotation, indexed for fast lookup.
    annotation = classification.drop_duplicates(subset=[id_col]).set_index(id_col)
    type_of = annotation[type_col].astype(str)

    # The presynaptic cell's transmitter sets the sign of every edge it makes: a neuron
    # releases one fast transmitter at all of its outputs (Dale's principle). Prefer a
    # per-neuron annotation where the table has one, and fall back to the per-edge
    # prediction otherwise.
    nt_by_neuron = None
    ann_nt_col = _resolve(annotation.reset_index(), "nt", required=False)
    if ann_nt_col is not None and ann_nt_col in annotation.columns:
        nt_by_neuron = annotation[ann_nt_col].astype(str).str.upper()

    ids = sorted(set(edges[pre_col]) | set(edges[post_col]))
    index = {root_id: i for i, root_id in enumerate(ids)}
    n = len(ids)

    rows = edges[pre_col].map(index).to_numpy(dtype=np.int64)
    cols = edges[post_col].map(index).to_numpy(dtype=np.int64)
    counts = edges[weight_col].to_numpy(dtype=np.float32)

    if nt_by_neuron is not None:
        nt_series = edges[pre_col].map(nt_by_neuron)
    elif nt_col is not None:
        nt_series = edges[nt_col].astype(str).str.upper()
    else:
        nt_series = pd.Series("UNK", index=edges.index)
    signs = nt_series.fillna("UNK").map(NT_SIGN).fillna(DEFAULT_NT_SIGN).to_numpy(np.float32)

    data = counts * pa_per_synapse * signs

    # Modulatory neurons map to sign 0, producing structural zeros. Dropping them keeps
    # the sparse matrix honest about how many real edges it holds.
    nonzero = data != 0.0
    dropped = int((~nonzero).sum())

    if sparse is None:
        sparse = n > 3000
    if sparse:
        import scipy.sparse as sp

        weights = sp.coo_matrix(
            (data[nonzero], (rows[nonzero], cols[nonzero])),
            shape=(n, n), dtype=np.float32,
        ).tocsr()
    else:
        weights = np.zeros((n, n), dtype=np.float32)
        # np.add.at accumulates duplicates instead of overwriting, matching the sparse
        # path: two synapses between the same pair add their currents.
        np.add.at(weights, (rows[nonzero], cols[nonzero]), data[nonzero])

    # Labels keep the true anatomy; populations carry the coarse functional role.
    labels: list[str] = []
    populations: dict[str, list[int]] = {}
    for i, root_id in enumerate(ids):
        cell_type = type_of.get(root_id, "unknown")
        nt = nt_by_neuron.get(root_id, "UNK") if nt_by_neuron is not None else "UNK"
        labels.append(f"{cell_type}:{root_id}")
        populations.setdefault(assign_population(cell_type, nt), []).append(i)

    population_arrays = {k: np.asarray(v, dtype=np.int64) for k, v in populations.items()}

    for required in ("LC4", "GF"):
        if required not in population_arrays:
            raise ValueError(
                f"The extracted subnetwork contains no {required} population, so the "
                "looming encoder or the Giant Fiber decoder would have nothing to bind "
                "to. Check that your seed types matched (see select_pathway's output)."
            )

    # Anatomical coordinates, in the same order as `ids` so row i is neuron i. Neurons
    # without a coordinate get NaN rather than being dropped: they still participate in
    # the simulation, they just cannot be drawn.
    coords = None
    if positions is not None:
        coords = positions.reindex(ids)[["x", "y", "z"]].to_numpy(dtype=np.float64)
        located = int(np.isfinite(coords[:, 0]).sum())
        if located == 0:
            coords = None
        elif located < len(ids):
            print(f"  {len(ids) - located:,} neurons have no coordinate (drawn as absent)")

    # Anatomical backdrop: positioned neurons excluded from this subnetwork. Subsampled,
    # because 139k faint dots costs render time and adds no information over 25k.
    context = None
    if positions is not None and coords is not None:
        outside = positions.drop(index=[i for i in ids if i in positions.index],
                                 errors="ignore")
        if len(outside):
            step = max(len(outside) // CONTEXT_MAX_POINTS, 1)
            context = outside.iloc[::step][["x", "y", "z"]].to_numpy(dtype=np.float64)
            print(f"  anatomical backdrop: {len(context):,} neurons (not simulated)")

    counts_str = ", ".join(f"{k}={len(v)}" for k, v in sorted(population_arrays.items()))
    print(f"  built connectome: {n:,} neurons, {int(nonzero.sum()):,} edges ({counts_str})")

    # A subnetwork of only visual cells and the Giant Fiber is degenerate, though the
    # reason stated here was wrong for a long time. Feedforward inhibition outrunning
    # excitation is how the hand-built 12-cell mock sets its threshold; on a real
    # connectome it was never tested and does not hold -- 8 of 5,476 inhibitory cells ever
    # fire, and DNp01 receives 12,629 inhibitory synapses that are essentially silent. The
    # real threshold there is integrate-to-threshold on a convergence sum, with the angle
    # set by where `pa_per_synapse` was fitted to put it.
    #
    # The warning is still worth keeping: a subnetwork missing its inhibitory cells is
    # missing a large part of the measured wiring, and that is a reason to distrust it
    # whatever the mechanism turns out to be.
    if "INH" not in population_arrays:
        print(
            "  WARNING: no inhibitory population in this subnetwork. A large part of the "
            "measured wiring is missing, so treat any threshold it produces with "
            "suspicion. Increase --flywire-hops or --flywire-max-neurons."
        )
    if dropped:
        print(f"  dropped {dropped:,} modulatory edges (aminergic, no fast current modelled)")

    return Connectome(
        name=name,
        labels=tuple(labels),
        weights=weights,
        populations=population_arrays,
        # Deliberately EMPTY. The hand-tuned per-population biophysics in PARAM_OVERRIDES
        # exists to make the 12-neuron teaching circuit produce an escape threshold; on a
        # real connectome it would let invented parameters do work that the measured
        # wiring should be doing. Real data gets uniform published parameters (SHIU_2024)
        # so that any structure in the behaviour is attributable to the anatomy.
        param_overrides={},
        positions=coords,
        context_positions=context,
        description=(
            f"Derived from FlyWire-shaped tables. {n} neurons, "
            f"{int(nonzero.sum())} edges at >= {min_synapses} synapses. "
            f"Weights are synapse count x {pa_per_synapse} pA, signed by predicted "
            "neurotransmitter -- a placeholder scaling, NOT a physiological measurement. "
            "Populations are a coarse functional mapping; true cell types are in labels."
        ),
    )


def build_flywire(
    directory: str | Path | None = None,
    version: str = "v783",
    seed_types: tuple[str, ...] = VISUAL_TYPES + ("DNp01",),
    hops: int = 1,
    max_neurons: int = 25_000,
    **kwargs,
) -> Connectome:
    """One-call path: Codex tables on disk -> a runnable :class:`Connectome`."""
    connections, classification, positions = load_codex_tables(directory, version)
    keep = select_pathway(
        connections, classification, seed_types=seed_types, hops=hops,
        min_synapses=kwargs.get("min_synapses", DEFAULT_MIN_SYNAPSES),
        max_neurons=max_neurons,
    )
    return connectome_from_tables(
        connections, classification, keep_ids=keep,
        name=f"flywire-{version}", positions=positions, **kwargs,
    )
