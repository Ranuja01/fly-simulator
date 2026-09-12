# Model Journal

Why this model is the way it is.

The other documents describe *what* the system does. This one records the decisions that
shaped it: what was measured, what was chosen, what was rejected, and what remains blocked.
It exists because almost every interesting choice here is a judgement about **where the
biology ends and the simulation's invention begins**, and those judgements are invisible in
the code once made.

Entries are added as decisions are taken. Numbers are measured on this machine unless
marked otherwise; where a decision rests on evidence, the evidence is given so it can be
argued with rather than taken on trust.

---

## 0. The target, and how we know when a step is done

Added after a session in which the work wandered from the escape reflex into walking,
proprioception, body models and jump aiming — none of them in scope — because **there was
no definition of done**. Every measurement opened a direction, and with nothing to check a
direction against, each looked as reasonable as the last.

### The scope

**Sight-based predator escape, recreated faithfully.** Not a whole fly. Once this is done
it becomes the template for a second modality.

### What "faithfully" means

Real escape has published, measurable properties. The model is faithful to the degree it
reproduces them. Sourcing is marked, because several values come from another group's
write-up rather than from primary literature we have read.

| measured fact | source | model | status |
|---|---|---|---|
| LC4+LPLC2 is ~30% of giant-fiber input | independently verified, 29.85% theirs / 31.3% ours | 31.3% | **pass** |
| one GF spike, one takeoff, all-or-none | established | holds | **pass** |
| faster looms trigger earlier | established | 37 -> 115 mm across 0.1 -> 2 m/s | **pass** |
| silencing LC4 *and* LPLC2 abolishes the escape | established | no takeoff, fly captured | **pass** |
| silencing LPLC2 nearly abolishes it | established | degrades 16.7 -> 31.8 deg only | **partial** |
| TTM fires 0.93 ms after the giant fiber | their page, cited as measured | 5.7 ms | **fail, 6x** |
| DLM fires 1.44 ms after the giant fiber | their page, cited as measured | ~12 ms | **fail, 8x** |
| short takeoff completes under 6.87 ms | their page | not measured | **unknown** |
| GF-mediated takeoff threshold ~39 deg angular size | von Reyn et al. 2014 | 16.7 deg | **fail, 2.3x early** |
| GF response peaks at 42 deg angular size | Ache et al. 2019 | no size channel exists | **fail** |
| **LC4 encodes looming SPEED; LPLC2 encodes angular SIZE** | Ache et al. 2019 | both driven identically | **fail — mechanism** |
| LC4:LPLC2 synapse ratio onto GF | 1.79 (Ache et al.) | 1.32 | **consistent** |
| escape direction is away from the threat | established | scripted geometry | **not neural** |
| direction is set by pre-takeoff leg posture | established | absent, and out of reach | **out of scope** |

Anything not on this list needs an argument before it is worked on. The propagation problem,
the ventral nerve cord, the aiming circuit and a physics body are all off it.

### Step B, run: verify the angular threshold

**Subgoal:** establish what our 16.7 deg actually is, find the corresponding published
quantity, and confirm the match or record the discrepancy.

**Result: failed, and the failure is informative.** Our figure is the angular size at
takeoff dispatch. The published quantity is the GF-mediated takeoff threshold, **~39 deg**
(von Reyn et al. 2014), with the GF response peaking at **42 deg** (Ache et al. 2019). Our
fly escapes at less than half the angular size a real one does.

**The mechanism error matters more than the number.** From Ache et al. 2019: *"LPLC2 input
to the giant fiber encodes the angular size of an approaching object, whereas LC4 input
directly encodes looming speed."* The GF response is modelled there as a linear function of
angular velocity from LC4 **plus a Gaussian function of angular size from LPLC2**, peaking
near 42 deg.

We drive both populations identically, with one expansion-rate signal. **We have been
treating two different feature detectors as one, and we have no size channel at all.**

That also explains the partial lesion result. Silencing LPLC2 is published to remove the
*size* component and leave velocity intact. Our model has no size component, so silencing
LPLC2 merely removes generic drive — degrading the threshold from 16.7 to 31.8 deg rather
than deleting a feature.

Anatomy is consistent across datasets: LC4:LPLC2 synapses onto the giant fiber are 1.32 here
against 1.79 in Ache et al., both with LC4 contributing more synapses from fewer cells.

**Sourcing caveat:** these values come from search results quoting the papers, not from the
papers read in full. The two independent figures agreeing (39 and 42 deg) and the anatomy
matching give reasonable confidence, but a primary read should confirm the Gaussian's width
before it is implemented.

### How a step is run

Before starting, write down three things:

1. **The subgoal**, in one sentence.
2. **The done-criterion** — a number or a comparison that can fail.
3. **What could make the measurement lie**, listed before the measurement is taken. Today's
   errors were all cases where this list was written afterwards, or not at all.

Then do the work, then check the criterion. If the criterion cannot be stated, the step is
not ready to start.

### How this project is built

Ground up, in small steps, each understood before the next. Not by delegating to agents and
accepting output — an external audit is a check on our work, not a substitute for it. The
value here is the documented understanding, not the volume of code.

## 1. The rule

**Measured beats invented, and invention must be labelled.**

A connectome gives anatomy, not physiology. Several numbers must be supplied from outside
it, and every one is a place where the model could quietly start doing the work the biology
is supposed to do. So:

* Anything not derived from the data is named, defaulted visibly, and justified.
* When a behaviour looks wrong, the first question is whether the *wiring* produces it or
  whether a constant does.
* **Do not fake it.** Adding plausible-looking noise to make output seem lifelike would
  improve the demo and destroy the point.

How far that rule actually holds is measured in §3.7, not asserted. An earlier version of
this document claimed the shuffle control showed "the escape vanishes entirely" against
"229 real LC4→DNp01 connections against 0". **That claim was never implemented, could not
be reproduced by a reader, and is wrong.** When the experiment was finally written
(`tools/shuffle_control.py`) it produced a more interesting and much less flattering
result.

---

## 2. Where the model stands

**A male fly's brain decides *when* to escape and fires the muscles that perform it.
Everything downstream of the muscles is scripted.**

| | source |
|---|---|
| when the escape fires | **neurons** — emergent from measured wiring |
| the ~15° angular threshold | **neurons** |
| discrimination of approach speed | **neurons** |
| takeoff trigger (CNS datasets) | **neurons** — read at TTMn |
| flight versus a bare hop | **neurons** — read at DLMn |
| seeing an object sweep past (`--motion`) | **neurons** — T4/T5 |
| escape *direction* | scripted — geometric, away from the threat |
| jump speed, flight duration, hop decay | scripted constants |
| all walking | scripted; no locomotor circuit is modelled |

### The map: populations, motions, files

Kept here because it is the thing that goes stale fastest. Counts are for the male CNS at
`hops=1, max_neurons=25000`.

**Populations — what each one is and whether anything reads it.**

