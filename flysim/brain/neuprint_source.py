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

POSTURAL_SEED_TYPES: tuple[str, ...] = (
    "Sternotrochanter MN",
    "Sternal posterior rotator MN",
    "Sternal anterior rotator MN",
    "Tr flexor MN",
    "Tr extensor MN",
    "Acc. tr flexor MN",
    "Tergotr. MN",
)
"""Leg motor neurons of the coxa-trochanter group -- the muscles that position the joint
the jump pushes from.

A real fly aims its escape by adjusting leg posture BEFORE the trigger fires; TTMn is the
trigger and carries no direction in the animal any more than it does here. Growing the
network outward from the escape reflex caught only the edge of that circuit: two
Sternotrochanter MN out of the 14 the dataset holds, receiving 6 to 29 synapses of
descending input, which at the fitted scaling is hundredths of a picoamp. They never fire.

Seeding on them directly reaches the real thing: 128 motor cells, and 146 descending
neurons driving them across 31,296 synapses."""

ESCAPE_AND_POSTURE_SEED_TYPES: tuple[str, ...] = (
    ESCAPE_SEED_TYPES + POSTURAL_SEED_TYPES
)
"""Both, so the escape pathway and the pathway that aims it live in one network."""
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
ELECTRICAL_SYNAPSE_PA = 175.0
"""Current per presynaptic spike across a modelled gap junction, pA.

**Set by the measured latency, not by a conduction requirement.** von Reyn et al. report
TTM firing 0.93 ms after the giant fiber and DLM 1.44 ms after. Those numbers fix this
constant, because in a leaky integrator the time to threshold is set by how hard the cell
is driven: the stronger the input, the sooner it crosses.

The earlier value, 55 pA, was derived from a different and weaker requirement -- that ONE
spike must carry the target across the 7 mV gap *at all*. That makes the pathway conduct
but says nothing about when, and it conducted 5.5x too slowly.

Measured on the real connectome, with these connections bypassing the axonal delay line:

===========  ==============  ==============
pA/spike     GF -> TTMn      GF -> DLMn
===========  ==============  ==============
55            3.60 ms         7.30 ms
150           1.00 ms         2.00 ms
**175**       **0.90 ms**     **1.80 ms**
250           0.60 ms         1.20 ms
===========  ==============  ==============

175 puts the one-hop measurement (GF -> TTMn, published 0.93) almost exactly on target.
The two-hop path is chosen against rather than averaged with it, because it is the more
confounded quantity -- and note that our two-hop latency is exactly 2x the one-hop, while
the published pair is 1.44/0.93 = 1.55x. **No single current can match both**, because the
ratio is fixed by the architecture. That residual says PSI -> DLMn is faster in the animal
than GF -> PSI, which this model has no way to express yet, and it is recorded rather than
tuned away.

Removing the axonal delay alone was not enough: it took GF -> TTMn from 5.10 to 3.60 ms,
still 3.9x the target. **Membrane charging dominates the latency, not conduction.**
"""

ELECTRICAL_SYNAPSES: tuple[tuple[str, str], ...] = (
    ("DNp01", "TTMn"),   # Giant Fiber -> jump-muscle motor neuron
    ("DNp01", "PSI"),    # Giant Fiber -> peripherally synapsing interneuron (wing)
)
"""Known gap-junction pathways, as (presynaptic type, postsynaptic type).

Deliberately short and specific. Every entry needs a citable reason to be here; this is a
place to record established anatomy, not a knob."""


SUPRATHRESHOLD_SYNAPSE_PA = ELECTRICAL_SYNAPSE_PA
"""Current per spike across a chemical synapse known to be reliably suprathreshold, pA.

The same number as the electrical case, because the requirement is the same: one
presynaptic spike must carry the target across the same 7 mV gap with the same Shiu
parameters. The *reason* the uniform scaling misses it is different, which is why it is a
different table. A gap junction is absent from EM data altogether; this connection is
present and simply under-weighted, because one global picoamps-per-synapse constant cannot
also express that a particular pathway is built to be relied on."""

