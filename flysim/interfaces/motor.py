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

    def __init__(self, params: DecoderParams, populations: Mapping[str, np.ndarray]) -> None:
        self._p = params
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
        self._last_takeoff_ms: float | None = None

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
        if bool(state.spikes[self._trigger].any()):
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
        if self._pending_spike_ms is not None:
            since_spike = state.t_ms - self._pending_spike_ms
            if p.takeoff_delay_ms <= since_spike <= p.takeoff_delay_ms + p.command_window_ms:
                escape = True
                # The rising edge fires once per GF spike, never twice for the same one.
                if self._dispatched_spike_ms != self._pending_spike_ms and self._can_take_off(
                    state.t_ms, obs
                ):
                    triggered_now = True
                    self._dispatched_spike_ms = self._pending_spike_ms
                    self._last_takeoff_ms = state.t_ms
                    self._takeoff_count += 1

        return MotorCommand(
            t=obs.t,
            escape=escape,
            triggered_now=triggered_now,
            heading=self._heading if escape else None,
            impulse=p.takeoff_speed_ms if escape else 0.0,
            raw={
                "gf_first_spike_t_ms": self._first_spike_ms,
                "gf_spike_count": int(state.spike_counts[self._trigger].sum()),
                "takeoff_count": self._takeoff_count,
                "awaiting_takeoff": (
                    self._pending_spike_ms is not None
                    and self._dispatched_spike_ms != self._pending_spike_ms
                ),
            },
        )

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

    def _escape_heading(self, obs: EnvObservation) -> np.ndarray:
        """Unit vector away from the threat, rotated by the escape bias."""
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
