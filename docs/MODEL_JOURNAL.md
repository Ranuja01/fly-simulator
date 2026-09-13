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

### What the scorecard measures, and what it does not

Written because the scorecard below can go entirely green while the model covers a sliver of
vision, and a future session should not mistake one for the other.

The work sits inside five nested scopes. Each row is contained by the one beneath it:

| scope | what it is | our coverage |
|---|---|---|
| Ache eq. 7 | one neuron's membrane voltage during a looming disk | **2 of its 4 components** |
| the giant fiber | one descending neuron, DNp01 | LC4+LPLC2 = **99.4%** of its optic-lobe input |
| short-mode takeoff | the escape the GF triggers | ~**20%** of real escape takeoffs |
| escape from looming | one visual behaviour | the fast branch only |
| vision | ~20 optic glomeruli, each feeding its own motor program | **2 of ~20** |

**Almost every scorecard row measures the top scope.** GF input composition, GF-to-muscle
timing, the angular threshold, the LPLC2 lesion, the size and velocity channels — all of
them are properties of one neuron's response to one stimulus class. A fully green scorecard
would mean *the giant fiber's looming response is right*, which is a milestone and not the
goal.

**The sharpest measure of what is missing.** In Ache et al.'s control flies, short-mode
takeoffs — the GF-dependent ones this model produces — were 26% (47/178) and 17% (18/105) of
all takeoffs. Roughly one escape in five. The long-mode takeoff, wing elevation followed by
leg extension, is slower but more stable and **does not require the GF at all**; we have no
representation of it. So when our fly jumps, it always jumps the way a real fly jumps about a
fifth of the time. That is a larger gap than the two missing inhibitory components, and it is
invisible to every row on the scorecard.

**This is not an argument for widening the scope.** The GF reflex is the right target for the
current work: it is the best-characterised pathway in the animal, and the only one with
published numbers precise enough to fail against. The point is that "done" here means done
with the innermost scope. The next scopes out have names — long-mode takeoff, the other
eighteen glomeruli, the inhibitory components of eq. 7 — and each needs its own argument
before it is started.

### What "faithfully" means

Real escape has published, measurable properties. The model is faithful to the degree it
reproduces them. Sourcing is marked, because several values come from another group's
write-up rather than from primary literature we have read.

| measured fact | source | model | status |
|---|---|---|---|
| LC4+LPLC2 is ~30% of giant-fiber input | independently verified, 29.85% theirs / 31.3% ours | 31.3% | **pass** |
| one GF spike, one takeoff, all-or-none | established | holds | **pass** |
| faster looms -> peak at LARGER angular size | Ache Fig 4B | 24.6 -> 48.6 deg over 0.1-0.6 m/s | **pass, direction** |
| GF fires across the loom speed range | Ache r/v 10-80 ms | fails below r/v ~12 ms | **fail at the fast end** |
| silencing LC4 *and* LPLC2 abolishes the escape | established | no takeoff, fly captured | **pass** |
| silencing LPLC2 nearly abolishes it | established | abolished, `--channels` | **pass** |
| TTM fires 0.93 ms after the giant fiber | von Reyn et al. | 0.90 ms | **pass** |
| DLM fires 1.44 ms after the giant fiber | von Reyn et al. | 1.80 ms | **pass** |
| short takeoff completes under 6.87 ms | their page | not measured | **unknown** |
| GF-mediated takeoff threshold ~39 deg angular size | von Reyn et al. 2014 | 38.6 deg, `--channels` | **pass** |
| GF response peaks at 42 deg angular size | Ache et al. 2019 | size channel peaks at 42 | **by construction** |
| LPLC2 is silent with nothing approaching | inferred | 0 of 1501 frames, and silent on a LARGE static object | **pass** |
| LPLC2 requires looming motion to respond | Ache et al. 2019 | gated on expansion; static object silent | **pass** |
| **LC4 encodes looming SPEED; LPLC2 encodes angular SIZE** | Ache et al. 2019 | split, fitted to 2 targets | **pass** |
| LC4:LPLC2 synapse ratio onto GF | 1.79 (Ache et al.) | 1.32 | **consistent** |
| escape direction is away from the threat | established | neural: 98% away, 29 deg error, `--neural-heading` | **pass, coarse** |
| direction is set by pre-takeoff leg posture | established | absent, and out of reach | **out of scope** |

**Every row names the encoder it was measured on.** A row measured with the combined
encoder says nothing about the split one, and carrying one across to the other without
re-measuring is how the speed-dependence row sat at **pass** while the split encoder was
failing to fire at all above 0.5 m/s (Step E).

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

### Step C, run: calibrate the two channels against two targets

**Subgoal.** Fix the three free parameters of the split encoder — `gain_pa` (LC4, velocity),
`size_gain_pa` and `size_width_deg` (LPLC2, size) — against two independent published facts
instead of the one they were fitted to.

**Why it is not already done.** `--channels` reaches the published 39 degree threshold at a
velocity gain near 4, but three parameters fitted to one number is under-determined: many
combinations hit 39, and the one in `config.py` was picked rather than derived. A fit that
can only be checked against the number it was fitted to is not evidence.

**The second target** is the LPLC2 lesion. Ache et al. 2019 has LPLC2 carrying the size
component and LC4 the velocity component, so silencing LPLC2 should remove size and leave
velocity — published as *nearly abolishing* the giant-fiber escape. Our pre-split model
degraded 16.7 -> 31.8 degrees instead, which is the signature of removing generic drive from
a model with no size channel at all. The lesion is independent of the threshold because it
constrains the *ratio* of the two channels, where the threshold constrains their sum.

**Done-criterion — one parameter set must satisfy both:**

1. Intact escape threshold within **39 +/- 3 degrees** (von Reyn et al. 2014).
2. Silencing LPLC2 **near-abolishes** the escape — no takeoff at all, or a threshold pushed
   far enough that the reflex has effectively stopped discriminating.

If no setting in the sweep satisfies both, that is the result, and it says the split as
implemented is wrong rather than merely mistuned. A criterion that cannot fail is not one.

**What could make the measurement lie**, written before measuring:

* **`build_runner` overwrites `gain_pa` from the calibration profile.** It silently
  invalidated an entire earlier sweep, every run using 26.0 while reporting the swept value.
  It now prints a note, but the safe move is to bypass `build_runner` and assemble the four
  layers directly, which is what this tool does.
* **`LIFBrain.silence` gates transmission but the neuron still spikes**, and the decoder
  reads `state.spikes`. Harmless here — the decoder reads MOTOR, not LPLC2 — but it would
  not be if the lesion moved downstream.
* **Angular size at dispatch is not angular size at threshold crossing.** The published 39
  degrees is the latter. Both must be reported so it is visible which is being compared.
* **Approach speed sets the threshold**, and a hand-moved pointer is far faster than the
  scripted predator. Calibrate scripted at a fixed speed; confirm interactive separately.
  Never mix the two in one comparison.
* **Hemifield tuning scales drive by bearing**, so it shifts the threshold on its own. The
  sweep runs with it off, and the winning point is then re-measured with it on, reported as
  a shift rather than folded in.
* **A "pass" that only exists at one grid point is a coincidence.** Report the size of the
  passing region, not just its existence.

**Result: both targets met, and the fit is better determined than it was — but not fully.**

Swept with `tools/calibrate_channels.py` on male-cns:v1.0 at 0.42 m/s, takeoff read from
MOTOR. 108 episodes.

| what the lesion does | velocity gain 2 | 3 | 4 | 5 | 7 | 9 |
|---|---|---|---|---|---|---|
| escape after silencing LPLC2 | abolished | abolished | abolished | abolished | 79.2 deg | 56.5 deg |

**The lesion bounds the velocity gain, and nothing else.** With LPLC2 silenced the size
channel is gone entirely, so the lesioned threshold depends on the velocity gain alone —
which is what makes it an independent constraint rather than a restatement of the first.
Above gain 5 the velocity channel alone still drives a takeoff, contradicting the published
near-abolition. At or below 5 the reflex is abolished, matching.

**The threshold then picks the size channel.** At velocity gain 4, hemifield tuning off:

