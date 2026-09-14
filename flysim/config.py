"""Every tunable number in the simulation, in one place.

Frozen dataclasses so a config cannot be mutated halfway through a run (a classic source
of irreproducible results). Use :func:`dataclasses.replace` to derive a variant, and
:meth:`SimConfig.from_json` to load overrides from ``configs/*.json``.

JSON rather than YAML on purpose: ``json`` is in the standard library, and the Starter
Phase promise is that it runs with numpy and matplotlib and nothing else.

Default parameter values are chosen to be *plausible* for Drosophila central neurons, not
to reproduce any specific published recording. Where a value is a modelling convenience
rather than a measurement, the comment says so.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NeuronParams:
    """Single-compartment leaky integrate-and-fire parameters.

    These are the *defaults*; :class:`~flysim.brain.connectome.Connectome` may override
    any of them per population (a Giant Fiber does not integrate like an LC4).

    Fly central neurons are small and have high input resistance — values in the GΩ range
    are typical, which is why tens of picoamps produce tens of millivolts here.
    """

    v_rest_mv: float = -52.0
    """Resting potential. Fly central neurons rest more depolarised than the textbook
    mammalian -70 mV."""

    v_reset_mv: float = -60.0
    """Post-spike reset potential. Below rest, producing a brief after-hyperpolarisation."""

    v_threshold_mv: float = -45.0
    """Spike threshold. The 7 mV gap from rest is small, so modest input drives firing."""

    v_floor_mv: float = -85.0
    """Hard clamp on how negative the membrane may go. Physically motivated (the chloride
    reversal potential is a real floor) and numerically useful: it stops strong inhibition
    or a mis-specified weight matrix from producing a runaway negative voltage."""

    tau_m_ms: float = 10.0
    """Membrane time constant, ``R_m * C_m``. Sets how long the neuron integrates."""

    r_m_gohm: float = 1.0
    """Input resistance. 1 pA x 1 GΩ = 1 mV, so this doubles as the pA->mV gain."""

    tau_syn_ms: float = 3.0
    """Synaptic current decay. Fast, matching nicotinic cholinergic transmission."""

    refractory_ms: float = 2.0
    """Absolute refractory period: the neuron is clamped at reset and cannot spike."""

    delay_ms: float = 1.0
    """Axonal + synaptic transmission delay. This is what makes signal propagation
    visible as a staircase across layers in the telemetry panel rather than instantaneous."""

    bias_current_pa: float = 0.0
    """Constant background drive, e.g. tonic excitation from outside the modelled circuit."""

    noise_mv: float = 0.35
    """Standard deviation of membrane potential noise. Stands in for channel noise and
    unmodelled synaptic bombardment; it is what gives the traces their fuzz and makes
    spike timing jitter trial-to-trial."""


SHIU_2024 = NeuronParams(
    # Published leaky integrate-and-fire parameters for whole-brain Drosophila
    # connectome simulation (Shiu et al., Nature 2024), as used by other connectome
    # simulators. Adopted for REAL connectomes so results are comparable to a reference
    # model rather than only to themselves.
    #
    # Note what is uniform here: every neuron gets identical biophysics. Any difference
    # in behaviour between cell types then comes from the wiring, which is the point --
    # per-population tuning would let the modeller smuggle in the answer.
    v_rest_mv=-52.0,
    v_reset_mv=-52.0,      # resets to rest: no after-hyperpolarisation
    v_threshold_mv=-45.0,
    tau_m_ms=20.0,
    tau_syn_ms=5.0,
    refractory_ms=2.2,
    delay_ms=1.8,
)
"""Reference parameter set. See docs/CONNECTOME_ACCESS.md for provenance.

