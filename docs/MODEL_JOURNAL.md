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

The sharpest test of whether the anatomy matters is the shuffle control: randomise the
wiring while holding every statistic constant, and the escape vanishes entirely — 229 real
LC4→DNp01 connections against 0.

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

The escape pathway runs end to end on measured wiring:

```
DNp01 (Giant Fiber)  ->  PSI, TTMn  ->  DLMn
       1179.2 ms          1184.9 ms      1192.0 ms
```

---

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

**What implementing it would involve.** Give each cell a receptive-field direction and drive
it by what happens in its own patch. The LC4 soma cloud within one hemisphere is a flat 2-D
sheet — 75.6% / 22.7% / 1.6% of variance along its principal axes — which is the shape a
retinotopic map should have, so the anatomy plausibly carries it.

**The caveat that must be tested first.** Those are *soma* positions. In flies the LC cell
bodies sit in a rind at the surface while their dendrites do the tiling in the lobula. Soma
position is a proxy and possibly a poor one; the real map lives in synapse coordinates, which
is a much larger fetch. Check whether soma position predicts anything sensible before
building on it.

---

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
observed, what was chosen, what it rules out, and the evidence. If the evidence is a
measurement, give the numbers. If a choice was made for convenience rather than
faithfulness, say so — that is the most useful kind of entry here.