| size gain | width 14 | width 18 | width 22 |
|---|---|---|---|
| 70 | 52.5 | 43.2 | 43.2 |
| 90 | 45.9 | **40.8 PASS** | 34.9 |
| 110 | 43.2 | **36.6 PASS** | 29.2 |

The passing region is a **ridge, not a point** — size gain and width trade off against each
other, as two parameters scaling one Gaussian's contribution near its peak must. Width 18 is
required across the sweep; size gain 90 and 110 both pass. So two targets fix one parameter,
bound a second and leave the third loose. **Three unknowns against two equations is still
under-determined, by exactly one dimension.** The defaults already in `config.py` (gain 4,
size 90, width 18) sit inside the band rather than on its edge, which is the most that can
be claimed for them.

**Two bugs the pre-measurement list caught.**

1. **The fitted gain could not reach a run.** `build_runner` sets the encoder gain from
   `encoder_gain_pa` unconditionally, so `--channels` ran the velocity channel at the
   combined encoder's 26.0 — six times the fitted value — no matter what was calibrated.
   Fixed with `CalibrationProfile.channel_gain_pa`, and the startup line now prints the gain
   actually in use rather than the profile's.
2. **The sweep triggered on the wrong population.** `DecoderParams` defaults to GF; this
   dataset reads the takeoff from MOTOR, ~6 ms later. The first pass therefore fitted the
   threshold at giant-fiber firing while every real run reports it at the muscle. Corrected,
   and it narrowed the passing band from 5 settings of 9 to 2.

**Two caveats that limit what this is worth.**

* **Resolution.** Thresholds are quantised by the frame at which angular size is sampled:
  the measured values step 36.6, 40.8, 43.2, 45.9. Those steps are 2-3 degrees against a
  tolerance of +/- 3, so the band's edges are set as much by sampling as by the circuit.
* **The fit is condition-specific, and the condition is the one normally run.** With
  hemifield tuning on — `--retinotopy`, which scales drive by bearing — the same parameters
  give 45.9 degrees, outside the band. Refitting with it on moves the answer to size gain
  135 at velocity gain 4 (40.8 deg). Both are recorded; neither is adopted as the default,
  because step 3 replaces the azimuth map and will invalidate any hemifield-on fit made now.

**Scorecard effect.** Three rows move. The threshold row goes 16.7 -> 40.8 degrees against a
published ~39; the LPLC2 lesion row goes from partial (16.7 -> 31.8, generic drive removed)
to abolished, which is the published behaviour and something the single-channel model could
not produce at any setting; and the mechanism row is no longer failing, because the two
populations now carry different signals.


### Step D, run: the size channel had no zero

**Found by Ranuja, in the telemetry, not by any test we had.** The LC4 row was lit almost
continuously and went *quiet* on approach — the reverse of the pre-split encoder's
behaviour. Nothing in the scripted sweeps could see it, and both published targets were
passing while it happened.

**Cause.** A Gaussian in degrees never reaches zero. At theta = 0 the size channel still
delivers 6.6% of peak — measured, 5.9 pA against the 7.0 pA a cell needs to fire, and the
per-cell gain spread of +/- 22% puts a large share of the 185 LPLC2 cells over the line. The
channel is above firing threshold for every theta between **1.3 and 82.7 degrees**. A 5 mm
object subtends 1.3 degrees at 220 mm, wider than the arena, so there is nowhere the threat
can sit that does not drive LPLC2. The upper edge is the other half of the report: past 83
degrees the Gaussian falls back under threshold and the channel goes **silent at the
strongest possible stimulus**.

Measured on a near-stationary object over 1,501 frames:

| size tuning | frames in which LPLC2 fired | takeoffs |
|---|---|---|
| Gaussian in degrees | **1,497 of 1,501 (100%)** | 0 |
| Gaussian in log angle | **0 of 1,501 (0%)** | 0 |

**Neither published target can see this.** Both describe what happens during an approach;
a resting discharge that never triggers a takeoff is invisible to both. Two targets caught
an under-determined fit and missed a mechanism error sitting underneath it. **A scorecard
constrains what it names and nothing else** — which is an argument for watching the thing
run, not only for adding targets.

**The fix, and its status.** `size_tuning_form` selects a Gaussian in degrees or in log
angular size. The log form has no floor and no upper cutoff. It also makes the published
C4 = 0.52 usable *as published*: 0.52 cannot be a width in degrees, but it works as a
dimensionless width in log-angle, which would explain why the value carries no unit.

**That interpretation is ours and remains unverified.** The paper's equation is paywalled —
Cell returns 403, PMC is behind a cookie wall, and the open papers citing it restate the
model only in words. It is recorded as inferred, and both forms are kept so the choice can
be revisited by whoever reads the equation.

**Refit.** The log form passes both targets over velocity gain 4-5 at size gain 90-135, with
the lesion bound looser than the linear form's (abolished up to gain 7, against 5). Adopted:
velocity gain 4, size gain 110, width 0.52, threshold 40.8 degrees. The velocity gain is
unchanged, so only one number moved.

**What the two forms do NOT differ on:** both hit 39 +/- 3 degrees, and both abolish on the
LPLC2 lesion. The fit did not choose between them. The resting discharge did.

### Step E, run: the fit is accurate at one speed and fails at the rest

Prompted by Ranuja's interactive run showing takeoffs spread from 24 to 70 degrees where the
scripted fit says 40.8. The spread is expected — a hand-moved threat varies wildly in speed —
but it was worth measuring what the calibrated model does across approach speeds, because
nothing in Steps C or D varied speed at all. **Both targets were measured at a single 0.42
m/s approach.**

Giant fiber firing and takeoff, scripted, same connectome:

| approach | combined encoder (gain 26) | split channels (log, fitted) |
|---|---|---|
| 0.42 m/s | GF 1182 ms, takeoff at 16.7 deg | GF 1277 ms, takeoff at **40.8 deg** |
| 0.80 m/s | GF 608 ms, takeoff at 13.1 deg | GF 700 ms, **no takeoff** |
| 1.50 m/s | GF 314 ms, takeoff at 11.3 deg | **GF never fires** |
| 2.50 m/s | GF 177 ms, takeoff at 9.3 deg | **GF never fires** |

**The split buys accuracy at one speed and loses the whole fast half of the range.** The
combined encoder fires across all of it but at 9-17 degrees, failing the published threshold
everywhere. Neither is right.

**Diagnosed, not guessed.** Two separate failures:

* At 0.80 m/s the giant fiber *does* fire, 45 ms before contact, and the takeoff never
  happens. Setting `sensory_delay_ms` to 0 restores it (takeoff at 39.0 deg). It is the 19 ms
  sensory delay spending the margin the animal needed.
* At 1.50 m/s the giant fiber does not fire at all. Raising the velocity gain from 4 to 26
  restores firing (38.4 deg); the size channel cannot carry it, because at that speed the
  object crosses 42 degrees roughly 17 ms before contact and the 19 ms delay means the fly
  never sees it.

**The two constraints pull against each other, and that is the finding.** The LPLC2 lesion
target requires the velocity channel to be *weak* — strong enough and silencing LPLC2 no
longer abolishes the escape, which is how Step C bounded the gain at 5 to 7. But escaping a
fast loom requires the velocity channel to be *strong*, because the size channel arrives too
late. Our velocity channel cannot satisfy both, which is evidence that its **functional form
is wrong**, not merely its gain: one linear term with one fitted constant is standing in for
whatever Ache et al. fit with C1 = 0.0002567 and C2 = 1.7, neither of which we can place.

**Caveat on the outcome column.** Above 0.62 m/s the predator outruns the fly's cruise speed,
so "captured" is guaranteed by the arena whatever the neurons do. Only *whether the giant
fiber fired* carries information at 1.5 and 2.5 m/s, which is why the table reports it.

**What this says about the method.** Three targets were available and we used two, because
the third — speed dependence — was already marked **pass** on the scorecard from a
measurement of the *combined* encoder. A row that passes for one configuration was carried
across to another without re-measuring. The scorecard has to say which encoder each row was
measured on.

### Step F, SUPERSEDED by Step G: fit against speed dependence as a third target