SUPRATHRESHOLD_SYNAPSES: tuple[tuple[str, str], ...] = (
    ("PSI", "DLMn c-f"),   # wing interneuron -> dorsal longitudinal (wing depressor)
    ("PSI", "DLMn a, b"),
)
"""Chemical synapses whose defining property is reliability, not strength.

The PSI is the wing arm of the escape: the Giant Fiber drives it electrically, and it in
turn drives the dorsal longitudinal motor neurons that power the wingbeat. It is the
strongest PSI output in the dataset by a wide margin -- 449 synapses across ten cells --
and under the uniform 0.002 pA/synapse it delivered under a picoamp, so the flight muscles
never fired and every escape was a bare jump. Same failure as GF->TTMn before the
electrical table, arrived at from the opposite direction."""


def _client(dataset: str):
    """Authenticated NeuPrint client, imported lazily to keep the starter path clean."""
    from neuprint import Client

    return Client(NEUPRINT_SERVER, dataset=dataset, token=get_token())


def _cache_dir(dataset: str) -> Path:
    return cache_root() / "neuprint" / dataset.replace(":", "-")


MIN_COLUMNAR_INPUTS = 10
"""Columnar partners a cell needs before its field position is trusted."""

def _preferred_azimuth(neurons, connections, ids, hemisphere):
    """Where in the visual field each cell prefers, derived from anatomy.

    Three measured ingredients and one unresolved sign:

    1. **Where a cell looks** is estimated as the weighted centroid of its presynaptic
       columnar partners (T4, T5, Tm), whose own soma positions carry the retinotopic map.
       The cells' *own* somata do not: measured, LC4 cells sitting next to each other share
       no more input than distant ones (1.03x against 3-4x for the columnar types), because
       LC cell bodies sit in a rind rather than where their dendrites look.
    2. **The body's anterior-posterior axis** is the vector from the brain's centroid to the
       nerve cord's. It lies within the columnar sheet -- |cos| 0.86-0.89 against the
       sheet's second principal axis, 0.05-0.14 against its thin axis -- so the front/back
       direction really is a direction *in* the map rather than across it.
    3. **Side** gives left versus right, from the dataset's own field.

    A cell's preferred direction is then placed on a circle: fully anterior points straight
    ahead, mid-range points straight out to its own side, fully posterior points behind.

    The unresolved sign is the polarity. Fly visual neuropils invert the image between
    layers, so whether a posterior position corresponds to forward- or backward-looking
    vision cannot be settled from coordinates. It is left as a parameter rather than
    guessed, and it does not affect whether front and rear are *distinguishable* -- only
    which is which.
    """
    n = len(ids)
    out = np.full(n, np.nan, dtype=np.float64)
    needed = {"x", "y", "z", "superclass", "type"}
    if not needed.issubset(set(neurons.columns)):
        return out

    coords = neurons[["x", "y", "z"]].to_numpy(dtype=float)
    finite = ~np.isnan(coords).any(axis=1)
    superclass = neurons["superclass"].astype(str)
    types = neurons["type"].astype(str)

    is_vnc = finite & superclass.str.startswith("vnc").to_numpy()
    is_brain = finite & superclass.isin(
        ["ol_intrinsic", "visual_projection", "cb_intrinsic"]
    ).to_numpy()
    if is_vnc.sum() < 5 or is_brain.sum() < 50:
        return out
    axis = coords[is_vnc].mean(axis=0) - coords[is_brain].mean(axis=0)
    norm = float(np.linalg.norm(axis))
    if norm <= 0:
        return out
    axis = axis / norm

    position = {int(b): coords[i] for i, b in enumerate(neurons.index) if finite[i]}
    columnar = {
        int(b) for i, b in enumerate(neurons.index)
        if finite[i] and (types.iat[i][:2] in ("T4", "T5") or types.iat[i].startswith("Tm"))
    }

    incoming: dict[int, list] = {}
    pre_all = connections.pre.to_numpy()
    post_all = connections.post.to_numpy()
    w_all = connections.weight.to_numpy()
    for pre, post, w in zip(pre_all, post_all, w_all):
        pre = int(pre)
        if pre in columnar:
            incoming.setdefault(int(post), []).append((pre, float(w)))

    # Front/back coordinate per cell: the input centroid projected onto the body axis.
    depth: dict[int, float] = {}
    for body, group in incoming.items():
        if len(group) < MIN_COLUMNAR_INPUTS:
            continue
        pts = np.array([position[p] for p, _ in group])
        wts = np.array([w for _, w in group])
        depth[body] = float(((pts * wts[:, None]).sum(axis=0) / wts.sum()) @ axis)
    if len(depth) < 20:
        return out

    values = np.array(list(depth.values()))
    mid = float(np.median(values))
    half = float(np.percentile(values, 95) - np.percentile(values, 5)) / 2.0
    if half <= 0:
        return out

    for i, body in enumerate(ids):
        d = depth.get(int(body))
        if d is None:
            continue
        # -1 anterior .. +1 posterior, clipped so the tails do not dominate.
        a = float(np.clip((d - mid) / half, -1.0, 1.0))
        forward = -a
        lateral = float(hemisphere[i]) * float(np.sqrt(max(0.0, 1.0 - a * a)))
        if hemisphere[i] == 0:
            continue
        out[i] = float(np.arctan2(lateral, forward))
    return out