| population | cells | what it is | carries | status |
|---|---|---|---|---|
| `T4T5` | 6,790 | elementary motion detectors | sweep across the eye | silent unless `--motion` |
| `LC4` | 966 | visual projection (LC4, LPLC2, other `visual_projection`) | looming, and bearing under `--retinotopy` | driven by `LoomingEncoder` |
| `INH` | 3,688 | cells with an inhibitory transmitter | suppression, incl. lobula-plate opponency | emergent |
| `PMN` | 11,437 | everything not otherwise classified, incl. VNC premotor | fires under strong drive, silent in scripted episodes | partial |
| `DN` | 67 | descending neurons other than DNp01 | left/right at several pairs; front/back at DNp04 | measured, **not read** |
| `GF` | 2 | DNp01, the Giant Fiber | the escape command | read on brain-only datasets |
| `MOTOR` | 10 | TTMn and other non-flight motor cells | jump trigger, carries left/right | read by the decoder on CNS datasets |
| `FLIGHT` | 13 | DLMn, DVMn | wing power | read for powered-versus-hop |

**Motions — what produces each, and whether it is measured or invented.**

| motion | produced by | source |
|---|---|---|
| when the escape fires | LC4 → DN → GF → TTMn | **measured** |
| flight versus a bare hop | DLMn | **measured** |
| which side leads | hemifield tuning → DN → TTMn | **measured** |
| escape heading | geometry, away-vector + 42° bias | scripted |
| jump speed, flight duration, hop decay | constants in `EnvParams` | scripted |
| mid-flight steering | geometric `redirect` | scripted |
| all walking | `WalkingFly` | scripted |
| aiming the jump | `Sternotrochanter MN` | present, **never fires** |

**Files — which side of the boundary each sits on.**

| file | role |
|---|---|
| `flysim/core/types.py` | the four boundary dataclasses; the entire inter-layer contract |
| `flysim/envs/predator2d.py`, `interactive2d.py` | world → `EnvObservation` — **input source** |
| `flysim/interfaces/sensory.py` | `EnvObservation` → `SensoryPacket` — **input encoder** |
| `flysim/brain/neuprint_source.py`, `loaders.py`, `builders.py` | connectome files/API → `Connectome` |
| `flysim/brain/lif.py` | `SensoryPacket` → `BrainState` — the engine, imports nothing else |
| `flysim/interfaces/motor.py` | `BrainState` → `MotorCommand` — **output decoder** |
| `flysim/envs/locomotion.py` | `MotorCommand` → kinematics — **output actuation** |
| `flysim/runner.py` | the only module that sees more than one layer |
| `flysim/calibration.py` | per-dataset constants that the data cannot supply |
| `flysim/viz/dashboard.py` | display only; reads everything, drives nothing |

**Tools — each answers one question.**

| tool | question |
|---|---|
| `shuffle_control.py` | is the escape due to the wiring, given every wiring the same tuning budget? |
| `direction_control.py` | does the left/right flip survive shuffling the wiring? |
| `frontback_control.py` | does any descending pair separate front from rear? |
| `field_map.py` | is the azimuth map spatially coherent, or noise? |
| `calibrate_pa.py` | what picoamps-per-synapse discriminates a real approach from a drift? |

The escape pathway runs end to end on measured wiring:

```
DNp01 (Giant Fiber)  ->  PSI, TTMn  ->  DLMn
       1179.2 ms          1184.9 ms      1192.0 ms
```

---

## 2b. Inventory: what works, and how much of the brain is doing it

**How much of the network ever fires.** Four hard approaches from four bearings, counting
distinct neurons that spiked at least once:

| population | spiked | present | |
|---|---|---|---|
| `LC4` | 966 | 966 | 100% — but these are driven directly by the encoder |
| `GF` | 2 | 2 | 100% |
| `MOTOR` | 3 | 4 | 75% |
| `FLIGHT` | 5 | 14 | 36% |
| `DN` | 14 | 268 | 5% |
| `INH` | 8 | 5,476 | 0.1% |
| `PMN` | 5 | 14,275 | 0.03% |
| `POSTURE` | 0 | 137 | 0% |
| `T4T5` | 0 | 6,790 | 0% (silent without `--motion`) |
| **total** | **1,003** | **27,932** | **3.6%** |

Take away the 966 cells the encoder injects current into and **37 neurons downstream ever
fire**. That is the working brain. Everything else is anatomically present and
electrically silent.

**Behaviour, against what a real fly does in a flat arena.**

| behaviour | present? | driven by |
|---|---|---|
| decide when to escape | yes | **neurons** |
| discriminate approach speed | yes | **neurons** |
| tell left from right | yes | **neurons** |
| tell front from rear | at DNp04 only | **neurons**, unread |
| flight versus a bare hop | yes | **neurons** |
| aim the jump | no | circuit present, never fires |
| escape direction | yes | scripted geometry |
| steer in flight | yes | scripted geometry |
| walk, turn, stand, land | yes | scripted kinematics |
| spontaneity | yes | scripted RNG; a LIF cell at rest never spikes |
| optomotor turning | no | T4/T5 driven, no behavioural readout |
| groom | no | — |
| odour, wind, taste, light | no | no encoder for any of them |
| courtship, aggression | no | neurons largely outside the subgraph |
| learning | no | no plasticity in the engine |

**How close is this to a fly moving in 2D?** One reflex is genuinely neural at its decision
point, and its motor consequences are scripted. Everything the animal does between escapes
is kinematics. The gap is not mostly missing anatomy any more — the postural fetch showed
the full chain from eye to leg muscle is present and still does not conduct. The gap is
that drive does not survive more than a synapse or two, so a connectome with 27,932 cells
behaves like a twelve-neuron circuit with a large inert scaffold attached.

That single fact now blocks aiming, steering, walking and optomotor behaviour alike, which
makes it the most valuable thing to work on and the hardest.

**How short is it?** Peak depolarisation reached during one approach, against the 7 mV a
cell must cross from rest:

| population | reaches | |
|---|---|---|
| `DN` | 7.00 mV | fires |
| `PMN` | 7.00 mV | fires |
| `MOTOR` | 6.90 mV | fires |
| `POSTURE` | **1.33 mV** | 19% of threshold, short by 5.7 mV |

About fivefold, which is not hopeless. But the shortfall is not really per-synapse strength:
`DN` fires 14 of 268 cells, `PMN` 5 of 14,275, `POSTURE` 0 of 137. Each stage loses roughly
threefold in *active cells*, so by the leg muscles a cell has almost no simultaneously
active presynaptic partners to summate from. The failure is convergence, not gain.

**The cause is not biology, it is a calibration error, and it is mine.**

The postural motor neurons are not missing input. Checked against the full dataset, we hold
**100%** of their presynaptic partners and synapses: 133 partners, 3,108 synapses each. So
do the arithmetic at 1 GOhm, where 7 mV needs 7 pA held steady:

| cell | synapses | at 0.002 pA | |
|---|---|---|---|
| postural motor neuron | 3,108 | 6.22 pA | 89% of threshold — **can never fire** |
| typical descending neuron | 205 | 0.41 pA | 6% of threshold — **can never fire** |

That is with *every* input firing continuously. These cells are incapable of spiking under
any stimulus at this calibration.

`pa_per_synapse` is a physiological constant — how much current one synapse delivers — and
it was fitted to control a behavioural quantity, the angle at which the escape triggers.
Pushing it to 0.002 to stop the reflex being twitchy made the whole network electrically
dead, and the one pathway that mattered was then propped up by hand: GF->TTMn at 55 pA,
twenty-seven thousand times the uniform value. The model behaves like a twelve-neuron
circuit because that is what it is; the rest cannot fire by construction.