> **Do not run this as written.** Two things changed before it started. (1) Its purpose was
> to close the degeneracy between the two channel gains with a third target; Ache et al.
> fixes their ratio outright, so that degeneracy is gone and only one scale remains to fit.
> (2) **Its third criterion has the direction backwards** — it requires angular size at
> firing to *decrease* with approach speed, and the published Figure 4B says it increases.
> Kept unedited below because the error is the instructive part: the criterion was written
> from the combined encoder's behaviour and from reading "faster looms trigger earlier" as
> "fires at a smaller angle", and it would have scored correct behaviour as a failure. See
> Step G, point 4.

**Subgoal.** Fit the two channels so the model reproduces the published threshold, the LPLC2
lesion, *and* the dependence on approach speed — across the range of speeds, rather than at
the single 0.42 m/s both earlier fits used.

**Why a third target rather than a better fit.** Step E showed the two existing targets pull
the velocity gain in opposite directions: the lesion needs it weak, a fast loom needs it
strong. A third relationship is what decides between them, and it is the one relationship we
already know the model gets wrong. It also closes the degeneracy Step C left open — three
targets against three parameters.

**Done-criterion — one parameter set must satisfy all three:**

1. Threshold at 0.42 m/s within **39 +/- 3 degrees**.
2. Silencing LPLC2 **abolishes** the escape at that speed.
3. The giant fiber **fires at every approach speed from 0.1 to 2.5 m/s**, and the angular
   size at firing **decreases monotonically** with speed.

(3) is deliberately qualitative. A quantitative curve would be better, but we cannot source
one, and asserting a fitted curve we have not read would be inventing a target — the failure
mode this whole scorecard exists to prevent. Monotonic decrease is weaker and falsifiable,
which is the correct trade.

**If no parameter set satisfies all three**, that is the result, and it says the velocity
channel's functional form is wrong rather than its gain — which is already the suspicion,
since one linear term with one fitted constant stands in for whatever Ache et al. fit with
C1 = 0.0002567 and C2 = 1.7.

**What could make the measurement lie**, written before measuring:

* **The current metric goes blind exactly where the problem is.** `escape_angular_size_deg`
  is measured at takeoff, and returns None when the giant fiber fires too late for a takeoff
  to follow — which is precisely the 0.80 m/s case. A speed sweep using it would score
  "reflex failed" and "takeoff suppressed" identically. **The sweep must measure angular size
  at GF first spike**, and that field does not exist yet. Build it first.
* **The arena decides the outcome above 0.62 m/s**, where the predator outruns the fly's
  cruise speed and capture is guaranteed whatever the neurons do. Outcome carries no
  information there; only GF firing does.
* **Episode duration scales with approach speed.** A slow approach needs a longer episode
  simply to arrive, and a fixed duration would read "no escape" for "ran out of time".
* **Monotonicity across a coarse grid is nearly free.** Four points can look monotonic by
  accident, and the thresholds are quantised by the sampling frame. Use enough speeds that a
  non-monotonic result would be visible, and report the quantisation step alongside.
* **Fitting three parameters to three targets can succeed and still mean nothing** if the
  targets are not independent. The threshold and the speed dependence are both about when the
  GF fires; if the fitted set turns out to sit at the edge of every band at once, suspect
  that rather than celebrate it.

**Dependency.** The Ache et al. 2019 equation would replace the velocity channel's invented
form with the published one, turning three fitted parameters into roughly one. Worth doing
first if the paper can be obtained; the step is runnable without it, at the cost of fitting a
form we are not confident in.

### Step G, run: the paper, and what it settles

Ranuja supplied the Ache et al. 2019 PDF after every fetch route returned 403. Worth noting
it is **CC BY open access** — it was never paywalled, only closed to an automated client.
A human could have opened it at any point in the four attempts spent working around it.

**1. The log-Gaussian is confirmed, exactly.** STAR Methods eq. 4:

    V_LPLC2 = C2 * exp( -(ln[theta(t - d2)] - ln[C3])^2 / (2 * C4^2) )

with C2 = 1.7 mV, C3 = 42 deg, C4 = 0.52, d2 = 0.019 s. A Gaussian in **ln theta**, which is
why 0.52 carries no unit. Step D inferred this from two things — that 0.52 cannot be a width
in degrees, and that a log Gaussian has no resting floor — and the inference was right. The
form stops being ours and becomes the paper's.

**2. The velocity channel is linear, as we had it.** Eq. 3: `V_LC4 = C1 * theta_dot(t - d1)`,
a line through the origin, C1 = 0.0002567 mV per deg/s, d1 = 0.019 s. So C2 = 1.7 was never
an exponent — it is the size channel's amplitude in millivolts. Step E's suspicion that the
velocity channel's *form* was wrong is **not supported**; the form was right.

**3. What the paper actually settles is the RATIO, which is what we could not fit.** With
the published weights (eq. 7, W_LPLC2 = 1.45, W_LC4 = 1.62):

    weighted size peak      = 1.45 * 1.7      = 2.465 mV
    weighted velocity slope = 1.62 * 0.0002567 = 4.159e-4 mV per deg/s
    the two are equal at 5,928 deg/s = 103.5 rad/s

Our velocity channel is per rad/s, so `size_gain_pa / gain_pa` must be **103.5**. It was
**27.5** — our velocity channel was **3.8x too strong relative to size**. The degeneracy
Step C could not close, and Step F was written to attack with a third target, is closed by
the paper instead. **Three fitted numbers become one**: an overall pA scale.

Refitted at the locked ratio, sweeping only that scale: velocity gain **2.2**, size gain
**227.7**, giving **38.6 degrees** against the published ~39, with the LPLC2 lesion still
abolishing the escape. Both targets met with one free parameter rather than three.

**4. I had the third criterion backwards.** Step F required angular size at firing to
*decrease* with approach speed. Figure 4B says the opposite: a pure size (eta) encoder peaks
at a fixed 42 degrees whatever the speed, a pure velocity (rho) encoder peaks at maximum
size, and the real GF sits between — so as the velocity contribution grows with faster
looms, the peak moves to **larger** angular size. Measured at the new fit:

| approach | r/v | GF | theta at takeoff |
|---|---|---|---|
| 0.10 m/s | 100 ms | fires | 24.6 deg |
| 0.20 m/s | 50 ms | fires | 30.9 deg |
| 0.42 m/s | 24 ms | fires | 38.6 deg |
| 0.60 m/s | 17 ms | fires | 48.6 deg |
| 0.80 m/s | 12 ms | fires, no takeoff | -- |
| 1.50 m/s | 6.7 ms | **never** | -- |

Monotonically increasing, which is the published direction. I wrote the criterion from the
*combined* encoder's behaviour and from the loose phrase "faster looms trigger earlier",
conflating earlier *in time* with *smaller angular size*. Had the sweep run before the paper
arrived, it would have scored a correct behaviour as a failure. Values below 42 at slow
approaches are expected: our threshold crossing necessarily precedes the paper's response
peak.

**5. What remains broken is narrower than Step E claimed.** The failure above 0.8 m/s is
real, but our arena at those speeds runs at r/v = 12.5, 6.7 and 4.0 ms, against the paper's
fitted range of **10 to 80 ms**. At 1.5 and 2.5 m/s we are extrapolating outside the data
the model was ever fitted to, so "the model fails there" is partly "we are using it outside
its domain". The 0.80 m/s case is inside the range and does fail: the giant fiber fires and
no takeoff follows, which Step E localised to the 19 ms delay rather than the encoder.

**6. Components of the published model we do not implement, deliberately.** Eq. 7 sums four
terms and we have two. The other pair are inhibitory: a tonic hyperpolarization that is a
sigmoid in angular size (eq. 5, weight **2.27** — the largest weight in the model) and a
small LC4-dependent Gaussian peaking at 26 degrees (eq. 6, weight 1). We supply inhibition
from the connectome's own INH population instead.

This was first written up here as "the most substantial known gap between our encoder and
theirs", which was the wrong framing — see §1a. Those components sit *downstream* of the
boundary where published description is legitimate: they describe what the giant fiber's
inhibitory partners do, and we have 3,688 of those cells wired by measured synapses.
Implementing the fitted curves would improve our agreement with the published traces
without the wiring having earned it. They are a **prediction to test**, not a gap to fill.

