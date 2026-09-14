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


def _soft_saturate(x: np.ndarray | float, ceiling: float) -> np.ndarray:
    """Compress toward a ceiling instead of clipping at it.

    A hard clip destroys information the moment two inputs both exceed the limit: they come
    out identical, and any comparison between them is gone. That is not a detail here. The
    left/right signal survives clipping because it is a contrast between a driven eye and a
    SILENT one, and zero stays zero — but front/back is a contrast in magnitude within the
    same eye, so once both exceed the ceiling the two directions become indistinguishable.
    Measured: front/back separates at DNp04 by 128 ms during the approach, and is gone by
    the time the threat is close and everything is pinned at 140 pA.

    ``ceiling * tanh(x / ceiling)`` is monotonic everywhere, so ordering is never lost; it
    is within a few percent of linear well below the ceiling, so the operating range is
    barely touched; and it approaches the ceiling asymptotically rather than hitting it.
    Real neurons compress rather than clip, so this is also the less invented choice.
    """
    if ceiling <= 0:
        return np.asarray(x, dtype=np.float32)
    return (ceiling * np.tanh(np.asarray(x, dtype=np.float64) / ceiling)).astype(np.float32)


def _relative_velocity(obs: EnvObservation, efference_copy: float) -> np.ndarray:
    """Threat velocity as the fly's visual system should treat it.

    ``efference_copy`` of the animal's own velocity is removed. At 1.0 only the threat's
    motion remains, so the fly no longer registers approach that it is itself creating;
    at 0.0 this returns the true relative velocity that
    :attr:`EnvObservation.closing_speed` is built from.
    """
    threat = np.asarray(obs.threat_velocity, dtype=np.float64)
    own = np.asarray(obs.agent_velocity, dtype=np.float64)
    return threat - (1.0 - float(efference_copy)) * own


def _line_of_sight(obs: EnvObservation, distance: float) -> np.ndarray:
    """Unit vector from fly to threat."""
    offset = np.asarray(obs.threat_position, dtype=np.float64) - np.asarray(
        obs.agent_position, dtype=np.float64
    )
    return offset / distance


