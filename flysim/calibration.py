"""Per-connectome calibration profiles.

A connectome gives you anatomy, not physiology. Several numbers have to be supplied from
outside it, and **they are not the same for different datasets** -- so they cannot live as
a single module-level default without one dataset silently inheriting another's fit.

That is not hypothetical. NeuPrint's male CNS initially ran on FlyWire's
``pa_per_synapse = 0.007`` and fired at 4.4 degrees where FlyWire fires at 14, which made
it twitchy enough to respond to two millimetres of hand tremor on the mouse. Its own fitted
value is 0.002 -- a 3.5x difference, because a different reconstruction of a different
animal has different absolute synapse counts.

Each profile therefore records:

* the fitted constants,
* **what escape threshold they were fitted to produce**, so a later change that shifts it
  is visible rather than silent,
* and how the fit was obtained, so it can be argued with.

These thresholds moved slightly when efference copy was introduced -- the fly's own
approach no longer adds to the closing speed, so the circuit triggers marginally later.
Measured shift: synthetic120 13.6 -> 14.2, flywire 14.2 -> 14.5, neuprint 15.9 -> 16.7,
mock12 unchanged at 15.6. Small enough not to warrant refitting ``pa_per_synapse``, and
recorded here rather than quietly absorbed, which is what these numbers are for.

Fitting procedure
-----------------
``tools/calibrate_pa.py`` sweeps ``pa_per_synapse`` and keeps the values where the circuit
escapes a genuine approach, ignores a slow drift, and (on a CNS dataset) actually drives
its motor neurons. Among those, the one whose escape threshold is closest to the others is
chosen -- a consistency argument across independently reconstructed brains, **not** a
physiological measurement. Nothing here is fitted to electrophysiology, and no quantitative
claim should be read out of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from flysim.config import SHIU_2024, NeuronParams


@dataclass(frozen=True)
class CalibrationProfile:
    """Everything that must be supplied to a connectome from outside the data."""

    name: str

    neuron: NeuronParams
    """Single-neuron biophysics.

    Real connectomes use the published uniform set so that behaviour comes from measured
    wiring rather than from per-population tuning. The hand-built mock keeps its own
    per-population overrides, because it was designed around them and is explicitly a
    teaching circuit rather than a claim about a fly.
    """

    encoder_gain_pa: float
    """Picoamps per unit of looming sensitivity."""

    pa_per_synapse: float | None = None
    """Picoamps delivered per synapse. ``None`` where weights are already in picoamps
    (the mock connectomes, whose matrices are written directly)."""

    uses_population_overrides: bool = False
    """Whether the connectome's own per-population biophysics should be honoured."""

    decoder_population: str = "GF"
    """Which population the motor decoder watches to detect a takeoff.

    On a brain-only connectome this must be the Giant Fiber: its motor targets are outside
    the volume, so GF firing is the last observable event and the takeoff has to be
    inferred from it. On a CNS dataset the motor neurons are present and fire ~8 ms later,
    so the takeoff can be READ from the muscle rather than inferred from the command.

    The kinematics remain scripted either way -- what changes is whether the trigger is
    measured or assumed.
    """

    channel_gain_pa: float | None = None
    """Velocity-channel gain when the two feature channels are split (``--channels``).

    The combined encoder drives every visual projection cell with one expansion-rate
    signal; the split encoder drives LC4 with velocity alone and hands angular size to
    LPLC2. Those are different signals reaching different cells, so they cannot share a
    gain -- and until this field existed they did, because ``build_runner`` sets the gain
    from ``encoder_gain_pa`` unconditionally. The fitted velocity gain never reached the
    simulation, and ``--channels`` silently ran at the combined encoder's 26.0.

    ``None`` means the profile has no separate fit and the combined gain is used.
    """

    channel_threshold_deg: float | None = None
    """Escape threshold measured with the feature channels split.

    Separate from ``escape_threshold_deg`` because the two encoders are fitted to different
    targets: the combined one to consistency across datasets, the split one to the published
    ~39 degrees. Reporting the combined figure during a ``--channels`` run would describe a
    fit the run is not using.
    """

    escape_threshold_deg: float | None = None
    """The angular size at which this profile was fitted to trigger an escape.

    Recorded so that a change which shifts it shows up as a discrepancy rather than
    passing quietly. Not a target the code enforces -- a value to compare against.
    """

    notes: str = ""