**7. Anatomy the paper confirms independently.** 55 LC4 and 108 LPLC2 synapse onto the GF,
with 2,442 and 1,366 synapses — a ratio of 1.79, matching the scorecard row. "LPLC2 and LC4
contribute 99.4% of the GF's direct-input synapses from the optic lobe", which supports the
decision not to drive the other 654 visual cells. And LPLC2 synapses onto LC4 (>175
synapses), the likely source of the supralinear summation.

**8. The lesion target, quantified.** Short-mode takeoffs fell from 26% to 3% with TNT and
17% to 7% with Kir. "Near-abolished" is the right reading, and our binary abolition is at
the strong end of it.

### Step H, H1 run: does our wiring produce the published inhibition?

The first experiment that tests the **connectome** rather than the boundary we inject into.
Every scorecard row so far measures our encoder; this one asks whether the measured synapses
reproduce something we deliberately did not implement (§1a).

**Subgoal.** Determine whether the giant fiber's inhibitory input, as wired in the
connectome, reproduces the tonic hyperpolarization Ache et al. measured — and if not, say
precisely what is missing.

**The published measurement.** Static disks of different angular sizes appear and remain for
1 s; GF membrane potential is averaged over a 200 ms window starting 200 ms after
appearance (Fig 2I, 2J). The result is size-tuned hyperpolarization, fitted by eq. 5:

    Vi1 = C5 + C6 / (1 + exp( -(theta(t - d3) - C7) / C8 ))
    C5 = -0.53, C6 = 0.59, C7 = 66 deg, C8 = -11, d3 = 0.0375 s

which runs from about **+0.06 mV at 5 degrees to -0.47 mV at 90 degrees**. Critically, it
was **unchanged** in LC4-silenced, LPLC2-silenced and control flies — so in the animal it
derives from input independent of both.

**H1 result: the anatomy is there, the activity is not. H2 is not worth building.**

274 of the 3,688 INH cells are presynaptic to the giant fiber. Of the synaptic weight
arriving at those 274, only **15% comes from LC4/LPLC2** — the cells we inject into — and
**85% from 1,350 other sources**. On the weight test alone, the wiring looks capable of
supporting an inhibitory component largely independent of the two driven populations, which
is what the paper measures. That is the encouraging half.

Then the activity:

| of the 274 INH cells presynaptic to the giant fiber | ever fire in a full escape episode |
|---|---|
| LC4/LPLC2 intact | **1** |
| LC4/LPLC2 silenced | **0** |

**One cell.** The substrate exists and is almost entirely silent, because those 1,350 other
presynaptic partners have no drive of their own: 98% of them are reachable from our single
injection point, and reachable is not the same as driven. This is the same finding as the
propagation problem in §5, arriving from a different direction — **we stimulate one input of
many**, and a connectome full of correctly wired cells does nothing without input.

So our model cannot reproduce the published tonic hyperpolarization, and the reason is not
missing anatomy. It is that the inhibitory cells' own visual drive is outside what we supply.

**My H1 criterion asked the wrong question.** It was written around the *weight* fraction —
"if their input is overwhelmingly from LC4/LPLC2, H2 is not worth building". The weight
fraction said go ahead (85% independent); the activity said stop. A structural criterion
about connectivity cannot settle a question about signal, and the two answers here point in
opposite directions. **Where a criterion can be phrased over anatomy or over activity,
phrase it over activity.**

**A claim now in doubt.** `--check` asserts "feedforward inhibition suppresses GF for a slow
approach", and it passes. But if only one inhibitory cell presynaptic to the giant fiber ever
fires, whatever withholds the escape on a slow approach is largely **not** direct inhibition
onto the giant fiber. The check's name may describe a mechanism it does not test. Not yet
investigated, and not to be repeated as fact until it is.

**H1 follow-up: it is not how many cells we inject into.** Ranuja's reading — that the real
problem is injecting at a target and expecting propagation to behave as it would in life —
is what the numbers say. Driving progressively more of the input surface changes nothing
about the inhibitory population:

| what we drive | cells that ever fire | INH cells presynaptic to GF |
|---|---|---|
| 312 (LC4 + LPLC2, split) | 338 of 22,973 (1.5%) | **1 of 274** |
| 966 (all visual projection, combined) | 984 (4.3%) | **1 of 274** |
| 966 + 3,201 T4/T5 (one layer earlier) | 1,761 (7.7%) | **1 of 274** |

Tripling the driven surface, and stepping a whole synaptic layer earlier, moves the number
not at all.

**The mechanism, measured.** Of the synaptic weight arriving at those 274 cells, **81.8%
comes from cells that never fire** in the entire episode. Their largest sources are PMN
(33%) and other INH cells (28%) — populations that are themselves almost entirely silent.
It is a **chain of silence**: every layer sits subthreshold, so nothing survives more than a
couple of hops from the injection, whatever the injection's breadth.

**Why a real brain does not have this problem.** A central neuron in life is under continuous
synaptic bombardment from thousands of cells, most of them outside any subgraph one might
fetch. That background holds it near threshold, so a modest signal can carry it over. Our
`bias_current_pa` is 0.0 and every cell rests a full 7 mV below threshold with no background
at all. **The absence of background is itself a modelling choice**, and an invisible one —
it was never decided, it was inherited from a 12-neuron circuit where it was correct.

**Two responses, and the honest problem with each.**

* **Fetch more brain.** Truer, and it recurses without terminating: whatever is fetched has
  its own silent upstream, because the brain is recurrent and the only true edge is the
  sensory surface. Reaching that edge means photoreceptors and an image, which is a far
  larger change than it sounds — though for a looming disk it needs geometry, not a
  renderer, so it is not strictly coupled to going 3D.
* **Declare a background drive.** Legitimate under §1a — it is a boundary condition standing
  in for brain we did not fetch, exactly like injecting into LC4 stands in for the optic
  lobe. But it is the most dangerous parameter this model could acquire: enough background
  makes any cell fire, and a result produced that way would look like propagation while
  being a property of the constant. It must not be added without a criterion, and any
  version of it must be checked against `tools/shuffle_control.py` — if a shuffled
  connectome escapes just as well, the background is doing the work, not the wiring.

Neither is started. The finding to carry forward is that **the model's silence is not a bug
in the wiring and not a shortage of injected cells — it is the absence of the rest of the
brain**, and that absence has been doing quiet work in every propagation result so far.

**Run it in two parts, cheap one first.**

**H1, structural — can it possibly succeed?** Our model injects current into LC4 and LPLC2
and nowhere else, so every inhibitory cell we have is driven *through* them. The published
hyperpolarization is LC4/LPLC2-**independent**. If our INH population has no drive except
via the cells whose silencing leaves the real hyperpolarization untouched, then our
inhibition is feedforward by construction and cannot reproduce an independent component —
and that is the answer, reached without building any stimulus machinery.

*Done-criterion for H1:* report, for the INH cells presynaptic to DNp01, what fraction of
their input synapses arrive from LC4/LPLC2 versus from cells outside that pathway. If it is
overwhelmingly the former, H2 is not worth building and the finding is structural.

**H2, behavioural — only if H1 leaves room.** Present static disks at a spread of angular
sizes, hold them, and measure mean GF membrane potential over the published window.

*Done-criterion for H2:* the measured curve is monotonically hyperpolarizing with angular
size above ~20 degrees, and the total swing between the smallest and largest disk is within
a factor of two of the published 0.53 mV. Sign and monotonicity matter more than magnitude,
because our picoamp scale is fitted and theirs is measured.

**What could make the measurement lie**, written before measuring:

* **The signal is at our noise floor.** The published swing is ~0.53 mV; `noise_mv` is 0.35
  mV per neuron per step. Measure the noise floor across repeated trials with no stimulus
  **first**, and report it beside the effect. Without that, any curve is uninterpretable.
* **Our encoder drives LPLC2 on a static disk, and the animal's does not.** The paper notes
  LPLC2 "require looming motion to be active"; our size channel is a function of instantaneous
  angular size alone, so a stationary disk of 42 degrees drives it at full strength. This is a
  real discrepancy in its own right and must be recorded separately — but it also contaminates
  H2, because our static-disk response is not the animal's static-disk response. Consider
  driving the *velocity* channel to zero and the size channel as the animal would leave it.
