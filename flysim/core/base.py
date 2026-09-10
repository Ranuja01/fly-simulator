"""Abstract interfaces for every swappable layer.

Four ABCs, one per stage of the loop. A concrete implementation of each is all the
:class:`~flysim.runner.SimulationRunner` needs; it has no idea whether the environment is
a 2D point-mass or a physics engine, or whether the brain is a 12-neuron mock or 140,000
real FlyWire nodes.

Import rule (enforced by convention, documented in CLAUDE.md): this module imports only
from :mod:`flysim.core.types`. Nothing here may reference a concrete environment, brain,
encoder, decoder, or the visualisation layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

import numpy as np

from flysim.core.types import BrainState, EnvObservation, MotorCommand, SensoryPacket


class BaseEnvironment(ABC):
    """A world the fly lives in.

    Implement this to swap the 2D arena for MuJoCo, Minecraft, or a socket bridge to an
    external simulator. The contract is intentionally tiny:

    * :meth:`reset` returns the first observation.
    * :meth:`step` advances the world by ``dt_s`` under a motor command.
    * :attr:`bounds` tells the visualiser how big the world is.

    A networked environment implements ``step`` as a request/response over the wire; a
    physics environment implements it as ``mj_step``. Neither changes anything upstream.
    """

    @property
    @abstractmethod
    def bounds(self) -> np.ndarray:
        """Axis-aligned world extent, shape ``(D, 2)`` as ``[[xmin, xmax], ...]``, metres."""

    @abstractmethod
    def reset(self) -> EnvObservation:
        """Return the world to its initial state and emit the first observation."""

    @abstractmethod
    def step(self, command: MotorCommand, dt_s: float) -> EnvObservation:
        """Advance the world by ``dt_s`` seconds, applying ``command``."""


class BaseBrain(ABC):
    """A neural simulator.

    Takes a current vector in, gives a state out. That is the entire interface, which is
    what allows a 12-neuron dense NumPy matrix and a 140k-neuron sparse CSR connectome to
    be interchangeable — and what would allow a Brian2 or GeNN backend to be dropped in
    without touching the environment or the dashboard.
    """

    @property
    @abstractmethod
    def size(self) -> int:
        """Number of neurons, ``N``."""

    @property
    @abstractmethod
    def populations(self) -> Mapping[str, np.ndarray]:
        """Named neuron groups, e.g. ``{"LC4": array([0, 1, 2, ...]), "GF": array([9])}``.

        The decoder and the dashboard address neurons by *population name*, never by raw
        index, so a connectome swap that renumbers everything is harmless.
        """

    @property
    @abstractmethod
    def labels(self) -> Sequence[str]:
        """Per-neuron human-readable names, length ``N``."""

    @abstractmethod
    def reset(self) -> None:
        """Return all state variables to rest."""

    @abstractmethod
    def step(self, currents_pa: np.ndarray) -> BrainState:
        """Integrate one timestep given external input current in pA, shape ``(N,)``."""


class BaseSensoryEncoder(ABC):
    """Translates world state into injected current.

    This is where the modality lives. The 2D starter turns a scalar distance into a
    looming drive; a 3D version would turn a rendered retinal image into per-ommatidium
    contrast and then into LC4 current. Both emit the same :class:`SensoryPacket`, so the
    brain cannot tell them apart.
    """

    @abstractmethod
    def reset(self) -> None:
        """Clear any internal temporal state (previous frame, adaptation, filters)."""

    @abstractmethod
    def encode(self, obs: EnvObservation, n_neurons: int) -> SensoryPacket:
        """Produce an ``(N,)`` pA current vector from one world observation."""


class BaseMotorDecoder(ABC):
    """Translates spiking activity into a motor command.

    The starter watches one Giant Fiber neuron for an all-or-none takeoff. A richer
    version would read a wing-steering population and emit continuous torques — same
    interface, same :class:`MotorCommand` out.
    """

    @abstractmethod
    def reset(self) -> None:
        """Clear latched state (e.g. "escape has already fired")."""

    @abstractmethod
    def decode(self, state: BrainState, obs: EnvObservation) -> MotorCommand:
        """Produce a motor command from the current brain state.

        ``obs`` is supplied because a motor command is inherently *embodied* — an escape
        direction is only meaningful relative to where the threat is. The decoder is the
        correct place for that coupling; the brain itself stays coordinate-free.
        """
