"""Mouse-driven arena: you are the threat.

Instead of a scripted predator, the threatening object follows your cursor. Move it at the
fly and watch the Giant Fiber decide. This is the most direct way to get a feel for what
the circuit is actually computing — you can hunt for the escape threshold by hand, and
discover that a slow approach lets you get much closer than a fast one.

Why this is a good test of the architecture
-------------------------------------------
This class implements the same :class:`BaseEnvironment` interface as
:class:`~flysim.envs.predator2d.Predator2DEnvironment`. The LIF engine, the looming
encoder, the Giant Fiber decoder and the telemetry panel are untouched — a live human
input source is, as far as the brain is concerned, indistinguishable from a scripted one.
That is exactly the property that is supposed to make a MuJoCo or Minecraft swap cheap.

Controls (wired up in :mod:`flysim.viz.dashboard`)
--------------------------------------------------
* **move the mouse** over the spatial panel — positions the threat
* **scroll wheel** — grows/shrinks the object. This matters: the looming cue is driven by
  angular size ``l/d``, so a big far object and a small near one are genuinely equivalent
  to the circuit, and you can verify that by hand.
* **r** — reset the fly to the centre
"""

from __future__ import annotations

import numpy as np

from flysim.config import EnvParams
from flysim.core.base import BaseEnvironment
from flysim.core.types import EnvObservation, MotorCommand
from flysim.envs.locomotion import EscapeFlight, WalkingFly

_COINCIDENT_EPS = 1e-9

# Mouse motion arrives as discrete jumps, and differentiating that directly produces a
# spiky velocity. Since closing speed feeds the looming computation, that noise would
# reach the neurons. This is deliberately light -- about one and a half pointer updates.
# It used to be 0.65, which was compensating for the substep inflation `_track_pointer`
# now removes; with the measurement corrected, the extra smoothing only bought lag, and
# lag shows up directly as a fast approach being spotted LATER than a slow one. Measured
# on the 22,973-neuron male CNS -- detection distance for a 20 mm head-on approach at
# 2 / 3 / 5 m/s: 115 / 115 / 55 mm at 0.35, against 75 / 55 / never at 0.65. The encoder's
# own `theta_dot_smoothing` handles what is left of the tremor.
_VELOCITY_SMOOTHING = 0.35

# The pointer only changes when the mouse handler fires, which is far less often than
# `step` runs. These bound how the gap between updates is interpreted -- see
# `InteractiveEnvironment._track_pointer`.
_POINTER_MAX_GAP_S = 0.06
"""Longest interval a single pointer displacement may be divided by."""

_POINTER_IDLE_S = 0.05
"""No movement for longer than this is read as a hand that has stopped, not a gap."""

_POINTER_DECAY_TAU_S = 0.03
"""Time constant the held velocity decays with once the pointer is judged stopped."""

MIN_THREAT_SIZE_M = 0.004
MAX_THREAT_SIZE_M = 0.120
_SCROLL_FACTOR = 1.18