* **A subthreshold read needs the cell not to spike.** The paper analysed only trials with no
  action potential, for exactly this reason. Ours must do the same or the average is dominated
  by reset dynamics.
* **The environment has no static-disk mode.** Building one is new machinery, and new
  machinery is where artefacts come from — the start-up teleport that produced a retracted
  result (§2a) was exactly this. Warm up before measuring, and verify the disk is actually
  static by reading back angular size per frame.
* **`LIFBrain.silence` gates transmission but the neuron still spikes.** Any lesion control
  here must silence upstream, not the readout cell.
* **A null result is the likely one, and is worth stating plainly.** If the wiring cannot
  produce the published inhibition, that is information about what our subgraph lacks — an
  independent visual drive to the inhibitory cells — not a failure of the experiment.

### Step I, run: 95% of the model is inert, and that reframes the goal

Ranuja asked how much the 22,000 surrounding cells actually matter, given the aim is a fly
that *behaves* like a fly. Measured by silencing them:

| silenced | escape | takeoffs | GF spike |
|---|---|---|---|
| nothing | 38.58 deg | 2 | 1273.8 ms |
| INH (3,688) | 38.58 deg | 2 | 1273.8 ms |
| PMN (11,437) | 38.58 deg | 2 | 1273.8 ms |
| **INH + PMN + T4T5 (21,915)** | **38.58 deg** | **2** | **1273.8 ms** |

**Silencing 95% of the model changes nothing, to the last decimal.** The escape is produced
by roughly 340 cells: the 312 we inject into, and ~26 downstream along
LC4 -> DN -> GF -> TTMn/PSI -> DLMn. Everything else is scenery.

**A documented claim, falsified.** `--check` asserts *"feedforward inhibition suppresses GF
for a slow approach"*, and it passes. With every inhibitory cell silenced, the slow drift
**still** fails to trigger and the real approach **still** triggers at the same millisecond.
Inhibition plays no part in the gating. What withholds the escape from a slow approach is the
encoder: the drive never reaches threshold. The test is correct about the behaviour and wrong
about the mechanism, and its name should say what it tests.

**The reframe this forces.** Two different targets have been running together:

* **Behavioural fidelity** — the fly does what a fly does. Achievable through validated
  pathways, and it is what the scorecard actually measures. **No scorecard row is blocked by
  the propagation problem.**
* **Mechanistic fidelity** — the network computes it the way the brain does. This *is*
  blocked, by two independent order-of-magnitude deficits (§ the capacity work above).

Everything in the last several steps has been chasing the second. The stated goal is the
first, and the first is not blocked.

**What this makes the model, stated plainly.** A **behaviour library on measured anatomy**:
each pathway anatomically real, its weights taken from the connectome, its behaviour checked
against published numbers — with the surrounding cells present but inert. That is a legitimate
and useful kind of model. It is **not** a brain simulation, and must not be described as one.
The cost is that it can never show emergence: every behaviour is one we chose to wire and
validate, so the model cannot surprise us. The benefit is that every behaviour it does have is
checkable, and it actually behaves.

**What now stands between here and "a fly in a 2D arena".** Not the 22,000 cells. The
behaviours that are still scripted geometry: escape *direction*, walking and turning, flight
steering, landing. Each needs its own validated wire, exactly as the escape did — not a
network that conducts. Prior evidence that this works: driving the locomotor command neurons
(MDN, DNa01/02) at 0.05-0.15 pA/synapse already produces leg motor activity.

### Step J, run: per-connection delay, and the gap-junction latency

**Result: both targets met, and the diagnosis in the criterion was wrong.**

| | before | after | published |
|---|---|---|---|
| GF -> TTMn, headless | 5.10 ms | **0.90 ms** | 0.93 ms |
| GF -> DLMn, headless | 10.60 ms | **1.80 ms** | 1.44 ms |
| GF -> TTMn, interactive (dt 0.4) | -- | 1.20 ms | 0.93 ms |
| GF -> DLMn, interactive (dt 0.4) | -- | 2.00 ms | 1.44 ms |

**The axonal delay was not the problem.** The criterion assumed it was, and named
per-connection delay as the fix. Removing all 1.8 ms of it took GF -> TTMn from 5.10 to
3.60 ms -- still 3.9x the target. **Membrane charging dominates the latency**, and in a
leaky integrator that is set by how hard the cell is driven. So the measured latency fixes
the *current*, a constant we had only ever justified as "enough to conduct at all".

Both changes were needed and both are physically motivated:

* Gap junctions bypass the delay line (`Connectome.fast_weights`, delivered one timestep
  after the spike rather than after 1.8 ms). They are resistive coupling; there is no
  vesicle release and no axon to conduct along.
* `ELECTRICAL_SYNAPSE_PA` 55 -> **175**, derived from the 0.93 ms latency rather than from
  the 7 mV gap. The old value answered "does it conduct"; the new one answers "when".

**One current cannot match both targets, and that is structural.** Our two-hop latency is
exactly 2x the one-hop, because GF -> PSI and PSI -> DLMn are given identical dynamics. The
published pair is 1.44/0.93 = **1.55x**. So the animal's second hop is *faster* than its
first, which this model has no way to express. 175 pA was chosen to put the one-hop
measurement -- the direct, least confounded one -- on target, rather than to minimise total
error across a comparison whose shape we know is wrong. The 0.36 ms residual on DLMn is
that structural mismatch, not slack in the fit.

**A prediction that did not come true, at a resolution that cannot settle it.** The
criterion predicted the escape threshold would fall about 2.4 degrees, because the muscle
now hears 4.2 ms sooner. It did not move: 38.6 degrees before and after. The metric is
quantised by the frame at which angular size is sampled, in steps of roughly 2 degrees, so
a 2.4 degree shift is one quantum and the takeoff fell in the same frame. **Neither
confirmed nor refuted** -- recorded that way rather than claimed as a success.

The channel calibration was re-run as the criterion required. Velocity gain 2.2 with size
gain 227.7 still passes both targets at 38.6 degrees and still sits centrally in the
passing region, so no refit was needed. All 15 `--check` assertions pass on the real
connectome.


**Subgoal.** Give the electrical synapses their own conduction delay and time constant, so
the giant fiber reaches muscle in roughly the measured latency instead of 5.5x it.

**The gap, measured at the current calibration.**

| | model | published | error |
|---|---|---|---|
| GF -> TTMn (jump) | 5.10 ms | 0.93 ms | **5.5x** |
| GF -> DLMn (wing) | 10.60 ms | 1.44 ms | **7.4x** |

For scale: the animal's entire short-mode takeoff completes in **under 6.87 ms** (Ache et
al. Fig 1C). Ours has not reached the wing muscle by then.

**Cause, already known and not in doubt.** `ELECTRICAL_SYNAPSES` restores two gap-junction
pathways that EM connectomics cannot see, but restores only their *strength*. They still
inherit a chemical synapse's 1.8 ms axonal delay and 5 ms synaptic time constant. A gap
junction has neither: it is a direct resistive connection, effectively instantaneous, with
no synaptic filtering. We fixed the amplitude of that pathway and left its dynamics wrong.

**Why the engine refuses.** `lif.py` uses **one shared ring buffer** of spike vectors and
raises explicitly if `delay_ms` varies by population. The delay is a property of the buffer,
not of the connection. Heterogeneous delay means either several buffers or a restructure.

**Done-criterion.** GF -> TTMn within **0.93 +/- 0.5 ms** and GF -> DLMn within
**1.44 +/- 0.7 ms**, with every existing `--check` assertion still passing on the real
connectome. If a delay small enough to hit the first target cannot be represented at the
brain timestep, that is the result and it is a statement about `brain_dt_ms`, not a failure
to be tuned around.

**What could make the measurement lie**, written before measuring:

* **The threshold will move, and that is expected, not a regression.** The muscle hearing
  4.17 ms sooner means the threat is ~2.4 degrees smaller when the takeoff is recorded:
  38.6 -> roughly 36.2. That is still inside 39 +/- 3 but close to the edge. **Re-run
  `tools/calibrate_channels.py` afterwards**, and if the refit lands outside the band, say
  so rather than widening the band.