The one thing NOT fixed by the reference is synaptic strength: that paper expresses it as
a millivolt step times a global gain, while this engine works in picoamps through an input
resistance. The conversion depends on the synapse model, so ``pa_per_synapse`` stays a
calibrated free parameter -- see tools/calibrate_pa.py.
"""


@dataclass(frozen=True)
class EnvParams:
    """2D arena and predator pursuit parameters."""

    arena_half_width_m: float = 0.55
    """Arena spans [-w, +w] on both axes. Wide enough that a full escape trajectory fits
    without bouncing off a wall."""

    fly_start: tuple[float, float] = (0.0, 0.0)
    predator_start_distance_m: float = 0.60
    """Initial fly-predator separation. Set to 0 to exercise the coincident-position
    edge case."""

    predator_start_angle_deg: float = 200.0
    """Bearing of the predator's starting position relative to the fly."""

    predator_speed_ms: float = 0.42
    """Pursuit speed. A real predatory strike is far faster; this is slowed so the
    looming ramp is visible in the dashboard."""

    threat_size_m: float = 0.020
    """Physical extent ``l`` of the looming object. Drives the ``l/d`` ratio."""

    fly_jitter_ms: float = 0.010
    """Std-dev of noise added to the walking velocity, m/s."""

    # --- Idle locomotion -------------------------------------------------------
    # Drosophila do not drift like Brownian particles. They walk in bouts along a body
    # axis, punctuated by rapid turns ("body saccades"), and stop frequently. Modelling
    # that is what stops the fly reading as a robot sliding on rails.
    #
    # IMPORTANT: this is kinematics, not neuroscience. No locomotor circuit produces it;
    # it is a scripted stand-in so the animal looks alive between escapes. Only the
    # ESCAPE is neurally driven. Do not report walking statistics from this model.

    fly_walk_speed_ms: float = 0.018
    """Forward walking speed during a bout. Drosophila walk at roughly 10-25 mm/s."""

    fly_saccade_rate_hz: float = 1.6
    """Rate of spontaneous turns. Each is near-instantaneous, as real body saccades are."""

    fly_saccade_deg: float = 65.0
    """Mean turn magnitude; sign is random and the size is drawn around this."""

    fly_pause_rate_hz: float = 0.9
    """Rate of switching between walking and standing still."""

    fly_walk_fraction: float = 0.65
    """Fraction of time spent walking rather than standing."""

    # --- Escape flight ---------------------------------------------------------
    # An escape is three phases, not one ballistic coast: a fast jump, a stretch of
    # powered flight away from the threat, then a landing. Modelling it as pure drag
    # decay from the takeoff velocity gets both ends wrong — the jump has to be slow to
    # decay (or the fly never outruns a pursuer), which makes the flight last seconds and
    # cross the whole arena, so the animal spends all its time gliding and never walks.

    fly_cruise_speed_ms: float = 0.62
    """Powered flight speed after the initial jump. Must exceed the predator's speed or
    escaping is impossible in principle."""

    fly_flight_duration_s: float = 0.85
    """How long powered flight lasts before the fly settles and lands."""

    fly_max_turn_rate_deg_s: float = 900.0
    """Cap on how fast the fly can change heading in flight. Escape turns are genuinely
    fast — banked within tens of milliseconds — but not instantaneous, and a cap turns a
    sequence of corrections into a curve rather than a zigzag."""

    fly_jump_decay_per_s: float = 11.0
    """How fast the takeoff impulse bleeds off toward cruise speed. High: the jump itself
    is brief."""

    fly_drag_per_s: float = 7.0
    """Deceleration once flight ends, 1/s. High enough that landing takes a fraction of a
    second rather than seconds."""

    fly_hop_drag_per_s: float = 30.0
    """Deceleration of an UNPOWERED escape -- legs only, wings never recruited, 1/s.

    Much higher than `fly_drag_per_s`, which describes a fly coasting on wings that have
    stopped beating. Without a wingbeat there is nothing holding the animal up, so the
    jump is spent almost immediately: at this value a 1.6 m/s takeoff is down in about
    0.11 s having covered roughly 5 cm, against 0.5 s and 22 cm on the flight drag.

    This number is SCRIPTED, chosen so an unpowered escape reads as a hop rather than a
    glide. What is measured is *which of the two happens* -- that comes from whether the
    dorsal longitudinal motor neurons fired. The shape of each is still invented."""

    landing_speed_ms: float = 0.06
    """Below this speed the fly is considered to have landed, which re-arms the reflex.
    The escape is a repeatable reflex, not a one-shot: a fly that lands next to a still-
    approaching predator will jump again."""

    capture_distance_m: float = 0.012
    """Below this separation the predator has caught the fly and the episode ends."""

    escape_success_distance_m: float = 0.28
    """Once airborne and this far from the predator, the getaway has succeeded and the
    episode ends. Without it the predator simply re-closes and the run has no ending."""

    duration_s: float = 2.4
    """Episode time limit."""

    seed: int = 7