PROFILES: dict[str, CalibrationProfile] = {
    "mock12": CalibrationProfile(
        name="mock12",
        neuron=NeuronParams(),
        encoder_gain_pa=26.0,
        pa_per_synapse=None,
        uses_population_overrides=True,
        escape_threshold_deg=15.6,
        notes=(
            "Hand-authored 12-neuron circuit. Weights are written directly in picoamps, "
            "and the per-population biophysics (notably the inhibitory population's long "
            "refractory period, which is what makes the escape threshold emergent) are "
            "part of the design rather than a fit."
        ),
    ),
    "synthetic120": CalibrationProfile(
        name="synthetic120",
        neuron=NeuronParams(),
        encoder_gain_pa=26.0,
        pa_per_synapse=None,
        uses_population_overrides=True,
        escape_threshold_deg=14.2,
        notes="Same rule table as mock12 at population scale; same biophysics.",
    ),
    "flywire": CalibrationProfile(
        name="flywire",
        neuron=SHIU_2024,
        encoder_gain_pa=26.0,
        pa_per_synapse=0.007,
        uses_population_overrides=False,
        escape_threshold_deg=14.5,
        notes=(
            "FAFB v783, female brain. Fitted window is roughly 0.005-0.01: above it the "
            "reflex fires at a harmless slow drift, below it the Giant Fiber never reaches "
            "threshold. Narrow, and a reason to distrust anything that depends on the "
            "exact value."
        ),
    ),
    "neuprint": CalibrationProfile(
        name="neuprint",
        neuron=SHIU_2024,
        encoder_gain_pa=26.0,
        pa_per_synapse=0.002,
        uses_population_overrides=False,
        decoder_population="MOTOR",
        channel_gain_pa=2.2,
        channel_threshold_deg=38.6,
        escape_threshold_deg=16.7,
        notes=(
            "male-cns:v1.0, male brain and ventral nerve cord. Fitted independently of "
            "FlyWire: 0.007 here produced an escape at 4.4 degrees, sensitive enough to "
            "respond to 2 mm of hand tremor. Measured sweep -- 0.007: 8.4 deg, 0.004: "
            "10.2, 0.002: 15.9, 0.001: 33.3, 0.0005: the motor neurons never fire. 0.002 "
            "is the value whose threshold sits closest to the other datasets."
        ),
    ),
}


def for_connectome(name: str) -> CalibrationProfile:
    """Profile for a connectome, falling back to the mock profile for unknown names."""
    return PROFILES.get(name, PROFILES["mock12"])


def describe(profile: CalibrationProfile, gain_pa: float | None = None) -> str:
    """One line for startup logging.

    ``gain_pa`` is the gain the run will ACTUALLY use, which differs from the profile's
    when the feature channels are split. Reporting the profile value there would print a
    number the simulation is not using -- the same mislabel that invalidated an earlier
    sweep -- so the caller passes the effective one.
    """
    parts = [f"calibration '{profile.name}'"]
    if profile.pa_per_synapse is not None:
        parts.append(f"{profile.pa_per_synapse} pA/synapse")
    effective = profile.encoder_gain_pa if gain_pa is None else gain_pa
    split = (profile.channel_gain_pa is not None
             and gain_pa == profile.channel_gain_pa)
    parts.append(f"gain {effective} pA" + (" (split channels)" if split else ""))
    parts.append(f"tau_m {profile.neuron.tau_m_ms} ms")
    parts.append(f"takeoff read from {profile.decoder_population}")
    threshold = (profile.channel_threshold_deg if split and profile.channel_threshold_deg
                 else profile.escape_threshold_deg)
    if threshold is not None:
        parts.append(f"fitted to escape at ~{threshold:.0f} deg")
    return "  " + "  |  ".join(parts)
