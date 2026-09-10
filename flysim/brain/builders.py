"""Connectome builders — three sources, one output type.

* :func:`build_mock12`      — hand-authored, fully readable, zero dependencies. Default.
* :func:`build_synthetic120` — seeded populations; unlocks quorum coding and lesions.
* :func:`build_benchmark`   — large sparse network for validating the scaling claims.

All three return a :class:`~flysim.brain.connectome.Connectome`. A real NeuPrint/FlyWire
loader would be a fourth function here with the same signature and the same return type;
see ``docs/CONNECTOME_ACCESS.md`` for the query code that would feed it.
"""

from __future__ import annotations

import numpy as np

from flysim.brain.connectome import PARAM_OVERRIDES, TOTAL_INPUT_PA, Connectome

# Population sizes for the two hand-designed models.
MOCK12_SIZES: dict[str, int] = {"LC4": 6, "PMN": 3, "INH": 2, "GF": 1}
SYNTHETIC120_SIZES: dict[str, int] = {"LC4": 80, "PMN": 30, "INH": 9, "GF": 1}

# Fraction of possible pre->post pairs that actually connect, in synthetic120.
SYNTHETIC_CONNECTION_PROB = 0.35

# Coefficient of variation of individual synaptic weights in synthetic120. Cortical and
# insect synaptic strengths are both well described by a lognormal distribution: many
# weak connections, a long tail of strong ones. A CV near 1 reproduces that shape.
SYNTHETIC_WEIGHT_CV = 0.85


def _allocate(sizes: dict[str, int]) -> tuple[tuple[str, ...], dict[str, np.ndarray]]:
    """Lay populations out contiguously and build the label list."""
    labels: list[str] = []
    populations: dict[str, np.ndarray] = {}
    cursor = 0
    for pop_name, count in sizes.items():
        populations[pop_name] = np.arange(cursor, cursor + count, dtype=np.int64)
        if count == 1:
            labels.append(pop_name)  # a singleton needs no index suffix (e.g. "GF")
        else:
            labels.extend(f"{pop_name}_{i}" for i in range(count))
        cursor += count
    return tuple(labels), populations


def schematic_layout(
    populations: dict[str, np.ndarray], n: int, seed: int = 0
) -> np.ndarray:
    """Cartoon brain coordinates for the hand-built circuits, in micrometres.

    The anatomical panel should work without a 70 MB download, so the mock circuits get a
    schematic layout arranged like a real fly brain: two lateral optic lobes holding the
    visual neurons, a central brain holding the premotor pool, and the Giant Fibers medial
    to both. Extents roughly match FlyWire's measured ones (~900 x 450 um) so the two
    views read at the same scale.

    This is a diagram, NOT anatomy. Positions here are invented; positions on a real
    connectome are measured. The panel says which it is showing.
    """
    rng = np.random.default_rng(seed)
    pos = np.zeros((n, 3), dtype=np.float64)

    midline_x, centre_y, centre_z = 460.0, 230.0, 180.0
    lobe_offset = 165.0

    def scatter(idx: np.ndarray, cx: float, cy: float, cz: float, spread: float) -> None:
        if idx.size == 0:
            return
        pos[idx] = rng.normal([cx, cy, cz], spread, size=(idx.size, 3))

    for name, idx in populations.items():
        idx = np.asarray(idx)
        if name in ("LC4", "INH"):
            # Visual and local inhibitory cells tile the two optic lobes, so split them
            # left/right the way the real populations divide.
            half = idx.size // 2
            depth = 40.0 if name == "LC4" else 30.0
            scatter(idx[:half], midline_x - lobe_offset, centre_y + 25, centre_z, depth)
            scatter(idx[half:], midline_x + lobe_offset, centre_y + 25, centre_z, depth)
        elif name == "GF":
            # One Giant Fiber per hemisphere, medial to the optic lobes.
            for k, single in enumerate(idx):
                side = -1 if k % 2 == 0 else 1
                pos[single] = [midline_x + side * 70.0, centre_y - 10, centre_z]
        else:
            scatter(idx, midline_x, centre_y - 20, centre_z, 55.0)

    return pos