* **A 0.93 ms target against a 0.4 ms interactive timestep is two samples.** Interactive
  runs use `brain_dt_ms = 0.4`; a delay of 1-2 steps is all the resolution there is, so the
  interactive and headless numbers will differ. Report both, and do not fit to the headless
  one and quote it as the model's latency.
* **Latency is measured between *first spikes* of populations**, which is not the same as
  the latency of one connection. TTMn's first spike could in principle be driven by a route
  other than the gap junction. Verify the path before attributing the improvement to it.
* **A shared delay buffer means changing the global `delay_ms` moves everything.** If the
  fix is implemented as "make the global delay smaller", every pathway in the model speeds
  up and the escape threshold moves for a second, unrelated reason. The change must be
  *per-connection* or the measurement is confounded.
* **Two targets, one mechanism.** GF->TTMn is direct; GF->DLMn goes through PSI and so
  carries one more synapse. If both land only by tuning two numbers independently, the fit
  is unconstrained in the way Step C was. Prefer one physically motivated change (gap
  junctions are fast) over two fitted delays.

**Not in scope for this step.** Making the rest of the network conduct. Step I established
that 95% of the model is inert and that this does not block the behavioural goal; this step
fixes a latency inside the working wire, nothing more.

### Step K, run:  escape direction from the neurons, not from the geometry

The first step that moves the *behaviour* rather than the reflex. Every previous step
improved when the fly jumps; this one is about where it goes.

**What happens today.** `GiantFiberDecoder._escape_heading` reads `obs.threat_position` and
`obs.agent_position` and returns the unit vector between them. The decoder — whose job is
to read brain state — is reading the world. The heading is geometry wearing a decoder's
coat, and the scorecard has said so all along: *escape direction is away from the threat,
**not neural***.

**What is available instead.** The motor output carries sides: 2 giant fibers (DNp01 left
and right), 2 TTMn (left and right), 2 PSI, and 11 DLMn split across both. So a left/right
balance — spike counts, or first-spike times — can be read from the muscles the model
already drives.

**K1 result: there is a bearing-dependent signal at the jump muscle, and it is the wrong
shape.** TTMn first-spike time, left minus right, three seeds per bearing:

| threat bearing | retinotopy ON | retinotopy OFF (control) |
|---|---|---|
| 45 deg (right) | **-958.7 +/- 651.6 ms** | -26.7 +/- 10.0 ms |
| 135 deg (LEFT) | +9.3 +/- 9.4 ms | -20.0 +/- 8.6 ms |
| 225 deg (LEFT) | +1.3 +/- 10.0 ms | -22.7 +/- 6.8 ms |
| 315 deg (right) | **-938.7 +/- 625.6 ms** | -28.0 +/- 8.6 ms |

**The control behaves exactly as it must.** With hemifield tuning off there is no azimuth in
the input, and the left-right difference becomes a **constant ~-25 ms at every bearing** --
a fixed wiring asymmetry, with no bearing dependence whatever. That is the control §2a's
retracted result never had, and it works.

**But the ON signal is not a directional code.** A graded ipsilateral-earlier response would
show a smooth swing with bearing. What we have is nearly binary and one-sided: for
**right-side** threats the right TTMn does not fire during the approach at all -- its 2,720
and 2,820 ms times are a *later* encounter, after the first escape -- while left-side threats
fire both sides within ~5 ms of each other. The effect is real and it is bearing-dependent,
but it reads as **one side failing** rather than as the two sides being differently timed,
and it is lopsided in a way no symmetry argument predicts. This is very likely the same
**34% left/right convergence asymmetry** already recorded as uncorroborated (§ open items),
now showing up behaviourally.

**A measurement error, caught.** The first pass read the `MOTOR` population and reported a
difference of exactly 0.00 ms at every bearing. `MOTOR` contains TTMn *and* PSI, and the
wiring shows why that matters: each giant fiber drives only its **own** side's TTMn, but
**both** PSI. The bilaterally-driven PSI fires on either side at the same instant and pins
the difference to zero. Reading the population instead of the cell type hid the entire
result. The pre-measurement list did not anticipate this, and should have: *check whether
the population you are reading mixes side-specific with bilateral cells.*

**K2 is now the decisive test and is not yet run.** The signal exists; whether the *wiring*
produces it is unanswered, because hemifield tuning is what puts azimuth into the drive in
the first place. Until a type-preserving shuffle is compared against this, the honest
statement is that our encoder's tuning reaches the jump muscle -- not that the fly's
connectome computes direction.

**K2, and it answers a different question than the one it was written for.** Before running
the shuffle, the convergence onto each giant fiber was measured:

| giant fiber | drive from left eye | from right eye | total |
|---|---|---|---|
| DNp01 **left** | 12.84 | 0.00 | **12.84** |
| DNp01 **right** | 0.01 | 9.56 | **9.56** |

Visual input is **perfectly ipsilateral**, with no crossover — and the two sides differ by
**34%**. That is the asymmetry already sitting in the open items as uncorroborated. It is
identical under the split and combined encoders (9.56 against 9.58), so the split did not
cause it.

**Equalising the two giant fibers changes everything.** Scaling the right one's incoming
weight by 12.84/9.56 and repeating the bearing sweep:

| bearing | as measured | giant fibers equalised |
|---|---|---|
| 45 deg (right) | -958.7 +/- 651.6 ms | **-26.7 +/- 5.0 ms** |
| 135 deg (LEFT) | +9.3 +/- 9.4 ms | **+33.3 +/- 1.9 ms** |
| 225 deg (LEFT) | +1.3 +/- 10.0 ms | **+34.7 +/- 3.8 ms** |
| 315 deg (right) | -938.7 +/- 625.6 ms | **-36.0 +/- 5.7 ms** |

That is a clean, graded, bilateral directional code: **the ipsilateral jump muscle fires
27-36 ms earlier, the sign flips correctly with side, and the spread collapses from +/-650
ms to +/-2-6 ms.**

**So K1's signal was the asymmetry masking the code, not the code itself.** The -958 ms
"direction" was the right giant fiber failing to fire during the approach, because it
receives 34% less drive and the current calibration puts it below threshold where the left
one is above. Remove the asymmetry and the real signal is underneath, and it is far better
than the one it was hiding. This also restores the earlier result -- "both giant fibers fire
earlier for a threat on their own side" (§ above) -- which the new calibration had appeared
to overturn.

**Is the 34% real?** Two reasons to doubt it. The dataset has 42% postsynaptic completion
and only 40.1% of synapses with both partners proofread, so a hemispheric difference in
traced convergence is very plausibly proofreading depth. And the dataset paper states that
**"the sensory and motor periphery are largely isomorphic"** (§0b) -- which argues against a
genuine 34% asymmetry in exactly this pathway. Neither settles it, and the paper offers no
left-right comparison to check against.

**What must NOT happen next.** Equalising the giant fibers is an intervention run to test a
hypothesis, and it worked as one. Adopting it as a model default would be a fitted
correction applied to measured anatomy to make a result appear -- precisely what §1 forbids.
If it is adopted it must be as a **declared, switchable hypothesis about reconstruction
completeness**, with the raw asymmetry still reachable, and with the shuffle control run
against both. The shuffle that K2 was written to run has still not been run.

**K2 proper: the directional code requires the measured wiring.** TTMn left-minus-right
first spike, averaged over two bearings and two seeds per side, on the equalised network:

| wiring | threat RIGHT | threat LEFT | flips? |
|---|---|---|---|
| **MEASURED** | **-35.0 ms** | **+31.0 ms** | **yes** |
| type-preserving shuffle | -13.0 ms | -4.0 ms | no |
| degree-preserving shuffle | no spikes | no spikes | no conduction |

The type-preserving shuffle is the strong null: it keeps every cell type, the weights
between every pair of types, the recorded sides, hemifield tuning, and the restored gap
junctions. It differs from the real network in exactly one respect -- which individual
cells are wired to which. **It cannot reproduce the flip.** What survives in it is a small
constant left-lead of a few milliseconds, with no bearing dependence, which is the same
shape as the retinotopy-off control's constant ~-25 ms.

So the answer to the question K2 was written to ask is: **not just our own tuning handed
back.** Hemifield tuning supplies azimuth to both networks equally; only the measured one
turns it into a sign that follows the threat.

