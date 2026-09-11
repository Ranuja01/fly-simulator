"""The orchestration loop — the only module that knows about more than one layer.

Everything else in the package sees exactly one side of a boundary. This is where the
four abstract components are wired into a working loop, and where the one unit conversion
in the system happens: environment time is in seconds, brain time is in milliseconds.

Two clocks
----------
The brain integrates at ``brain_dt_ms`` (0.1 ms — small enough to resolve a 6 ms membrane
time constant), while the environment and the display update at ``frame_dt_ms`` (4 ms).
One frame is therefore 40 brain steps. This matters for more than performance: the
LC4 -> PMN -> GF propagation takes only a few milliseconds, so stepping the world at the
neural timestep would make the whole cascade happen inside a single rendered frame and the
telemetry panel would show a vertical line instead of a visible staircase.

Sensory input is held constant across the substeps of a frame (a zero-order hold). The
world moves ~1.7 mm per frame at the default predator speed, so the looming value barely
changes within one — resampling it 40 times would cost 40x the encoder work for no
measurable difference.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from flysim.config import SimConfig
from flysim.core.base import (
    BaseBrain,
    BaseEnvironment,
    BaseMotorDecoder,
    BaseSensoryEncoder,
)
from flysim.core.types import BrainState, EnvObservation, MotorCommand, SensoryPacket


@dataclass
class Telemetry:
    """Recorded history for the telemetry panel and the post-run summary.

    Voltages are summarised per population as mean/min/max rather than stored per neuron.
    That keeps the memory cost independent of network size — the same buffer serves a
    12-neuron mock and a 50,000-neuron connectome — and it is what the plot needs anyway.
    """

    populations: tuple[str, ...]
    t_ms: list[float] = field(default_factory=list)
    mean: dict[str, list[float]] = field(default_factory=dict)
    low: dict[str, list[float]] = field(default_factory=dict)
    high: dict[str, list[float]] = field(default_factory=dict)
    spike_times: dict[str, list[float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for pop in self.populations:
            self.mean.setdefault(pop, [])
            self.low.setdefault(pop, [])
            self.high.setdefault(pop, [])
            self.spike_times.setdefault(pop, [])

    def record(
        self,
        state: BrainState,
        indices: dict[str, np.ndarray],
        store_voltage: bool,
        population_of: np.ndarray | None = None,
    ) -> None:
        """Append one sample.

        Spikes are recorded on *every* substep regardless of ``store_voltage``: a spike is
        a point event lasting one timestep, so decimating the spike record would silently
        drop most of them. Voltages are smooth and can be decimated safely.

        ``population_of`` maps each neuron to the index of the population it belongs to.
        When supplied, spike attribution costs O(number of spikes) rather than O(network
        size): the naive ``state.spikes[idx].any()`` per population slices out a fresh
        13,000-element array on every substep for the large populations, which profiling
        showed to be ~16% of total runtime. Spiking is sparse, so work proportional to the
        spikes is the right shape.
        """
        if population_of is None:
            for pop in self.populations:
                if state.spikes[indices[pop]].any():
                    self.spike_times[pop].append(state.t_ms)
        else:
            fired = np.flatnonzero(state.spikes)
            if fired.size:
                for pop_index in np.unique(population_of[fired]):
                    if pop_index >= 0:
                        self.spike_times[self.populations[pop_index]].append(state.t_ms)

        if not store_voltage:
            return

        self.t_ms.append(state.t_ms)
        for pop in self.populations:
            v = state.voltages[indices[pop]]
            self.mean[pop].append(float(v.mean()))
            self.low[pop].append(float(v.min()))
            self.high[pop].append(float(v.max()))

    def window(self, end_ms: float, width_ms: float) -> slice:
        """Index slice covering ``[end_ms - width_ms, end_ms]`` of the voltage record."""
        if not self.t_ms:
            return slice(0, 0)
        times = np.asarray(self.t_ms)
        start = np.searchsorted(times, end_ms - width_ms, side="left")
        return slice(int(start), len(times))


@dataclass
class StepResult:
    """Everything one environment frame produced, for display and logging."""

    observation: EnvObservation
    packet: SensoryPacket
    state: BrainState
    command: MotorCommand
    done: bool
    frame_spikes: np.ndarray | None = None
    """Neurons that spiked at ANY point during this frame, shape ``(N,)`` bool.

    ``state.spikes`` is the final substep only. A spike occupies exactly one 0.1 ms
    timestep while a frame spans 4 ms, so anything sampling ``state.spikes`` per frame
    sees roughly one fortieth of the spikes that actually happened — enough to look
    plausible and be badly wrong. Anything drawing spikes per frame wants this instead.
    """


class SimulationRunner:
    """Drives environment, encoder, brain and decoder in lockstep."""

    def __init__(
        self,
        env: BaseEnvironment,
        brain: BaseBrain,
        encoder: BaseSensoryEncoder,
        decoder: BaseMotorDecoder,
        config: SimConfig,
        track_populations: tuple[str, ...] | None = None,
    ) -> None:
        self.env = env
        self.brain = brain
        self.encoder = encoder
        self.decoder = decoder
        self.config = config

        r = config.runner
        substeps = r.frame_dt_ms / r.brain_dt_ms
        if abs(substeps - round(substeps)) > 1e-9:
            raise ValueError(
                f"frame_dt_ms ({r.frame_dt_ms}) must be an exact multiple of brain_dt_ms "
                f"({r.brain_dt_ms}); got {substeps} substeps per frame."
            )
        self.substeps = int(round(substeps))
        self.frame_dt_s = r.frame_dt_ms / 1000.0

        available = set(brain.populations)
        wanted = track_populations or tuple(
            p for p in ("T4T5", "LC4", "PMN", "INH", "GF", "MOTOR") if p in available
        )
        missing = set(wanted) - available
        if missing:
            raise KeyError(f"Cannot track unknown population(s): {sorted(missing)}")
        self.tracked = tuple(wanted)
        self._indices = {p: np.asarray(brain.populations[p]) for p in self.tracked}

        # Reverse map: neuron -> index into self.tracked, or -1 for untracked neurons.
        # Lets telemetry attribute spikes in time proportional to the spike count.
        self._population_of = np.full(brain.size, -1, dtype=np.int32)
        for position, pop in enumerate(self.tracked):
            self._population_of[self._indices[pop]] = position

        self.reset()

    def reset(self) -> StepResult:
        """Reset every component and return the initial (un-stepped) state."""
        self.brain.reset()
        self.encoder.reset()
        self.decoder.reset()
        self.observation = self.env.reset()
        self.telemetry = Telemetry(populations=self.tracked)
        self.frame_index = 0
        self._substep_counter = 0
        self.escape_frame: int | None = None
        self.escape_t_s: float | None = None
        self.escape_distance_m: float | None = None
        self.escape_threat_size_m: float | None = None
        self.takeoff_geometry: list[tuple[float, float]] = []
        """(distance_m, threat_size_m) at every takeoff, not only the first.

        A scripted episode contains one approach, so the first takeoff is the whole
        story. An interactive session contains dozens, and its first one is wherever the
        cursor happened to be when the window opened -- which made the reported escape
        angle an arbitrary number rather than a measurement.
        """

        packet = self.encoder.encode(self.observation, self.brain.size)
        state = BrainState(
            t_ms=0.0,
            voltages=np.zeros(self.brain.size, dtype=np.float32),
            spikes=np.zeros(self.brain.size, dtype=bool),
            synaptic_current=np.zeros(self.brain.size, dtype=np.float32),
            spike_counts=np.zeros(self.brain.size, dtype=np.int32),
        )
        command = MotorCommand(t=0.0, escape=False)
        return StepResult(self.observation, packet, state, command, done=False)

    def step(self) -> StepResult:
        """Advance one environment frame, running ``substeps`` brain steps inside it."""
        obs = self.observation

        # One encode per frame: a zero-order hold on sensory input across substeps.
        packet = self.encoder.encode(obs, self.brain.size)

        decimation = max(self.config.runner.telemetry_decimation, 1)
        state: BrainState | None = None
        command = MotorCommand(t=obs.t, escape=False)
        triggered_this_frame = False
        redirected_this_frame = False

        frame_spikes = np.zeros(self.brain.size, dtype=bool)

        for _ in range(self.substeps):
            state = self.brain.step(packet.currents)
            command = self.decoder.decode(state, obs)
            triggered_this_frame |= command.triggered_now
            redirected_this_frame |= command.redirect
            frame_spikes |= state.spikes

            store_voltage = self._substep_counter % decimation == 0
            self.telemetry.record(
                state, self._indices, store_voltage, self._population_of
            )
            self._substep_counter += 1

        assert state is not None  # substeps >= 1 is guaranteed by the constructor

        # The environment is stepped ONCE per frame with the final substep's command, but
        # both of these are single-substep edges. Without re-attaching them, an edge raised
        # on any of the other substeps is silently dropped -- measured at 36 of 376 steering
        # commands surviving before this was fixed.
        if triggered_this_frame and not command.triggered_now:
            command = replace(command, triggered_now=True)
        if redirected_this_frame and not command.redirect:
            command = replace(command, redirect=True)

        if triggered_this_frame:
            self.takeoff_geometry.append((obs.distance, obs.threat_size))
        # The *first* takeoff is kept separately; later ones are re-arms of the reflex.
        if triggered_this_frame and self.escape_frame is None:
            self.escape_frame = self.frame_index
            self.escape_t_s = obs.t
            self.escape_distance_m = obs.distance
            # Capture the threat's size AT the escape. Reading it from the config
            # instead reports the wrong angle whenever the object can be resized --
            # a 120 mm object at 173 mm subtends 38 deg, not the 6.6 deg the 20 mm
            # config default implies.
            self.escape_threat_size_m = obs.threat_size

        self.observation = self.env.step(command, self.frame_dt_s)
        self.frame_index += 1

        return StepResult(
            observation=self.observation,
            packet=packet,
            state=state,
            command=command,
            done=self.observation.done,
            frame_spikes=frame_spikes,
        )

    def run(self, max_frames: int | None = None) -> list[StepResult]:
        """Run to completion headlessly, returning every frame's result."""
        limit = max_frames if max_frames is not None else self._default_frame_limit()
        results: list[StepResult] = []
        for _ in range(limit):
            result = self.step()
            results.append(result)
            if result.done:
                break
        return results

    def _default_frame_limit(self) -> int:
        return int(np.ceil(self.config.env.duration_s / self.frame_dt_s)) + 1

    def summary(self) -> dict[str, object]:
        """Post-run facts, used by ``--check`` and printed by ``--no-show``."""
        gf_ms = getattr(self.decoder, "gf_spike_time_ms", None)
        first_spikes = {
            pop: (times[0] if times else None)
            for pop, times in self.telemetry.spike_times.items()
        }
        counts = {pop: len(times) for pop, times in self.telemetry.spike_times.items()}

        # Angular size of the threat at the moment of takeoff. Escape decisions in real
        # flies track angular size rather than absolute distance, so this is the number
        # worth comparing against the literature.
        theta_deg = None
        if self.escape_distance_m is not None and self.escape_distance_m > 0:
            size = self.escape_threat_size_m or self.config.env.threat_size_m
            half = size / (2.0 * self.escape_distance_m)
            theta_deg = float(np.rad2deg(2.0 * np.arctan(half)))

        # Across every takeoff, not just the first. The median is the honest summary of
        # an interactive session: individual takeoffs range from a considered approach to
        # a cursor that happened to appear next to the fly.
        angles = [
            float(np.rad2deg(2.0 * np.arctan(size / (2.0 * d))))
            for d, size in self.takeoff_geometry
            if d > 0
        ]

        return {
            "frames": self.frame_index,
            "sim_time_s": self.observation.t,
            "outcome": self.outcome(),
            "airborne": self.observation.escaped,
            "gf_first_spike_ms": gf_ms,
            "takeoffs": int(self.observation.raw.get("takeoffs", 0)),
            "escape_t_s": self.escape_t_s,
            "escape_distance_m": self.escape_distance_m,
            "escape_angular_size_deg": theta_deg,
            "escape_angular_size_deg_median": (
                float(np.median(angles)) if angles else None
            ),
            "escape_angular_size_deg_all": [round(a, 1) for a in angles],
            "final_distance_m": self.observation.distance,
            "first_spike_ms": first_spikes,
            "active_substeps": counts,
        }

    def outcome(self) -> str:
        """Current episode outcome as a short label, safe to call mid-run."""
        raw = self.observation.raw
        if raw.get("captured"):
            return "captured"
        if raw.get("got_away"):
            return "escaped"
        if self.escape_frame is not None:
            return "escaped_but_still_pursued"
        return "no_escape"
