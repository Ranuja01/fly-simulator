"""NeuPrint loader: the male central nervous system, brain *and* nerve cord.

Why this dataset exists in the project
--------------------------------------
FlyWire's FAFB is a brain volume that stops at the neck. The Giant Fiber's cell body and
dendrites are in the brain, but its axon runs down the neck connective into the ventral
nerve cord, where it drives TTMn (the jump-muscle motor neuron) and PSI (wing). Those
cells are simply not in FAFB -- measured, its DNp01 receives 20,749 synapses and sends
540, none of them to a motor neuron. The escape circuit is decapitated.

``male-cns:v1.0`` contains both halves, and the pathway closes::

    LC4    -> DNp01    6,362 synapses
    LPLC2  -> DNp01    4,862 synapses
    DNp01  -> TTMn        90 synapses     <- the jump muscle
    DNp01  -> PSI         16 synapses     <- the wing

That is what this module is for: an output read from motor neurons rather than invented.

A different animal, not an upgrade
----------------------------------
This is a male fly; FAFB is a female. Cell identities do not correspond between them, so
calibration does not transfer -- ``pa_per_synapse`` and the encoder gain are refitted here.
Both stay selectable at runtime, which also makes an interesting control available: the
same engine, encoder and decoder driven by two independently reconstructed brains.

Credentials
-----------
Needs a NeuPrint auth token in ``NEUPRINT_APPLICATION_CREDENTIALS``; see
``flysim/brain/credentials.py``, which also reads it from the Windows registry when the
shell has a stale environment. Free, with no published rate limit -- but every fetch is
cached to Parquet, so a given subnetwork is downloaded once and never again.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover - depends on local environment
    raise ImportError(
        "NeuPrint loading needs pandas. Install with `pip install pandas pyarrow`."
    ) from exc

from flysim.brain.connectome import Connectome
from flysim.brain.credentials import get_token
from flysim.brain.loaders import DEFAULT_MIN_SYNAPSES, cache_root

NEUPRINT_SERVER = "neuprint.janelia.org"

VOXEL_NM = 8.0
"""Nanometres per unit of ``somaLocation``. Inferred from the resulting extent."""
DEFAULT_DATASET = "male-cns:v1.0"

ESCAPE_SEED_TYPES: tuple[str, ...] = ("LC4", "LPLC2", "DNp01", "TTMn", "PSI")
"""The escape circuit end to end: visual input, the command neuron, and its muscles."""

# Synapse count -> picoamps. Refitted for this dataset rather than inherited from
# FlyWire: a different animal has different absolute synapse counts. See
# tools/calibrate_pa.py for how this is fitted rather than chosen.
DEFAULT_PA_PER_SYNAPSE = 0.007

# NeuPrint spells transmitters out in full where Codex uses short codes.
#
# Note on glutamate: mapped inhibitory, which is correct for CENTRAL synapses in
# Drosophila (acting through the GluCl chloride channel) and wrong at the neuromuscular
# junction, where glutamate is excitatory. TTMn is glutamatergic and drives muscle -- but
# muscle is not modelled here, so the discrepancy has no effect today. It would matter
# the moment a body model is added.
NT_SIGN_FULL: dict[str, float] = {
    "acetylcholine": +1.0,
    "glutamate": -1.0,
    "gaba": -1.0,
    "histamine": -1.0,   # photoreceptor transmitter, inhibitory via HisCl
    "dopamine": 0.0,     # modulatory: a LIF model has no way to represent it
    "serotonin": 0.0,
    "octopamine": 0.0,
    "unclear": +1.0,     # commonest case when the prediction is uncertain
}


# ---------------------------------------------------------------------------
# Electrical synapses
# ---------------------------------------------------------------------------
# EM connectomics scores CHEMICAL synapses. Gap junctions leave no comparable signature
# and do not appear in ConnectsTo weights at all -- so a connectome is structurally
# incapable of carrying them, no matter how well reconstructed.
#
# That matters here more than almost anywhere else in the fly. The Giant Fiber drives TTMn
# and PSI through MIXED electrical-chemical synapses, and it is the electrical component
# that makes a single GF spike reliably fire the jump. Measured on the chemical counts
# alone, one GF spike delivers 0.49 pA to TTMn against the ~7 pA it needs: a 14x shortfall,
# and the escape pathway simply does not conduct.
#
# These connections are therefore supplied explicitly. This is NOT tuning to obtain a
# result: it is restoring a documented, named piece of anatomy that the data format cannot
# represent. It is listed here, in one table, rather than folded into a scaling constant,
# so that it stays visible and arguable.
ELECTRICAL_SYNAPSE_PA = 55.0
"""Current per presynaptic spike across a modelled gap junction, pA.