@dataclass(frozen=True)
class MotionParams:
    """T4/T5 elementary-motion-detector encoder parameters.

    Separate from :class:`EncoderParams` because it is a different modality with its own
    calibration, not a variant of looming. Looming asks "is it getting closer"; this asks
    "is it sweeping across the eye", and an object can do either without the other.
    """

    efference_copy: float = 1.0
    """How much of the fly's OWN motion is cancelled before encoding, 0 to 1.

    A retina cannot tell whether an image expanded because an object approached or because
    the animal advanced. `EnvObservation.closing_speed` is computed from the RELATIVE
    velocity and so contains both, which is physically correct and sensorily wrong: it
    made the fly flee its own forward motion. Measured with the threat held perfectly
    still (0.0016 m/s) while the fly flew at it at 1.04 m/s -- 50 pA of drive and two
    mid-flight course corrections away from a motionless object. That is what a full
    U-turn toward a stationary observer was.

    Real flies solve this two ways. The spatial pattern differs -- self-motion flows the
    whole visual field outward, an approaching object expands locally against a static
    surround -- and that discrimination needs retinotopy this encoder does not have, in a
    world with a background this arena does not have. What is left is efference copy: a
    signal from the motor side that cancels the predicted sensory consequence of
    self-generated movement, documented in Drosophila for the lobula plate.

    1.0 is complete cancellation, which is available here only because the fly's motion is
    scripted and therefore exactly known; a real corollary discharge is partial. Set to
    0.0 to recover the raw relative-velocity behaviour."""

    target_population: str = "T4T5"

    gain_pa: float = 12.0
    """Picoamps per radian/second of azimuthal sweep.

    Deliberately below the looming gain. T4/T5 feed LC4 and LPLC2 through measured
    wiring, so motion drive reaches the Giant Fiber whether or not that is desirable --
    and a real fly does not escape from things merely moving past it. This is the
    number to turn down if translational motion starts triggering takeoffs."""

    size_reference_deg: float = 20.0
    """Angular size at which an object is treated as filling its share of the field.

    Drive scales with ``min(theta / this, 1)``. Without it a distant speck sweeping fast
    would drive the motion detectors as hard as a looming wall, because the encoder has
    no retinotopy and therefore no notion of how many columns an object covers."""

    max_rate_rad_s: float = 40.0
    """Sweep rate above which the drive saturates, rad/s."""

    max_current_pa: float = 140.0
    """Per-neuron ceiling, matching the looming encoder's."""

    min_distance_m: float = 0.002
    """Division-by-zero guard, as in the looming encoder."""