class InteractiveEnvironment(BaseEnvironment):
    """A 2D arena whose threat is wherever the user last pointed."""

    def __init__(self, params: EnvParams | None = None) -> None:
        self._p = params or EnvParams()
        self._rng = np.random.default_rng(self._p.seed)
        half = self._p.arena_half_width_m
        self._bounds = np.array([[-half, half], [-half, half]], dtype=np.float64)
        self.reset()

    @property
    def bounds(self) -> np.ndarray:
        return self._bounds

    # ------------------------------------------------------------------
    # User input
    # ------------------------------------------------------------------

    def set_threat_position(self, x: float, y: float) -> None:
        """Point the threat at a world coordinate. Called from the mouse handler."""
        self._target = np.clip(
            np.array([x, y], dtype=np.float64),
            self._bounds[:, 0],
            self._bounds[:, 1],
        )

    def scale_threat(self, steps: int) -> None:
        """Grow or shrink the object (scroll wheel)."""
        self._threat_size = float(
            np.clip(
                self._threat_size * (_SCROLL_FACTOR**steps),
                MIN_THREAT_SIZE_M,
                MAX_THREAT_SIZE_M,
            )
        )

    def reset_agent(self) -> None:
        """Put the fly back in the middle without restarting the neural simulation."""
        self._fly_pos = np.array(self._p.fly_start, dtype=np.float64)
        self._fly_vel = np.zeros(2, dtype=np.float64)
        self._airborne = False
        self._walk.reset()

    @property
    def threat_size(self) -> float:
        return self._threat_size

    # ------------------------------------------------------------------
    # BaseEnvironment
    # ------------------------------------------------------------------

    def reset(self) -> EnvObservation:
        self._fly_pos = np.array(self._p.fly_start, dtype=np.float64)
        self._fly_vel = np.zeros(2, dtype=np.float64)
        self._walk = WalkingFly(self._p, self._rng)
        self._flight = EscapeFlight(self._p)

        # Start the threat parked in a corner, far enough away to be sub-threshold, so the
        # simulation does not open with a spurious escape before the user touches anything.
        half = self._p.arena_half_width_m
        self._threat_pos = np.array([-half * 0.9, -half * 0.9], dtype=np.float64)
        self._target = self._threat_pos.copy()
        self._threat_vel = np.zeros(2, dtype=np.float64)
        self._threat_size = self._p.threat_size_m
        self._pointer_gap_s = 0.0
        self._pointer_idle_s = 0.0

        self._t = 0.0
        self._step_index = 0
        self._airborne = False
        self._takeoffs = 0
        return self._observe()

    def step(self, command: MotorCommand, dt_s: float) -> EnvObservation:
        p = self._p

        if command.triggered_now and command.heading is not None:
            self._airborne = True
            self._takeoffs += 1
            self._flight.start(command.heading, command.impulse)
        elif command.redirect and command.heading is not None and self._airborne:
            # Steer the flight already in progress; do not relaunch it.
            self._flight.steer(command.heading)

        if self._airborne:
            # Jump -> powered flight -> landing. See EscapeFlight.
            self._fly_vel = self._flight.velocity(dt_s)
            self._fly_pos = self._fly_pos + self._fly_vel * dt_s
            if not self._flight.active:
                self._airborne = False
                self._walk.turn(self._flight.heading_angle - self._walk.heading)
        else:
            # Walking in bouts with saccadic turns — kinematics, not a locomotor circuit.
            self._fly_vel = self._walk.velocity(dt_s)
            self._fly_pos = self._fly_pos + self._fly_vel * dt_s

        # Threat follows the cursor. Velocity is measured over the interval since the
        # pointer last actually moved, not per environment step -- see _track_pointer.
        previous = self._threat_pos.copy()
        self._threat_pos = self._target.copy()
        self._track_pointer(self._threat_pos - previous, dt_s)

        lo, hi = self._bounds[:, 0], self._bounds[:, 1]
        hit = (self._fly_pos < lo) | (self._fly_pos > hi)
        self._fly_pos = np.clip(self._fly_pos, lo, hi)
        if hit.any() and not self._airborne:
            self._walk.reflect(bool(hit[0]), bool(hit[1]))

        self._t += dt_s
        self._step_index += 1
        return self._observe()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _track_pointer(self, delta: np.ndarray, dt_s: float) -> None:
        """Estimate pointer velocity independently of how many substeps a frame has.

        The pointer changes only when the mouse handler fires, while ``step`` runs several
        times per rendered frame (five, interactively). Dividing each step's displacement
        by that step's own ``dt`` therefore reports a whole frame's worth of motion as if
        it had happened inside a single 4 ms step, inflating the apparent speed by roughly
        ``steps_per_frame * (1 - smoothing)``. Measured: a hand moving 5 m/s read as
        9.9 m/s, which is past the encoder's teleport guard -- so the fastest and most
        threatening approaches were precisely the ones being discarded as implausible, and
        a hard charge at the fly did nothing while a gentler one triggered an escape.

        Dividing by the time since the pointer last moved gives the same answer at any
        substep rate, which is the property that was missing.
        """
        if dt_s <= 0:
            return

        if np.any(delta):
            # The interval is capped. A genuine discontinuity -- the pointer leaving the
            # axes and re-entering somewhere else -- must still read as an enormous speed
            # so the encoder rejects it, rather than being spread across however long the
            # pointer was away and arriving as a plausible approach.
            elapsed = min(self._pointer_gap_s + dt_s, _POINTER_MAX_GAP_S)
            self._threat_vel = (
                _VELOCITY_SMOOTHING * self._threat_vel
                + (1.0 - _VELOCITY_SMOOTHING) * (delta / elapsed)
            )
            self._pointer_gap_s = 0.0
            self._pointer_idle_s = 0.0
            return

        # No movement this step is ambiguous: it is either the gap between two mouse
        # events or a hand that has stopped. Hold the estimate briefly, then decay it.
        # Decaying at once would make a steady drag stutter; never decaying would leave a
        # parked pointer looming at the fly forever.
        self._pointer_gap_s += dt_s
        self._pointer_idle_s += dt_s
        if self._pointer_idle_s > _POINTER_IDLE_S:
            self._threat_vel *= float(np.exp(-dt_s / _POINTER_DECAY_TAU_S))

    def _observe(self) -> EnvObservation:
        offset = self._threat_pos - self._fly_pos
        distance = float(np.linalg.norm(offset))

        if distance <= _COINCIDENT_EPS:
            closing = 0.0
        else:
            relative = self._threat_vel - self._fly_vel
            closing = float(-np.dot(offset, relative) / distance)

        return EnvObservation(
            t=self._t,
            step_index=self._step_index,
            agent_position=self._fly_pos.copy(),
            agent_velocity=self._fly_vel.copy(),
            threat_position=self._threat_pos.copy(),
            threat_velocity=self._threat_vel.copy(),
            distance=distance,
            closing_speed=closing,
            threat_size=self._threat_size,
            escaped=self._airborne,
            # Never ends. The point is to keep poking at it.
            done=False,
            raw={
                "interactive": True,
                "takeoffs": self._takeoffs,
                "threat_size_m": self._threat_size,
                "fly_speed_ms": float(np.linalg.norm(self._fly_vel)),
            },
        )
