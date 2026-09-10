# System Architecture Plan

How the Starter Phase's decoupled I/O becomes a 3D game hook, a network socket, or a
physics engine **without touching the LIF engine**.

---

## 1. The seam

Four abstract classes, four dataclasses. That is the whole architecture.

```
   ┌─────────────────┐   EnvObservation   ┌──────────────────┐
   │ BaseEnvironment │ ─────────────────> │ BaseSensory      │
   │                 │                    │ Encoder          │
   │  2D arena       │                    │                  │
   │  MuJoCo         │                    │  looming -> pA   │
   │  Minecraft      │                    │  retina  -> pA   │
   │  socket bridge  │                    │  wind    -> pA   │
   └─────────────────┘                    └──────────────────┘
          ▲                                        │
          │                                        │ SensoryPacket
          │ MotorCommand                           │  (currents, pA)
          │                                        ▼
   ┌─────────────────┐    BrainState      ┌──────────────────┐
   │ BaseMotor       │ <───────────────── │ BaseBrain        │
   │ Decoder         │                    │                  │
   │                 │                    │  LIFBrain        │
   │  GF -> takeoff  │                    │  TorchLIFBrain   │
   │  wing torques   │                    │  Brian2 backend  │
   └─────────────────┘                    └──────────────────┘
```

**The brain's entire contract is `np.ndarray[N] -> BrainState`.** It has never heard of a
coordinate, a pixel, a socket, or a frame rate. That is not an accident of the current
implementation — it is enforced by an import rule (see CLAUDE.md):

* `flysim/brain/` may not import `envs/`, `interfaces/`, or `viz/`
* `flysim/envs/` may not import `brain/`
* only `runner.py` and `main.py` know about more than one layer

You can verify it holds at any time:

```powershell
python -c "from flysim.brain.lif import LIFBrain; import sys; print('matplotlib' in sys.modules)"
# -> False
```

---

## 2. Swapping the environment

### 2a. MuJoCo

```python
import mujoco
import numpy as np
from flysim.core.base import BaseEnvironment
from flysim.core.types import EnvObservation, MotorCommand

class MuJoCoFlyEnvironment(BaseEnvironment):
    def __init__(self, model_path: str):
        self.model = mujoco.MjModel.from_xml_path(model_path)
        self.data = mujoco.MjData(self.model)
        self._fly = self.model.body("fly").id
        self._threat = self.model.body("threat").id

    @property
    def bounds(self) -> np.ndarray:
        return np.array([[-1, 1], [-1, 1], [0, 1]])   # 3D: the pipeline already handles D>2

    def reset(self) -> EnvObservation:
        mujoco.mj_resetData(self.model, self.data)
        return self._observe()

    def step(self, command: MotorCommand, dt_s: float) -> EnvObservation:
        if command.triggered_now and command.heading is not None:
            # The command is an intent; MuJoCo interprets it with real physics.
            self.data.xfrc_applied[self._fly, :3] = command.heading * command.impulse * MASS
        for _ in range(int(dt_s / self.model.opt.timestep)):
            mujoco.mj_step(self.model, self.data)
        return self._observe()
```

Note what did **not** change: `LIFBrain`, `GiantFiberDecoder`, `SimulationRunner`, the
dashboard's telemetry panel. `EnvObservation` positions are already `(D,)` arrays, so
3D vectors flow through unmodified. Only the *spatial* panel of the dashboard needs a 3D
projection, and that is a visualisation concern, not a simulation one.

### 2b. Minecraft / any game engine

Game engines are a separate *process*, so the environment becomes a client:

```python
class MinecraftEnvironment(BaseEnvironment):
    """Talks to a Fabric/Forge mod or an RCON-style bridge over a socket."""

    def step(self, command: MotorCommand, dt_s: float) -> EnvObservation:
        if command.triggered_now:
            self._send({"op": "impulse",
                        "vec": command.heading.tolist(),
                        "speed": command.impulse})
        state = self._request({"op": "observe"})
        return EnvObservation(
            t=state["tick"] / 20.0,           # Minecraft runs at 20 ticks/s
            step_index=state["tick"],
            agent_position=np.array(state["fly"]["pos"]),
            agent_velocity=np.array(state["fly"]["vel"]),
            threat_position=np.array(state["mob"]["pos"]),
            threat_velocity=np.array(state["mob"]["vel"]),
            distance=state["distance"],
            closing_speed=state["closing"],
            threat_size=state["mob"]["width"],
            raw={"blocks": state.get("nearby_blocks")},   # richer payload rides here
        )
```