**That fix was predicted, tested, and failed.** The prediction was that raising
`pa_per_synapse` to a physiological value would let cells fire from their measured
convergence and largely dissolve the problem. Sustained 100 pA into every LC4 cell, 240 ms,
counting distinct cells that spiked:

| pA/synapse | cells fired | `POSTURE` | `PMN` of 14,275 | `DN` of 268 |
|---|---|---|---|---|
| 0.002 | ~1,003 | 0 | 5 | 14 |
| 0.007 | 1,108 | 0 | 49 | 29 |
| 0.020 | 1,281 | 0 | 116 | 55 |
| 0.050 | 1,684 | **6** | 269 | 81 |

Twenty-five times the synaptic strength buys 68% more active cells and six leg muscles of
137. The network does not become epileptic either — it stays almost exactly as dead.

The arithmetic above assumed *every* input firing at once. In reality a handful of
presynaptic cells are active, so the effective input is a small fraction of 3,108 synapses
however strong each one is. Multiplying a near-zero active fraction by a larger constant is
still near zero.

**So the corrected diagnosis is not calibration.** These cells are not silent because their
synapses are weak. They are silent because **they are not downstream of what we stimulate.**
The optic-lobe-to-escape pathway is a narrow chain. The premotor pool that drives the legs
is driven in a real animal by proprioception, by other descending pathways and by central
pattern generators, none of which this model supplies. It is "neurons present, input absent"
again, at the scale of the whole nerve cord.

Which means the leg muscles were never going to fire from a looming stimulus alone — nor,
arguably, would a real fly's, with its legs reporting nothing back.

## 2a. RETRACTION — the directional results were measured through a start-up artefact

An external audit found it and direct measurement confirmed it. Recorded at the top because
the affected claims were the project's headline results and were stated as verified.

**The artefact.** `InteractiveEnvironment.reset()` parks the threat in a corner at
(-0.495, -0.495). The measurement tools then call `set_threat_position` at the start
bearing on frame 0, and the length *and radial sign* of that jump depend on the bearing:

| bearing | jump | radial component | effect |
|---|---|---|---|
| front (0°), right (+90°) | 0.979 m | **-0.845** receding | no drive |
| rear (180°), left (-90°) | 0.516 m | **+0.145** approaching | a ~47 pA pulse |

So the four bearings split into two groups by where the threat happened to be parked, and
that split is exactly the pattern the results showed.

**Front/rear, retracted and re-measured.** The claimed +128 ms at DNp04, "reproducible
across five seeds", persists at **+138 ms with retinotopy switched OFF** — it was never
retinotopy. With a warm-up that lets every bearing start from rest:

| | DNp04 front - rear |
|---|---|
| warm-up, tuning **off** | +6 ms (all pairs inside noise) |
| warm-up, tuning **on** | **-42 ms** |

Front/rear is real, about a third the claimed size, and **in the opposite direction**: rear
is *slower*. Which is what the anatomy predicts — DNp04 draws less from a rear threat
(rear/front 0.87 and 0.73) — and what the artefact had inverted.

**Left/right, weakened.** Five repeats with the warm-up:

| wiring | threat right | threat left |
|---|---|---|
| measured | +76, +88, +96, +96, +100 (mean **+91**) | +60, -104, +64, +36, -96 (mean -8) |
| type-preserving shuffle | ~+5 | ~+18 |

A right-side threat reliably makes the right Giant Fiber lead, by ~91 ms against ~5 ms for
the shuffle — a genuine wiring-dependent effect, and it survives. "The sign flips with the
threat's side" is still wrong as stated; the clean -180/-208 was the pulse.

**"One-sided" was itself a metric artefact, though.** Raw first-spike times, five repeats:

| | left GF | right GF |
|---|---|---|
| threat right | 1108-1128 (tight) | 1028-1048 (tight) |
| threat left | **1104, 968, 1112, 1104, 964** | 1080-1096 (tight) |

The left Giant Fiber is **bimodal** on left-side threats — two clusters near 965 and 1108 —
and that bistability scrambles the between-GF difference. Comparing each cell against
*itself* across bearings is not confounded:

| | threat right | threat left | ipsilateral advantage |
|---|---|---|---|
| right GF | **1038** | 1088 | 50 ms earlier |
| left GF | 1120 | **~1035** | ~85 ms earlier |

Both Giant Fibers fire earlier for a threat on their own side. The directional response is
bilateral. Using a between-cell difference as the metric, when one cell is bistable, hid it
— the same shape of error as measuring along the wrong axis.

**The bimodality is real and unexplained.** The left GF sits at threshold during a left-side
approach and noise decides whether it crosses at 965 or 1108. Trial-to-trial variability at
a threshold is arguably realistic, real escape latencies being variable, but it is not
something this model was designed to produce and it should not be claimed as a feature.

**Why the left side has the advantage to begin with: wiring, not the encoder.** The encoder
is symmetric to three significant figures — a right-side threat delivers 19.66 / 56.10 pA to
the left and right eyes, a left-side threat 56.96 / 19.92. But left eye to left Giant Fiber
is 163 cells and 6,418 synapses, against 139 cells and 4,780 for the right: **34% more
convergence**. A right-side threat therefore has a structural handicap to overcome, and
does.

**The noise floor is also suspect**, since it was measured with the same protocol, and is
bearing-dependent for the same reason.

**Why it was missed.** This exact artefact was found and fixed earlier in the session — the
warm-up exists in the scratch probes for precisely this reason — and then not carried into
the tools written afterwards. The lesson in §6b is the right one and it was not applied.

## 2b0. A generic filter was deleting a declared pathway

Found by following up the audit's observation that `powered` looked like a laterality
readout. Measured by silencing each Giant Fiber in turn, on the scripted environment:

| | takeoffs | powered | FLIGHT substeps |
|---|---|---|---|
| intact | 1 | True | 5 |
| **left** GF silenced | 5 | **False x5** | **0** |
| right GF silenced | 1 | True | 5 |

`powered` depended entirely on the *left* Giant Fiber; silencing the right one changed
nothing. So "flight versus hop is read at the muscle" had quietly become "did the left GF
fire", and with hemifield tuning on a right-side threat could report an escape as a hop for
reasons unrelated to wings.

**The cause was our own weight floor.** Queried unfiltered, DNp01 -> PSI has four edges:

    DNp01_L -> PSI_L   9 synapses   kept
    DNp01_R -> PSI_L   3 synapses   discarded by min_synapses = 5
    DNp01_R -> PSI_R   2 synapses   discarded
    DNp01_L -> PSI_R   2 synapses   discarded

The pathway is fully bilateral in the reconstruction. A generic threshold kept the strongest
edge and deleted the rest, making the wing pathway unilateral. No anatomy was missing and
none needed inserting — the data was there and we filtered it out.