**A correctness fix the null models needed first.** `_rebuild` listed the fields to carry
across explicitly, and `fast_weights` -- added the same day for the gap-junction latency --
was not among them. Every shuffle would have been built without the electrical synapses, so
the escape pathway would not have conducted and each null would have failed for a reason
having nothing to do with its wiring. That is the rigged comparison the tool's own docstring
warns against, reintroduced by a field addition elsewhere. Now uses `dataclasses.replace`,
so a new field is carried by default rather than silently dropped.

**Three things this result is not.**

* It is **two seeds and two bearings per side**, not a distribution. The separation is large
  against K1's measured spread of +/-2-6 ms, but the sample is small.
* The degree-preserving shuffle produced **no spikes at all**, so it says nothing about
  direction. It fails an earlier gate -- conduction -- and must not be counted as a second
  independent confirmation.
* It is measured on the **equalised** network. On the raw one the 34% convergence asymmetry
  stops the right giant fiber firing at all for right-side threats, so there is no usable
  code to test. The honest form of the claim is therefore conditional: *if* the asymmetry is
  a reconstruction artefact, the measured wiring computes escape direction and no shuffle of
  it does. If the asymmetry is real biology, this model's fly is deaf on one side and the
  code is not available to it.

**K3 result: the escape direction is neural, and it is much worse than the geometry it
replaces.** `--neural-heading` reads which jump motor neuron fired first and turns away from
that side, using the spikes and the fly's own body axis. The threat's coordinates are never
read.

Escape heading against the true away-from-threat direction (+1 straight away, 0 chance):

| | takeoffs | mean dot | away from threat |
|---|---|---|---|
| geometric (scripted) | 8 | **1.000** | 100% *by construction* |
| neural, raw wiring | 16 | 0.069 | 62% |
| neural, equalised | **63** | **0.351** | **76%**, p < 0.0001 |

On the equalised network over 8 bearings and 4 seeds it is **significantly better than
chance** -- 48 of 63 takeoffs directed away, one-sided binomial p < 0.0001 -- with a **mean
angular error of 69 degrees**. All 15 `--check` assertions still pass.

**At n = 16 this was not significant** (11 of 16, p = 0.105) and the first pass nearly went
into the journal as a pass. It took 63 takeoffs to establish. Worth remembering: "better
than chance" is a claim with a sample size attached, and four bearings times two seeds does
not carry it.

**Why it is coarse, and why that is honest.** The measured signal is a 27-36 ms lead of the
ipsilateral TTMn. That says which *side* the threat is on and nothing about where within
that side, so the decode turns a fixed 90 degrees and is wrong by however far the threat sits
from straight abeam. A graded heading could be fitted from the timing magnitude, but nothing
has shown that magnitude maps linearly onto bearing, and fitting one would be inventing
precision the measurement does not have. The 90 degrees is itself invented and labelled as
such (`neural_turn_deg`).

**So the trade is explicit:** mean dot falls from 1.000 to 0.351, and in exchange the
direction stops being read from coordinates the brain cannot see. Off by default. The
geometric heading remains the accurate one and the honest description of it is unchanged --
it is not a model of anything.

**Still conditional on the equalisation.** On the raw wiring the same decode manages 0.069
and 62%, because the right giant fiber does not fire for right-side threats. K3 inherits the
caveat from the asymmetry work: this is what the model does *if* the two sides are symmetric,
which the dataset cannot rule out and cannot confirm.


**Run it in three parts, cheap first.**

**K1 — is there a usable signal at all?** Sweep the threat's starting bearing around the
fly and measure, at the motor neurons, the left-right difference in first-spike time and in
spike count. *Done-criterion:* the difference must separate ipsilateral from contralateral
threats by more than the trial-to-trial spread across seeds. If it does not, the rest is
moot and that is the result.

**K2 — is it the wiring, or is it our own encoder handed back?** This is the whole
experiment. Directional information only exists in this model because `--retinotopy`
scales each cell's drive by how near the threat is to its eye — **we put the azimuth in**.
Reading azimuth back out of the motor neurons and calling it neural direction would be
circular. *Done-criterion:* the K1 signal must be **larger on the real connectome than on a
type-preserving shuffle given the same tuning budget** (`tools/shuffle_control.py`,
`tools/direction_control.py`). If the shuffle does as well, the wiring contributes nothing
and the honest report is that the encoder's tuning survives transit — which is not a
finding about the fly.

**K3 — use it.** Replace the geometric heading with one decoded from the motor balance.
*Done-criterion:* escapes still go away from the threat more often than chance, and
`--check`'s existing assertions still pass.

**What could make the measurement lie**, written before measuring:

* **This exact experiment has already produced one retracted result.** §2a: a +128 ms
  front/rear difference that was a start-up teleport artefact, and which persisted with
  retinotopy *off* — the tell that it was not neural at all. **Reuse the warm-up in the
  existing tools; do not rebuild the harness.** Any new harness must be checked with
  retinotopy off, where the answer must be *no signal*.
* **The polarity of the retinotopic map is undetermined** (§4). We may recover direction
  with the sign inverted. K1 and K2 ask whether left and right are *distinguishable*;
  which is which is a separate unresolved question and must not be quietly fixed by
  flipping a constant until the plot looks right.
* **n = 2 per side, and the left GF is bimodal.** Measured previously: 1104, 968, 1112,
  1104, 964 ms on repeated left threats. A mean over such a distribution is not a
  measurement. Report the spread, and compare each cell against *itself* across conditions
  rather than left against right — the earlier "one-sided response" was an artefact of the
  latter.
* **Only ~26 cells downstream of the injection conduct** (Step I). The directional signal
  has to survive a very thin path, and there is no population averaging to smooth it.
* **A weak signal here may be biologically correct.** The GF drives the *short-mode*
  takeoff, which is the fast stereotyped one; directed escape is associated with the
  long-mode sequence and with pre-takeoff leg posture, which this model does not have. A
  null result at K1 should be read as "the GF pathway is not where direction lives",
  not as "the model failed".
* **`escape_bias_deg` already rotates the heading.** If it is non-zero, a decoded heading
  will be compared against a target that is itself offset. Zero it for the comparison or
  account for it explicitly.

**Out of scope for this step.** Pre-takeoff leg posture, which the scorecard marks out of
reach and which is where the animal's directional control mostly lives. K3 replaces a
geometric constant with a neural readout; it does not claim to reproduce how a fly aims.

### The 34% asymmetry, measured against the dataset's own distribution

Whether the giant fiber's left/right convergence difference is biology or reconstruction was
blocking K3. Rather than argue it, it was measured against every other bilateral cell type in
the subgraph -- turning a judgement about someone else's data into a comparison with that
data's own spread. No refetch: all of this is in the cache.

**Asymmetry is pervasive, and it is not sampling noise.** Absolute left/right difference in
total excitatory input, by cell type:

| restriction | types | median | within 10% |
|---|---|---|---|
| >= 1 cell per side | 444 | 29.2% | 17% |
| >= 3 cells per side | 112 | 35.9% | 16% |
| >= 5 cells per side | 72 | 41.9% | 10% |
| **>= 10 cells per side** | **62** | **42.9%** | **8%** |

If this were small-sample noise it would shrink with better sampling. It **grows**. Only 8%
of well-sampled bilateral types have their two sides within 10% of each other.

**It is also systematic, and it runs the opposite way to the giant fiber's.** Of the 112
well-sampled types, **79% are right-biased**, median signed imbalance -0.198. Over the whole
subgraph, left receives 2,693 pA against right's 3,733 -- a ratio of **0.722**, or about 20%
per cell after accounting for the 10,606/12,209 cell-count difference.

The giant fiber's visual input ratio is **1.339** -- left-heavy, against a dataset that is
globally right-heavy. So the easy explanation is not available: **this is not the global
tracing bias showing through**, because the global bias points the other way.

**What can be concluded, and what cannot.**

* **Cannot** conclude the 34% is a reconstruction artefact. It runs against the systematic
  bias, so it is not simply one hemisphere traced more deeply.
* **Cannot** conclude it is biology either. The median well-sampled bilateral type in this
  dataset differs between sides by **43%**. A 34% difference is *below this dataset's own
  noise floor for left/right claims*. It is not distinguishable from the amount by which
  this reconstruction routinely differs between sides for no biological reason.