**The timing problem this creates, and how to handle it.** A game engine runs on its own
clock (Minecraft: 20 Hz) which is far coarser than the brain's 0.1 ms timestep. Three
options, in order of preference:

1. **Brain-authoritative (recommended for science).** The game is stepped by the runner,
   as here. Real time is irrelevant; you get reproducible results. Use this for
   experiments.
2. **Game-authoritative with catch-up.** The game free-runs and the brain integrates as
   many substeps as have accumulated since the last frame. Real-time, but results depend
   on machine load — never publish numbers from this mode.
3. **Decoupled with interpolation.** Brain in its own thread at a fixed rate, game reading
   the latest `MotorCommand` and the brain reading the latest `EnvObservation`. Lowest
   latency, hardest to reason about.

The current `SimulationRunner` implements (1). Implementing (2) is a change to the runner
only — again, not to the brain.

### 2c. Network socket as a general bridge

Because the boundary types are small and flat, a generic remote environment is short:

```python
class RemoteEnvironment(BaseEnvironment):
    """Proxies any external simulator that speaks JSON over a socket."""
    def step(self, command, dt_s):
        self._sock.sendall(json.dumps({
            "escape": command.escape,
            "triggered": command.triggered_now,
            "heading": None if command.heading is None else command.heading.tolist(),
            "impulse": command.impulse,
            "dt": dt_s,
        }).encode() + b"\n")
        return _observation_from_json(self._readline())
```

`MotorCommand` is four scalars and a short vector. It fits in a UDP datagram. This is why
the boundary types were kept deliberately narrow.

---

## 3. Swapping the sensory layer

The 2D encoder collapses the world to one scalar (distance) before encoding. A 3D
environment gives you an image, and the encoder is where that becomes current:

```python
class RetinalEncoder(BaseSensoryEncoder):
    """Per-ommatidium contrast -> LC4 current, for an environment that renders."""

    def encode(self, obs, n_neurons):
        frame = obs.raw["retina"]                       # (H, W) luminance
        # Temporal derivative is the actual looming cue: LC neurons respond to expanding
        # edges, not to static size.
        dI = (frame - self._previous) / max(obs.t - self._t_prev, 1e-6)
        self._previous, self._t_prev = frame, obs.t

        # Each LC4 pools a retinotopic patch — its receptive field.
        drive = np.array([dI[sl].clip(0).mean() for sl in self._receptive_fields])

        currents = np.zeros(n_neurons, dtype=np.float32)
        currents[self._lc4] = np.clip(drive * self._gain, 0, self._ceiling)
        return SensoryPacket(t=obs.t, currents=currents, raw={"mean_dI": float(dI.mean())})
```

The existing `LoomingEncoder` already computes and reports `theta` and `theta_dot` in
`SensoryPacket.raw`, so the transition from "exponential proxy" to "genuine expansion
rate" is a one-line change *inside the encoder* and invisible everywhere else.

---

## 4. Swapping the brain

`LIFBrain` is one implementation of `BaseBrain`. Alternatives that would drop in:

| Backend | When | Change required |
|---|---|---|
| `TorchLIFBrain` | Batched trials, GPU, differentiable | New class, same interface |
| Brian2 / GeNN | Published, validated neuron models | Adapter class |
| Multi-compartment | Dendritic integration in GF | New class + richer `Connectome` |

The scale change — 12 neurons to 139,000 — needs **no** code change at all: the engine
already does `spikes @ weights`, which is identical for a dense NumPy array and a SciPy
CSR matrix, and every parameter is already a per-neuron vector rather than a scalar.
`python main.py --benchmark 139255` exercises exactly that path today.

---

