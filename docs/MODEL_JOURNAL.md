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