Sized so that ONE presynaptic spike fires the target, because that is the defining
functional property of this connection: one Giant Fiber spike, one jump. It is a statement
about reliability, not a measurement of conductance.

Derived rather than guessed. A single instantaneous current jump of amplitude A, decaying
with ``tau_syn`` into a membrane with time constant ``tau_m``, peaks at::

    V_peak = R * A * (tau_syn / (tau_m - tau_syn)) * (exp(-t/tau_m) - exp(-t/tau_syn))

which for the Shiu et al. parameters (tau_m 20 ms, tau_syn 5 ms, R 1 GOhm) comes to
0.157 * A, at t = 9.2 ms. Crossing the 7 mV gap from rest to threshold therefore needs
at least 44 pA; 55 leaves margin against inhibition arriving at the same moment.

The first attempt used 12 pA -- the STEADY-STATE current for a 7 mV deflection -- and the
motor neurons stayed silent, because a single spike never reaches steady state. It peaked
at 1.9 mV.
"""

ELECTRICAL_SYNAPSES: tuple[tuple[str, str], ...] = (
    ("DNp01", "TTMn"),   # Giant Fiber -> jump-muscle motor neuron
    ("DNp01", "PSI"),    # Giant Fiber -> peripherally synapsing interneuron (wing)
)
"""Known gap-junction pathways, as (presynaptic type, postsynaptic type).