def assign_population(cell_type: str, superclass: str, nt: str) -> str:
    """Map a NeuPrint cell onto one of the engine's functional populations.

    Unlike the FlyWire loader, which had only a transmitter to sort by, NeuPrint carries a
    ``superclass``, so motor neurons are identified by what they *are* rather than guessed
    from their name.
    """
    sc = (superclass or "").lower()
    upper = (cell_type or "").upper()

    # Motor and efferent cells are the entire reason for using this dataset. The flight
    # muscles are split out from the jump muscle: they are driven by a different arm of
    # the same circuit (GF -> PSI -> DLMn, wings) and mean a different behaviour, so a
    # decoder that lumps them cannot tell a jump from a jump that becomes flight.
    if "motor" in sc or "efferent" in sc:
        # Split by ROLE, because the decoder triggers the takeoff on MOTOR firing and a
        # leg motor neuron firing is not a takeoff. Seeding on the postural pool grew this
        # group from 10 cells to 157, so a rule that lumped them would have launched the
        # fly whenever it shifted its stance.
        if upper.startswith(("DLMN", "DVMN", "MNWM")):
            return "FLIGHT"          # wing power
        if upper.startswith(("TTMN", "PSI")):
            return "MOTOR"           # the jump trigger and its wing counterpart
        return "POSTURE"             # leg muscles: they aim the jump, they do not fire it
    if upper == "DNP01":
        return "GF"
    # The rest of the descending population. DNp01 is the Giant Fiber and keeps its own
    # population because the decoder triggers on it, but it is not even the largest target
    # of the visual projection neurons -- LC4 and LPLC2 drive ten bilateral descending
    # pairs, each perfectly ipsilateral, reading partly disjoint subsets of the visual
    # population. Roughly 78% of that output used to land in the premotor bucket, where it
    # was invisible. Identified by the dataset's own superclass rather than by name, and
    # matched exactly so that `sensory_descending` is not swept in with it.
    if sc == "descending_neuron":
        return "DN"
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
    # "r" marks that the declared reliable pathways are exempt from the weight floor.
    # Without it a cache built under the old rule would be reused silently.
    key = f"{'-'.join(seed_types)}_h{hops}_s{min_synapses}r_n{max_neurons}"
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
    # A generic weight floor must not delete a pathway we have separately declared to be
    # load-bearing. It did: DNp01 -> PSI has four edges in the reconstruction, and three of
    # them (weights 2, 2, 3) fell below min_synapses=5. Only DNp01_L -> PSI_L survived, so
    # the wing pathway became unilateral and `MotorCommand.powered` silently reduced to
    # "did the LEFT Giant Fiber fire" -- measured by silencing each side in turn.
    exempt = " ".join(
        f'OR (a.type = "{pre}" AND b.type = "{post}")'
        for pre, post in ELECTRICAL_SYNAPSES + SUPRATHRESHOLD_SYNAPSES
    )
    connections = client.fetch_custom(
        f"MATCH (a:Neuron)-[w:ConnectsTo]->(b:Neuron) "
        f"WHERE a.bodyId IN [{ids}] AND b.bodyId IN [{ids}] "
        f"AND (w.weight >= {min_synapses} {exempt}) "
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
    is_fast = np.zeros(len(connections), dtype=bool)
    type_of = neurons["type"].astype(str)
    pre_types = connections.pre.map(type_of).fillna("")
    post_types = connections.post.map(type_of).fillna("")
    for table, current, note in (
        (ELECTRICAL_SYNAPSES, ELECTRICAL_SYNAPSE_PA,
         "electrical synapses restored -- absent from EM connectome data"),
        (SUPRATHRESHOLD_SYNAPSES, SUPRATHRESHOLD_SYNAPSE_PA,
         "reliable chemical synapses raised -- under-weighted by a uniform pA/synapse"),
    ):
        selected = np.zeros(len(connections), dtype=bool)
        for pre_type, post_type in table:
            selected |= (
                (pre_types == pre_type).to_numpy()
                & (post_types == post_type).to_numpy()
            )
        if selected.any():
            data = np.where(selected, current, data).astype(np.float32)
            is_fast |= selected
            pairs = ", ".join(f"{a}->{b}" for a, b in table)
            print(f"  {int(selected.sum())} {note} ({pairs}) at {current} pA/spike")

    # These pathways skip the axonal delay line -- see Connectome.fast_weights. Removing
    # them from `data` rather than leaving them in both matrices is what stops the
    # connection being applied twice.
    nonzero = (data != 0.0) & ~is_fast
    fast_nonzero = (data != 0.0) & is_fast
    dropped = int(((data == 0.0)).sum())

    if n > 3000:
        import scipy.sparse as sp

        weights = sp.coo_matrix(
            (data[nonzero], (rows[nonzero], cols[nonzero])), shape=(n, n), dtype=np.float32
        ).tocsr()
    else:
        weights = np.zeros((n, n), dtype=np.float32)
        # np.add.at accumulates duplicates rather than overwriting.
        np.add.at(weights, (rows[nonzero], cols[nonzero]), data[nonzero])

    if fast_nonzero.any():
        if n > 3000:
            import scipy.sparse as sp

            fast_weights = sp.coo_matrix(
                (data[fast_nonzero], (rows[fast_nonzero], cols[fast_nonzero])),
                shape=(n, n), dtype=np.float32,
            ).tocsr()
        else:
            fast_weights = np.zeros((n, n), dtype=np.float32)
            np.add.at(fast_weights, (rows[fast_nonzero], cols[fast_nonzero]),
                      data[fast_nonzero])
        print(f"  {int(fast_nonzero.sum())} of those bypass the axonal delay line "
              f"(gap junctions do not wait on conduction)")
    else:
        fast_weights = None

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

    # Which side of the animal each cell is on, straight from the dataset.
    side_lookup = {}
    if "side" in neurons.columns:
        side_lookup = {int(b): str(v) for b, v in neurons["side"].items()}
    hemisphere = np.zeros(n, dtype=np.int8)
    for i, body in enumerate(ids):
        s_ = side_lookup.get(int(body), "")
        hemisphere[i] = -1 if s_ == "L" else (+1 if s_ == "R" else 0)

    preferred = _preferred_azimuth(neurons, connections, ids, hemisphere)

    return Connectome(
        name=f"neuprint-{dataset}",
        labels=tuple(labels),
        weights=weights,
        fast_weights=fast_weights,
        populations=population_arrays,
        hemisphere=hemisphere,
        preferred_azimuth=preferred,
        positions=positions,
        param_overrides={},
        description=(
            f"NeuPrint {dataset}, seeded from {list(seed_types)}, {hops} hop(s). "
            "Male CNS: brain and ventral nerve cord, so the escape pathway reaches motor "
            f"neurons. Weights are synapse count x {pa_per_synapse} pA signed by predicted "
            "transmitter -- a placeholder scaling, not a measurement."
        ),
    )