Connections named in `ELECTRICAL_SYNAPSES` and `SUPRATHRESHOLD_SYNAPSES` are now exempt from
the floor, on the same justification as the tables themselves: a pathway declared
load-bearing should not be removed by a rule that knows nothing about it. Three edges added;
the cache key carries an `r` so an older cache cannot be reused silently. Afterwards either
Giant Fiber engages the wings, wing activity triples, and the spurious hop-then-rejump loop
disappears. Only this one pair was affected — the other declared connections were all above
the floor.

**Generalisable:** a filter chosen for one purpose (keeping the graph sparse) silently
overrode a decision made for another (declaring specific pathways essential). Worth checking
wherever a global parameter and a specific exception coexist.

## 2c. Status by evidence, not by intent

Sorted by how much would have to be wrong for the claim to fail.

### Works, and is tested

| capability | evidence |
|---|---|
| escape timing and threshold | ~16.7 deg on neuprint, per-dataset profiles, `--check` on four connectomes |
| speed discrimination | detection distance rises 37 -> 61 -> 91 -> 115 mm across 0.1 -> 2 m/s; 0.05 m/s never fires |
| **left/right direction** | TTMn flips +70 vs -213 ms; **destroyed by the type-preserving shuffle**; field map spatially coherent (one eye lit, other at zero) |
| flight versus bare hop | read at DLMn; silencing PSI gives 21.5 cm against 50.0 cm and repeated short hops |
| efference copy | zero self-driven redirects after the fix, against two before, with the threat held at 0.0016 m/s |
| architecture and gates | four connectomes interchangeable behind one `Connectome`; `--check` catches commanded-but-unperformed takeoffs |

Of these, left/right is the strongest: it is the only claim verified three independent ways,
including a null that destroys it.

### Works partially, or is not readable where it matters

| capability | what is true | what is missing |
|---|---|---|
| front/rear | +128 ms at DNp04, five seeds, ±4 ms | DNp04 has **zero** synapses onto TTMn, so it never reaches muscle |
| retinotopic map | derived from anatomy, spatially coherent, sub-regions per bearing | **polarity unresolved** — we cannot say which end is front |
| motion channel (T4/T5) | 24,700 spikes on an orbit where looming gives 0; recruits lobula-plate inhibition | no behavioural readout; the fly sees an orbit and does nothing |
| premotor pool | fires under interactive drive (348 substeps) | 5 cells of 14,275 |

### Not working

| capability | why |
|---|---|
| aiming the jump | `POSTURE` records 0 spikes in every run; needs proprioception, which needs a body |
| escape heading | geometric; the neural signal exists and nothing reads it |
| in-flight steering | geometric |
| walking, turning, landing | scripted kinematics, no neural basis at all |
| optomotor turning | motion is seen, never acted on |
| non-visual senses | **395 proprioceptors present and undriven**, 0 photoreceptors in the network |
| learning | no plasticity in the engine |
| neuromodulation | 926 edges dropped; LIF cannot represent slow modulation |
| spontaneity | a LIF cell with no input sits at rest forever |

### What this is, honestly

One reflex, driven by measured wiring at its decision point, with scripted motor
consequences — plus an unusually complete account of which parts are which. The
contribution is not scale. It is that every claim above has a number attached, a null where
one is possible, and a record of the times the number was wrong.

## 3. Decisions

### 3.1 Representation

**Sparse, never dense.** A dense adjacency matrix at FlyWire scale is 72 GiB; the sparse
form is 20.7 MiB. This decides the whole architecture and is why `Connectome` carries CSR
weights above a size threshold.

**One `Connectome` object regardless of source.** The mock circuits, the FlyWire CSVs and
the NeuPrint API all produce the same type. The LIF engine cannot tell them apart, which is
the decoupling test rather than a convenience.

**Populations are labels, not biology.** Splitting T4/T5 out of PMN, or DLMn out of MOTOR,
moves no edges and changes no signs. Each such split was verified to reproduce the previous
run exactly before being accepted.

### 3.2 Calibration

**Per-dataset, never global.** NeuPrint's male CNS initially inherited FlyWire's
`pa_per_synapse = 0.007` and fired at 4.4°, twitchy enough to respond to two millimetres of
hand tremor. Its own fitted value is 0.002 — a 3.5× difference, because a different
reconstruction of a different animal has different absolute synapse counts. Profiles live
in `flysim/calibration.py`, each recording the escape threshold it was fitted to produce so
a later change shows up as a discrepancy instead of passing quietly.

Current thresholds: mock12 15.6°, synthetic120 14.2°, flywire 14.5°, neuprint 16.7°.

**Real connectomes get uniform published neuron parameters.** Per-population tuning on real
data would let invented parameters do work the measured wiring should be doing. The
hand-built mock keeps its own per-population biophysics, because it is explicitly a teaching
circuit and not a claim about a fly.

### 3.3 Connections the data cannot carry

Two tables, deliberately separate, because the same correction has two different
justifications and conflating them would hide one.

**Electrical synapses** (`ELECTRICAL_SYNAPSES`) — GF→TTMn and GF→PSI. EM connectomics scores
chemical synapses; gap junctions are simply absent. On chemical counts alone one Giant Fiber
spike delivers 0.49 pA against the ~7 mV it must cross, a 14× shortfall, and the pathway
does not conduct.

**Reliable chemical synapses** (`SUPRATHRESHOLD_SYNAPSES`) — PSI→DLMn. This connection *is*
in the data, 449 synapses across ten cells, the strongest PSI output by a wide margin. It is
merely under-weighted, because one global picoamps-per-synapse constant cannot also express
that a particular pathway is built to be relied upon.

Both use 55 pA, derived rather than guessed: a single current jump of amplitude *A* decaying
with `tau_syn` into a membrane with `tau_m` peaks at 0.157·*A* for the published parameters,
so crossing 7 mV needs at least 44 pA. An earlier attempt used 12 pA — the *steady-state*
current for 7 mV — and the motor neurons stayed silent, because a single spike never reaches
steady state. It peaked at 1.9 mV.

### 3.4 What the sensory layer encodes

**Expansion rate, not angular size.** The earlier size-based encoder made the fly flee a
large object parked nearby and never moving, and could not ignore a receding one, because
magnitude carries no sign. Angular-size constancy was lost in the change, deliberately.

**Computed analytically, never by finite difference.** The runner takes several simulation
steps per rendered frame while a mouse-driven threat updates once, so differencing put all
the motion into one sample: four of five samples reported no expansion and the Giant Fiber
never reached threshold.

**Discontinuities rejected on speed, not on expansion rate.** A rate threshold tightens as
the object nears — measured, it discarded any approach faster than 0.52 m/s once a 120 mm
object was within 40 mm. Speed is scale-independent and means the same thing everywhere.

**The size-decay term is capped at 90°.** Uncapped, `exp(-alpha*theta)` made drive peak
around 60 mm and fall to half by 5 mm, leaving the fly least responsive exactly when
something was on top of it — a blind spot you could sit inside.

**Efference copy.** `EnvObservation.closing_speed` is computed from the *relative* velocity
and so contains the fly's own motion. Physically correct, sensorily wrong: a retina cannot
tell whether an image expanded because an object approached or because the animal advanced.
Measured with the threat held at 0.0016 m/s while the fly flew at it at 1.04 m/s — 50 pA of
drive and two mid-flight course corrections away from a motionless object, which at the
900°/s turn limit read as a full U-turn.