def build_mock12() -> Connectome:
    """A 12-neuron escape circuit written out as an explicit, editable matrix.

    Every weight is derived from the shared rule table by dividing the total incoming
    current by the fan-in, with all-to-all connectivity within each projection. The result
    is a matrix small enough to print and reason about by hand.

    Requires nothing but NumPy. This is the out-of-the-box path.
    """
    labels, populations = _allocate(MOCK12_SIZES)
    n = sum(MOCK12_SIZES.values())
    weights = np.zeros((n, n), dtype=np.float32)

    for (pre_name, post_name), total_pa in TOTAL_INPUT_PA.items():
        pre_idx = populations[pre_name]
        post_idx = populations[post_name]

        if pre_name == post_name:
            # Recurrent projection: a neuron does not synapse onto itself, so each
            # postsynaptic cell sees only (n_pre - 1) inputs.
            fan_in = len(pre_idx) - 1
            if fan_in <= 0:
                continue
        else:
            fan_in = len(pre_idx)

        w = np.float32(total_pa / fan_in)
        block = np.full((len(pre_idx), len(post_idx)), w, dtype=np.float32)
        if pre_name == post_name:
            np.fill_diagonal(block, 0.0)
        weights[np.ix_(pre_idx, post_idx)] = block

    return Connectome(
        name="mock12",
        labels=labels,
        weights=weights,
        populations=populations,
        param_overrides=PARAM_OVERRIDES,
        positions=schematic_layout(populations, n),
        description=(
            "Hand-authored 12-neuron looming-escape circuit. Connection topology and the "
            "LC4->GF pathway are drawn from the Drosophila escape literature; the specific "
            "weights, time constants and the existence of a discrete PMN relay stage are "
            "modelling choices, not measurements. Replace with a real connectome via the "
            "loaders in docs/CONNECTOME_ACCESS.md."
        ),
    )


def build_synthetic120(seed: int = 0) -> Connectome:
    """A ~120-neuron version of the same circuit, with realistic population structure.

    Identical total drive per postsynaptic neuron as :func:`build_mock12`, so the two are
    directly comparable. What the larger version adds:

    * **Quorum coding** — GF fires because *enough* LC4 neurons are active, not because
      one gain constant was tuned. Escape latency emerges from a distribution.
    * **Trial-to-trial variability** — a different ``seed`` gives a different latency,
      which is what makes "how reliable is this reflex?" a question you can actually ask.
    * **Graded lesions** — silencing 30% of LC4 shifts the latency instead of switching
      the reflex off, because no single neuron is load-bearing.

    Sparse random connectivity with lognormally distributed weights, which is the standard
    first-order description of real synaptic strength distributions.
    """
    rng = np.random.default_rng(seed)
    labels, populations = _allocate(SYNTHETIC120_SIZES)
    n = sum(SYNTHETIC120_SIZES.values())
    weights = np.zeros((n, n), dtype=np.float32)

    for (pre_name, post_name), total_pa in TOTAL_INPUT_PA.items():
        pre_idx = populations[pre_name]
        post_idx = populations[post_name]
        n_pre, n_post = len(pre_idx), len(post_idx)

        mask = rng.random((n_pre, n_post)) < SYNTHETIC_CONNECTION_PROB
        if pre_name == post_name:
            np.fill_diagonal(mask, False)

        # Expected fan-in under the connection probability. Dividing the shared total by
        # it keeps mean drive per postsynaptic neuron equal to mock12's.
        effective_pre = (n_pre - 1) if pre_name == post_name else n_pre
        expected_fan_in = max(effective_pre * SYNTHETIC_CONNECTION_PROB, 1e-9)
        w_mean = abs(total_pa) / expected_fan_in

        # Lognormal parameterised so the arithmetic mean is exactly w_mean.
        sigma = np.sqrt(np.log1p(SYNTHETIC_WEIGHT_CV**2))
        mu = np.log(w_mean) - 0.5 * sigma**2
        drawn = rng.lognormal(mean=mu, sigma=sigma, size=(n_pre, n_post))

        block = np.where(mask, drawn, 0.0) * np.sign(total_pa)
        weights[np.ix_(pre_idx, post_idx)] = block.astype(np.float32)

    return Connectome(
        name=f"synthetic120(seed={seed})",
        labels=labels,
        weights=weights,
        populations=populations,
        param_overrides=PARAM_OVERRIDES,
        positions=schematic_layout(populations, n, seed=seed),
        description=(
            "Seeded 120-neuron realisation of the same circuit rule table as mock12. "
            "Sparse random connectivity with lognormal weights. Population sizes are "
            "chosen for legibility and are not FlyWire counts."
        ),
    )