* **Can** conclude that **no left/right claim from this dataset is safe at the 34% level**,
  and that includes any our own model makes. That is the finding, and it is more useful than
  a verdict on this one pathway would have been.

**Consequence for the model.** Equalising the giant fibers is therefore a **declared
sensitivity test**, not a correction: *if the two sides were symmetric -- which the dataset
cannot rule out at this magnitude -- the measured wiring computes escape direction and no
shuffle of it does (K2).* It must be labelled that way wherever it appears, and the raw
asymmetry must stay reachable. Adopting the equalised network as the default and quietly
dropping the qualifier would be exactly the move §1 forbids.

**This also bears on the dataset paper's own claim.** §0b records "the sensory and motor
periphery are largely isomorphic". That may well hold for the *anatomy*; the **traced
connectivity** is not isomorphic, differing by ~43% at the median between sides. Those are
compatible statements about different things, and the distinction matters for anyone using
this data quantitatively.

**Two bugs found by driving it, and the fix more than doubled the directional accuracy.**
Ranuja reported that the fly could be steered into near-perfect circles, and that it escaped
from a pointer that was not moving.

**1. The size channel had no motion requirement.** Ache et al. state that LPLC2 *"though
they encode looming size, require looming motion to be active"* -- they are radial motion
opponency detectors. Their Gaussian was fitted to LOOMING stimuli, where size and expansion
co-vary. Read as a function of instantaneous size alone, it says a stationary object of 42
degrees drives LPLC2 at full strength forever. Measured:

| motionless object at | before | after |
|---|---|---|
| 25 deg | GF fires at 55 ms, 1 takeoff | **silent** |
| 42 deg | GF fires at 46 ms, 1 takeoff | **silent** |
| 60 deg | GF fires at 48 ms, 1 takeoff | **silent** |

The fly was jumping at furniture. `size_requires_motion` gates the channel on expansion,
softly, so it does not chatter on noise around zero. **The escape threshold is unchanged at
38.6 degrees**, so nothing needed refitting.

**This was written down in the Step F criterion and not acted on.** The exact words were:
"our size channel is a function of instantaneous angular size alone, so a stationary disk of
42 degrees drives it at full strength. This is a real discrepancy in its own right and must
be recorded separately." It was recorded and then left. A known defect in a list is not a
fixed defect, and this one took a person driving the model to surface.

**It also shows how a true test can cover the wrong half of the space.** The scorecard row
"LPLC2 is silent with nothing approaching" passed -- 0 of 1,501 frames -- but it was measured
on a *distant* object subtending a small angle, where the log Gaussian is correctly near
zero. It never tested a LARGE stationary object, which is the case that failed.

**2. The neural heading re-aimed on every spike, which traces a circle.** The decode turns a
fixed 90 degrees from the *current* body axis. TTMn keeps firing through a flight, so the
rotation was reapplied again and again -- and repeatedly rotating a heading by a constant
angle is a circle. It now re-aims only when the threat changes **side**. A short-mode escape
is ballistic, and nothing measured here supports re-aiming mid-flight from an unchanged
signal.

**Effect of the two together**, 8 bearings x 4 seeds on the equalised network:

| | takeoffs | mean dot | away from threat | mean error |
|---|---|---|---|---|
| before | 63 | 0.351 | 76% | 69 deg |
| **after** | **59** | **0.878** | **98%** | **29 deg** |

All 15 `--check` assertions still pass. The remaining 29 degrees is the honest floor of a
side-only decode: the neurons say which side, not where within it.

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

## 0b. What the dataset paper says, and what it does not

*Sexual dimorphism in the complete Drosophila male central nervous system connectome*, Cell,
3 Sept 2026 (bioRxiv 10.1101/2025.10.09.680999). Read via the open preprint; the Cell
version is paywalled.

**The dataset.** 166,691 neurons including sensory axons, 46 million presynapses connected
to 312 million PSDs, 11,691 unique cell types. `superclass` is documented as encoding
"the direction of information flow, anatomical location and broad function" — which is what
we had inferred from its values, so our population assignment rests on the intended meaning.

**Completeness, and what it does not excuse.** 94% presynaptic and 42% postsynaptic
completion; only **40.1%** of detected synapses have *both* partners belonging to a
proofread neuron. That undercounts connections to incompletely traced cells — but **not**
connections between two fully proofread ones. DNp01 and PSI are both named, proofread types,
so the measured counts between them (L→L 9, R→L 3, R→R 2, L→R 2) are real weights, not
tracing artefacts.

That weakens the justification given for exempting them from the weight floor. The exemption
still stands on its original ground — a gap junction is invisible to EM whatever the chemical
count — but it should be read honestly: **applying 55 pA to all four edges asserts a
bilateral symmetry the chemical data does not show**, since one edge is 4.5x another.

**Two of our choices are unsupported by the paper.** It gives *no recommended minimum
synapse threshold*, so `min_synapses = 5` is ours alone — and it has already cost us once.
And it reports *no left-right hemispheric comparison*, so our finding that the left Giant
Fiber receives 34% more convergence (6,418 against 4,780 synapses) is uncorroborated: it may
be anatomy or it may be tracing variance, and this paper cannot distinguish them.

**One worry resolved.** "Sex-specific and dimorphic neurons are concentrated in higher brain
centres while the sensory and motor periphery are largely isomorphic." The escape pathway
sits in that periphery, so comparing our male-CNS figures against literature measured in
female flies — which most of the scorecard does — is justified.

**What it does not contain.** No discussion of the giant fiber, LC4, LPLC2, TTMn, PSI or the
escape circuit. It is a whole-connectome and dimorphism paper; the escape pathway has to come
from the specialist literature.

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

### 1a. What the literature is for, and where it must stop

Added after a proposal to implement the two inhibitory components of Ache et al.'s eq. 7,
which this document had called "the most substantial known gap between our encoder and
theirs". That framing was wrong, and the reason it was wrong is worth stating as a rule.

**Their model and ours are different kinds of model.** Ache et al. fit curves to recorded
giant-fiber voltage: a phenomenological description of what the neuron does. This is a
mechanistic simulation: leaky integrate-and-fire cells wired by measured synapses, from
which behaviour is supposed to *emerge*. Two models of the same animal, answering different
questions. They should not converge in implementation, and a gap between them is not
automatically a defect in ours.

So published values sort into three kinds, and only two of them may enter the code:

* **Targets — always adopt.** What the system must *do*: the ~39 degree threshold, the
  LPLC2 lesion abolishing escape, the 0.93 ms giant-fiber-to-muscle latency, the direction
  of the speed dependence. These constrain without dictating, and they are what the
  scorecard is made of.
* **Boundary conditions — adopt the form.** Where our model simply *has no upstream*. We do
  not simulate photoreceptors or the optic lobe, so current is injected into LC4 and LPLC2
  directly; eqs. 3 and 4 describe exactly the machinery we are missing, and using them is
  honest substitution rather than smuggling. They are labelled as the boundary they are.
* **Mechanisms the wiring is supposed to explain — never adopt.** The inhibitory components
  of eqs. 5 and 6 are *downstream* of the boundary. They describe what the giant fiber's
  presynaptic inhibitory partners do — and **we have those cells**, 3,688 of them in the
  INH population, wired by measured synapses. Pasting in a fitted sigmoid would replace a
  prediction with an assumption, and the model could no longer be wrong about it.

**The test of a rule is what it forbids.** This one forbids the change that would most
improve our agreement with the published traces, and it forbids it precisely *because* it
would improve that agreement without the wiring having earned it.

**It also converts a gap into an experiment.** Eqs. 5 and 6 stop being components we lack
and become a **prediction we can check**: does the connectome's own inhibition reproduce
the measured tonic hyperpolarization — a sigmoid in angular size, saturating near 66
degrees — and the small LC4-dependent dip near 26 degrees? That is a real test of the
wiring, with published curves to fail against, and it is worth far more than reproducing
those curves by construction.

**The boundary is a judgement, not a formula.** Where our model has no upstream, published
description is the only option; where it has the cells, the cells must do the work. Cases
that sit near the line get argued in this document before code is written, not after.

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
