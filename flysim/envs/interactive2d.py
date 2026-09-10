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

# Mouse motion arrives as discrete jumps between rendered frames, and differentiating that
# directly produces a violently spiky velocity. Since closing speed feeds the looming
# computation, that noise would reach the neurons. An exponential filter over roughly
# three frames is enough to make it usable without hiding a real fast approach.
_VELOCITY_SMOOTHING = 0.65

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

        # Threat follows the cursor. Velocity comes from the actual displacement, so a
        # fast flick really is a fast approach as far as the looming encoder is concerned.
        previous = self._threat_pos.copy()
        self._threat_pos = self._target.copy()
        if dt_s > 0:
            instantaneous = (self._threat_pos - previous) / dt_s
            self._threat_vel = (
                _VELOCITY_SMOOTHING * self._threat_vel
                + (1.0 - _VELOCITY_SMOOTHING) * instantaneous
            )

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
