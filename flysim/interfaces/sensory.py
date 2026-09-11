r"""Sensory interface: world geometry in, injected current out.

The looming cue
---------------
An object of physical width ``l`` at distance ``d`` subtends an angle

.. math::  \theta = 2 \arctan\!\left(\frac{l}{2d}\right)

on the retina. What a looming-selective neuron responds to is not that angle but its
**rate of change** -- the visual signature of an impending collision. This encoder uses the
standard looming-sensitivity form

.. math::  \eta = \dot{\theta} \, e^{-\alpha \theta}

rectified so that only expansion counts.

Both terms earn their place:

* ``theta_dot`` means a **stationary object produces no drive at all**, however large and
  however close. An earlier version of this encoder drove LC4 from angular *size*, and a
  60 mm object parked 50 mm away and never moved still made the fly flee -- which is not
  what a fly does, and not what LC4 encodes.
* The rectification means a **receding** object is ignored. Under a size-based drive,
  something retreating still produced current, because magnitude carries no sign.
* ``exp(-alpha * theta)`` makes the response peak at a characteristic angular size rather
  than growing without bound as the object arrives, giving the circuit a size reference as
  well as a rate one.

``theta_dot`` is computed in closed form from the closing speed the environment already
maintains, not by differencing ``theta`` between frames -- see :meth:`LoomingEncoder.encode`
for why that distinction turned out to matter. A jump in the threat's position is rejected
on SPEED rather than on expansion rate, because a speed threshold means the same thing at
every distance while a rate threshold tightens as the object nears, discarding ordinary
approaches at close range.

Scaling to 3D: a MuJoCo or Minecraft environment would render an actual retinal image, and
this class would be replaced by one that computes per-ommatidium contrast. It would emit
the identical :class:`SensoryPacket`, so the brain would not need to change.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from flysim.config import EncoderParams, MotionParams
from flysim.core.base import BaseSensoryEncoder
from flysim.core.types import EnvObservation, SensoryPacket


class LoomingEncoder(BaseSensoryEncoder):
    """Converts fly-predator geometry into LC4 input current."""

    def __init__(
        self,
        params: EncoderParams,
        populations: Mapping[str, np.ndarray],
        n_neurons: int,
    ) -> None:
        self._p = params
        self._n = int(n_neurons)

        try:
            self._target = np.asarray(populations[params.target_population], dtype=np.int64)
        except KeyError:
            raise KeyError(
                f"Encoder targets population {params.target_population!r}, which this "
                f"connectome does not have. Available: {sorted(populations)}"
            ) from None

        # Per-neuron gain heterogeneity. LC4 neurons tile the visual field with distinct
        # receptive fields, so a given expansion does not drive them all equally. Without
        # this every LC4 trace is identical, which is both unrealistic and visually
        # useless. Seeded so runs reproduce exactly.
        rng = np.random.default_rng(params.seed)
        gains = 1.0 + params.receptive_field_spread * rng.standard_normal(self._target.size)
        # A receptive field can be weakly driven but not negatively driven.
        self._gains = np.clip(gains, 0.05, None).astype(np.float32)

        self.reset()

    def reset(self) -> None:
        self._prev_theta: float | None = None
        self._prev_t: float | None = None
        self._theta_dot: float = 0.0

    def encode(self, obs: EnvObservation, n_neurons: int) -> SensoryPacket:
        if n_neurons != self._n:
            raise ValueError(
                f"Encoder was built for {self._n} neurons but was asked to drive "
                f"{n_neurons}. Rebuild the encoder when the connectome changes."
            )

        p = self._p

        # Division-by-zero guard. `distance` legitimately reaches zero when the threat
        # lands exactly on the fly, which is not an error condition -- it is the most
        # threatening state possible. Clamp rather than raise.
        distance = max(float(obs.distance), p.min_distance_m)

        # Angular subtense, and its rate of change: the actual looming cue.
        theta = 2.0 * float(np.arctan(obs.threat_size / (2.0 * distance)))

        # Expansion rate, computed ANALYTICALLY from the closing speed rather than by
        # differencing theta between frames.
        #
        #   theta      = 2 arctan(l / 2d)
        #   dtheta/dd  = -4l / (4d^2 + l^2)
        #   theta_dot  = dtheta/dd * d_dot,  and d_dot = -closing_speed
        #              = 4 * l * closing_speed / (4d^2 + l^2)
        #
        # Finite differencing looked equivalent and was not. The runner takes several
        # simulation steps per rendered frame while a mouse-driven threat updates only
        # once per frame, so the difference put all of the motion into one sample and left
        # the rest at zero: four of every five samples reported no expansion at all, the
        # sustained drive collapsed to about a fifth of its true value, and the Giant Fiber
        # never reached threshold. The closing speed is continuous across those substeps
        # because the environment maintains it, so this form has no such blind spot -- and
        # it is exact rather than approximate.
        size = float(obs.threat_size)
        raw_theta_dot = (
            4.0 * size * float(obs.closing_speed) / (4.0 * distance**2 + size**2)
        )

        # Teleport detection on SPEED, which is scale-independent: no real object in
        # this arena moves at 6 m/s whatever its distance. Thresholding the expansion rate
        # instead made the guard tighter the closer the threat got, discarding ordinary
        # approaches at close range.
        discontinuity = abs(float(obs.closing_speed)) > p.max_closing_speed_ms
        if discontinuity:
            raw_theta_dot = 0.0
        else:
            # Sensory ceiling, kept only so the arithmetic stays finite as d -> 0.
            raw_theta_dot = float(
                np.clip(raw_theta_dot, -p.max_expansion_rate_rad_s,
                        p.max_expansion_rate_rad_s)
            )

        # Light smoothing. The analytic form is already continuous across substeps, so this
        # only takes the edge off hand tremor rather than reconstructing a signal.
        self._theta_dot = (
            p.theta_dot_smoothing * self._theta_dot
            + (1.0 - p.theta_dot_smoothing) * raw_theta_dot
        )

        # eta = theta_dot * exp(-alpha * theta), rectified. Expansion only: an object
        # moving away has a negative rate and must not drive an escape.
        expansion = max(self._theta_dot, 0.0)
        # Decay is capped: past the cap the object already fills the visual field, and
        # further suppression would make a closer threat matter less than a distant one.
        decay_theta = min(theta, np.deg2rad(p.size_decay_cap_deg))
        eta = expansion * float(np.exp(-p.size_decay_alpha * decay_theta))
        raw_drive_pa = p.gain_pa * eta

        # Saturation is applied per neuron, *after* the receptive-field gain. Response
        # compression happens in each cell, so a strongly-driven LC4 can be at ceiling
        # while a weakly-driven one is still in its linear range — clipping the shared
        # drive first would erase that difference.
        currents = np.zeros(self._n, dtype=np.float32)
        currents[self._target] = np.clip(
            raw_drive_pa * self._gains, 0.0, p.max_current_pa
        )

        injected = currents[self._target]
        return SensoryPacket(
            t=obs.t,
            currents=currents,
            raw={
                "loom": eta,
                "theta_dot_smoothed": self._theta_dot,
                "drive_pa": float(injected.mean()),
                "drive_pa_max": float(injected.max()),
                "distance_m": distance,
                "theta_rad": theta,
                "theta_dot_rad_s": raw_theta_dot,
                "saturated": bool(np.any(injected >= p.max_current_pa)),
                "discontinuity": discontinuity,
            },
        )


class MotionEncoder(BaseSensoryEncoder):
    """Drives T4/T5 from the threat's sweep across the eye.

    T4 and T5 are the fly's elementary motion detectors -- T4 for moving light edges, T5
    for dark ones -- and each has four subtypes with different preferred directions: *a*
    and *b* horizontal and opposed, *c* and *d* vertical and opposed. They are the input
    to the lobula plate and, in this connectome, one synapse upstream of LC4 and LPLC2.

    Why this exists: looming is blind to anything that does not approach. An object
    orbiting the fly at constant radius produces **exactly zero** drive in the looming
    encoder -- measured at 0.0-0.2 pA across every speed and radius tried -- because the
    radial component of its velocity is nil. A real fly plainly sees such a thing. This
    encoder supplies the modality that was missing.

    What is honest about it, and what is not
    ----------------------------------------
    * The sweep rate is computed **analytically** from the relative velocity, for the same
      reason the looming encoder does: the runner takes several simulation steps per
      rendered frame, and a finite difference puts all the motion into one sample.
    * **There is no retinotopy.** Real T4/T5 tile the visual field, each cell reporting
      motion in its own small patch. Here every cell of a subtype receives the same drive,
      so a single global sweep signal stands in for a spatial map. This is the largest
      simplification in the class, and it is why drive has to be scaled by angular size by
      hand -- a real array would get that for free from how many columns an object covers.
    * **Subtypes are assigned by the sign of the sweep alone.** Whether motion is
      progressive or regressive is eye-specific in the animal, and assigning eyes needs
      the retinotopy above. Vertical subtypes (*c*, *d*) are left undriven, because a
      top-down arena has no elevation for them to report -- they are present in the
      network and stay silent, which is the truthful outcome rather than a fudge.
    * **T4 and T5 are driven identically.** Separating them needs luminance polarity,
      which needs a rendered image.
    * **Self-motion is not included.** A turning fly sweeps its whole visual field, and
      that signal dominates T4/T5 in a real animal. Adding it without the compensation
      circuitry that cancels it would make the fly blind itself every time it turned.
    """

    def __init__(
        self,
        params: MotionParams,
        populations: Mapping[str, np.ndarray],
        labels: Sequence[str],
        n_neurons: int,
    ) -> None:
        self._p = params
        self._n = int(n_neurons)

        try:
            target = np.asarray(populations[params.target_population], dtype=np.int64)
        except KeyError:
            raise KeyError(
                f"Motion encoder targets population {params.target_population!r}, which "
                f"this connectome does not have. Available: {sorted(populations)}"
            ) from None

        # Sort the target cells by preferred direction. The subtype letter is the third
        # character of the cell type, e.g. "T4c:12345" -> "c".
        positive: list[int] = []
        negative: list[int] = []
        vertical: list[int] = []
        for index in target:
            cell_type = str(labels[int(index)]).split(":", 1)[0]
            suffix = cell_type[2:3].lower()
            if suffix == "a":
                positive.append(int(index))
            elif suffix == "b":
                negative.append(int(index))
            else:
                vertical.append(int(index))
        self._preferring_positive = np.asarray(positive, dtype=np.int64)
        self._preferring_negative = np.asarray(negative, dtype=np.int64)
        self._vertical = np.asarray(vertical, dtype=np.int64)
        self.reset()

    def reset(self) -> None:
        self._sweep_rad_s: float = 0.0

    def describe(self) -> str:
        return (
            f"  motion encoder: {self._preferring_positive.size} + "
            f"{self._preferring_negative.size} horizontal T4/T5 driven, "
            f"{self._vertical.size} vertical silent (a 2D arena has no elevation)"
        )

    def encode(self, obs: EnvObservation, n_neurons: int) -> SensoryPacket:
        if n_neurons != self._n:
            raise ValueError(
                f"Motion encoder was built for {self._n} neurons but was asked to drive "
                f"{n_neurons}. Rebuild the encoder when the connectome changes."
            )
        p = self._p
        distance = max(float(obs.distance), p.min_distance_m)

        # Signed angular velocity of the threat about the fly, in the plane. For a line of
        # sight u and relative velocity v, the component of v ALONG u is the closing speed
        # the looming encoder uses; the component ACROSS u is what sweeps the image over
        # the eye, and dividing it by distance turns it into an angular rate.
        offset = np.asarray(obs.threat_position, dtype=np.float64) - np.asarray(
            obs.agent_position, dtype=np.float64
        )
        relative = np.asarray(obs.threat_velocity, dtype=np.float64) - np.asarray(
            obs.agent_velocity, dtype=np.float64
        )
        if offset.size >= 2:
            unit = offset[:2] / distance
            cross = float(unit[0] * relative[1] - unit[1] * relative[0])
            self._sweep_rad_s = cross / distance
        else:
            self._sweep_rad_s = 0.0

        rate = float(np.clip(self._sweep_rad_s, -p.max_rate_rad_s, p.max_rate_rad_s))

        # Occupancy stands in for the retinotopic tiling this encoder does not have: a
        # larger object covers more columns and so recruits more of the array.
        theta = 2.0 * float(np.arctan(obs.threat_size / (2.0 * distance)))
        occupancy = min(theta / float(np.deg2rad(p.size_reference_deg)), 1.0)

        drive = p.gain_pa * abs(rate) * occupancy
        currents = np.zeros(self._n, dtype=np.float32)
        # Opposed subtypes: each half of the population reports one direction only, which
        # is what makes the pair a direction-selective signal rather than a speedometer.
        active = self._preferring_positive if rate > 0 else self._preferring_negative
        if active.size:
            currents[active] = min(drive, p.max_current_pa)

        return SensoryPacket(
            t=obs.t,
            currents=currents,
            raw={
                "sweep_rad_s": self._sweep_rad_s,
                # Reported AFTER the ceiling, so the number means what reached a neuron.
                "motion_drive_pa": float(min(drive, p.max_current_pa)),
                "motion_drive_raw_pa": float(drive),
                "motion_direction": ("a" if rate > 0 else "b" if rate < 0 else "none"),
                "motion_occupancy": occupancy,
            },
        )


class CompositeEncoder(BaseSensoryEncoder):
    """Sums several encoders into one packet.

    The :class:`SensoryPacket` is a flat per-neuron current vector, so combining
    modalities really is addition -- a neuron receiving both looming and motion input gets
    both currents, exactly as it would if two afferent pathways converged on it. No
    encoder needs to know that another exists.

    The runner holds exactly one encoder, which was fine while there was only one
    modality. This is the smallest thing that lifts that restriction.
    """

    def __init__(self, *encoders: BaseSensoryEncoder) -> None:
        if not encoders:
            raise ValueError("CompositeEncoder needs at least one encoder.")
        self._encoders = encoders

    def reset(self) -> None:
        for encoder in self._encoders:
            encoder.reset()

    def encode(self, obs: EnvObservation, n_neurons: int) -> SensoryPacket:
        total = np.zeros(n_neurons, dtype=np.float32)
        raw: dict = {}
        for encoder in self._encoders:
            packet = encoder.encode(obs, n_neurons)
            total += packet.currents
            raw.update(packet.raw)
        return SensoryPacket(t=obs.t, currents=total, raw=raw)