@dataclass(frozen=True)
class EncoderParams:
    """Looming (visual expansion) encoder parameters."""

    split_feature_channels: bool = False
    """Drive LC4 and LPLC2 as the two different feature detectors they are.

    Ache et al. 2019 measured that these populations do NOT compute the same thing:
    **LPLC2 encodes angular SIZE, LC4 encodes looming SPEED**, and the giant fiber's
    response is a linear function of angular velocity from LC4 plus a Gaussian function of
    angular size from LPLC2. Driving both with one expansion-rate signal, as this encoder
    did, collapses two measured channels into one.

    It also explains two scorecard failures at once. Our escape fired at 16.7 degrees
    against a published GF-mediated takeoff threshold of ~39 (von Reyn et al. 2014); a
    Gaussian centred on 42 degrees is exactly what holds a fly back until the object is
    large, and without it a monotonically rising velocity signal fires as soon as it can.
    And silencing LPLC2 is published to remove the size component while leaving velocity —
    which a model with no size component cannot reproduce.

    Off by default so the two conditions stay comparable."""

    size_peak_deg: float = 42.0
    """Angular size at which the LPLC2 size channel peaks. Published: C3 = 42 degrees."""

    size_width_deg: float = 18.0
    """Width of the size Gaussian in DEGREES. Used only by ``size_tuning_form="linear"``.

    Fitted, never measured, and now superseded: the published Gaussian is in log-angle with
    width C4 = 0.52 (see `size_log_width`), so this parameter belongs to the alternative
    form kept for comparison rather than to the model as run. It is the value the linear
    form was fitted to under two published targets, and 18 was the only width that passed
    across that sweep -- see MODEL_JOURNAL.md Steps C and D.
    """

    size_gain_pa: float = 227.7
    """Picoamps at the peak of the size channel.

    **No longer independently fitted.** Ache et al. 2019 fixes the RATIO of the two
    channels, which this model previously treated as two free numbers. From eqs. 3, 4 and 7
    with the published weights (W_LPLC2 = 1.45, W_LC4 = 1.62):

        weighted size peak      = 1.45 * C2 = 2.465 mV
        weighted velocity slope = 1.62 * C1 = 4.159e-4 mV per deg/s

    so the velocity term equals the size peak at 5,928 deg/s = 103.5 rad/s. Our velocity
    channel is per rad/s, so **`size_gain_pa` must equal `channel_gain_pa` x 103.5** if the
    two channels are to stand in the published proportion. At the previous 4 and 110 the
    ratio was 27.5 -- our velocity channel was 3.8x too strong relative to size.

    That leaves ONE free number, the overall pA scale, instead of three. It is fitted to the
    published threshold: velocity gain 2.2 with this value gives 38.6 degrees. Keep the two
    in proportion when changing either, or the published relationship is silently discarded.
    """

    size_tuning_form: str = "log"
    """Functional form of the LPLC2 size channel: ``"linear"`` or ``"log"``.

    ``"log"`` is the published form (Ache et al. 2019 eq. 4, see `size_log_width`). The
    ``"linear"`` alternative -- a Gaussian in degrees -- is kept only because it was what
    this model used first, and because the comparison is instructive: a Gaussian in degrees
    never reaches zero, so it delivered 5.9 pA at zero angular size against the 7 pA a cell
    needs to fire. LPLC2 fired in 100% of frames with nothing approaching, and went silent
    past 83 degrees. Found by Ranuja in the telemetry, before the equation was available.
    """

    size_requires_motion: bool = True
    """Gate the size channel on the image actually expanding.

    Ache et al. report that LPLC2 "though they encode looming size, require looming motion
    to be active" -- they are radial motion opponency detectors, and a static disk does not
    excite them. Their Gaussian in angular size was fitted to LOOMING stimuli, where size
    and expansion co-vary; read as a function of instantaneous size alone it says a
    stationary object of 42 degrees drives LPLC2 at full strength forever.

    That is not a subtle error. Measured without this gate, a completely motionless object
    at 25-60 degrees fires the giant fiber within ~50 ms: the fly jumps at furniture. Found
    by Ranuja, who could steer the model into repeated escapes from a stationary pointer.

    The earlier "LPLC2 is silent with nothing approaching" result is not contradicted --
    it was measured on a distant object subtending a small angle, where the log Gaussian is
    correctly near zero. It simply never tested a LARGE stationary object, which is the case
    that fails. A test can be true and still cover the wrong half of the space.
    """

    size_motion_ref_rad_s: float = 0.2
    """Expansion rate at which the size channel reaches ~63% of its ungated value.

    Soft rather than a hard theta_dot > 0 test, which would chatter on noise around zero.
    The value is invented: the paper establishes that motion is REQUIRED, not how steeply
    the requirement turns on."""

    size_log_width: float = 0.52
    """Width of the log-angle Gaussian, in natural-log units. Published: C4 = 0.52.

    **Confirmed from the paper.** Ache et al. 2019, STAR Methods eq. 4:

        V_LPLC2 = C2 * exp( -(ln[theta(t - d2)] - ln[C3])^2 / (2 * C4^2) )

    with C2 = 1.7 mV, C3 = 42 deg, C4 = 0.52, d2 = 0.019 s. The Gaussian is in **ln theta**,
    which is why 0.52 carries no unit -- it is a width in log-angle. This was inferred here
    before the paper could be read, from the fact that 0.52 cannot be a width in degrees and
    that a log Gaussian has no resting floor; the equation confirms it exactly.
    """

    sensory_delay_ms: float = 19.0
    """Stimulus-to-giant-fiber delay. Published: d1 = d2 = 0.019 s.

    Covers phototransduction and optic-lobe processing, which this model bypasses by
    injecting current directly into LC4 and LPLC2. Without it the fly reacts to the present
    instant rather than to a 19 ms old image, which makes it respond earlier than the animal
    and is part of why the threshold sat at 16.7 degrees."""

    hemifield_tuning: float = 0.0
    """How strongly looming drive is tuned to the eye that can see it, 0 to 1.

    **Hemifield-based tuning with a curve-based falloff.** At 0 every visual projection
    cell receives the identical current however the threat is placed, which is the state
    this parameter exists to fix: azimuth never reaches the neurons, so a threat on the
    left and one on the right are byte-identical inputs, and nothing downstream can encode
    direction. At 1 each cell's drive is scaled by how near the threat is to the centre of
    its own eye's field, following a raised cosine:

        weight = floor + (1 - floor) * 0.5 * (1 + cos(threat_azimuth - eye_azimuth))

    which is 1 when the threat is straight out to that eye's side, 0.5 when it is directly
    ahead -- balanced across both eyes, correctly -- and falls to the floor behind.

    Only the cell's SIDE is used, which is measured and unambiguous. A finer within-eye
    map can be derived from the anatomy, but the descending projection is perfectly
    ipsilateral, so within-hemisphere position is discarded before it can affect anything
    downstream. Adding it would be machinery without consequence until that changes.

    Default 0 so this is opt-in and the two conditions stay comparable."""

    retinotopy_polarity: float = 1.0
    """+1 or -1: which end of the anterior-posterior axis is forward-looking.

    UNRESOLVED, and deliberately a parameter rather than a guess. Fly visual neuropils
    invert the image between layers, so a cell's position along the body axis does not by
    itself say whether it looks forward or backward. It does not affect whether front and
    rear are distinguishable -- only which is which."""

    hemifield_floor: float = 0.25
    """Drive retained by the eye facing away, as a fraction. Not zero: the fly's eyes wrap
    far around its head with a binocular region in front, so an object behind one eye is
    not invisible to it."""

    efference_copy: float = 1.0
    """How much of the fly's OWN motion is cancelled before encoding, 0 to 1.

    A retina cannot tell whether an image expanded because an object approached or because
    the animal advanced. `EnvObservation.closing_speed` is computed from the RELATIVE
    velocity and so contains both, which is physically correct and sensorily wrong: it
    made the fly flee its own forward motion. Measured with the threat held perfectly
    still (0.0016 m/s) while the fly flew at it at 1.04 m/s -- 50 pA of drive and two
    mid-flight course corrections away from a motionless object. That is what a full
    U-turn toward a stationary observer was.

    Real flies solve this two ways. The spatial pattern differs -- self-motion flows the
    whole visual field outward, an approaching object expands locally against a static
    surround -- and that discrimination needs retinotopy this encoder does not have, in a
    world with a background this arena does not have. What is left is efference copy: a
    signal from the motor side that cancels the predicted sensory consequence of
    self-generated movement, documented in Drosophila for the lobula plate.

    1.0 is complete cancellation, which is available here only because the fly's motion is
    scripted and therefore exactly known; a real corollary discharge is partial. Set to
    0.0 to recover the raw relative-velocity behaviour."""

    gain_pa: float = 26.0
    """Picoamps per unit of looming sensitivity.

    Calibrated against a discrimination battery rather than picked: it is the value at
    which the circuit ignores a stationary object, a receding one, and a slow drift, while
    fleeing a slow-but-committed approach that ends in contact, a normal approach and a
    fast strike. At 18 a contact approach was ignored; at 34 a harmless slow drift set it
    off. See tools/calibrate_pa.py for the same treatment of synaptic strength."""

    size_decay_cap_deg: float = 90.0
    """Angular size beyond which the decay term stops growing, degrees.

    Without a cap, ``exp(-alpha * theta)`` keeps suppressing the response as the object
    fills the visual field, so the drive PEAKS around 60 mm and then falls -- measured at
    half its peak by the time the threat is 5 mm away. That makes the fly least responsive
    exactly when something is on top of it, and creates a blind spot you can sit inside
    and move freely.

    Capping the decay keeps the early size-referencing while letting the expansion rate
    carry the response the rest of the way in."""

    size_decay_alpha: float = 1.0
    """``alpha`` in ``eta = theta_dot * exp(-alpha * theta)``.

    Without this term the drive would track expansion rate alone and grow without bound as
    the object arrives. The decay makes the response peak at a characteristic angular
    size, which is what gives the circuit a size-referenced threshold as well as a
    rate-referenced one."""

    max_closing_speed_ms: float = 6.0
    """Closing speed above which a sample is treated as a DISCONTINUITY and discarded, m/s.

    A teleport must be detected by something SCALE-INDEPENDENT. The first version of this
    guard thresholded on expansion rate instead, which grows as the object gets nearer --
    so the closer the threat, the more easily genuine motion was thrown away. Measured, it
    rejected any approach faster than 0.52 m/s once a 120 mm object was within 40 mm,
    which is an ordinary speed and a close-range blind spot of exactly the kind the
    size-decay cap already had to fix.

    Speed does not have that problem: no real object in this arena moves at 6 m/s, at any
    distance, so the same number is correct everywhere."""

    max_expansion_rate_rad_s: float = 400.0
    """Ceiling on expansion rate, rad/s -- a SENSORY limit, not a teleport catcher.

    Photoreceptors have finite temporal bandwidth, so there is a real biological ceiling on
    how fast an edge can sweep the retina and still be resolved. Drosophila photoreceptors
    are fast, well beyond human flicker fusion, so this sits high: it exists to keep the
    arithmetic finite at d -> 0, not to reject plausible motion.

    A discontinuity is not a looming stimulus. When the threat jumps position -- the mouse
    entering the panel, a teleport, a dropped frame -- the finite difference reports an
    essentially infinite rate and saturates LC4 from one sample, triggering an escape from
    something that never approached.

    Clamping the rate is not enough: a clamped jump still reports "expanding as fast as
    anything possibly can", which is maximally threatening. The sample is therefore thrown
    away and the rate reported as zero -- the honest answer, since a jump tells us nothing
    about whether the object is approaching.

    12 rad/s sits far above any genuine approach in this arena (a fast strike peaks near
    3 rad/s) while still catching a teleport."""

    theta_dot_smoothing: float = 0.7
    """Exponential smoothing on the expansion rate, in [0, 1).

    ``theta_dot`` is a finite difference between frames, so it inherits every jitter in the
    threat's position -- and under mouse control that jitter is large. Smoothing over a few
    frames keeps a genuine fast approach intact while stopping hand tremor from reading as
    a looming stimulus."""

    max_current_pa: float = 140.0
    """Saturation ceiling. Real photoreceptor and LC4 responses saturate; this also
    bounds the input no matter how small the distance becomes."""

    max_exponent: float = 20.0
    """Hard clip on the exponent before ``exp``. ``exp(20)`` is ~4.9e8, comfortably
    finite; without this, a predator at d->0 overflows float64 and yields inf/NaN."""

    min_distance_m: float = 1e-4
    """Division-by-zero guard: ``l / max(d, eps)``."""

    receptive_field_spread: float = 0.22
    """Per-cell gain heterogeneity, fractional standard deviation. Seeded, so reproducible.

    Justified as receptive-field variation -- cells tiling the visual field do not all see
    an expansion equally -- but it was introduced partly because identical traces looked
    wrong on the telemetry panel, and appearance is not a reason to add anything to this
    model. It also now overlaps with `preferred_azimuth`, which represents the same
    heterogeneity from measured anatomy rather than from a random number generator.

    Kept for now because removing it changes every calibrated threshold, which is a change
    that deserves its own step rather than being folded into another. It should be replaced
    by the anatomical map, not merely deleted."""

    target_population: str = "LC4"
    """Which population receives the visual drive. Named, not indexed, so a connectome
    swap that renumbers neurons needs no change here."""

    seed: int = 11


