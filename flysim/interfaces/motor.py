"""Motor interface: spikes in, motor command out.

The Giant Fiber (GF, descending neuron DNp01) is one of the best-characterised command
neurons in any animal. It is **all-or-none**: a single GF action potential is sufficient
to drive a short-mode escape takeoff, via the tergotrochanteral motor neuron (TTMn) and
the peripherally synapsing interneuron (PSI). There is no rate code and no graded
version — the decision has already been made by the time GF fires, so this decoder simply
watches for the first spike and latches.

Two details taken from the biology:

* **Takeoff delay.** The GF spike is not the jump. The electrical-plus-chemical synapse
  onto TTMn, then muscle activation, costs a few milliseconds. The decoder therefore
  latches the spike time and only reports ``escape=True`` once that delay has elapsed.
* **Directional bias.** Flies do not take off straight backwards. Escape trajectories are
  directed away from the threat with a consistent lateral component, so the away-vector is
  rotated by a fixed bias angle.

Scaling up: a richer motor layer would read a wing-steering population and emit continuous
torques. It would still emit a :class:`MotorCommand`, so the environment would not change.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from flysim.config import DecoderParams
from flysim.core.base import BaseMotorDecoder
from flysim.core.types import BrainState, EnvObservation, MotorCommand

# Below this separation the away-from-threat direction is numerically meaningless.
_COINCIDENT_EPS = 1e-9

# Deterministic fallback heading for the degenerate case where fly and predator occupy
# exactly the same point. Arbitrary, but fixed, so runs stay reproducible.
_FALLBACK_HEADING = np.array([1.0, 0.0])


class GiantFiberDecoder(BaseMotorDecoder):
    """Watches the GF population and converts its first spike into a takeoff."""

    def __init__(self, params: DecoderParams, populations: Mapping[str, np.ndarray],
                 hemisphere: np.ndarray | None = None,
                 side_readout: np.ndarray | None = None) -> None:
        self._p = params
        # Which cells' side is informative. NOT the whole trigger population: on the male
        # CNS that population holds TTMn *and* PSI, and each giant fiber drives its own
        # side's TTMn but BOTH PSI. The bilaterally driven PSI fires on either side at the
        # same instant, which pins any left-right difference to exactly zero -- measured,
        # and it hid the entire directional result once (MODEL_JOURNAL Step K1). The
        # caller names the cells that carry side; the decoder does not guess.
        self._side_left = np.asarray((), dtype=np.int64)
        self._side_right = np.asarray((), dtype=np.int64)
        if hemisphere is not None and side_readout is not None and len(side_readout):
            sr = np.asarray(side_readout, dtype=np.int64)
            self._side_left = sr[hemisphere[sr] < 0]
            self._side_right = sr[hemisphere[sr] > 0]
        # The wing muscles, where the dataset has them. A brain-only connectome does not,
        # and there the escape is reported unpowered-but-scripted exactly as before --
        # the flag only ever carries information when the muscles are in the volume.
        self._flight = np.asarray(populations.get("FLIGHT", ()), dtype=np.int64)
        try:
            self._trigger = np.asarray(
                populations[params.trigger_population], dtype=np.int64
            )
        except KeyError:
            raise KeyError(
                f"Decoder watches population {params.trigger_population!r}, which this "
                f"connectome does not have. Available: {sorted(populations)}"
            ) from None
        self.reset()

    def reset(self) -> None:
        self._pending_spike_ms: float | None = None
        self._first_spike_ms: float | None = None
        self._dispatched_spike_ms: float | None = None
        self._heading: np.ndarray | None = None
        self._takeoff_count = 0
        self._steer_count = 0
        self._last_takeoff_ms: float | None = None
        self._last_steer_ms: float | None = None
        self._flight_seen = False
        self._lead_side = 0
        self._last_used_side = 0
        self.neural_heading_misses = 0

    @property
    def gf_spike_time_ms(self) -> float | None:
        """Brain time of the *first* GF spike, or None if it has never fired."""
        return self._first_spike_ms

    @property
    def takeoff_count(self) -> int:
        """How many distinct takeoffs have been commanded."""
        return self._takeoff_count

    def decode(self, state: BrainState, obs: EnvObservation) -> MotorCommand:
        p = self._p

        # --- Register a GF spike -----------------------------------------------------
        # Every GF spike is serviced, not just the first: the escape is a reflex that can
        # fire again if the threat is still there when the fly lands.
        # The wing muscles fire a few milliseconds after the command, within the takeoff
        # delay, so this latch is set before the command is dispatched. Latched rather
        # than sampled because a spike occupies one 0.1 ms step and the dispatch happens
        # on a later one.
        if self._flight.size and bool(state.spikes[self._flight].any()):
            self._flight_seen = True

        # Which side's jump motor neuron fires first is the directional signal. Recorded
        # before the heading is committed, because the commit happens on the same step.
        if self._lead_side == 0 and (self._side_left.size or self._side_right.size):
            left_now = bool(state.spikes[self._side_left].any())
            right_now = bool(state.spikes[self._side_right].any())
            if left_now != right_now:
                self._lead_side = -1 if left_now else 1

        if bool(state.spikes[self._trigger].any()):
            # A fresh command starts a fresh judgement about the wings, so a later escape
            # cannot inherit an earlier flight's wingbeat. Reset HERE rather than at
            # dispatch: the trigger spike precedes the wing muscles, so this window opens
            # before they can fire, where a dispatch-time reset would open after.
            if self._pending_spike_ms is None or state.t_ms > self._pending_spike_ms:
                self._flight_seen = False
            self._pending_spike_ms = state.t_ms
            if self._first_spike_ms is None:
                self._first_spike_ms = state.t_ms
            # The escape direction is committed at the moment of the spike, using where
            # the threat was then. A real fly cannot re-aim mid-jump either.
            self._heading = self._escape_heading(obs)

        # --- Convert to a command ----------------------------------------------------
        # A spike commands a takeoff during the window
        # [spike + takeoff_delay, spike + takeoff_delay + command_window].
        escape = False
        triggered_now = False
        redirect = False
        powered_now = False
        if self._pending_spike_ms is not None:
            since_spike = state.t_ms - self._pending_spike_ms
            if p.takeoff_delay_ms <= since_spike <= p.takeoff_delay_ms + p.command_window_ms:
                escape = True
                # The rising edge fires once per GF spike, never twice for the same one.
                fresh = self._dispatched_spike_ms != self._pending_spike_ms
                if fresh and self._can_take_off(state.t_ms, obs):
                    triggered_now = True
                    powered_now = self._powered()
                    self._dispatched_spike_ms = self._pending_spike_ms
                    # Cleared after the heading has been committed and used, so a second
                    # escape in the same episode reads its own side rather than inheriting
                    # the first one's.
                    self._lead_side = 0
                    self._last_takeoff_ms = state.t_ms
                    self._takeoff_count += 1
                elif fresh and obs.escaped and self._can_steer(state.t_ms):
                    # Already in the air. The command cannot start a second jump, but it
                    # can change where this one is going -- which is what keeps the fly
                    # responsive to a threat that keeps chasing it mid-flight.
                    redirect = True
                    self._dispatched_spike_ms = self._pending_spike_ms
                    self._last_steer_ms = state.t_ms
                    self._steer_count += 1

        return MotorCommand(
            t=obs.t,
            escape=escape,
            triggered_now=triggered_now,
            redirect=redirect,
            heading=self._heading if (escape or redirect) else None,
            impulse=p.takeoff_speed_ms if escape else 0.0,
            powered=powered_now if triggered_now else self._powered(),
            raw={
                "gf_first_spike_t_ms": self._first_spike_ms,
                "gf_spike_count": int(state.spike_counts[self._trigger].sum()),
                "takeoff_count": self._takeoff_count,
                "steer_count": self._steer_count,
                "wing_muscles_fired": self._flight_seen,
                "awaiting_takeoff": (
                    self._pending_spike_ms is not None
                    and self._dispatched_spike_ms != self._pending_spike_ms
                ),
            },
        )

    def _powered(self) -> bool:
        """Did the wing muscles fire, so this escape is flight rather than a hop?

        With no FLIGHT population in the connectome there is nothing to read, and the
        answer is True -- the previous behaviour, which assumed powered flight. Assuming
        it is the honest default when the muscles are outside the imaged volume; on a CNS
        dataset the assumption is replaced by a measurement.
        """
        if not self._flight.size:
            return True
        return self._flight_seen

    # Known limitation: `LIFBrain.silence` gates a neuron's OUTPUT but leaves it spiking
    # so its voltage stays inspectable, and this reads `state.spikes`. Lesioning DLMn
    # directly therefore still reads as a wingbeat. Lesioning the PSI upstream works
    # correctly and is the meaningful experiment; a `BrainState` field for spikes that
    # actually left the neuron would close the gap.

    def _can_take_off(self, t_ms: float, obs: EnvObservation) -> bool:
        """Is the body physically able to jump right now?

        Two constraints, both about the body rather than the brain:

        * **Already airborne.** A fly in flight has nothing to push against. Without this
          the Giant Fiber keeps firing during flight and every spike re-launches the fly.
        * **Just landed.** The short-mode escape needs a brief postural reset.

        The Giant Fiber is left free to spike whenever the circuit says it should -- those
        spikes still appear in the telemetry. What is gated here is the *takeoff*, which
        is the honest place to gate it.
        """
        if obs.escaped:
            return False
        if self._last_takeoff_ms is None:
            return True
        return (t_ms - self._last_takeoff_ms) >= self._p.takeoff_refractory_ms

    def _can_steer(self, t_ms: float) -> bool:
        """Rate-limit mid-flight course corrections.

        The Giant Fiber can spike ~90 times a second under a relentless loom. Honouring
        every one as a separate turn would be a seizure rather than a flight path.
        """
        if self._last_steer_ms is None:
            return True
        return (t_ms - self._last_steer_ms) >= self._p.steer_refractory_ms

    def _neural_heading(self, obs: EnvObservation) -> np.ndarray | None:
        """Turn away from the side whose jump motor neuron fired first.

        Uses only the spikes and the fly's own body axis. The threat's position is never
        read -- which is the whole point, and also why this is coarser than the geometric
        version: it knows a side, not a bearing.
        """
        if self._lead_side == 0 or obs.agent_heading is None:
            return None
        # Re-aim only when the threat CHANGES side. The decode is a fixed rotation away
        # from the current body axis, so applying it again on every trigger spike during
        # one flight turns the fly through 90 degrees over and over -- which traces a
        # circle. Ranuja found it by driving the model: the fly could be steered into
        # near-perfect loops. A real short-mode escape is ballistic, and nothing measured
        # here supports re-aiming mid-flight from the same unchanged signal.
        if self._lead_side == self._last_used_side and self._heading is not None:
            return self._heading
        self._last_used_side = self._lead_side
        # The same-side jump motor neuron leads, so the leading side is the side the threat
        # is on: turn the other way. Arena angles run counter-clockwise, so a turn to the
        # RIGHT is negative -- left leading (-1) must give heading - 90 degrees.
        #
        # This read `heading - side * turn` until the encoder's eyes were found mirrored.
        # That sign turned the fly TOWARD the leading side, which only pointed it away from
        # the threat because the mirrored encoder made the OPPOSITE jump muscle lead. The two
        # errors cancelled; fixing either alone sends the fly at the threat. They change
        # together, and --check now guards both.
        angle = float(obs.agent_heading) + self._lead_side * np.deg2rad(
            self._p.neural_turn_deg
        )
        return np.array([np.cos(angle), np.sin(angle)], dtype=np.float64)

    def _escape_heading(self, obs: EnvObservation) -> np.ndarray:
        """Unit vector away from the threat, rotated by the escape bias."""
        if self._p.neural_heading:
            decoded = self._neural_heading(obs)
            if decoded is not None:
                return decoded
            # No side fired yet, or the environment reports no body axis. Falling back to
            # geometry is a silent return to the scripted behaviour, so it is counted.
            self.neural_heading_misses += 1
        away = np.asarray(obs.agent_position, dtype=np.float64) - np.asarray(
            obs.threat_position, dtype=np.float64
        )
        norm = float(np.linalg.norm(away))

        if norm <= _COINCIDENT_EPS:
            # Predator exactly on top of the fly: "away" has no meaning. Use a fixed
            # direction rather than dividing by zero or producing NaN.
            away = _FALLBACK_HEADING[: away.size].copy()
            if away.size and not away.any():
                away[0] = 1.0
            norm = float(np.linalg.norm(away))

        unit = away / norm

        # Lateral bias. Defined as a rotation, which only has an unambiguous meaning in
        # the plane; a 3D environment would supply its own body-axis-relative bias, so
        # higher dimensions are left unrotated rather than rotated arbitrarily.
        if unit.size == 2 and self._p.escape_bias_deg:
            angle = np.deg2rad(self._p.escape_bias_deg)
            cos_a, sin_a = np.cos(angle), np.sin(angle)
            unit = np.array(
                [cos_a * unit[0] - sin_a * unit[1], sin_a * unit[0] + cos_a * unit[1]]
            )

        return unit
