"""Vectorised leaky integrate-and-fire engine.

The model
---------
Each neuron is a single electrical compartment — a capacitor leaking through a resistor:

.. math::

    \\tau_m \\frac{dV}{dt} = -(V - V_{rest}) + R_m I_{total}

When ``V`` reaches ``V_threshold`` the neuron emits a spike, ``V`` is clamped to
``V_reset``, and it is held there for an absolute refractory period. The LIF model throws
away the spike's shape (that is what "integrate-and-fire" means — the action potential is
a stereotyped event, so only its *timing* is simulated) and keeps subthreshold
integration, which is what actually decides when a neuron fires.

Total input current has four parts::

    I_total = I_syn + I_external + I_bias + noise

``I_syn`` is network input. A presynaptic spike delivers an instantaneous jump of
``W[pre, post]`` picoamps, which then decays exponentially with ``tau_syn`` — the standard
"exponential synapse" approximation to a fast nicotinic conductance. ``I_external`` is the
sensory drive handed in by the caller; the engine neither knows nor cares where it came
from.

Integration
-----------
Exponential Euler, not forward Euler. Over one timestep, holding ``I`` constant, the
membrane equation has an exact solution:

.. math::

    V(t + dt) = V_\\infty + (V(t) - V_\\infty) e^{-dt/\\tau_m},
    \\quad V_\\infty = V_{rest} + R_m I

This is exact for constant input, unconditionally stable at any ``dt``, and no more
expensive than forward Euler (the decay factor is precomputed once). Forward Euler would
oscillate and diverge whenever ``dt > 2 tau_m``, which is a real hazard when a connectome
brings in heterogeneous time constants you did not choose.

Every state variable is a length-``N`` NumPy array and every update is a whole-array
operation. There is no Python-level loop over neurons, so a 12-neuron mock and a
50,000-neuron sparse connectome run through identical code.

Import rule: this module imports from ``flysim.core`` and ``flysim.brain`` only. It must
never learn what a coordinate, a pixel, or a socket is.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from flysim.brain.connectome import Connectome
from flysim.config import NeuronParams
from flysim.core.base import BaseBrain
from flysim.core.types import BrainState


class LIFBrain(BaseBrain):
    """Leaky integrate-and-fire network driven by a :class:`Connectome`."""

    def __init__(
        self,
        connectome: Connectome,
        params: NeuronParams | None = None,
        dt_ms: float = 0.1,
        seed: int = 0,
    ) -> None:
        if dt_ms <= 0:
            raise ValueError(f"dt_ms must be positive, got {dt_ms}.")

        self._connectome = connectome
        self._params = params or NeuronParams()
        self._dt = float(dt_ms)
        self._rng = np.random.default_rng(seed)
        self._n = connectome.size
        self._weights = connectome.weights

        self._build_parameter_vectors()
        self._prepare_synaptic_delivery()
        self._check_timestep()

        # Lesions are structural, not dynamical: they must survive reset() so that
        # re-running a trial does not silently heal the network.
        self._silenced = np.zeros(self._n, dtype=bool)

        # Scratch buffer for membrane noise. Profiling put `standard_normal` at ~32% of
        # total runtime, largely because the obvious call generates float64 and then
        # converts: asking for float32 directly and writing into a reused buffer avoids
        # both the wider arithmetic and a fresh allocation on every timestep.
        self._noise_buffer = np.zeros(self._n, dtype=np.float32)
        self._has_noise = bool(np.any(self._noise_scale > 0))

        self.reset()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _build_parameter_vectors(self) -> None:
        """Expand scalar defaults into per-neuron arrays, then apply population overrides.

        Storing every parameter as a length-N vector rather than a scalar is what lets
        heterogeneous populations coexist at no cost: a real connectome with per-cell-type
        biophysics slots straight in, and the integration code never changes.
        """
        n = self._n
        p = self._params

        def full(value: float) -> np.ndarray:
            return np.full(n, value, dtype=np.float32)

        self._v_rest = full(p.v_rest_mv)
        self._v_reset = full(p.v_reset_mv)
        self._v_threshold = full(p.v_threshold_mv)
        self._v_floor = full(p.v_floor_mv)
        self._tau_m = full(p.tau_m_ms)
        self._r_m = full(p.r_m_gohm)
        self._tau_syn = full(p.tau_syn_ms)
        self._bias = full(p.bias_current_pa)
        self._noise_sd = full(p.noise_mv)
        refractory_ms = full(p.refractory_ms)
        delay_ms = p.delay_ms

        field_to_array = {
            "v_rest_mv": self._v_rest,
            "v_reset_mv": self._v_reset,
            "v_threshold_mv": self._v_threshold,
            "v_floor_mv": self._v_floor,
            "tau_m_ms": self._tau_m,
            "r_m_gohm": self._r_m,
            "tau_syn_ms": self._tau_syn,
            "bias_current_pa": self._bias,
            "noise_mv": self._noise_sd,
            "refractory_ms": refractory_ms,
        }

        for pop_name, overrides in self._connectome.param_overrides.items():
            idx = self._connectome.population(pop_name)
            for field_name, value in overrides.items():
                if field_name == "delay_ms":
                    raise ValueError(
                        "delay_ms cannot vary per population in this engine: the delay "
                        "line is a single shared ring buffer. Use a per-population delay "
                        "buffer if heterogeneous conduction delays are needed."
                    )
                try:
                    field_to_array[field_name][idx] = value
                except KeyError:
                    raise ValueError(
                        f"param_overrides[{pop_name!r}] names unknown parameter "
                        f"{field_name!r}. Valid: {sorted(field_to_array)}"
                    ) from None

        if np.any(self._tau_m <= 0) or np.any(self._tau_syn <= 0):
            raise ValueError("tau_m_ms and tau_syn_ms must be positive for every neuron.")
        if np.any(self._v_threshold <= self._v_reset):
            raise ValueError("v_threshold must exceed v_reset for every neuron.")

        # Precomputed decay factors. Exact for constant input over one timestep.
        self._membrane_decay = np.exp(-self._dt / self._tau_m).astype(np.float32)
        self._synaptic_decay = np.exp(-self._dt / self._tau_syn).astype(np.float32)

        # Refractory period counted in whole timesteps. Integer counters rather than a
        # float clock: accumulating dt in floating point drifts over long runs, and a
        # neuron that comes out of refractory one step early is a silent bug.
        self._refractory_steps = np.maximum(
            np.ceil(refractory_ms / self._dt).astype(np.int32), 0
        )

        # Axonal delay line. One shared ring buffer of spike vectors; reading the slot
        # about to be overwritten yields spikes emitted exactly delay_steps ago.
        self._delay_steps = max(int(round(delay_ms / self._dt)), 1)

        # Noise is applied as an Ornstein-Uhlenbeck-like perturbation of the membrane.
        # Scaling by sqrt(1 - decay^2) makes the stationary standard deviation exactly
        # noise_mv regardless of dt, so changing the timestep does not change how noisy
        # the model is — an easy thing to get wrong and a common source of dt-dependent
        # results.
        self._noise_scale = (
            self._noise_sd * np.sqrt(1.0 - self._membrane_decay**2)
        ).astype(np.float32)

    def _prepare_synaptic_delivery(self) -> None:
        """Cache the raw CSR arrays so synaptic input avoids SciPy's per-call overhead.

        The obvious implementation, ``spikes @ weights``, is correct but spends almost all
        of its time in SciPy's Python-level dispatch rather than on arithmetic: measured at
        15,452 neurons / 181,186 edges it costs ~0.38 ms, while a full elementwise pass
        over every neuron costs 0.005 ms. That call happens on every 0.1 ms timestep, so
        it dominated the whole simulation.

        Spiking is *sparse* — a handful of neurons out of thousands fire on any given
        timestep — so instead of multiplying by a mostly-zero vector, gather just the CSR
        rows belonging to neurons that actually spiked and scatter-add them. Measured
        4-8x faster, with identical results.

        Dense connectomes keep the plain matmul: they are small by construction (a dense
        matrix is only viable below a few thousand neurons) and NumPy has no comparable
        dispatch overhead.
        """
        self._sparse_weights = not isinstance(self._weights, np.ndarray)
        if self._sparse_weights:
            csr = self._weights.tocsr()
            self._w_indptr = csr.indptr
            self._w_indices = csr.indices
            self._w_data = csr.data.astype(np.float32)

        # The fast path: connections that do not wait on axonal conduction. Prepared
        # identically, so the two differ only in which delay line feeds them.
        self._fast_weights = getattr(self._connectome, "fast_weights", None)
        self._has_fast = self._fast_weights is not None
        if self._has_fast:
            self._sparse_fast = not isinstance(self._fast_weights, np.ndarray)
            if self._sparse_fast:
                fcsr = self._fast_weights.tocsr()
                self._f_indptr = fcsr.indptr
                self._f_indices = fcsr.indices
                self._f_data = fcsr.data.astype(np.float32)

    def _gather_offsets(self, rows: np.ndarray) -> np.ndarray | None:
        """Flat CSR positions for several rows at once, with no Python-level loop.

        Builds the concatenation of ``range(indptr[r], indptr[r+1])`` for every ``r`` in
        ``rows`` using a repeat/cumsum trick, so the cost scales with the number of
        outgoing synapses rather than with network size.
        """
        starts = self._w_indptr[rows]
        counts = self._w_indptr[rows + 1] - starts
        total = int(counts.sum())
        if total == 0:
            return None
        base = np.repeat(starts, counts)
        within = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
        return base + within

    def _check_timestep(self) -> None:
        """Warn loudly if dt is too coarse to resolve the fastest dynamics."""
        fastest = float(min(self._tau_m.min(), self._tau_syn.min()))
        if self._dt > 0.5 * fastest:
            raise ValueError(
                f"dt_ms={self._dt} is too large for the fastest time constant "
                f"({fastest} ms). Exponential Euler stays stable, but spike timing "
                f"becomes meaningless. Use dt_ms <= {0.5 * fastest:.2f}."
            )

    # ------------------------------------------------------------------
    # BaseBrain interface
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        return self._n

    @property
    def populations(self) -> Mapping[str, np.ndarray]:
        return self._connectome.populations

    @property
    def labels(self) -> Sequence[str]:
        return self._connectome.labels

    @property
    def connectome(self) -> Connectome:
        return self._connectome

    @property
    def dt_ms(self) -> float:
        return self._dt

    @property
    def v_threshold(self) -> np.ndarray:
        """Per-neuron threshold, exposed so the dashboard can draw it."""
        return self._v_threshold

    def reset(self) -> None:
        """Return every state variable to rest.

        Lesions applied with :meth:`silence` are deliberately NOT cleared — see
        ``__init__``. Use :meth:`heal` to undo them explicitly.
        """
        self._v = self._v_rest.copy()
        self._i_syn = np.zeros(self._n, dtype=np.float32)
        self._refractory_countdown = np.zeros(self._n, dtype=np.int32)
        self._spike_counts = np.zeros(self._n, dtype=np.int32)
        self._delay_buffer = np.zeros((self._delay_steps, self._n), dtype=bool)
        self._delay_cursor = 0
        # One step, not zero: a spike is emitted at the END of a step, so the earliest it
        # can be delivered is the next one. That floor is dt, which is 0.1 ms headless and
        # 0.4 ms interactive -- report both rather than quoting the headless figure.
        self._fast_buffer = np.zeros((1, self._n), dtype=bool)
        self._t_ms = 0.0

    @property
    def silenced(self) -> np.ndarray:
        """Boolean mask of lesioned neurons."""
        return self._silenced

    def heal(self) -> None:
        """Undo every lesion."""
        self._silenced[:] = False

    def silence(self, indices: np.ndarray) -> None:
        """Permanently silence neurons — a lesion.

        Silenced neurons still integrate (so their voltage remains inspectable) but their
        spikes never reach the network. This is the model of an optogenetic silencing or
        an ablation experiment, and it is the manipulation that shows the difference
        between a 12-neuron circuit, where one cell is load-bearing, and a population,
        where the reflex degrades gracefully.
        """
        self._silenced[np.asarray(indices, dtype=np.int64)] = True

    def step(self, currents_pa: np.ndarray) -> BrainState:
        """Integrate one timestep.

        Args:
            currents_pa: External input, shape ``(N,)``, picoamps.

        Returns:
            The post-step :class:`BrainState`.
        """
        external = np.asarray(currents_pa, dtype=np.float32)
        if external.shape != (self._n,):
            raise ValueError(
                f"Expected current vector of shape ({self._n},), got {external.shape}. "
                "The sensory encoder must emit one value per neuron."
            )

        # --- 1. Synaptic current decays toward zero ---------------------------------
        self._i_syn *= self._synaptic_decay

        # --- 2. Spikes emitted `delay_steps` ago arrive now -------------------------
        # Reading the slot we are about to overwrite is what implements the delay: it
        # holds the spike vector from exactly one full lap of the ring buffer ago.
        arriving = self._delay_buffer[self._delay_cursor]
        if arriving.any():
            if self._sparse_weights:
                # Gather only the outgoing synapses of neurons that actually fired.
                # np.add.at (not `+=` with fancy indexing) because two presynaptic
                # neurons commonly target the same cell, and plain fancy-index assignment
                # would keep only one of those contributions instead of summing them.
                offsets = self._gather_offsets(np.flatnonzero(arriving))
                if offsets is not None:
                    np.add.at(
                        self._i_syn, self._w_indices[offsets], self._w_data[offsets]
                    )
            else:
                # spikes @ W sums over presynaptic neurons: for each post, the total
                # weight from every pre that just fired.
                self._i_syn += (
                    arriving.astype(np.float32) @ self._weights
                ).astype(np.float32)

        # --- 2b. Gap junctions: spikes from ONE step ago, no axonal delay -----------
        if self._has_fast:
            fast_arriving = self._fast_buffer[0]
            if fast_arriving.any():
                if self._sparse_fast:
                    rows = np.flatnonzero(fast_arriving)
                    starts = self._f_indptr[rows]
                    counts = self._f_indptr[rows + 1] - starts
                    total = int(counts.sum())
                    if total:
                        base = np.repeat(starts, counts)
                        within = (np.arange(total)
                                  - np.repeat(np.cumsum(counts) - counts, counts))
                        off = base + within
                        np.add.at(self._i_syn, self._f_indices[off], self._f_data[off])
                else:
                    self._i_syn += (
                        fast_arriving.astype(np.float32) @ self._fast_weights
                    ).astype(np.float32)

        # --- 3. Total input ---------------------------------------------------------
        i_total = self._i_syn + external + self._bias

        # --- 4. Membrane update (exponential Euler) ---------------------------------
        v_infinity = self._v_rest + self._r_m * i_total
        v_next = v_infinity + (self._v - v_infinity) * self._membrane_decay

        if self._has_noise:
            self._rng.standard_normal(
                self._n, dtype=np.float32, out=self._noise_buffer
            )
            v_next += self._noise_scale * self._noise_buffer

        # Refractory neurons are clamped at reset rather than integrating. This is the
        # "absolute" refractory period: no amount of input can move them.
        refractory = self._refractory_countdown > 0
        self._v = np.where(refractory, self._v_reset, v_next).astype(np.float32)
        np.subtract(
            self._refractory_countdown, 1, out=self._refractory_countdown, where=refractory
        )

        # --- 5. Threshold crossing --------------------------------------------------
        spikes = (~refractory) & (self._v >= self._v_threshold)
        if spikes.any():
            self._v[spikes] = self._v_reset[spikes]
            self._refractory_countdown[spikes] = self._refractory_steps[spikes]
            self._spike_counts += spikes

        # A lesioned neuron's spikes are not transmitted. Applied after counting so the
        # telemetry still shows what the neuron *would* have done.
        transmitted = spikes & ~self._silenced

        # --- 6. Voltage floor -------------------------------------------------------
        # Physically the chloride reversal potential; numerically, a guard that keeps a
        # mis-scaled inhibitory weight from producing an unrecoverable voltage.
        np.clip(self._v, self._v_floor, None, out=self._v)

        # --- 7. Push this step's spikes into the delay line -------------------------
        self._delay_buffer[self._delay_cursor] = transmitted
        self._delay_cursor = (self._delay_cursor + 1) % self._delay_steps
        if self._has_fast:
            self._fast_buffer[0] = transmitted

        self._t_ms += self._dt

        return BrainState(
            t_ms=self._t_ms,
            voltages=self._v.copy(),
            spikes=spikes,
            synaptic_current=self._i_syn.copy(),
            spike_counts=self._spike_counts.copy(),
        )