Real flies discriminate this two ways: the spatial pattern (self-motion flows the whole
field outward; an object expands locally against a static surround) and efference copy, which
is documented in *Drosophila* for the lobula plate. The first needs retinotopy this encoder
lacks in a world with a background this arena lacks — in an empty void with one object the
two cases are *literally the same stimulus*, so the information is absent rather than
degraded. That leaves efference copy. Complete cancellation is available only because the
fly's motion is scripted and therefore exactly known; a real corollary discharge is partial.

### 3.5 What the motor layer reads

**Body constraints belong in the decoder, not in neuron parameters.** Switching real
connectomes to the published parameters silently dropped the Giant Fiber's 60 ms refractory
period to 2.2 ms, producing 415 takeoffs in 20 seconds. The fix was a takeoff refractory in
the decoder — a fly in flight has nothing to push against — rather than restoring a neural
parameter to obtain a behavioural result. The Giant Fiber stays free to spike whenever the
circuit says it should, and those spikes still appear in telemetry.

**Read the takeoff at the muscle where the muscle exists.** On a brain-only connectome the
motor neurons are outside the imaged volume, so the Giant Fiber is the last observable event
and the takeoff must be inferred. On a CNS dataset it is *read*.

**Flight versus hop is read, not assumed.** Silencing the PSI is the clean experiment:
`powered=False`, zero DLMn spikes, 21.5 cm travelled against 50.0 cm intact, and repeated
short hops instead of one flight. What is measured is *which* behaviour happens; the shape of
each remains scripted.

### 3.7 How much of the behaviour is the anatomy?

The strongest claim this project could make is that the escape comes from the measured
wiring rather than from the constants fitted on top of it. `tools/shuffle_control.py` tests
it, and the design matters more than the result.

**The rigged version is the obvious one.** Shuffle the wiring, re-run with constants fitted
for the *real* wiring, watch the escape disappear. That proves almost nothing: the constants
were chosen to make the real network work, and denying a different network its own constants
is not a comparison. **Every wiring therefore gets the same tuning budget** — the same sweep
of `pa_per_synapse` — and the question is what the *best achievable* behaviour is for each.
Passing requires discriminating: fire at a real approach *and* withhold from a slow drift,
at the same value. Firing at everything is not a threshold.

Measured on the male CNS, 388,722 edges:

| wiring | direct LC4→GF | best achievable |
|---|---|---|
| measured | 304 | works — escapes at 8.6 / 10.4 / 16.7° |
| degree-preserving shuffle | 70 | **never works, at any value** |
| type-preserving shuffle | 245 | works — 9.0 / 11.3 / 18.6° |

**The anatomy is load-bearing at the level of cell types, and not at the level of individual
cells.** Destroy the type structure and no amount of tuning recovers a reflex. Preserve the
connection counts and weights between every pair of cell types while scrambling which
individual cells are joined, and the behaviour is reproduced indistinguishably.

That second row is the honest limit of what this model currently demonstrates, and it is
**not** a fact about the fly — it is a fact about the model. The looming encoder drives all
966 LC4 cells identically, so individual identity carries no information by construction and
nothing downstream could be sensitive to it. This is the retinotopy gap of §4, measured from
a third direction: no spatial input, therefore no way for individual wiring to matter.

**It also gives the retinotopy work its acceptance criterion, pre-registered here before
that work begins.** If a retinotopic encoder is doing real work, the type-preserving shuffle
must *stop* reproducing the behaviour — because then which particular LC4 cell connects
where decides whether a threat on one side reaches the right cells. A retinotopy that leaves
this table unchanged has added machinery and no information, and should be rejected however
plausible its output looks.

Caveats: one shuffle seed, four values in the sweep. The degree shuffle loses 0.9% of edges
and the type shuffle 4.8% to collisions merging into existing connections. The type-
preserving null is deliberately generous — it is *constructed* to preserve the LC4→GF
connection count — which is what makes it the right test of individual-cell specificity and
the wrong test of anything else.

### 3.6 The motion channel

T4 and T5 were already present as one-hop inputs to LC4 and LPLC2 — 2,643 and 4,147 cells
across all four directional subtypes — with nothing driving them. `--motion` supplies the
sweep signal. Comparing an orbit against a head-on approach:

| | T4T5 | LC4 | INH | GF |
|---|---|---|---|---|
| orbit, 2 m/s | 24,700 | 62 | 2,421 | 0 |
| head-on, 0.6 m/s | 710 | 3,260 | 155 | 13 |

The fly now sees the orbit and still does not flee it, because the drive recruits the
inhibitory lobula-plate intrinsic cells rather than LPLC2. That is the right behaviour and it
comes out of measured wiring. It is **not** evidence that real direction opponency is
reproduced — driving an entire subtype uniformly is a crude stimulus and this test cannot
separate the two.

---

## 4. The shared blocker: retinotopy

The fly's eye is a spatial array, and the visual system preserves that arrangement — each
LC4 cell answers for a small patch of visual space, and the population tiles the field. Our
encoder computes **one** expansion rate and gives every LC4 cell the identical current.

The brain therefore knows something is looming and has no idea *where*. Three separate
limitations are all this one fact:

1. **Escape direction cannot be neural.** A threat on the left and a threat on the right are
   the same input. Measured first-spike times per side, approaching from four bearings:

   | bearing | PSI/L | PSI/R | TTMn/L | TTMn/R |
   |---|---|---|---|---|
   | 0° | 248 | — | 248 | 300 |
   | 90° | 248 | — | 248 | 296 |
   | 180° | 96 | — | 96 | 220 |
   | 270° | 92 | — | 92 | 208 |

   There *is* strong laterality — the left TTMn leads by 48–124 ms and the right PSI never
   fires — but it is **identical at every bearing**. A fixed structural asymmetry, carrying
   no directional information. Nothing to steer with.

2. **Motion cannot drive behaviour.** One global sweep number cannot say what is moving
   where.

3. **Self-motion cannot be distinguished from object approach**, which is why efference copy
   had to substitute for the spatial discrimination a real fly uses.

### Front and back: a per-cell azimuth map derived from anatomy

Left/right tuning off the `side` field leaves a **front/back ambiguity by construction**.
Two sensors symmetric about the body axis cannot separate a threat at 45 degrees front-left
from one at 135 degrees back-left — they produce the same left/right ratio, exactly as two
ears do. Moving the preferred direction off lateral changes the magnitude, not the ratio,
and magnitude is already confounded with distance and closing speed.

Breaking it needs structure *within* an eye, and three of the four ingredients turned out to
be measurable:

1. **Where a cell looks** — the weighted centroid of its presynaptic columnar partners.
2. **The body's anterior-posterior axis** — brain centroid to nerve-cord centroid. It lies
   *within* the columnar sheet: |cos| 0.86-0.89 against the sheet's second principal axis
   and 0.05-0.14 against its thin axis, so front/back is a direction in the map rather than
   across it. No orientation had to be invented.
3. **Side** — from the dataset.
4. **Polarity — NOT determined.** Fly visual neuropils invert the image between layers, so
   whether a posterior position means forward- or backward-looking cannot be settled from
   coordinates. Left as `retinotopy_polarity` rather than guessed. It decides which of
   front and rear is which, not whether they are distinguishable.

