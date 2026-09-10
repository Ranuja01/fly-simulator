# Data & Compute Specifications

What it actually costs to go from a 12-neuron mock to the full adult *Drosophila*
connectome, and how to lay the project out so you do not fight your own tooling.

Numbers marked **(measured)** were produced on this machine by `python main.py --benchmark`.
Numbers marked **(estimate)** are order-of-magnitude and will drift as datasets are
re-released — verify before provisioning hardware.

---

## 1. The one number that decides your architecture

The full FlyWire adult brain (**FAFB v783**, as Codex reports it) contains **139,255
proofread neurons** and **3,732,460 connections**.

A dense adjacency matrix at that scale:

| Representation | Size | Verdict |
|---|---|---|
| `float32[139255, 139255]` | **72.2 GiB** (77.6 GB) | Impossible on any workstation |
| `float16` | 36.1 GiB | Still impossible |
| `int8` synapse counts | 18.0 GiB | Technically loadable on a 64 GB box; still wrong |

A sparse matrix of the same connectome:

| Component | Size |
|---|---|
| `data` float32 × 3.73M | 14.9 MB |
| `indices` int32 × 3.73M | 14.9 MB |
| `indptr` int32 × 139k | 0.6 MB |
| **CSR total** | **~29 MB** |

**A ~2,500× difference.** The entire wiring diagram of a fly brain fits in less memory
than a photograph. This is why `Connectome.weights` accepts either a dense NumPy array or
a SciPy sparse matrix, and why `LIFBrain` only ever does `spikes @ weights` — an operation
with identical semantics for both.

This is not a projection. A network built at exactly FAFB v783's shape reports
**(measured, this machine)**:

```
edges          : 3,759,538
sparse weights :     29.2 MiB
dense would be :     72.2 GiB   <- why we do not do this
ratio          :     2532x
```