def build_benchmark(n: int = 50_000, seed: int = 0, avg_degree: int = 19) -> Connectome:
    """A large sparse network for testing that the engine scales as ``docs/`` claims.

    Neither ``mock12`` nor ``synthetic120`` is a performance test — a 120x120 matmul is
    instant regardless of how the code is written. This builder exists to make the
    sparse-versus-dense argument empirically rather than rhetorically.

    ``avg_degree=19`` approximates FlyWire's aggregated connectivity (~2.7M edges across
    ~139k proofread neurons at the conventional 5-synapse threshold).

    SciPy is imported **inside this function** on purpose: the Starter Phase promise is
    that ``python main.py`` needs only NumPy and Matplotlib, and this is the one code path
    that legitimately needs more.
    """
    try:
        import scipy.sparse as sp
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise ImportError(
            "--benchmark needs SciPy for sparse matrices. Install it with "
            "`pip install scipy`, or use --connectome mock12 / synthetic120, which do not."
        ) from exc

    if n < 10:
        raise ValueError(f"benchmark size must be >= 10, got {n}.")

    rng = np.random.default_rng(seed)
    n_edges = int(n * avg_degree)

    # Random directed edges. Duplicates are summed by coo_matrix, which is the correct
    # behaviour: two synapses between the same pair add their currents.
    pre = rng.integers(0, n, size=n_edges, dtype=np.int64)
    post = rng.integers(0, n, size=n_edges, dtype=np.int64)

    # ~80/20 excitatory/inhibitory, the usual first-order assumption.
    sign = np.where(rng.random(n_edges) < 0.8, 1.0, -3.0)
    magnitude = rng.lognormal(mean=np.log(2.0), sigma=0.7, size=n_edges)
    data = (sign * magnitude).astype(np.float32)

    weights = sp.coo_matrix((data, (pre, post)), shape=(n, n), dtype=np.float32).tocsr()

    # Reuse the real population names so the encoder/decoder work unchanged, with the
    # bulk of the network as unnamed "BULK" cells standing in for the rest of the brain.
    n_lc4 = max(int(n * 0.02), 1)
    n_pmn = max(int(n * 0.02), 1)
    n_inh = max(int(n * 0.01), 1)
    sizes = {
        "LC4": n_lc4,
        "PMN": n_pmn,
        "INH": n_inh,
        "GF": 1,
        "BULK": n - n_lc4 - n_pmn - n_inh - 1,
    }
    labels, populations = _allocate(sizes)

    return Connectome(
        name=f"benchmark(n={n})",
        labels=labels,
        weights=weights,
        populations=populations,
        param_overrides=PARAM_OVERRIDES,
        description=(
            f"Random sparse network, {n} neurons at average degree {avg_degree}. "
            "Structurally meaningless — it exists solely to measure integration "
            "throughput and memory at connectome scale."
        ),
    )


BUILDERS = {
    "mock12": build_mock12,
    "synthetic120": build_synthetic120,
}
"""Registry for ``--connectome``. ``build_benchmark`` is reached via ``--benchmark N``."""


def build(name: str, seed: int = 0, **kwargs) -> Connectome:
    """Dispatch to a registered builder by name.

    ``"flywire"`` is handled separately because it needs pandas and SciPy; importing the
    loader lazily keeps the Starter Phase runnable on NumPy and Matplotlib alone.
    """
    if name == "flywire":
        from flysim.brain.loaders import build_flywire

        return build_flywire(**kwargs)

    if name == "neuprint":
        from flysim.brain.neuprint_source import build_neuprint

        return build_neuprint(**kwargs)

    try:
        builder = BUILDERS[name]
    except KeyError:
        raise KeyError(
            f"Unknown connectome {name!r}. Available: {sorted(BUILDERS)} (plus 'flywire')"
        ) from None
    # mock12 is fully deterministic and takes no seed.
    return builder(seed=seed) if name != "mock12" else builder()
