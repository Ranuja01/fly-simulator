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

``theta_dot`` is a finite difference between frames and therefore noisy -- badly so under
mouse control -- so it is smoothed before use. That smoothing is a real modelling choice:
too little and hand tremor reads as looming, too much and a genuine fast strike is blunted.

Scaling to 3D: a MuJoCo or Minecraft environment would render an actual retinal image, and
this class would be replaced by one that computes per-ommatidium contrast. It would emit
the identical :class:`SensoryPacket`, so the brain would not need to change.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from flysim.config import EncoderParams
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

        # A teleporting threat still produces a spurious spike through the closing speed,
        # so the discontinuity guard stays. Zero is the honest answer for a jump: it carries
        # no information about whether the object is approaching, and clamping would instead
        # report the maximum possible expansion rate, which reads as maximally threatening.
        discontinuity = abs(raw_theta_dot) > p.max_expansion_rate_rad_s
        if discontinuity:
            raw_theta_dot = 0.0

        # Light smoothing. The analytic form is already continuous across substeps, so this
        # only takes the edge off hand tremor rather than reconstructing a signal.
        self._theta_dot = (
            p.theta_dot_smoothing * self._theta_dot
            + (1.0 - p.theta_dot_smoothing) * raw_theta_dot
        )

        # eta = theta_dot * exp(-alpha * theta), rectified. Expansion only: an object
        # moving away has a negative rate and must not drive an escape.
        expansion = max(self._theta_dot, 0.0)
        eta = expansion * float(np.exp(-p.size_decay_alpha * theta))
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