Reproduce with `python main.py --benchmark 139255` (which uses a slightly lower default
degree; pass `avg_degree=27` to `build_benchmark` for FAFB's actual density).

### Simulation state is not the problem either

Every per-neuron state vector is `float32[139255]` = **557 KB**. The engine holds about a
dozen (voltage, synaptic current, thresholds, time constants, refractory counters, …), so
**whole-brain state is ~7 MB**. Plus the delay ring buffer: `bool[delay_steps, N]`, which
at 1 ms delay and 0.1 ms timestep is `10 × 139255` = 1.4 MB.

**Whole-brain LIF fits comfortably in under 100 MB of RAM.** Memory is not what stops you.

---

## 2. What actually stops you: time, and raw synapse tables

### Throughput

Three measurements, pure NumPy on CPU, single-threaded **(measured, this machine)**:

| Scale | Edges | ms/step |
|---|---|---|
| 50,000 neurons | 950k | 2.0 |
| 139,255 neurons | 2.65M | 6.5 |
| **139,255 neurons (FAFB v783 density)** | **3.76M** | **16.1** |

Note that this is **superlinear**: 1.4× the edges costs 2.5× the time. A sparse
matrix-vector product at this size stops fitting in cache, so each additional edge is
increasingly likely to be a random DRAM access. Do not extrapolate the small-scale numbers
linearly — measure at the scale you actually intend to run.

At `dt = 0.1 ms`, one second of simulated brain time is 10,000 steps:

> **~160 seconds of wall clock per second of simulated fly time** at full FAFB scale,
> single-threaded NumPy.

That is fine for single trials and hopeless for parameter sweeps. See §5 for when a GPU
starts paying for itself.

Two ways to buy time back before reaching for hardware: raise `dt` toward the stability
limit the engine enforces (it uses exponential Euler, so it stays stable — but spike
timing degrades, and the engine will refuse a `dt` above half the fastest time constant),
or simulate a *subnetwork* rather than the whole brain. The second is almost always the
right answer; see ARCHITECTURE.md §6.

### Raw synapse tables

The aggregated *connection* table is small. The per-*synapse* table — one row per synapse
with 3D coordinates, cleft scores, and neurotransmitter predictions — is not:

| Artifact | Size | Notes |
|---|---|---|
| Aggregated connections (≥5 syn) | ~100–300 MB **(estimate)** | This is what you want 95% of the time |
| Neuron annotations / classification | ~20–80 MB **(estimate)** | Types, sides, super-classes |
| Full per-synapse table (~54M rows) | **tens of GB** **(estimate)** | Only for spatial/compartment analysis |
| Skeletons (SWC, via `navis`) | single-digit GB **(estimate)** | Morphology, NBLAST |
| Meshes | **100+ GB** **(estimate)** | The real disk hog. Cache selectively |

**Rule: never load a per-synapse table with a text editor, a notebook cell that prints it,
or an agent's file-read tool.** Query it, filter it server-side, aggregate, then persist
the small result as Parquet.

---

## 3. Recommended hardware

| Task | RAM | Disk | GPU |
|---|---|---|---|
| Starter Phase (this repo) | 2 GB | 5 MB | none |
| Whole-brain connectivity + sparse LIF | 8 GB | 2 GB | none |
| Per-synapse analysis in pandas | **32–64 GB** | 100 GB | none |
| Morphology / meshes / NBLAST | 32 GB | **200+ GB** | none |
| Large parameter sweeps, batched trials | 16 GB | 20 GB | **useful** |

The RAM jump for per-synapse work is not about the file size — it is that pandas joins and
sorts on a 54M-row frame transiently allocate several multiples of the frame.

**This machine:** `C:\` has ~58 GB free and is OneDrive-synced. `E:\` has ~336 GB free and
is not. Everything below follows from that.

---

## 4. Directory layout

### The repo — small, versioned, synced

```
Fly Simulator/
├── main.py                        # entry point + CLI; the only wiring diagram
├── CLAUDE.md                      # agent/contributor rules (import rules, data rules)
├── README.md
├── requirements-starter.txt       # numpy, matplotlib  <- Starter Phase needs only this
├── requirements-connectome.txt    # neuprint-python, caveclient, fafbseg, navis
├── .gitignore                     # excludes data/, cache/, outputs/
├── .vscode/
│   └── settings.json              # watcher/search/index excludes (see note below)
├── configs/
│   └── starter_2d.json            # partial overrides; defaults live in flysim/config.py
├── docs/
│   ├── COMPUTE_BUDGET.md          # this file
│   ├── CONNECTOME_ACCESS.md       # tokens, queries, LC4->GF extraction
│   └── ARCHITECTURE.md            # how 2D becomes MuJoCo/Minecraft/sockets
├── outputs/                       # git-ignored renders (.mp4/.gif)
└── flysim/
    ├── __init__.py
    ├── config.py                  # every tunable number, frozen dataclasses
    ├── core/
    │   ├── types.py               # the 4 boundary dataclasses
    │   └── base.py                # BaseEnvironment / BaseBrain / encoder / decoder ABCs
    ├── brain/
    │   ├── connectome.py          # Connectome container + the circuit rule table
    │   ├── builders.py            # mock12 / synthetic120 / benchmark  (+ real loaders)
    │   └── lif.py                 # the vectorized LIF engine
    ├── envs/
    │   └── predator2d.py          # 2D arena          (+ mujoco.py, minecraft.py later)
    ├── interfaces/
    │   ├── sensory.py             # looming -> current
    │   └── motor.py               # GF spike -> takeoff
    ├── viz/
    │   └── dashboard.py           # the two-panel live figure
    └── runner.py                  # the substep loop; owns the s <-> ms conversion
```

### The cache — large, unversioned, NOT synced

**This must not live inside the repo.** OneDrive has previously burned ~237,000
CPU-seconds on this machine syncing generated files.

```
E:\FlyConnectome\
└── cache\
    ├── neuprint\
    │   ├── hemibrain_v1.2.1\
    │   │   ├── neurons.parquet          # annotations, one row per body
    │   │   └── adjacency.parquet        # bodyId_pre, bodyId_post, weight
    │   └── malecns_v1.0\
    ├── flywire\
    │   └── v783\
    │       ├── connections.parquet      # the ~2.7M-edge aggregated table
    │       ├── classification.parquet   # cell type / side / super class
    │       └── synapses\                # per-synapse shards, only if you need them
    ├── skeletons\                       # navis SWC, fetched on demand
    └── derived\
        └── lc4_gf_subnetwork.npz        # extracted circuits, ready for Connectome()
```

Point the code at it with an environment variable so no path is ever hardcoded:

```powershell
setx FLYSIM_CACHE_DIR "E:\FlyConnectome\cache"
```

```python
import os
from pathlib import Path
CACHE = Path(os.environ.get("FLYSIM_CACHE_DIR", Path.home() / ".flysim-cache"))
```

### VS Code indexing

Large generated trees will make the language server balloon. `.vscode/settings.json` in
this repo already sets `python.analysis.indexing: false` plus `files.watcherExclude` and
`search.exclude` for `data/`, `cache/`, `outputs/`, and `__pycache__/`. If you add a new
generated directory, add it there too.

---

## 5. When a GPU is worth it

Not for a single whole-brain sparse LIF run — a 2.7M-edge sparse matrix-vector product is
memory-bandwidth-bound and small, and kernel launch overhead at `dt = 0.1 ms` eats the
gain.

A GPU pays for itself when:

1. **You batch trials.** Turning the state vectors into `[batch, N]` matrices makes the
   SpMV a sparse matrix-*matrix* product, which is exactly what GPUs are for. 256 parallel
   trials for barely more than the cost of one.
2. **The neuron model gets expensive.** Conductance-based synapses, multiple compartments,
   or Hodgkin-Huxley channels shift the cost from the sparse product to dense per-neuron
   arithmetic, which parallelises perfectly.
3. **You are fitting parameters.** Gradient-based tuning over a differentiable surrogate
   spiking model is a training workload.

`torch` is already installed on this machine. The migration path is small precisely
because of the seam: `LIFBrain` would be joined by a `TorchLIFBrain` implementing the same
`BaseBrain` interface, and nothing else in the package would change.

---

## 6. Sanity checks you can run right now

```powershell
python main.py --benchmark 50000     # sparse vs dense, measured
python main.py --benchmark 139255    # full FlyWire scale (needs SciPy)
```

The second is the honest test of everything claimed above — it is where the 20.7 MiB,
72.2 GiB and 6.5 ms/step figures in §1 and §2 come from. It completes in a few seconds and
needs no downloaded data, because the point being tested is the *engine's* scaling, not
the biology.
