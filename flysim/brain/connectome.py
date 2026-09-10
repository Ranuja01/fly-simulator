"""The connectome container — the single output contract every data source must satisfy.

A hand-written 12-neuron mock, a seeded 120-neuron synthetic population, a 50,000-neuron
sparse benchmark, and a real 139,255-neuron FlyWire download all produce *this* object.
:class:`~flysim.brain.lif.LIFBrain` accepts it and cannot tell them apart. That is the
whole point: when you later swap in real data, nothing downstream changes.

Weight convention
-----------------
``weights[pre, post]`` is the current in **picoamps** delivered to neuron ``post`` the
moment neuron ``pre`` spikes. That jump then decays with ``tau_syn``. Positive is
excitatory, negative inhibitory.

Real connectome data gives you *synapse counts*, not picoamps. The adapter that loads
real data is responsible for the conversion (a linear scaling is the usual first
approximation, since synapse count correlates with physiological strength); see
``docs/CONNECTOME_ACCESS.md``.

Sparsity
--------
``weights`` may be a dense ``np.ndarray`` or any SciPy sparse matrix supporting
``spikes @ weights``. Dense is right up to a few thousand neurons; past that it is
catastrophic (139,255² float32 = ~78 GB — see ``docs/COMPUTE_BUDGET.md``). Nothing in
this module imports SciPy; only :func:`~flysim.brain.builders.build_benchmark` does, and
it imports it lazily.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True, eq=False)
class Connectome:
    """Network structure: who is who, who connects to whom, and how strongly."""

    name: str
    """Identifier for logs and plot titles, e.g. ``"mock12"``."""

    labels: tuple[str, ...]
    """Per-neuron names, length ``N``. Used for legends and debugging only."""

    weights: Any
    """``(N, N)`` synaptic weights in pA/spike, ``[pre, post]``. Dense or SciPy sparse."""

    populations: dict[str, np.ndarray]
    """Name -> int64 index array. Must partition ``range(N)`` exactly.

    Everything downstream addresses neurons by population name, never by raw index, so a
    connectome that renumbers its neurons breaks nothing.
    """

    param_overrides: dict[str, dict[str, float]] = field(default_factory=dict)
    """Population name -> ``{NeuronParams field: value}``.

    A Giant Fiber does not integrate like an LC4, so per-population biophysics belongs
    with the structure that defines those populations.
    """

    description: str = ""
    """Human-readable provenance. Say where the numbers came from and what is invented."""

    positions: Any = None
    """Optional ``(N, D)`` anatomical coordinates in micrometres, or None.

    Where each neuron physically sits. Real connectomes supply measured coordinates; the
    hand-built circuits supply a schematic layout so the anatomical view works without a
    download. Purely for visualisation -- the LIF engine never reads this, because a
    simulated neuron has no location.

    A caveat that matters for interpretation: FlyWire's coordinates are a single *marked
    point* per neuron, not the centre of its arbor. A cell spanning the optic lobe and the
    central brain is still one dot.
    """

    context_positions: Any = None
    """Optional ``(M, D)`` positions of neurons NOT in this model, for anatomical reference.

    A subnetwork extracted from a whole brain has no recognisable outline on its own -- the
    LC4/DNp01 circuit is a flat wide sheet with no landmarks. Drawing the rest of the brain
    behind it, greyed out, is what makes the anatomy legible.

    These neurons are **not simulated**. Nothing reads this except the visualisation, and
    the panel labels them as excluded so the picture cannot imply a whole-brain model.
    """

    def __post_init__(self) -> None:
        n = len(self.labels)
        if n == 0:
            raise ValueError("Connectome must contain at least one neuron.")

        shape = getattr(self.weights, "shape", None)
        if shape is None or len(shape) != 2:
            raise TypeError(f"weights must be a 2-D matrix, got {type(self.weights)!r}.")
        if shape != (n, n):
            raise ValueError(f"weights shape {shape} does not match {n} labels.")

        # Finiteness: a single NaN weight silently poisons every downstream voltage, and
        # the failure surfaces far from its cause. Check dense arrays directly; for sparse
        # matrices only the stored entries can be non-zero, so checking .data suffices.
        stored = self.weights if isinstance(self.weights, np.ndarray) else self.weights.data
        if not np.all(np.isfinite(stored)):
            raise ValueError("weights contains NaN or inf.")

        seen = np.zeros(n, dtype=bool)
        for pop_name, idx in self.populations.items():
            idx = np.asarray(idx)
            if idx.size == 0:
                raise ValueError(f"Population {pop_name!r} is empty.")
            if idx.min() < 0 or idx.max() >= n:
                raise ValueError(f"Population {pop_name!r} has out-of-range indices.")
            if seen[idx].any():
                raise ValueError(f"Population {pop_name!r} overlaps another population.")
            seen[idx] = True

        if not seen.all():
            missing = np.flatnonzero(~seen)[:8]
            raise ValueError(
                f"Neurons {missing.tolist()} belong to no population. Populations must "
                "partition the network — the decoder and dashboard address neurons by "
                "population name only."
            )

        for pop_name in self.param_overrides:
            if pop_name not in self.populations:
                raise ValueError(f"param_overrides names unknown population {pop_name!r}.")

        if self.positions is not None:
            pos = np.asarray(self.positions)
            if pos.ndim != 2 or pos.shape[0] != n:
                raise ValueError(
                    f"positions must be ({n}, D); got {pos.shape}. One row per neuron, "
                    "in the same order as labels."
                )

    @property
    def size(self) -> int:
        """Number of neurons, ``N``."""
        return len(self.labels)

    @property
    def is_sparse(self) -> bool:
        return not isinstance(self.weights, np.ndarray)

    def population(self, name: str) -> np.ndarray:
        """Index array for a population, with a helpful error if it is absent."""
        try:
            return self.populations[name]
        except KeyError:
            raise KeyError(
                f"No population {name!r} in connectome {self.name!r}. "
                f"Available: {sorted(self.populations)}"
            ) from None

    def summary(self) -> str:
        """One-line-per-population description for startup logging."""
        if self.is_sparse:
            n_edges = self.weights.nnz
        else:
            n_edges = int(np.count_nonzero(self.weights))
        density = n_edges / max(self.size**2, 1)

        lines = [
            f"connectome '{self.name}': {self.size} neurons, {n_edges} edges "
            f"(density {density:.3%}, {'sparse' if self.is_sparse else 'dense'})"
        ]
        for pop_name, idx in self.populations.items():
            lines.append(f"    {pop_name:<8} n={len(idx):<6}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Circuit rule table
# ---------------------------------------------------------------------------
#
# The escape circuit is specified once, as **total incoming picoamps per postsynaptic
# neuron**, rather than as a per-synapse weight. That choice is what makes `mock12` and
# `synthetic120` genuinely comparable: both realise the same total drive, so any
# behavioural difference between them comes from population structure (quorum sensing,
# heterogeneity, graded lesions) and not from an accidental rescaling.
#
# Each builder converts a total into per-synapse weights by dividing by its own expected
# fan-in:  w = total / (n_pre * connection_probability).
#
# Anatomy, honestly labelled:
#   LC4  - lobula columnar type 4. Looming-selective visual projection neurons that
#          respond to an expanding edge and are a documented input to the Giant Fiber.
#   PMN  - a convergent premotor/relay pool. THIS IS A SIMPLIFICATION. In the real animal
#          LC4 and LPLC2 synapse directly onto GF dendrites; there is no obligatory
#          interneuron stage. This layer stands in for the broader convergent input
#          population and gives the model somewhere to show signal propagation.
#   INH  - feedforward inhibition. GF is under strong inhibitory control that sets how
#          readily it fires; modelled here as a saturating population (see below).
#   GF   - the Giant Fiber, descending neuron DNp01. All-or-none: one spike commands a
#          short-mode takeoff.
#
# The gating mechanism is worth understanding, because the escape threshold is *emergent*
# rather than hand-set. INH is given a long refractory period, so its firing rate
# saturates near ~125 Hz while PMN can climb past 400 Hz. At a weak loom, inhibition
# outpaces excitation and GF sits below rest. As the loom sharpens, excitation keeps
# growing and inhibition cannot, so GF crosses threshold. Nothing in the code contains a
# "fire when distance < X" rule.

TOTAL_INPUT_PA: dict[tuple[str, str], float] = {
    ("LC4", "PMN"): 72.0,
    ("LC4", "INH"): 54.0,
    ("LC4", "GF"): 24.0,   # direct LC4->GF, the biologically real pathway
    ("PMN", "PMN"): 16.0,  # recurrent amplification; self-connections excluded
    ("PMN", "GF"): 42.0,
    ("INH", "PMN"): -32.0,
    ("INH", "GF"): -60.0,
}

PARAM_OVERRIDES: dict[str, dict[str, float]] = {
    "LC4": {
        # Fast, tonically responsive visual neurons.
        "tau_m_ms": 8.0,
        "refractory_ms": 2.0,
    },
    "PMN": {
        "tau_m_ms": 12.0,
        "refractory_ms": 2.0,
    },
    "INH": {
        # The long refractory period is the load-bearing parameter: it caps inhibitory
        # output at ~1000/8 = 125 Hz, so excitation can eventually outrun it. Shorten it
        # and the escape never triggers.
        "tau_m_ms": 6.0,
        "refractory_ms": 8.0,
        "v_threshold_mv": -46.0,
    },
    "GF": {
        # Large integrating neuron with a higher threshold: it demands strong convergent
        # input rather than responding to any single LC4.
        "tau_m_ms": 16.0,
        "v_threshold_mv": -41.0,
        # A 60 ms refractory period enforces the all-or-none character of the escape
        # command: the GF fires once per takeoff, not a burst.
        "refractory_ms": 60.0,
    },
}