@dataclass(frozen=True)
class DecoderParams:
    """Giant Fiber motor decoder parameters."""

    neural_heading: bool = False
    """Decode the escape direction from the motor neurons instead of from the geometry.

    Off by default, because it is strictly *less* accurate than reading the threat's
    position -- and that is the point. The scripted heading is a unit vector straight away
    from the threat, computed from coordinates the brain never sees. This reads which side's
    jump motor neuron fired first and turns away from that side, using nothing but the
    spikes and the fly's own body axis.

    What it can express is therefore only a SIDE, not a bearing: the measured signal is a
    27-36 ms lead of the same-side TTMn on equalised wiring (MODEL_JOURNAL Step K, and "The
    eyes were mirrored" -- until that fix the model ran with the OPPOSITE side leading, and
    this line said ipsilateral anyway), and nothing has shown that
    its magnitude maps linearly onto angle. Claiming a graded heading from it would be
    inventing precision the measurement does not have.
    """

    neural_turn_deg: float = 90.0
    """How far from the body axis to turn, away from the side that fired first.

    Invented. The neurons supply the sign; this supplies the magnitude, and it is a
    placeholder until something measured constrains it."""

    trigger_population: str = "GF"
    """A spike in any neuron of this population triggers escape."""

    takeoff_delay_ms: float = 5.0
    """Delay from GF spike to the fly actually leaving the ground. The GF drives the
    tergotrochanteral (jump) muscle via TTMn; the electrical-plus-chemical synapse and
    muscle activation together cost a few milliseconds."""

    takeoff_speed_ms: float = 1.60
    """Initial takeoff velocity. Chosen so the getaway is decisive against the default
    predator speed rather than merely buying a few centimetres."""

    takeoff_refractory_ms: float = 120.0
    """Minimum interval between takeoffs, on top of "not while airborne".

    A fly cannot jump again the instant it lands: the short-mode escape needs a
    preparatory postural adjustment before the jump muscle can fire usefully.

    This is a MOTOR constraint, deliberately enforced here rather than by lengthening the
    Giant Fiber's refractory period. The hand-built circuit gives GF a 60 ms refractory to
    make it all-or-none, but real connectomes run uniform published biophysics precisely so
    that invented per-neuron parameters cannot shape their behaviour -- which left GF free
    to fire at 455 Hz and produced 415 takeoffs in 20 seconds. The body is the right place
    to say a fly cannot jump twenty times a second.
    """

    steer_refractory_ms: float = 45.0
    """Minimum interval between mid-flight course corrections.

    The Giant Fiber can spike ~90 times a second under a relentless loom; honouring every
    one as a separate turn would be a seizure, not a flight path."""

    command_window_ms: float = 20.0
    """How long a single GF spike keeps commanding a takeoff. Makes the escape a
    re-armable reflex: the decoder does not latch permanently, so a second GF spike later
    in the episode drives a second jump."""

    escape_bias_deg: float = 42.0
    """Flies do not jump straight backwards — they take off away from the threat with a
    consistent lateral bias. Applied as a rotation of the away-from-threat vector."""