744 of 966 visual cells get a preferred azimuth, spanning -160 to +150 degrees: 108 frontal,
70 rear, the rest lateral.

**An earlier negative here was wrong, and the reason is worth keeping.** Measuring whether
descending neurons sample different parts of the field, using the sheet's first two
principal axes, gave centres clustered inside a quarter of the cell spread — recorded as
"they all look at the same place". But the first principal axis is only obliquely related to
the body axis (|cos| 0.45). Re-measured along the anatomically-derived axis, the
differentiation is plain: front-half input share runs from **0.080 for DNp11 to 0.608 for
DNp103**. The conclusion had been drawn on the wrong axis.

**Preliminary result.** First spike per pair, threat at front versus rear, both on the
midline so the left/right effect is excluded:

| | DNp01 | DNp11 | DNp103 | DNp04 |
|---|---|---|---|---|
| front | 232 | 420 | 312 | **200** |
| rear | 244 | 420 | 320 | **76** |

DNp04 separates front from rear by 124 ms, well outside the 30-40 ms noise floor; the other
three sit inside it.

**Repeated across five seeds** (`tools/frontback_control.py`), it holds:

| pair | front | rear | difference |
|---|---|---|---|
| DNp04 | 204 ±4 | 76 ±0 | **+128 ms** |
| DNp01 | 231 ±5 | 214 ±59 | +17 |
| DNp103 | 312 ±8 | 324 ±5 | -12 |
| DNp11 | 423 ±10 | 433 ±10 | -10 |

One pair of four carries front/back, reproducibly. The ±0 is frame quantisation — timing
resolves to 4 ms — not infinite precision. Which of the two directions is actually "front"
remains undetermined, being the polarity question above.

**Normalisation changed with it.** Dividing by the per-frame mean rescales every bearing to
the same total drive, which asserts the threat is equally visible wherever it is and erases
front/back before it starts. The reference is now fixed — the mean weight for a frontal
threat — so total drive varies with bearing. A head-on approach is then unchanged by
construction, and the scripted escape reads 16.7 degrees with tuning on or off.

**Saturation is now a compression, not a clip** — ``ceiling * tanh(x / ceiling)``. A hard
clip destroys information the moment two inputs both exceed it: they come out identical and
any comparison between them is gone. Left/right survived clipping because it contrasts a
driven eye against a SILENT one and zero stays zero; front/back is a magnitude contrast
*within* an eye, so a ceiling erases it. Elevation in 3D would have the same shape and the
same vulnerability.

**It did not, however, fix front/back at the muscle, which is what it was meant to do.**
The escape threshold is unchanged (16.7 degrees either way) and DNp04 still separates by
+127 ms, but TTMn still shows front -56 ±13 against rear -100 ±65. The reason is wiring:

| DN | → TTMn | → PSI | → DLMn |
|---|---|---|---|
| DNp01 | 90 | 9 | 0 |
| DNp04 | **0** | 14 | 0 |
| DNp03 | 0 | 0 | **524** |
| DNp06 | 53 | 75 | 0 |
| DNp02 | 26 | 44 | 0 |

**DNp04 has no synapses onto TTMn at all.** The one pair carrying front/back does not reach
the jump muscle; it reaches PSI, which drives the wings. So front/back was never going to
appear at TTMn whatever the saturation did — and that is biologically sensible, the jump
being coarse and ballistic while the wings steer. The place to look for front/back in the
motor output is DLMn, not TTMn.

The table also shows **DNp03 → DLMn at 524 synapses**, larger than the PSI→DLMn connection
already restored, currently running at the uniform 0.002 pA and therefore silent. A major
descending input to the flight muscles is being ignored.

**One caveat remains.** The spread of preferred azimuths — mostly lateral, fewer frontal and
rear — follows from mapping the anterior-posterior coordinate onto a circle, which is a
choice rather than a measurement.

### The experiment, run before implementing anything

The obvious approach was to treat soma position as a receptive-field proxy: the LC4 soma
cloud within a hemisphere is a flat 2-D sheet (75.6% / 22.7% / 1.6% of variance along its
principal axes), which is the shape a retinotopic map should have.

**That approach was tested and rejected.** If a cell type is retinotopic, two cells sitting
near each other look at neighbouring patches and should receive more similar input. Measuring
input-vector similarity against soma distance, with columnar cell types as a positive control:

| type | near/far input similarity | baseline similarity |
|---|---|---|
| Tm (columnar) | **3.2× / 4.3×** | 0.005–0.018 |
| T4/T5 (columnar) | **1.9× / 1.8×** | 0.012–0.031 |
| LC4 | 1.03× / 1.08× | 0.17–0.19 |
| LPLC2 | 1.07× / 1.07× | 0.26–0.29 |

The method detects columnar retinotopy strongly, and finds **nothing** for LC4 — at sample
sizes where Tm shows a 3–4× effect, so this is a real negative and not lack of power. The
baseline figures say why: LC4 pairs share input at 0.18 cosine *regardless of distance*,
against 0.005–0.03 for Tm. LC4 pools broadly, which matches its large overlapping receptive
fields, and its soma sits in the cell-body rind rather than where its dendrite looks.

**The route that does work, and needs no new data.** Locate each LC4 cell's receptive field
as the weighted centroid of its presynaptic columnar partners, whose own soma positions *do*
carry the map. Using connectivity to find the dendrite instead of assuming the cell body
marks it:

| | median columnar inputs | centroid spread, as a fraction of the source cloud |
|---|---|---|
| LC4 L / R | 74 / 99 | 0.93 · 1.08 · 0.61  /  0.93 · 1.12 · 0.63 |
| LPLC2 L / R | 73 / 108 | 0.70 · 0.82 · 0.32  /  0.71 · 0.82 · 0.32 |

The inferred centres spread across essentially the whole columnar cloud, so different LC4
cells genuinely look at different parts of the visual field and the population tiles it. The
third axis is consistently the weakest, as expected from a curved 2-D sheet — and two
dimensions is what a visual map needs.

**What remains invented if this is built.** The centroids are positions in CNS coordinates,
not visual angles. Turning them into azimuth and elevation requires choosing in-sheet axes
and their orientation and sign — a fitted mapping, not a measurement, and it must be labelled
as such. The arena also has no elevation and no background, so only azimuth would carry
information, and the self-motion discrimination would still not work without a textured
surround.

---

### What the bottleneck allows, measured before building

Retinotopy is only worth having if cells looking at different places project differently.
Measured on the male CNS:

| LC4 hemisphere | cells reaching a Giant Fiber | to left DNp01 | to right DNp01 |
|---|---|---|---|
| left | 71 | **100.0%** | 0.0% |
| right | 55 | 0.0% | **100.0%** |

Perfectly ipsilateral, no crossover. Within a hemisphere the spread of Giant Fiber
preference is exactly **0.000** — every cell converges identically onto its one GF.

So at DNp01, bearing survives as left-versus-right and no finer. **That is a limit of the
decoder, not of the data**, and reading it as a limit of the problem was a mistake worth
recording: DNp01 is not even the largest target of the visual projection neurons.