## 5. What has to change, honestly

Not everything is free. When you move to 3D and real data:

| Concern | Status |
|---|---|
| Positions in 3D | **already works** — `(D,)` arrays throughout |
| Sparse connectome | **already works** — `spikes @ W` is representation-agnostic |
| Heterogeneous neuron params | **already works** — per-neuron vectors + population overrides |
| Panel A rendering in 3D | **needs work** — 2D axes; swap for a 3D projection or a game-side view |
| Per-population axonal delays | **needs work** — one shared delay ring buffer today; the engine raises a clear error if you try |
| Real-time execution | **needs work** — see §2b, and expect ~2.7 min per simulated second at full FAFB scale |
| Synapse count → picoamps | **unsolved, and not a coding problem** — see CONNECTOME_ACCESS.md §5 |

The last row is the real one. The architecture will happily carry 139,000 neurons; whether
the resulting spike trains mean anything depends on physiological calibration that no
amount of software design supplies.

---

## 6. Suggested build order

1. **Now** — Starter Phase runs; `--check` passes; `synthetic120` proves the seam.
2. **Next** — FlyWire Codex bulk CSV → `Connectome` via the loader in
   CONNECTOME_ACCESS.md §5. Extract the real LC4 + LPLC2 → DNp01 subnetwork (a few hundred
   neurons) and run it through the *unchanged* 2D environment. This is the highest-value
   step: real anatomy, small enough to interrogate, same dashboard.
3. **Then** — whole-brain sparse run, headless, with `--benchmark`-style profiling.
4. **Then** — swap the environment for MuJoCo; keep the 2D env as a regression baseline.
5. **Later** — batched GPU backend for parameter sweeps and calibration.

Keep step 2's subnetwork around permanently as an integration test. It is small enough to
run in seconds and real enough to catch mistakes that the mock cannot.

---

## 7. Project conventions

These are the rules the codebase is written against. They are not style preferences —
breaking them causes real bugs, and each one is here because it already has.

### Units (do not mix)

| Quantity | Unit | Notes |
|---|---|---|
| Membrane voltage | mV | |
| Current | pA | |
| Membrane resistance | GΩ | 1 pA × 1 GΩ = 1 mV |
| Time constants, delays | ms | `dt_ms` everywhere inside `flysim/brain/` |
| Synaptic weight | pA per presynaptic spike | instantaneous jump, then decays with `tau_syn` |
| Environment time | **s** | `EnvObservation.t` is the only seconds-valued time |
| Position, distance | m | |
| Anatomical coordinates | µm | converted from the source's nanometres on load |

`EnvObservation.t` is in **seconds**; everything inside `flysim/brain/` is in
**milliseconds**. The conversion happens exactly once, in `SimulationRunner`.

### Verification

```powershell
python main.py --check                            # acceptance test, exit code
python main.py --connectome synthetic120 --check  # seam test: no source edits allowed
python main.py --connectome flywire --check       # the same gate on REAL data
python -c "from flysim.brain.lif import LIFBrain" # decoupling smoke test
```

**Run the real-connectome check, not just the mock.** Switching real connectomes to
uniform published parameters once removed the Giant Fiber's long refractory period and let
it fire at 455 Hz, producing 415 takeoffs in 20 seconds of interactive play — while every
mock-only check still passed, because the mock keeps its own biophysics. Any change
affecting real connectomes is untested until it has been run against real data.

### Data location

Connectome caches must live **outside the repository**, pointed at by `FLYSIM_CACHE_DIR`.
They run to hundreds of megabytes; `.gitignore` covers the extensions as a backstop, but
the real protection is keeping the cache root elsewhere entirely.

### Comments

Comments explain the **neuroscience** and the **why**, never the edit history.

* Good: `# Exponential Euler: exact for constant I over dt, unconditionally stable.`
* Good: `# LC4 also synapses directly onto GF dendrites; this layer is a simplification.`
* Bad: `# NEW:`, `# Phase 2 fix`, `# updated per feedback`

Where the model departs from biology, **say so in the comment**. Do not present a
simplification as ground truth — that is how a model quietly becomes a claim.