@dataclass(frozen=True)
class RunnerParams:
    """Loop timing."""

    brain_dt_ms: float = 0.1
    """Neural integration timestep. Must be well below the smallest time constant."""

    frame_dt_ms: float = 4.0
    """Environment/render timestep. One frame = ``frame_dt_ms / brain_dt_ms`` brain steps,
    which is how ~5-10 ms of synaptic propagation becomes visible instead of a blip."""

    telemetry_decimation: int = 4
    """Record every Nth brain substep into the scrolling plot buffer. Purely a plotting
    concern — the simulation always integrates at full resolution."""


@dataclass(frozen=True)
class VizParams:
    """Dashboard appearance."""

    window_ms: float = 260.0
    """Width of the scrolling telemetry window."""

    trail_frames: int = 400
    """Length of the position trails in Panel A. Long enough to show the whole approach,
    so the panel reads as a trajectory rather than two dots on an empty field."""

    interval_ms: int = 20
    """Target wall-clock delay between animation frames (~50 fps)."""


@dataclass(frozen=True)
class SimConfig:
    """Top-level configuration bundle."""

    neuron: NeuronParams = field(default_factory=NeuronParams)
    env: EnvParams = field(default_factory=EnvParams)
    encoder: EncoderParams = field(default_factory=EncoderParams)
    motion: MotionParams = field(default_factory=MotionParams)
    decoder: DecoderParams = field(default_factory=DecoderParams)
    runner: RunnerParams = field(default_factory=RunnerParams)
    viz: VizParams = field(default_factory=VizParams)

    connectome: str = "mock12"
    """Which connectome builder to use. See :mod:`flysim.brain.builders`."""

    seed: int = 3
    """Master seed for the brain's noise process."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, path: str | Path) -> SimConfig:
        """Load a config, filling anything unspecified from the defaults above.

        Only the sections present in the file are overridden, and only the keys present
        within each section — so a config file can be three lines long.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimConfig:
        sections = {
            "neuron": NeuronParams,
            "env": EnvParams,
            "encoder": EncoderParams,
            "decoder": DecoderParams,
            "runner": RunnerParams,
            "viz": VizParams,
        }
        kwargs: dict[str, Any] = {}
        for name, klass in sections.items():
            if name in data:
                kwargs[name] = klass(**data[name])
        for scalar in ("connectome", "seed"):
            if scalar in data:
                kwargs[scalar] = data[scalar]

        unknown = set(data) - set(sections) - {"connectome", "seed", "_comment"}
        if unknown:
            raise ValueError(f"Unknown config section(s): {sorted(unknown)}")
        return cls(**kwargs)

    def with_overrides(self, **section_updates: dict[str, Any]) -> SimConfig:
        """Return a copy with nested fields replaced, e.g.::

            cfg.with_overrides(env={"predator_speed_ms": 0.9})
        """
        kwargs: dict[str, Any] = {}
        for name, updates in section_updates.items():
            current = getattr(self, name)
            kwargs[name] = replace(current, **updates) if updates else current
        return replace(self, **kwargs)