| target | synapses from LC4 + LPLC2 | | target | synapses |
|---|---|---|---|---|
| DNp04 | 14,978 | | DNp11 | 3,643 |
| DNp01 | 11,198 | | DNp06 | 2,679 |
| DNp103 | 5,231 | | DNp03 | 2,492 |
| DNp02 | 4,205 | | DNpe056 | 1,536 |
| DNg40 | 3,834 | | DNp05 | 1,255 |

Ten bilateral descending pairs, **every one of them perfectly ipsilateral** like DNp01, so
each is a clean left/right comparator. Roughly 78% of that descending output goes to cells
this model currently discards into the premotor bucket.

They are also **not redundant**. Mean pairwise overlap of their input sets is 0.42, with
structure: DNp04/DNp01/DNg40/DNp06/DNp103 overlap 0.56-0.90; DNp02/DNp11/DNp03/DNp05
overlap 0.56-0.87 among themselves but only 0.09-0.39 with the first group; DNpe056 shares
exactly 0.00 with the whole second group. Different descending neurons read different
subsets of the visual population — a population code, present in the data and unused.

(Caveat: Jaccard is sensitive to set size, and the second group reads smaller sets, 35-53
cells against 107-165. That inflates their mutual overlap. The 0.00 is not a size artifact.)

The implication for the retinotopy work is that the decoder should read the descending
population rather than one pair, and that bearing may be recoverable far more finely than
the DNp01 race alone allows.

This also explains the constant laterality of §4: with no retinotopy both hemispheres
receive identical drive, so the side with more cells always wins the race to threshold. 71
against 55 is why the left TTMn led at *every* bearing. It was a cell-count handicap, not a
code.

**Prediction, recorded before the work:** with a retinotopic encoder, a threat on the right
should overcome the 71-versus-55 handicap and make the right Giant Fiber fire first. If it
cannot, the map is not carrying enough signal to matter and should be rejected.

**Baseline and noise floor, measured before the work.** Under the current uniform drive the
descending pairs carry no bearing information, as they cannot: the encoder's output is a
function of distance, closing speed and threat size only, so azimuth never reaches them.
Repeating the *same* bearing four times gives a left-minus-right first-spike spread of
roughly 30 ms (DNp04: -28, -44, -56, -48). Apparent differences between bearings sit inside
that band, except at bearings pointing toward the threat's parked corner, where a shorter
startup jump changes the transient.

So **any retinotopic effect must exceed about 30-40 ms of run-to-run jitter to count**, and
the test is a change of *sign* — which side leads — rather than a change of magnitude.

### Hemifield-based tuning with a curve-based falloff

The first mechanism in this model by which direction reaches the neurons. Each visual
projection cell's looming drive is scaled by how near the threat is to the centre of its own
eye's field:

    weight = floor + (1 - floor) * 0.5 * (1 + cos(threat_bearing - eye_bearing))

with the eye bearing at -90 degrees on the left and +90 on the right, a floor of 0.25
because a fly's eyes wrap far around its head, and the whole vector **normalised to mean 1**.

Only the cell's *side* is used, which is measured. A finer within-eye map can be derived
from the anatomy — weighted centroids of each cell's presynaptic columnar partners, which
spread across the whole columnar cloud — but the descending projection is perfectly
ipsilateral, so within-hemisphere position is discarded before it can reach anything. It
would be machinery without consequence, and is deliberately not built.

**Result against the pre-registered prediction.** Left-minus-right first spike, fly held
still with a fixed body axis, two repeats:

| | DNp01, threat right | DNp01, threat left |
|---|---|---|
| tuning off | -80, -60 | -200, -216 |
| tuning on | **+88, +88** | -180, -208 |

Negative means the left Giant Fiber leads. With tuning off the left leads wherever the
threat is, exactly as a 71-versus-55 cell-count handicap predicts, and the sign never
changes. With tuning on **the sign flips with the threat's side**: a right-side threat now
makes the right Giant Fiber fire first, beating the handicap. The swing is around 140 ms
against a 30-40 ms jitter floor, and repeats agree to within a few milliseconds. DNp04
behaves the same way; DNp103 stays positive on both sides, so two of the three pairs
examined carry bearing and one does not.

**The normalisation is not cosmetic.** Weights are all <= 1, so without it the tuning
attenuates rather than redistributes: measured, the escape threshold slipped from 16.7 to
26.9 degrees and the fly stopped getting away. That reads as a change in sensitivity and is
really an artifact of losing drive. Normalised, the threshold holds at 17.2 degrees against
16.7 with tuning off, and the outcome is unchanged. Retinotopy is a claim about *where* the
drive goes, and the implementation now says only that.

**The second pre-registered test, run** (`tools/direction_control.py`). Note the prediction
as first written said the shuffle must stop reproducing "the behaviour", which was
imprecise: the escape only needs enough total drive to reach the Giant Fiber, and
scrambling partners need not prevent that. The sharp claim is about the flip.

| wiring | threat right | threat left | flips? |
|---|---|---|---|
| measured | +88.0, +88.0 | -180.0, -208.0 | **yes** |
| type-preserving shuffle | +4.0, -8.0 | +16.0, -12.0 | no |
| degree-preserving shuffle | silent | silent | no |

Scrambling which individual cells are joined, while preserving every type-level statistic,
**destroys the flip entirely** — it collapses to ±16 ms around zero, inside the jitter
floor. So hemifield tuning does not produce direction on its own; the measured wiring
carries it.

**This inverts §3.7, in the way that section predicted.** Without spatial input the
type-preserving shuffle reproduced the escape indistinguishably, and the conclusion was that
the anatomy is load-bearing at the level of cell types but not individual cells. The stated
reason was that the encoder drove every cell identically, so individual identity could not
matter. Give the encoder spatial structure and individual identity becomes load-bearing,
which is the first result in this project where it does.

A caveat on the null: one shuffle seed, two repeats, one descending pair. The effect is far
outside the noise floor, but the degree-preserving row proves less than it appears — DNp01
is silent there, so it fails to flip for want of any spikes at all rather than for want of
organisation.

### The fetch for the aiming circuit, and what it revealed

Seeded on the coxa-trochanter leg motor pool alongside the escape reflex
(`--postural`): 27,932 neurons, 595,118 edges. The motor population went from 10 cells to
157 and the descending population from 67 to 268. `Sternotrochanter MN` went from 2 cells
to 14.

The complete anatomical chain from eye to leg muscle is now present:

| stage | edges | synapses |
|---|---|---|
| visual → descending | 2,272 | 54,893 |
| descending → postural MN (direct) | 1,348 | 36,874 |
| descending → VNC interneuron | 16,637 | **343,178** |
| VNC interneuron → postural MN | 16,105 | **488,015** |

The premotor route dominates the direct one by an order of magnitude, as it should — real
descending neurons mostly drive premotor interneurons rather than motor neurons — and all
4,374 of those interneurons are in the network.

**The leg muscles still do not fire.** `POSTURE` records zero spikes. The escape itself
still works (18.1 degrees on this network against 16.7 on the smaller one).