Deliberately short and specific. Every entry needs a citable reason to be here; this is a
place to record established anatomy, not a knob."""


def _client(dataset: str):
    """Authenticated NeuPrint client, imported lazily to keep the starter path clean."""
    from neuprint import Client

    return Client(NEUPRINT_SERVER, dataset=dataset, token=get_token())


def _cache_dir(dataset: str) -> Path:
    return cache_root() / "neuprint" / dataset.replace(":", "-")


def assign_population(cell_type: str, superclass: str, nt: str) -> str:
    """Map a NeuPrint cell onto one of the engine's functional populations.

    Unlike the FlyWire loader, which had only a transmitter to sort by, NeuPrint carries a
    ``superclass``, so motor neurons are identified by what they *are* rather than guessed
    from their name.
    """
    sc = (superclass or "").lower()
    upper = (cell_type or "").upper()

    # Motor and efferent cells are the entire reason for using this dataset.
    if "motor" in sc or "efferent" in sc:
        return "MOTOR"
    if upper == "DNP01":
        return "GF"
    if upper.startswith(("LC4", "LPLC2")) or sc == "visual_projection":
        return "LC4"
    # T4 and T5 are the fly's elementary motion detectors -- T4 for moving light edges,
    # T5 for dark ones -- and each comes in four subtypes with opposite preferred
    # directions (a/b horizontal, c/d vertical). They arrive here for free as one-hop
    # inputs to LC4 and LPLC2, so the motion pathway is already wired into the escape
    # circuit; what was missing was anything to drive them. Split out of PMN so a motion
    # encoder can target them. The split moves no edges and changes no signs -- it is a
    # relabelling, and the regression gate confirms behaviour is unchanged without a
    # motion encoder attached.
    if upper.startswith(("T4", "T5")):
        return "T4T5"
    if NT_SIGN_FULL.get((nt or "unclear").lower(), +1.0) < 0:
        return "INH"
    return "PMN"


def fetch_subnetwork(
    dataset: str = DEFAULT_DATASET,
    seed_types: tuple[str, ...] = ESCAPE_SEED_TYPES,
    hops: int = 1,
    min_synapses: int = DEFAULT_MIN_SYNAPSES,
    max_neurons: int = 6000,
    refresh: bool = False,
):
    """Download, or load from cache, a subnetwork grown from a set of seed cell types.

    Returns ``(neurons, connections)`` as DataFrames. The cache key covers every parameter
    that changes the result, so re-running never re-queries the server.
    """
    key = f"{'-'.join(seed_types)}_h{hops}_s{min_synapses}_n{max_neurons}"
    directory = _cache_dir(dataset)
    neurons_path = directory / f"{key}.neurons.parquet"
    conn_path = directory / f"{key}.connections.parquet"

    if not refresh and neurons_path.exists() and conn_path.exists():
        neurons = pd.read_parquet(neurons_path)
        connections = pd.read_parquet(conn_path)
        print(f"  cached: {len(neurons):,} neurons, {len(connections):,} edges")
        return neurons, connections

    client = _client(dataset)
    quoted = ", ".join(f'"{t}"' for t in seed_types)

    seeds = client.fetch_custom(
        f"MATCH (n:Neuron) WHERE n.type IN [{quoted}] RETURN n.bodyId AS bodyId"
    )
    keep = set(seeds.bodyId.astype(np.int64))
    print(f"  seeds: {len(keep):,} neurons matching {list(seed_types)}")

    for hop in range(hops):
        ids = ", ".join(str(int(b)) for b in keep)
        grown = client.fetch_custom(
            f"MATCH (a:Neuron)-[w:ConnectsTo]->(b:Neuron) "
            f"WHERE (a.bodyId IN [{ids}] OR b.bodyId IN [{ids}]) "
            f"AND w.weight >= {min_synapses} "
            f"RETURN a.bodyId AS pre, b.bodyId AS post"
        )
        candidate = keep | set(grown.pre.astype(np.int64)) | set(grown.post.astype(np.int64))
        if len(candidate) > max_neurons:
            print(f"  hop {hop + 1} would reach {len(candidate):,} neurons "
                  f"(cap {max_neurons:,}); stopping expansion.")
            break
        keep = candidate
        print(f"  hop {hop + 1}: {len(keep):,} neurons")

    ids = ", ".join(str(int(b)) for b in keep)
    neurons = client.fetch_custom(
        f"MATCH (n:Neuron) WHERE n.bodyId IN [{ids}] "
        f"RETURN n.bodyId AS bodyId, n.type AS type, n.superclass AS superclass, "
        f"n.consensusNt AS nt, n.somaSide AS side, n.somaLocation AS soma"
    )
    connections = client.fetch_custom(
        f"MATCH (a:Neuron)-[w:ConnectsTo]->(b:Neuron) "
        f"WHERE a.bodyId IN [{ids}] AND b.bodyId IN [{ids}] "
        f"AND w.weight >= {min_synapses} "
        f"RETURN a.bodyId AS pre, b.bodyId AS post, w.weight AS weight"
    )
    # somaLocation arrives as a GeoJSON-ish dict; flatten to plain columns so the
    # cached Parquet stays simple and readable.
    def _xyz(value, axis):
        if isinstance(value, dict):
            coords = value.get("coordinates")
            if coords and len(coords) == 3:
                # NeuPrint stores somaLocation in dataset voxels, not nanometres.
                # At 8 nm/voxel the full extent works out to ~730 um across brain and
                # nerve cord, which is right for a Drosophila CNS; reading them as
                # nanometres gives 91 um, which is far too small for the animal.
                return float(coords[axis]) * VOXEL_NM / 1000.0
        return np.nan

    if "soma" in neurons.columns:
        for axis, name in enumerate(("x", "y", "z")):
            neurons[name] = neurons["soma"].map(lambda v, a=axis: _xyz(v, a))
        neurons = neurons.drop(columns=["soma"])
        located = int(neurons["x"].notna().sum())
        print(f"  soma coordinates for {located:,}/{len(neurons):,} neurons")

    print(f"  fetched {len(neurons):,} neurons, {len(connections):,} edges")

    directory.mkdir(parents=True, exist_ok=True)
    neurons.to_parquet(neurons_path, index=False)
    connections.to_parquet(conn_path, index=False)
    print(f"  cached to {directory}")
    return neurons, connections


def build_neuprint(
    dataset: str = DEFAULT_DATASET,
    seed_types: tuple[str, ...] = ESCAPE_SEED_TYPES,
    hops: int = 1,
    min_synapses: int = DEFAULT_MIN_SYNAPSES,
    max_neurons: int = 6000,
    pa_per_synapse: float = DEFAULT_PA_PER_SYNAPSE,
    refresh: bool = False,
) -> Connectome:
    """Fetch a NeuPrint subnetwork and return it as a :class:`Connectome`."""
    print(f"Loading NeuPrint {dataset}")
    neurons, connections = fetch_subnetwork(
        dataset, seed_types, hops, min_synapses, max_neurons, refresh
    )
    if connections.empty:
        raise ValueError("No connections survived filtering; nothing to simulate.")

    neurons = neurons.drop_duplicates("bodyId").set_index("bodyId")
    ids = sorted(set(connections.pre) | set(connections.post))
    index = {body: i for i, body in enumerate(ids)}
    n = len(ids)

    rows = connections.pre.map(index).to_numpy(np.int64)
    cols = connections.post.map(index).to_numpy(np.int64)

    # Sign comes from the PREsynaptic cell's transmitter (Dale's principle).
    nt_of = neurons["nt"].astype(str).str.lower()
    signs = connections.pre.map(nt_of).fillna("unclear").map(NT_SIGN_FULL)
    signs = signs.fillna(+1.0).to_numpy(np.float32)
    data = connections.weight.to_numpy(np.float32) * pa_per_synapse * signs

    # Modulatory neurons map to sign 0; dropping those edges keeps the matrix honest
    # about how many real connections it holds.
    # Restore the electrical connections the data format cannot carry.
    type_of = neurons["type"].astype(str)
    pre_types = connections.pre.map(type_of).fillna("")
    post_types = connections.post.map(type_of).fillna("")
    electrical = np.zeros(len(connections), dtype=bool)
    for pre_type, post_type in ELECTRICAL_SYNAPSES:
        electrical |= (pre_types == pre_type).to_numpy() & (post_types == post_type).to_numpy()
    if electrical.any():
        data = np.where(electrical, ELECTRICAL_SYNAPSE_PA, data).astype(np.float32)
        pairs = ", ".join(f"{a}->{b}" for a, b in ELECTRICAL_SYNAPSES)
        print(f"  {int(electrical.sum())} electrical synapses restored ({pairs}) "
              f"at {ELECTRICAL_SYNAPSE_PA} pA/spike -- absent from EM connectome data")

    nonzero = data != 0.0
    dropped = int((~nonzero).sum())

    if n > 3000:
        import scipy.sparse as sp

        weights = sp.coo_matrix(
            (data[nonzero], (rows[nonzero], cols[nonzero])), shape=(n, n), dtype=np.float32
        ).tocsr()
    else:
        weights = np.zeros((n, n), dtype=np.float32)
        # np.add.at accumulates duplicates rather than overwriting.
        np.add.at(weights, (rows[nonzero], cols[nonzero]), data[nonzero])

    have_xyz = all(c in neurons.columns for c in ("x", "y", "z"))
    positions = np.full((n, 3), np.nan, dtype=np.float64) if have_xyz else None

    labels: list[str] = []
    populations: dict[str, list[int]] = {}
    for i, body in enumerate(ids):
        if body in neurons.index:
            row = neurons.loc[body]
            cell_type, superclass, nt = str(row["type"]), str(row["superclass"]), str(row["nt"])
        else:
            cell_type, superclass, nt = "unknown", "", "unclear"
        labels.append(f"{cell_type}:{body}")
        populations.setdefault(assign_population(cell_type, superclass, nt), []).append(i)
        if positions is not None and body in neurons.index:
            row = neurons.loc[body]
            positions[i] = (row["x"], row["y"], row["z"])

    population_arrays = {k: np.asarray(v, np.int64) for k, v in populations.items()}
    for required in ("LC4", "GF"):
        if required not in population_arrays:
            raise ValueError(
                f"The extracted subnetwork contains no {required} population, so the "
                "encoder or decoder would have nothing to bind to."
            )

    counts = ", ".join(f"{k}={len(v)}" for k, v in sorted(population_arrays.items()))
    print(f"  built connectome: {n:,} neurons, {int(nonzero.sum()):,} edges ({counts})")
    if dropped:
        print(f"  dropped {dropped:,} modulatory edges (aminergic, no fast current modelled)")
    if "MOTOR" in population_arrays:
        print("  MOTOR population present: the Giant Fiber's output is readable, not invented")

    if positions is not None:
        located = int(np.isfinite(positions[:, 0]).sum())
        print(f"  positions for {located:,}/{n:,} neurons "
              f"(brain and nerve cord, so the panel spans the whole CNS)")

    return Connectome(
        name=f"neuprint-{dataset}",
        labels=tuple(labels),
        weights=weights,
        populations=population_arrays,
        positions=positions,
        param_overrides={},
        description=(
            f"NeuPrint {dataset}, seeded from {list(seed_types)}, {hops} hop(s). "
            "Male CNS: brain and ventral nerve cord, so the escape pathway reaches motor "
            f"neurons. Weights are synapse count x {pa_per_synapse} pA signed by predicted "
            "transmitter -- a placeholder scaling, not a measurement."
        ),
    )