class LoomingEncoder(BaseSensoryEncoder):
    """Converts fly-predator geometry into LC4 input current."""

    def __init__(
        self,
        params: EncoderParams,
        populations: Mapping[str, np.ndarray],
        n_neurons: int,
        hemisphere: np.ndarray | None = None,
        preferred_azimuth: np.ndarray | None = None,
        labels: Sequence[str] | None = None,
    ) -> None:
        self._p = params
        self._n = int(n_neurons)
        self._hemisphere = (
            None if hemisphere is None else np.asarray(hemisphere).astype(np.int8)
        )
        self._preferred = (
            None if preferred_azimuth is None
            else np.asarray(preferred_azimuth, dtype=np.float64)
        )

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

        self._split_targets(labels if labels is not None
                            else [""] * (int(np.max(self._target)) + 1))
        self.reset()

    def reset(self) -> None:
        self._reference = None
        self._history: list[tuple[float, float, float]] = []
        self._prev_theta: float | None = None
        self._prev_t: float | None = None
        self._theta_dot: float = 0.0

    def _split_targets(self, labels) -> None:
        """Sort the driven cells into the two measured feature channels.

        Ache et al. 2019: LC4 encodes looming speed, LPLC2 encodes angular size. Other
        visual projection neurons in this population are not covered by that result and
        keep the combined drive, because we have no measurement telling us otherwise.
        """
        velocity, size, other = [], [], []
        for index in self._target:
            name = str(labels[int(index)]).split(":", 1)[0].upper()
            if name.startswith("LPLC2"):
                size.append(int(index))
            elif name.startswith("LC4"):
                velocity.append(int(index))
            else:
                other.append(int(index))
        self._velocity_cells = np.asarray(velocity, dtype=np.int64)
        self._size_cells = np.asarray(size, dtype=np.int64)
        self._other_cells = np.asarray(other, dtype=np.int64)

    def _delayed(self, now_s: float, delay_ms: float):
        """The (theta, theta_dot) the fly is actually reacting to.

        A real fly's giant fiber sees a 19 ms old image: phototransduction and the optic
        lobe take that long, and this model injects current straight into LC4 and LPLC2,
        skipping both. Indexed by timestamp rather than frame count so it is correct
        whatever the environment's step size is.
        """
        target = now_s - delay_ms / 1000.0
        if not self._history or target <= self._history[0][0]:
            return self._history[0][1:] if self._history else (0.0, 0.0)
        for t, theta, theta_dot in reversed(self._history):
            if t <= target:
                return theta, theta_dot
        return self._history[0][1:]

    def _size_drive_pa(self, theta_rad: float, theta_dot: float | None = None) -> float:
        """LPLC2's angular-size channel, in picoamps.

        Two candidate forms for the same published Gaussian, because the paper's equation
        is paywalled and we have only the parameter values quoted secondhand:

        * ``"linear"`` -- a Gaussian in degrees, width fitted. Its flaw is that a Gaussian
          has no zero: at theta = 0 it still delivers 6.6% of peak, which measured out as
          5.9 pA against the 7 pA a cell needs to fire. With the per-cell gain spread on
          top, LPLC2 fires tonically for a threat anywhere in the arena -- and then falls
          SILENT past 83 degrees, when the threat is closest. Both were visible in the
          telemetry as a permanently lit LC4 row that went quiet on approach.
        * ``"log"`` -- a Gaussian in log angular size. This is a hypothesis, not a reading:
          the published C4 = 0.52 cannot be a width in degrees (a delta function at 42),
          but it works as a dimensionless width in log-angle, which would explain why it
          carries no unit. It goes to zero for a distant object and stays high up close.

        The form is switchable so the two published targets decide between them rather
        than our preference. Whichever is adopted, it stays labelled as inferred.
        """
        p = self._p
        theta_deg = float(np.rad2deg(theta_rad))
        if p.size_tuning_form == "log":
            if theta_deg <= 0.0:
                return 0.0
            offset = np.log(theta_deg) - np.log(p.size_peak_deg)
            width = p.size_log_width
        else:
            offset = theta_deg - p.size_peak_deg
            width = p.size_width_deg
        if width <= 0.0:
            return 0.0
        drive = float(p.size_gain_pa * np.exp(-(offset * offset) / (2.0 * width * width)))
        if p.size_requires_motion:
            # LPLC2 need looming motion to respond at all. Without this the channel reads
            # angular size alone and a stationary object of the right size drives it
            # forever -- see EncoderParams.size_requires_motion.
            # The DELAYED rate, matching the delayed theta this channel reads. Using
            # the instantaneous one would gate a 19 ms old image on a present-moment
            # expansion, which is a different signal.
            rate = max(float(self._theta_dot if theta_dot is None else theta_dot), 0.0)
            ref = max(float(p.size_motion_ref_rad_s), 1e-9)
            drive *= 1.0 - float(np.exp(-rate / ref))
        return drive

    def describe_channels(self) -> str:
        return (f"  feature channels: {self._velocity_cells.size} LC4 on angular velocity, "
                f"{self._size_cells.size} LPLC2 on angular size "
                f"(peak {self._p.size_peak_deg:.0f} deg), "
                f"{self._other_cells.size} other visual cells unchanged")

    def _hemifield_weights(self, obs: EnvObservation) -> np.ndarray:
        """Per-target-cell gain from which eye can see the threat.

        Each eye's field is centred out to its own side, so the preferred direction is
        -90 degrees for the left eye and +90 for the right. Drive follows a raised cosine
        in the angle between the threat and that preferred direction: full when the threat
        is out to that side, half when it is directly ahead — which is the correct
        balanced answer for a frontal approach — and falling to ``hemifield_floor``
        behind. The floor is not zero because a fly's eyes wrap far around its head.

        Returns all-ones when tuning is off, when the environment supplies no body axis,
        or when the connectome does not say which side a cell is on. In each of those
        cases the honest answer is the previous uniform behaviour rather than a guess.
        """
        p = self._p
        if p.hemifield_tuning <= 0.0 or self._hemisphere is None:
            return np.ones(self._target.size, dtype=np.float32)
        if obs.agent_heading is None:
            return np.ones(self._target.size, dtype=np.float32)

        offset = np.asarray(obs.threat_position, dtype=np.float64) - np.asarray(
            obs.agent_position, dtype=np.float64
        )
        if offset.size < 2 or not np.any(offset):
            return np.ones(self._target.size, dtype=np.float32)

        # Threat bearing in the fly's own frame: 0 straight ahead, POSITIVE TO ITS RIGHT --
        # the convention the eye preferences below and neuprint_source._preferred_azimuth
        # both use. The arena's angles run counter-clockwise (the fly moves along
        # (cos h, sin h)), so `world - heading` is positive to the fly's LEFT and has to be
        # negated to reach it.
        #
        # It was not negated, for as long as hemifield tuning existed. Every eye was tuned to
        # the opposite side of the arena: a threat on the fly's left drove its right eye
        # 1.6x and its left eye 0.4x. Behaviour still looked right, because the neural
        # heading's turn sign had been matched to the mirrored data, so the two errors
        # cancelled. Found when a body-frame measurement showed the jump muscle OPPOSITE
        # the threat firing first in 14 of 15 escapes -- impossible for a pathway measured
        # ipsilateral at every stage. Every result that a left/right flip EXISTS survives
        # (a mirror preserves a flip); every statement of WHICH side leads was inverted.
        # See MODEL_JOURNAL, "The eyes were mirrored".
        world = float(np.arctan2(offset[1], offset[0]))
        bearing = float(obs.agent_heading) - world

        side = self._hemisphere[self._target]
        # Straight out to the side, unless the anatomy says otherwise for this cell.
        preferred = np.where(side < 0, -np.pi / 2.0, np.pi / 2.0)
        if self._preferred is not None:
            derived = self._preferred[self._target] * p.retinotopy_polarity
            known = np.isfinite(derived)
            preferred = np.where(known, derived, preferred)
        # side == 0 (unknown or midline) gets no preference, so it stays uniform.
        raised = 0.5 * (1.0 + np.cos(bearing - preferred))
        weights = p.hemifield_floor + (1.0 - p.hemifield_floor) * raised
        weights = np.where(side == 0, 1.0, weights)

        # Normalised against a FIXED reference rather than the per-frame mean. Dividing by
        # the per-frame mean rescales every bearing to the same total drive, which says the
        # threat is equally visible wherever it is -- and that erases front/back, since two
        # eyes symmetric about the body axis differ only in magnitude there, not in ratio.
        # The reference is the mean weight for a threat straight ahead.
        # Retinotopy is a statement about WHERE the drive goes, not
        # how much of it there is: the same object at the same distance produces the same
        # total expansion on a near-panoramic eye wherever it sits. Without this the
        # weights, all being <= 1, simply attenuate -- measured, the escape threshold
        # slipped from 16.7 to 26.9 degrees and the fly stopped getting away, which is an
        # attenuation artifact masquerading as a change in sensitivity.
        reference = self._reference_mean(preferred, side)
        if reference > 0:
            weights = weights / reference

        # Blend toward uniform so the effect can be dialled rather than only switched.
        k = float(np.clip(p.hemifield_tuning, 0.0, 1.0))
        return ((1.0 - k) + k * weights).astype(np.float32)

    def _reference_mean(self, preferred: np.ndarray, side: np.ndarray) -> float:
        """Mean weight for a threat directly ahead — the fixed normalisation reference.

        Cached: it depends only on the cells, not on where the threat is.
        """
        if getattr(self, "_reference", None) is None:
            p = self._p
            raised = 0.5 * (1.0 + np.cos(0.0 - preferred))
            w = p.hemifield_floor + (1.0 - p.hemifield_floor) * raised
            w = np.where(side == 0, 1.0, w)
            self._reference = float(w.mean())
        return self._reference

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
        # Closing speed with the fly's own contribution cancelled -- see
        # EncoderParams.efference_copy. At efference_copy = 0 this is exactly
        # obs.closing_speed.
        unit = _line_of_sight(obs, distance)
        relative = _relative_velocity(obs, p.efference_copy)
        closing = -float(np.dot(unit[: relative.size], relative))

        size = float(obs.threat_size)
        raw_theta_dot = 4.0 * size * closing / (4.0 * distance**2 + size**2)

        # Teleport detection on SPEED, which is scale-independent: no real object in
        # this arena moves at 6 m/s whatever its distance. Thresholding the expansion rate
        # instead made the guard tighter the closer the threat got, discarding ordinary
        # approaches at close range.
        discontinuity = abs(closing) > p.max_closing_speed_ms
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
        # Hemifield-based tuning with a curve-based falloff. Without it every cell gets
        # the same current wherever the threat is, so azimuth never reaches the neurons.
        tuning = self._hemifield_weights(obs)

        currents = np.zeros(self._n, dtype=np.float32)
        if not p.split_feature_channels:
            currents[self._target] = _soft_saturate(
                np.maximum(raw_drive_pa * self._gains * tuning, 0.0), p.max_current_pa
            )
        else:
            # Two measured channels instead of one invented composite. The velocity
            # channel is theta_dot ALONE -- the exp(-alpha*theta) decay that used to sit
            # on it was a crude stand-in for size dependence, and LPLC2 now supplies that
            # properly rather than by suppressing the velocity signal.
            self._history.append((float(obs.t), theta, self._theta_dot))
            if len(self._history) > 4096:
                del self._history[:2048]
            d_theta, d_theta_dot = self._delayed(float(obs.t), p.sensory_delay_ms)

            velocity_pa = p.gain_pa * max(d_theta_dot, 0.0)
            size_pa = self._size_drive_pa(d_theta, d_theta_dot)

            gains = self._gains
            # Only the two measured populations are driven. The remaining visual
            # projection cells compute other features; driving them with a looming signal
            # was our assumption, not a measurement, and with 654 of them against 312
            # measured cells that assumption dominated the result.
            for cells, drive in ((self._velocity_cells, velocity_pa),
                                 (self._size_cells, size_pa)):
                if not cells.size:
                    continue
                sel = np.isin(self._target, cells)
                currents[cells] = _soft_saturate(
                    np.maximum(drive * gains[sel] * tuning[sel], 0.0), p.max_current_pa
                )

        injected = currents[self._target]
        left = self._hemisphere is not None and np.any(
            self._hemisphere[self._target] < 0
        )
        return SensoryPacket(
            t=obs.t,
            currents=currents,
            raw={
                "loom": eta,
                "theta_dot_smoothed": self._theta_dot,
                "drive_pa": float(injected.mean()),
                "drive_pa_max": float(injected.max()),
                "size_drive_pa": (
                    self._size_drive_pa(
                        *self._delayed(float(obs.t), p.sensory_delay_ms)
                    ) if p.split_feature_channels else 0.0
                ),
                "closing_ms": closing,
                "closing_raw_ms": float(obs.closing_speed),
                "distance_m": distance,
                "theta_rad": theta,
                "theta_dot_rad_s": raw_theta_dot,
                "drive_pa_left": (
                    float(injected[self._hemisphere[self._target] < 0].mean())
                    if left else 0.0
                ),
                "drive_pa_right": (
                    float(injected[self._hemisphere[self._target] > 0].mean())
                    if left else 0.0
                ),
                "saturated": bool(np.any(injected >= 0.95 * p.max_current_pa)),
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
    * **Self-motion is cancelled** by ``MotionParams.efference_copy``, for the same
      reason the looming encoder cancels it: a moving fly sweeps its own visual field,
      and without the circuitry that discounts that, the animal responds to itself.
      Translation is cancelled here; the fly's *rotation* is not represented at all,
      which in a real animal is the larger of the two signals.
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
        relative = _relative_velocity(obs, p.efference_copy)
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
            currents[active] = float(_soft_saturate(drive, p.max_current_pa))

        return SensoryPacket(
            t=obs.t,
            currents=currents,
            raw={
                "sweep_rad_s": self._sweep_rad_s,
                # Reported AFTER the ceiling, so the number means what reached a neuron.
                "motion_drive_pa": float(_soft_saturate(drive, p.max_current_pa)),
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