The premotor stage, however, **does** fire, and an earlier version of this entry was wrong
to say otherwise. It was written from scripted episodes, where the drive is gentle. Under
interactive stimulation the chain reads `DN 890 -> PMN 348 -> POSTURE 0` substeps. So the
signal reaches the premotor interneurons and dies at the last synapse before muscle, which
is a far tighter localisation than "it dies somewhere in the middle".

**This is the most important limitation in the model, and the fetch is what exposed it.**
Drive attenuates stage by stage. `pa_per_synapse = 0.002` was fitted so the escape triggers
near 16 degrees, and that pathway only conducts because two synapses were restored by hand
at 55 pA — GF→TTMn and PSI→DLMn. Anything more than a synapse or two deep is
sub-threshold. So the model is a single hand-propped pathway inside a large inert scaffold,
and that was invisible while the scaffold was small.

Raising `pa_per_synapse` globally is not the fix and has been measured: 0.007 makes the
escape fire at 8.4 degrees, sensitive enough to respond to hand tremor. The problem is that
a LIF network with uniform parameters, no dendritic amplification and no recurrent gain does
not propagate through three or four stages, and a synapse count is not a conductance.

## 5. Neurons present, input absent

A recurring shape: the cells are in the connectome and nothing drives them.

* **Aminergic modulation.** Dopamine, serotonin and octopamine edges map to sign 0 and are
  dropped — 911 of them. A LIF neuron cannot represent slow parameter modulation at all, so
  this needs an engine change rather than more data. It is also why there is no spontaneity:
  a LIF neuron with no input sits at rest forever, measured as zero spikes anywhere over 15 s
  with no threat.
* **Mushroom body.** 5,177 Kenyon cells, 96 MBONs and 331 dopaminergic neurons are present
  in FAFB. No plasticity exists in the engine; weights are set once and never change.
* **Wing steering muscles.** The b1/b2/i1/i2 motor neurons that produce turning are not in
  the subgraph — they are driven by descending neurons the Giant Fiber does not touch, so a
  one-hop expansion from the escape seeds never reaches them.

**Why the escape direction question is not a wing question.** In a real fly, escape direction
is set *before* takeoff by leg positioning — the animal shifts posture to aim the jump — and
the wings take over afterwards for course control. The neural route to a directional escape
therefore runs through retinotopy and **leg** motor neurons, of which this subgraph contains
two.

**What a firing rate can honestly give.** The DLM and DVM are asynchronous, stretch-activated
muscles: their motor neurons fire at roughly 5–20 Hz while the wings beat near 200 Hz, and
the wingbeat frequency comes from thoracic resonance, not from spikes. A spike is not a wing
stroke. What the firing rate sets is **power** — so flight speed and duration can honestly be
derived from DLMn activity, while direction cannot.

---

## 6. How this project finds bugs

Every real bug here was found by hands-on use, because the automated test exercised a
convenient proxy instead of the path actually run. The recurring failure has one shape:
**something sampled per frame while the simulation runs several steps inside each frame.**

* The looming encoder's finite difference put a whole frame's motion into one substep.
* The decoder's steering edge survived on 36 of 376 commands.
* Pointer velocity was divided by one substep's `dt`, inflating a 5 m/s hand to 9.9 m/s and
  pushing genuine fast approaches past the teleport guard.
* A takeoff edge raised on a non-final substep had its flag re-attached but not its heading,
  and the environment discarded it: Giant Fiber fired, muscles fired, telemetry recorded it,
  fly did not move.
* `state.spikes` is the final substep only; anything counting spikes per frame wants
  `frame_spikes`.

Consequently: `--check` must run against a **real** connectome, not only the mock, and
invariants are preferred that compare two numbers from *opposite sides* of a boundary — for
instance requiring that every commanded takeoff was actually performed.

---

## 6b. Mistakes, and the one shape they share

Kept because the errors were more instructive than the results, and because each was
*confidently* wrong in a way that produced a plausible number.

**They are the same mistake repeated: reporting a property of our own setup as a property
of the system.**

| what was concluded | what was actually true |
|---|---|
| "the model cannot propagate through four stages" | we stimulate one input of many; the rest is not downstream of it |
| "PMN is inert, zero spikes" | measured only on scripted episodes; it fires under interactive drive |
| "the descending neurons all look at the same place" | measured along the sheet's first principal axis, oblique to the body axis; along the anatomical axis they differ 0.08 to 0.61 |
| "front/back is destroyed by saturation" | DNp04 has zero synapses onto TTMn; it was never going to appear there |
| "soma position can serve as a receptive-field map" | LC somata sit in a rind; neighbours share no more input than distant cells |
| "the shuffle control shows the anatomy is load-bearing" | published in a public document with **no implementation at all**, and the number was wrong |
| "front and rear light scattered regions" | spread taken from one centroid across a bimodal distribution |
| "raising pA/synapse will wake the network" | 25x wakes 68% more cells; strength was never the limit |

Four further errors of technique, each producing confident nonsense: reading `state.spikes`
(the final substep) instead of `frame_spikes`, losing ~90% of spikes; measuring spike
*counts* when the signal was in *timing*; measuring at saturation, after the quantity of
interest had been clipped away; and building a test runner without the connectome kwargs,
so a 317-neuron graph was validated instead of the 22,973-neuron one actually run.

### The countermeasure

Before concluding "the system does X", ask **what in my setup could produce this observation
regardless of the system**. In practice:

* **Which path did I measure?** Scripted and interactive differ in drive strength, substep
  handling and pointer sampling. Three separate bugs came from that alone.
* **Which axis, metric, resolution?** An oblique axis, a count instead of a latency, a
  clipped ceiling and a bimodal distribution each gave a clean wrong answer.
* **What is the noise floor?** Measure it *before* the change. The 30-40 ms figure is what
  made the direction result meaningful rather than suggestive.
* **Is there a null?** A result a shuffled network also produces is not a result.
* **Is the claim implemented?** If a document asserts an experiment, a reader must be able
  to run it.

### The structural error underneath

The subgraph was grown outward from one reflex and then treated as "the brain". That yields
an excellent escape circuit surrounded by cells that happen to be adjacent, and guarantees
most of it is silent, because most of it is not downstream of the single input we supply.
**The 3.6% activity figure is a fact about how the network was chosen and driven, not about
connectome simulation.** Reading it as the latter was the largest error in the project.

## 7. Deliberate choices not to re-litigate

* Reliable synapses are supplied in visible tables rather than folded into a scaling
  constant.
* Angular-size constancy was given up on purpose when the encoder moved to expansion rate.
* The mock keeps per-population biophysics; real connectomes get uniform published values.
* Connectome caches never live inside the repository.
* Kinematic realism is not purchased with noise.

---

## 8. Adding an entry

When a decision is made that a reader could reasonably disagree with, record: what was
observed, what was chosen, what it rules out, and the evidence.

**Name the mechanism, not just the outcome.** "The fly escapes in the right direction" is
an observation; "hemifield-based tuning with a curve-based falloff" is the thing someone
else could implement, argue with, or rule out. A mechanism named precisely enough to be
wrong is the whole point of writing it down, and the distinction usually only becomes clear
while the work is being done — so record it then, not afterwards from memory. If the evidence is a
measurement, give the numbers. If a choice was made for convenience rather than
faithfulness, say so — that is the most useful kind of entry here.
