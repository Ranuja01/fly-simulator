"""Boundary data structures.

These dataclasses are the **only** types permitted to cross a layer boundary:

    Environment --EnvObservation--> SensoryEncoder --SensoryPacket--> Brain
         ^                                                              |
         |                                                          BrainState
         +-------- MotorCommand <-- MotorDecoder <---------------------+

Keeping the set this small is what lets the 2D environment be swapped for MuJoCo, a
Minecraft bridge, or a network socket without the LIF engine noticing. Every structure
carries a free-form ``raw`` dict so a richer environment can attach extra payload
(retinal images, contact forces, joint torques) without changing this file.

Position vectors are ``(D,)`` arrays, not hard-coded 2-vectors, so the same structures
describe a 3D world unchanged.

Units: seconds and metres at the environment boundary, picoamps in the sensory packet,
millivolts in the brain state. See CLAUDE.md for the full units table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class EnvObservation:
    """One frame of world state, emitted by any :class:`BaseEnvironment`.

    This is deliberately *physical*, not neural: it describes what is happening in the
    world, and says nothing about how a nervous system should encode it. Choosing an
    encoding is the sensory layer's job.
    """

    t: float
    """Environment time in **seconds** since reset."""

    step_index: int
    """Number of environment frames elapsed since reset."""

    agent_position: np.ndarray
    """Fly position, shape ``(D,)``, metres."""

    agent_velocity: np.ndarray
    """Fly velocity, shape ``(D,)``, m/s."""

    threat_position: np.ndarray
    """Predator position, shape ``(D,)``, metres."""

    threat_velocity: np.ndarray
    """Predator velocity, shape ``(D,)``, m/s."""

    distance: float
    """Euclidean fly-to-predator distance in metres. Always >= 0, never NaN."""

    closing_speed: float
    """Rate of approach in m/s. Positive means the gap is shrinking."""

    threat_size: float
    """Physical extent of the looming object in metres (the ``l`` of ``l/d``)."""

    escaped: bool = False
    """True once the escape reflex has fired and the fly is ballistic."""

    done: bool = False
    """True when the episode has ended (time limit, capture, or successful getaway)."""

    raw: dict[str, Any] = field(default_factory=dict)
    """Environment-specific extras. A 3D env puts its camera buffer here."""


@dataclass(frozen=True)
class SensoryPacket:
    """Injected current for every neuron in the brain, in picoamps.

    This is the narrowest seam in the system and the most important one. The brain
    receives a flat ``(N,)`` current vector and nothing else — no coordinates, no
    distances, no notion that a predator exists. Any environment that can be reduced to
    "how much current does each neuron receive right now" can drive this brain.
    """

    t: float
    """Environment time in **seconds** (matches the observation that produced it)."""

    currents: np.ndarray
    """Shape ``(N,)`` float32, picoamps. Index ``i`` is neuron ``i``'s external drive."""

    raw: dict[str, Any] = field(default_factory=dict)
    """Diagnostics for plotting/logging (looming value, angular size, theta_dot).

    Nothing in the brain may read this. It exists so the dashboard can show *why* the
    current has the value it does without the encoder having to log separately.
    """


@dataclass(frozen=True)
class BrainState:
    """Snapshot of the neural simulation after one integration step."""

    t_ms: float
    """Brain time in **milliseconds** since reset."""

    voltages: np.ndarray
    """Shape ``(N,)`` float32, membrane potential in mV."""

    spikes: np.ndarray
    """Shape ``(N,)`` bool. True where the neuron crossed threshold on *this* step."""

    synaptic_current: np.ndarray
    """Shape ``(N,)`` float32, pA arriving from other neurons in the network."""

    spike_counts: np.ndarray
    """Shape ``(N,)`` int32, cumulative spike count since reset."""


@dataclass(frozen=True)
class MotorCommand:
    """Decoded motor output, consumed by the environment.

    Like :class:`SensoryPacket`, this is deliberately abstract: ``heading`` and
    ``impulse`` describe an intent that a 2D point-mass, a MuJoCo model, or a Minecraft
    entity can each interpret in their own terms.
    """

    t: float
    """Environment time in **seconds**."""

    escape: bool
    """True on and after the step where the Giant Fiber fired."""

    triggered_now: bool = False
    """True only on the single step where a takeoff first latched (edge, not level)."""

    redirect: bool = False
    """True when the escape command arrived while the agent is ALREADY escaping.

    A body cannot start a jump with no legs on the ground, but it can steer once airborne
    — banked turns mid-escape-flight are real. Separating the two lets a Giant Fiber spike
    during flight change course instead of either relaunching the fly (which produced
    hundreds of takeoffs a second) or being discarded (which left it unresponsive for the
    whole ~1.2 s flight, ignoring a threat in its face).
    """

    heading: np.ndarray | None = None
    """Unit vector of the intended takeoff direction, shape ``(D,)``. None until escape."""

    impulse: float = 0.0
    """Takeoff speed in m/s to apply along ``heading``."""

    raw: dict[str, Any] = field(default_factory=dict)
    """Decoder diagnostics (GF spike time, latency) for logging and display."""
