"""Sensory interface: world geometry in, injected current out.

The looming cue
---------------
An object of physical width ``l`` at distance ``d`` subtends an angle

.. math::  \\theta = 2 \\arctan\\!\\left(\\frac{l}{2d}\\right)

on the retina. As the object approaches at constant speed, ``theta`` grows slowly at
first and then explosively — the signature that visual systems across the animal kingdom
use to detect an impending collision. Locust LGMD/DCMD and *Drosophila* LC neurons are the
classic examples.

This encoder produces an **exponential looming value**

.. math::  L = e^{k\\,l/d} - 1

which is zero at infinite distance and rises steeply as ``d`` shrinks, then converts it to
picoamps and injects it into the LC4 population.

A note on fidelity: the ethologically correct drive for a looming-selective neuron is the
*rate of expansion* ``dtheta/dt``, not size itself — a large stationary object is not a
threat. This encoder computes ``theta`` and ``theta_dot`` and reports both in the packet's
``raw`` dict, so switching the drive term is a one-line change here and nothing downstream
notices. The exponential form is used as the primary drive for the Starter Phase because
it produces a clean monotone ramp that is easy to read on the telemetry panel.

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

    def encode(self, obs: EnvObservation, n_neurons: int) -> SensoryPacket:
        if n_neurons != self._n:
            raise ValueError(
                f"Encoder was built for {self._n} neurons but was asked to drive "
                f"{n_neurons}. Rebuild the encoder when the connectome changes."
            )

        p = self._p

        # Division-by-zero guard. `distance` legitimately reaches zero when the predator
        # lands exactly on the fly, which is not an error condition — it is the most
        # threatening state possible. Clamp rather than raise.
        distance = max(float(obs.distance), p.min_distance_m)
        ratio = float(obs.threat_size) / distance

        # Overflow guard. exp(20) is ~4.9e8, comfortably finite in float32; without the
        # clip, a small enough distance produces inf, then NaN voltages, and the failure
        # appears far away from its cause.
        exponent = float(np.clip(p.steepness * ratio, 0.0, p.max_exponent))

        # expm1 rather than exp(x) - 1: at the small exponents that dominate early
        # approach, the naive form loses most of its significant digits to cancellation.
        loom = float(np.expm1(exponent))

        raw_drive_pa = p.gain_pa * loom

        # Angular size and its rate of change: reported for diagnostics and as the
        # drop-in replacement drive term described in the module docstring.
        theta = 2.0 * float(np.arctan(obs.threat_size / (2.0 * distance)))
        theta_dot = 0.0
        if self._prev_theta is not None and self._prev_t is not None:
            dt = obs.t - self._prev_t
            if dt > 0.0:
                theta_dot = (theta - self._prev_theta) / dt
        self._prev_theta = theta
        self._prev_t = obs.t

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
                "loom": loom,
                "drive_pa": float(injected.mean()),
                "drive_pa_max": float(injected.max()),
                "distance_m": distance,
                "theta_rad": theta,
                "theta_dot_rad_s": theta_dot,
                "saturated": bool(np.any(injected >= p.max_current_pa)),
            },
        )
