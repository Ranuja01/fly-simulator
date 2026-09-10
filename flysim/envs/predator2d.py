"""2D arena with a pursuing predator.

The Starter Phase world: a fly at the origin, a predator that closes on it at constant
speed, and a motor command that can override the fly's kinematics into a ballistic
escape.

This class knows nothing about neurons. It receives a :class:`MotorCommand` describing an
*intent* ("go this way, this fast") and applies it with its own physics. A MuJoCo or
Minecraft environment would interpret the identical command with its own physics, which
is why swapping them requires no change anywhere else.

Positions are ``(2,)`` arrays here, but every consumer treats them as ``(D,)``, so the
same pipeline runs in 3D once an environment supplies 3D vectors.
"""

from __future__ import annotations

import numpy as np

from flysim.config import EnvParams
from flysim.core.base import BaseEnvironment
from flysim.core.types import EnvObservation, MotorCommand
from flysim.envs.locomotion import EscapeFlight, WalkingFly

# Below this separation the direction from predator to fly is numerically meaningless.
# Used to keep unit-vector maths finite when the two coincide exactly.
_COINCIDENT_EPS = 1e-9


class Predator2DEnvironment(BaseEnvironment):
    """A point-mass fly stalked by a point-mass predator."""

    def __init__(self, params: EnvParams | None = None) -> None:
        self._p = params or EnvParams()
        self._rng = np.random.default_rng(self._p.seed)
        self._bounds = np.array(
            [
                [-self._p.arena_half_width_m, self._p.arena_half_width_m],
                [-self._p.arena_half_width_m, self._p.arena_half_width_m],
            ],
            dtype=np.float64,
        )
        self.reset()

    @property
    def bounds(self) -> np.ndarray:
        return self._bounds

    def reset(self) -> EnvObservation:
        p = self._p
        self._rng = np.random.default_rng(p.seed)

        self._fly_pos = np.array(p.fly_start, dtype=np.float64)
        self._fly_vel = np.zeros(2, dtype=np.float64)
        self._walk = WalkingFly(p, self._rng)
        self._flight = EscapeFlight(p)

        angle = np.deg2rad(p.predator_start_angle_deg)
        offset = p.predator_start_distance_m * np.array([np.cos(angle), np.sin(angle)])
        self._pred_pos = self._fly_pos + offset
        self._pred_vel = np.zeros(2, dtype=np.float64)

        self._t = 0.0
        self._step_index = 0
        self._airborne = False
        self._captured = False
        self._got_away = False
        self._takeoffs = 0
        return self._observe()

    def step(self, command: MotorCommand, dt_s: float) -> EnvObservation:
        p = self._p

        # --- Motor command overrides kinematics -------------------------------------
        # The escape is an override, not a nudge: a giant-fiber takeoff replaces whatever
        # the fly was doing with a ballistic jump. The command carries an intent; turning
        # that into velocity is this environment's job.
        #
        # Keyed on `triggered_now` (the rising edge) rather than `escape` (the level), so
        # each GF spike produces exactly one impulse instead of re-accelerating the fly on
        # every frame of the command window.
        if command.triggered_now and command.heading is not None:
            self._airborne = True
            self._takeoffs += 1
            self._flight.start(command.heading, command.impulse)

        # --- Fly kinematics ----------------------------------------------------------
        if self._airborne:
            # Jump -> powered flight -> landing. See EscapeFlight for why this is three
            # phases and not a single drag decay.
            self._fly_vel = self._flight.velocity(dt_s)
            self._fly_pos = self._fly_pos + self._fly_vel * dt_s
            if not self._flight.active:
                # Landed: the reflex re-arms and walking resumes on the flight heading.
                self._airborne = False
                self._walk.turn(self._flight.heading_angle - self._walk.heading)
        else:
            # Walking in bouts with saccadic turns — kinematics, not a locomotor circuit.
            self._fly_vel = self._walk.velocity(dt_s)
            self._fly_pos = self._fly_pos + self._fly_vel * dt_s

        # --- Predator pursuit ---------------------------------------------------------
        # Pure pursuit: always heads at the fly's current position at constant speed.
        to_fly = self._fly_pos - self._pred_pos
        gap = float(np.linalg.norm(to_fly))
        if gap > _COINCIDENT_EPS:
            direction = to_fly / gap
        else:
            # Predator is exactly on top of the fly. Any direction is as good as another;
            # pick a fixed one so the run stays reproducible.
            direction = np.array([1.0, 0.0])
        self._pred_vel = direction * p.predator_speed_ms
        self._pred_pos = self._pred_pos + self._pred_vel * dt_s

        self._reflect_at_walls()

        self._t += dt_s
        self._step_index += 1

        distance = self._distance()
        if not self._airborne and distance < p.capture_distance_m:
            self._captured = True
        if self._takeoffs > 0 and distance > p.escape_success_distance_m:
            self._got_away = True

        return self._observe()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _reflect_at_walls(self) -> None:
        """Keep both agents inside the arena by reflecting off the walls."""
        lo, hi = self._bounds[:, 0], self._bounds[:, 1]

        below = self._fly_pos < lo
        above = self._fly_pos > hi
        hit = below | above
        self._fly_pos = np.clip(self._fly_pos, lo, hi)
        self._fly_vel[hit] *= -1.0
        # A walking fly turns away from the wall rather than pressing into it.
        if hit.any() and not self._airborne:
            self._walk.reflect(bool(hit[0]), bool(hit[1]))

        self._pred_pos = np.clip(self._pred_pos, lo, hi)

    def _distance(self) -> float:
        return float(np.linalg.norm(self._pred_pos - self._fly_pos))

    def _closing_speed(self) -> float:
        """Rate at which the gap is shrinking, m/s. Positive means approaching.

        The gap ``d = |r|`` where ``r = pred - fly`` changes at
        ``d_dot = (r . v_rel) / d``, so closing speed is ``-d_dot``. At ``d = 0`` the
        derivative is undefined; report zero rather than dividing.
        """
        r = self._pred_pos - self._fly_pos
        d = float(np.linalg.norm(r))
        if d <= _COINCIDENT_EPS:
            return 0.0
        v_rel = self._pred_vel - self._fly_vel
        return float(-np.dot(r, v_rel) / d)

    def _observe(self) -> EnvObservation:
        p = self._p
        distance = self._distance()
        timed_out = self._t >= p.duration_s
        return EnvObservation(
            t=self._t,
            step_index=self._step_index,
            agent_position=self._fly_pos.copy(),
            agent_velocity=self._fly_vel.copy(),
            threat_position=self._pred_pos.copy(),
            threat_velocity=self._pred_vel.copy(),
            distance=distance,
            closing_speed=self._closing_speed(),
            threat_size=p.threat_size_m,
            escaped=self._airborne,
            done=timed_out or self._captured or self._got_away,
            raw={
                "captured": self._captured,
                "timed_out": timed_out,
                "got_away": self._got_away,
                "takeoffs": self._takeoffs,
                "fly_speed_ms": float(np.linalg.norm(self._fly_vel)),
            },
        )
