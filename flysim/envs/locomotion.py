"""Idle walking behaviour, shared by the scripted and interactive arenas.

*Drosophila* do not drift like Brownian particles. They walk in bouts along a body axis,
punctuated by rapid turns — **body saccades** — and they stop often. A fly that slides
smoothly in a straight line, or vibrates in place, reads as a machine; one that walks,
stops, snaps to a new heading and walks again reads as an animal.

**This is kinematics, not neuroscience.** No locomotor circuit produces this motion — it is
a scripted stand-in so the animal behaves plausibly between escapes. Only the *escape* is
neurally driven, by the Giant Fiber. Do not report walking statistics from this model.

Making walking neurally driven would mean modelling the descending neurons that actually
control it (DNa02 and relatives for steering, among others) plus a ventral-nerve-cord
motor model — a substantial project, and one that needs a CNS dataset rather than a
brain-only one. See ``docs/CONNECTOME_ACCESS.md`` §1.
"""

from __future__ import annotations

import numpy as np

from flysim.config import EnvParams


class EscapeFlight:
    """Velocity during an escape: jump, powered flight, landing.

    Three phases, because a single drag-decay from the takeoff velocity cannot represent
    both of the things an escape has to do. To outrun a pursuer the velocity must stay
    above the pursuer's speed for a while, which forces a low drag coefficient — and a low
    drag coefficient makes the takeoff impulse itself take seconds to bleed off, so the
    fly crosses the entire arena in one enormous glide and is never on the ground.

    Splitting them fixes both: the jump decays fast (toward cruise, not toward zero),
    cruise is held for a bounded time and is genuinely faster than the threat, and only
    then does the fly decelerate to a stop.

    Direction is fixed at takeoff. A fly cannot re-aim mid-jump either.
    """

    def __init__(self, params: EnvParams) -> None:
        self._p = params
        self._elapsed = 0.0
        self._heading = np.array([1.0, 0.0])
        self._speed = 0.0
        self.active = False

    def start(self, heading: np.ndarray, takeoff_speed: float) -> None:
        self._heading = np.asarray(heading, dtype=np.float64)
        norm = float(np.linalg.norm(self._heading))
        if norm > 0:
            self._heading = self._heading / norm
        self._speed = float(takeoff_speed)
        self._elapsed = 0.0
        self.active = True

    def velocity(self, dt_s: float) -> np.ndarray:
        """Advance the flight and return the current velocity vector."""
        p = self._p
        self._elapsed += dt_s

        if self._elapsed < p.fly_flight_duration_s:
            # Jump impulse decaying toward cruise — not toward zero.
            gap = self._speed - p.fly_cruise_speed_ms
            self._speed = p.fly_cruise_speed_ms + gap * float(
                np.exp(-p.fly_jump_decay_per_s * dt_s)
            )
        else:
            self._speed *= float(np.exp(-p.fly_drag_per_s * dt_s))
            if self._speed < p.landing_speed_ms:
                self.active = False

        return self._heading * self._speed

    @property
    def heading_angle(self) -> float:
        return float(np.arctan2(self._heading[1], self._heading[0]))


class WalkingFly:
    """A body heading, a walk/stand state, and saccadic turns."""

    def __init__(self, params: EnvParams, rng: np.random.Generator) -> None:
        self._p = params
        self._rng = rng
        self.reset()

    def reset(self) -> None:
        self._heading = float(self._rng.uniform(0.0, 2.0 * np.pi))
        self._walking = True

    @property
    def heading(self) -> float:
        """Body orientation in radians. Also used to aim the escape realistically."""
        return self._heading

    def turn(self, radians: float) -> None:
        self._heading = float((self._heading + radians) % (2.0 * np.pi))

    def velocity(self, dt_s: float) -> np.ndarray:
        """Advance the behavioural state one tick and return a velocity vector.

        Transitions are sampled as Poisson events over the timestep, so behaviour does not
        change with the frame rate — ``rate * dt`` is the probability of an event in this
        tick, which is the correct discretisation of a continuous-time process.
        """
        p = self._p

        # Spontaneous body saccade: a fast turn to a new heading.
        if self._rng.random() < p.fly_saccade_rate_hz * dt_s:
            magnitude = abs(self._rng.normal(p.fly_saccade_deg, p.fly_saccade_deg * 0.4))
            self.turn(np.deg2rad(magnitude) * self._rng.choice([-1.0, 1.0]))

        # Walk/stand switching, with the dwell times implied by fly_walk_fraction.
        if self._rng.random() < p.fly_pause_rate_hz * dt_s:
            self._walking = bool(self._rng.random() < p.fly_walk_fraction)

        if not self._walking:
            # Standing still is not perfectly still — postural micro-movement remains.
            return self._rng.normal(0.0, p.fly_jitter_ms * 0.35, size=2)

        forward = np.array([np.cos(self._heading), np.sin(self._heading)])
        speed = max(self._rng.normal(p.fly_walk_speed_ms, p.fly_walk_speed_ms * 0.25), 0.0)
        return forward * speed + self._rng.normal(0.0, p.fly_jitter_ms * 0.4, size=2)

    def reflect(self, hit_x: bool, hit_y: bool) -> None:
        """Turn away from a wall instead of sliding along it.

        A fly that walks into the arena edge and keeps pressing against it looks broken.
        Reflecting the heading — plus a random component, so it does not ping-pong along a
        perfectly repeating path — reads as the animal turning away.
        """
        if not (hit_x or hit_y):
            return
        direction = np.array([np.cos(self._heading), np.sin(self._heading)])
        if hit_x:
            direction[0] *= -1.0
        if hit_y:
            direction[1] *= -1.0
        self._heading = float(np.arctan2(direction[1], direction[0]))
        self.turn(self._rng.normal(0.0, np.deg2rad(25.0)))
