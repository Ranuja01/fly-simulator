"""Entry point for the Starter Phase experiment.

    python main.py                                  # live dashboard
    python main.py --check                          # headless acceptance test
    python main.py --connectome synthetic120        # population model
    python main.py --connectome synthetic120 --lesion-lc4 0.4
    python main.py --save outputs/escape.mp4 --no-show
    python main.py --benchmark 50000                # scaling measurement

Requires only NumPy and Matplotlib. No API token, no download, no data files.

This module and :mod:`flysim.runner` are the only two places that know about more than
one layer of the system. Everything below is assembly.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace

import numpy as np

from flysim.brain.builders import build, build_benchmark
from flysim.brain.lif import LIFBrain
from flysim import calibration
from flysim.config import EncoderParams, SimConfig
from flysim.core.base import BaseSensoryEncoder
from flysim.envs.interactive2d import InteractiveEnvironment
from flysim.envs.predator2d import Predator2DEnvironment
from flysim.interfaces.motor import GiantFiberDecoder
from flysim.interfaces.sensory import (
    CompositeEncoder,
    LoomingEncoder,
    MotionEncoder,
)
from flysim.runner import SimulationRunner

INTERACTIVE_BRAIN_DT_MS = 0.4
"""Coarser timestep for interactive sessions. See config_from_args for the measurements."""

INTERACTIVE_STEPS_PER_FRAME = 5
"""Simulation frames per rendered frame in interactive mode.

One env frame advances the world 4 ms, so at 50 fps a 1:1 loop runs at a fifth of real
time and a walking fly appears frozen. Five gives ~1.0x real time on the mock circuit and
~0.6x on the 15k-neuron FlyWire circuit, measured with blitting enabled.
"""


def build_runner(
    config: SimConfig,
    lesion_lc4: float = 0.0,
    connectome_kwargs: dict | None = None,
    interactive: bool = False,
    motion: bool = False,
    retinotopy: bool = False,
    channels: bool = False,
    neural_heading: bool = False,
) -> SimulationRunner:
    """Assemble the four layers into a runnable simulation.

    This function is the entire wiring diagram. Swapping the environment for a MuJoCo or
    Minecraft bridge means changing one line here; nothing else in the package moves.
    """
    # A connectome supplies anatomy; everything else comes from its calibration profile.
    # Keeping these together per dataset is what stops one silently inheriting another's
    # fit -- see flysim/calibration.py for why that is not hypothetical.
    profile = calibration.for_connectome(config.connectome)
    kwargs = dict(connectome_kwargs or {})
    if profile.pa_per_synapse is not None:
        kwargs.setdefault("pa_per_synapse", profile.pa_per_synapse)

    connectome = build(config.connectome, seed=config.seed, **kwargs)
    # The profile owns the encoder gain, and used to overwrite a caller's value in
    # silence -- which invalidated a whole sweep before it was noticed, every run
    # quietly using 26.0 while reporting the swept value. Say so instead.
    #
    # The split encoder needs its own gain. It drives LC4 with angular velocity alone
    # while LPLC2 carries size, so the number that suits one composite signal does not
    # suit either half -- with --channels on the combined 26.0, the velocity channel
    # fired far below the published threshold. Fitted separately in
    # tools/calibrate_channels.py against the threshold AND the LPLC2 lesion.
    profile_gain = profile.encoder_gain_pa
    if channels and profile.channel_gain_pa is not None:
        profile_gain = profile.channel_gain_pa
    if config.encoder.gain_pa != EncoderParams().gain_pa and (
            config.encoder.gain_pa != profile_gain):
        print(f"  note: encoder gain {config.encoder.gain_pa} replaced by calibration "
              f"profile value {profile_gain}")
    config = config.with_overrides(encoder={"gain_pa": profile_gain})
    neuron_params = profile.neuron
    print(calibration.describe(profile, profile_gain))

    brain = LIFBrain(
        connectome,
        params=neuron_params,
        dt_ms=config.runner.brain_dt_ms,
        seed=config.seed,
    )

    if lesion_lc4 > 0.0:
        _lesion(brain, "LC4", lesion_lc4, seed=config.seed)

    # The entire cost of swapping a scripted world for a live human-driven one. Nothing
    # below this line changes, because nothing below this line knows where an observation
    # came from.
    environment = (
        InteractiveEnvironment(config.env) if interactive
        else Predator2DEnvironment(config.env)
    )
    if retinotopy:
        config = config.with_overrides(encoder={"hemifield_tuning": 1.0})
    if channels:
        # LC4 on looming speed, LPLC2 on angular size -- the two measured feature
        # channels, rather than one composite driving both (Ache et al. 2019).
        config = config.with_overrides(encoder={"split_feature_channels": True})
    encoder: BaseSensoryEncoder = LoomingEncoder(
        config.encoder, brain.populations, brain.size,
        hemisphere=getattr(connectome, "hemisphere", None),
        preferred_azimuth=getattr(connectome, "preferred_azimuth", None),
        labels=connectome.labels,
    )
    if config.encoder.split_feature_channels:
        print(encoder.describe_channels())
    if retinotopy:
        h = getattr(connectome, "hemisphere", None)
        if h is None:
            print("  note: this connectome records no sides; --retinotopy has no effect")
        else:
            t = brain.populations[config.encoder.target_population]
            print(f"  hemifield tuning ON: {int((h[t] < 0).sum())} left-eye and "
                  f"{int((h[t] > 0).sum())} right-eye cells tuned separately")

    # A second modality. Looming reports approach and nothing else, so an object circling
    # the fly is invisible to it; T4/T5 report the sweep across the eye. They are already
    # one synapse upstream of LC4 and LPLC2 in this connectome, so their drive reaches the
    # Giant Fiber through measured wiring rather than through anything added here.
    if motion:
        if "T4T5" not in brain.populations:
            print("  note: this connectome has no T4/T5 cells; --motion has no effect")
        else:
            motion_encoder = MotionEncoder(
                config.motion, brain.populations, connectome.labels, brain.size
            )
            print(motion_encoder.describe())
            encoder = CompositeEncoder(encoder, motion_encoder)

    # Read the takeoff from the motor neurons when the dataset has them. On a brain-only
    # connectome they are outside the volume, so the Giant Fiber is the last observable
    # event and the takeoff must be inferred from it instead.
    watched = profile.decoder_population
    if watched not in brain.populations:
        if watched != "GF":
            print(f"  note: no {watched} population in this connectome; "
                  f"falling back to GF")
        watched = "GF"
    decoder_params = replace(config.decoder, trigger_population=watched)
    # Which cells carry side. TTMn only: each giant fiber drives its own side's TTMn but
    # BOTH PSI, so including the bilaterally driven PSI pins the left-right difference to
    # zero. See MODEL_JOURNAL Step K1, where that error hid the whole result.
    side_readout = np.asarray(
        [i for i in brain.populations.get(watched, ())
         if str(connectome.labels[i]).upper().startswith("TTMN")], dtype=np.int64
    )
    if neural_heading:
        decoder_params = replace(decoder_params, neural_heading=True)
        if side_readout.size < 2:
            print("  note: fewer than two TTMn with sides; --neural-heading cannot decode "
                  "and will fall back to geometry")
        else:
            print(f"  escape direction read from {side_readout.size} TTMn, not from the "
                  f"threat's coordinates")
    decoder = GiantFiberDecoder(
        decoder_params, brain.populations,
        hemisphere=getattr(connectome, "hemisphere", None),
        side_readout=side_readout,
    )

    return SimulationRunner(environment, brain, encoder, decoder, config)


def _lesion(brain: LIFBrain, population: str, fraction: float, seed: int) -> None:
    """Silence a fraction of a population.

    The victims are chosen from a single fixed permutation, so successive lesion
    fractions are *nested*: the 60% lesion silences everything the 40% lesion did, plus
    more. Drawing an independent sample per fraction would make a dose-response curve
    non-monotonic for reasons that have nothing to do with the biology.
    """
    if not 0.0 < fraction <= 1.0:
        raise ValueError(f"--lesion-lc4 must be in (0, 1], got {fraction}.")
    indices = np.asarray(brain.populations[population])
    order = np.random.default_rng(seed).permutation(indices)
    count = int(round(fraction * indices.size))
    brain.silence(order[:count])
    print(f"lesion: silenced {count}/{indices.size} {population} neurons")


def run_benchmark(size: int, config: SimConfig, steps: int = 500) -> int:
    """Measure integration throughput and memory at connectome scale.

    Exists because neither of the small models is a performance test. This is what backs
    the sparse-versus-dense argument in ``docs/COMPUTE_BUDGET.md`` with a measurement.
    """
    print(f"Building sparse benchmark connectome, n={size} ...")
    connectome = build_benchmark(size, seed=config.seed)
    print(connectome.summary())

    weights = connectome.weights
    edge_bytes = weights.data.nbytes + weights.indices.nbytes + weights.indptr.nbytes
    dense_bytes = size * size * 4

    print(f"\n  sparse weights : {edge_bytes / 2**20:10.1f} MiB (CSR, float32)")
    print(f"  dense would be : {dense_bytes / 2**30:10.1f} GiB  <- why we do not do this")
    print(f"  ratio          : {dense_bytes / edge_bytes:10.0f}x")

    brain = LIFBrain(connectome, config.neuron, config.runner.brain_dt_ms, seed=config.seed)
    drive = np.zeros(brain.size, dtype=np.float32)
    drive[connectome.population("LC4")] = 30.0

    brain.step(drive)  # warm up: first call touches allocation paths
    start = time.perf_counter()
    for _ in range(steps):
        brain.step(drive)
    elapsed = time.perf_counter() - start

    per_step_ms = elapsed / steps * 1000
    sim_ms = steps * config.runner.brain_dt_ms
    print(f"\n  {steps} steps in {elapsed:.2f} s  ({per_step_ms:.2f} ms/step)")
    print(f"  simulated {sim_ms:.1f} ms of brain time at {sim_ms / (elapsed * 1000):.3f}x real time")
    return 0


def run_check(config: SimConfig, connectome_kwargs: dict | None = None) -> int:
    """Headless acceptance test. Returns a process exit code.

    Asserts the behaviour the Starter Phase is supposed to demonstrate, so a change that
    quietly breaks the reflex fails loudly instead of producing a plausible-looking plot.
    """
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        status = "ok  " if condition else "FAIL"
        print(f"  [{status}] {message}")
        if not condition:
            failures.append(message)

    print(f"\n=== acceptance: default escape ({config.connectome}) ===")
    runner = build_runner(config, connectome_kwargs=connectome_kwargs)
    runner.run()
    s = runner.summary()

    require(s["outcome"] == "escaped", "fly escapes the predator")
    require(s["takeoffs"] == 1, f"exactly one takeoff (got {s['takeoffs']})")

    # Every commanded takeoff must actually be performed. These two counts come from
    # opposite sides of the boundary -- the decoder's edges as the runner recorded them,
    # and what the environment did about them -- so a command lost in transit shows up
    # here as a mismatch. One HAS been lost, twice: the substep edge re-attached without
    # the heading the environment gates on.
    commanded = len(s["takeoff_events"])
    require(
        commanded == s["takeoffs"],
        f"every commanded takeoff was performed ({commanded} commanded, "
        f"{s['takeoffs']} performed)",
    )

    first = s["first_spike_ms"]
    require(first["LC4"] is not None, "LC4 fires")
    require(first["GF"] is not None, "GF fires")
    if first["LC4"] is not None and first["GF"] is not None:
        require(first["GF"] > first["LC4"],
                f"GF ({first['GF']:.1f} ms) fires after LC4 ({first['LC4']:.1f} ms)")
    # SOMETHING must relay between the visual cells and the Giant Fiber, and this used to
    # be asserted of "PMN" while guarded by `is not None` -- so when the premotor pool went
    # completely silent the check did not fail, it vanished from the output. A check that
    # can disappear without failing is worse than no check.
    #
    # The pool really is silent: 11,437 cells, zero spikes. The only cells in it that ever
    # participated were descending neurons mislabelled as premotor, and now that they have
    # their own population the relay is visible as what it is.
    relay = next((p for p in ("DN", "PMN") if first.get(p) is not None), None)
    require(relay is not None,
            "some population relays between LC4 and the Giant Fiber")
    if relay is not None and first["GF"] is not None:
        require(first["GF"] > first[relay],
                f"GF fires after the {relay} relay ({first[relay]:.1f} ms)")

    # Only a CNS dataset has motor neurons at all; on a brain-only connectome the Giant
    # Fiber's targets are outside the volume and there is nothing downstream to check.
    if "MOTOR" in first:
        if first["MOTOR"] is not None and first["GF"] is not None:
            require(first["MOTOR"] >= first["GF"],
                    f"motor neurons fire after GF "
                    f"({first['MOTOR']:.1f} ms vs {first['GF']:.1f} ms)")
        else:
            require(False, "motor neurons fire when the Giant Fiber does")
    # All-or-none is a claim about BEHAVIOUR, not about spike count. The mock circuit's
    # GF fires exactly once only because it was given a 60 ms refractory period; a real
    # connectome runs uniform 2.2 ms biophysics and its GF bursts during a strong loom.
    # The escape is still all-or-none, because a fly cannot take off while airborne -- which
    # is enforced in the motor decoder, where a body constraint belongs. Asserting the spike
    # count would be asserting a property of my own hand-tuning.
    gf_spikes = s["active_substeps"]["GF"]
    require(s["takeoffs"] == 1,
            f"escape is all-or-none behaviourally: 1 takeoff from {gf_spikes} GF spike(s)")

    theta = s["escape_angular_size_deg"]
    require(theta is not None and 5.0 < theta < 90.0,
            f"escape triggers at a plausible angular size ({theta:.1f} deg)")

    print("\n=== edge case: predator spawns exactly on the fly (d = 0) ===")
    zero = config.with_overrides(env={"predator_start_distance_m": 0.0})
    zero_runner = build_runner(zero, connectome_kwargs=connectome_kwargs)
    packet = zero_runner.encoder.encode(zero_runner.observation, zero_runner.brain.size)
    require(np.all(np.isfinite(packet.currents)),
            "looming current stays finite at zero distance")
    # Bounded, not saturated. Under the expansion-rate drive a threat sitting at zero
    # distance and NOT moving correctly produces zero current -- size alone is not a
    # looming stimulus. The property worth asserting is that the drive stays inside its
    # ceiling, which is what protects the engine from an overflow.
    require(float(packet.currents.max()) <= config.encoder.max_current_pa,
            f"looming drive stays within its ceiling "
            f"({packet.currents.max():.1f} <= {config.encoder.max_current_pa} pA)")
    zero_results = zero_runner.run()
    require(
        bool(np.all(np.isfinite(zero_results[-1].state.voltages))),
        "no NaN or inf voltages after a d=0 episode",
    )

    print("\n=== gating: a slow approach must NOT trigger the reflex ===")
    slow = config.with_overrides(
        env={"predator_speed_ms": 0.08, "duration_s": 6.0}
    )
    slow_runner = build_runner(slow, connectome_kwargs=connectome_kwargs)
    slow_runner.run()
    slow_summary = slow_runner.summary()
    # This asserts the BEHAVIOUR, and deliberately says nothing about the mechanism. It
    # used to claim "feedforward inhibition suppresses GF", which is false on this
    # connectome: silencing all 3,688 inhibitory cells leaves the slow drift still failing
    # to trigger and the real approach still triggering at the same millisecond. What
    # withholds the reflex is the encoder -- a slow approach never produces enough drive
    # to reach threshold. A test named for a mechanism it does not test is worse than one
    # named for the behaviour it does. See MODEL_JOURNAL.md Step I.
    require(slow_summary["first_spike_ms"]["GF"] is None,
            "a slow approach does not trigger the reflex")

    # The two checks below exist because both bugs they guard against got past every check
    # above -- and they got past for the same reason: everything above builds the DEFAULT
    # configuration (combined encoder, no channels, no neural heading), while the bugs lived
    # in the configuration people actually run. A check has to exercise the path it claims
    # to protect, so these build `--channels --retinotopy [--neural-heading]` explicitly.
    # On a connectome where that path cannot exist they SKIP out loud rather than vanish:
    # a check that can disappear without failing is worse than no check.

    print("\n=== a large MOTIONLESS object must NOT trigger the reflex (--channels) ===")
    # 42 degrees is the peak of the LPLC2 size Gaussian: the most a stationary object can
    # drive the size channel. Without the motion gate this fired the giant fiber within
    # 46 ms -- the fly jumped at furniture (MODEL_JOURNAL, Step K).
    size_m = 0.020
    still = config.with_overrides(env={
        "predator_speed_ms": 0.0, "duration_s": 3.0, "threat_size_m": size_m,
        "predator_start_distance_m": size_m / (2.0 * np.tan(np.deg2rad(42.0) / 2.0)),
    })
    still_runner = build_runner(still, connectome_kwargs=connectome_kwargs,
                                channels=True, retinotopy=True)
    size_cells = getattr(getattr(still_runner, "encoder", None), "_size_cells", ())
    if len(size_cells) == 0:
        print("  [skip] no LPLC2 cells in this connectome, so there is no size channel to test")
    else:
        still_runner.run()
        still_summary = still_runner.summary()
        require(still_summary["first_spike_ms"]["GF"] is None
                and still_summary["takeoffs"] == 0,
                f"a motionless object at 42 deg does not trigger the reflex "
                f"({still_summary['takeoffs']} takeoffs)")

    print("\n=== a pointer frozen beside a flying fly must NOT make it circle "
          "(--neural-heading) ===")
    # Reproduces the report: pointer sweeps in, the fly takes off, the hand comes off the
    # mouse mid-flight with a large object left close by. With the motion gate off AND the
    # heading re-aimed on every spike, this gave 42 redirects, a flight that never landed,
    # and 2,700 degrees of turning. Each bug alone did not circle, so this is what catches
    # the interaction. A circle means more than one full turn while the pointer is still.
    circ = config.with_overrides(runner={"brain_dt_ms": INTERACTIVE_BRAIN_DT_MS})
    circ_runner = build_runner(circ, connectome_kwargs=connectome_kwargs,
                               interactive=True, channels=True, retinotopy=True,
                               neural_heading=True)
    dec = circ_runner.decoder
    if (len(getattr(dec, "_side_left", ())) == 0
            or len(getattr(dec, "_side_right", ())) == 0):
        print("  [skip] no left and right TTMn in this connectome, so the neural heading "
              "has nothing to decode")
    else:
        env = circ_runner.env
        env._threat_size = 0.075
        dt = circ_runner.frame_dt_s
        pos = np.array([0.30, 0.0])
        for _ in range(60):          # warm-up; see MODEL_JOURNAL 2a for why
            env.set_threat_position(*pos)
            circ_runner.step()
        took_off = False
        for _ in range(3000):
            toward = np.asarray(env._fly_pos, dtype=float) - pos
            dist = float(np.linalg.norm(toward))
            if dist > 1e-6:
                pos = pos + toward / dist * 0.6 * dt
            env.set_threat_position(*pos)
            result = circ_runner.step()
            if result.command is not None and result.command.triggered_now:
                took_off = True
                break
        # Without a takeoff the circle check below would pass vacuously, so the
        # precondition is a requirement in its own right.
        require(took_off, "the sweeping pointer triggers a takeoff (precondition)")
        if took_off:
            turn, prev = 0.0, None
            for _ in range(int(4.0 / dt)):
                env.set_threat_position(*pos)
                obs = circ_runner.step().observation
                heading = obs.agent_heading
                if obs.escaped and prev is not None and heading is not None:
                    turn += abs((heading - prev + np.pi) % (2.0 * np.pi) - np.pi)
                prev = heading
            require(np.rad2deg(turn) < 360.0,
                    f"with the pointer frozen the fly does not circle "
                    f"({np.rad2deg(turn):.0f} deg of turning in 4 s)")

    print("\n=== sides: a threat on the fly's LEFT drives its LEFT eye, and it turns RIGHT ===")
    # The eyes were mirrored for as long as hemifield tuning existed, and nothing caught it,
    # because the decoder's turn sign had been matched to the mirrored data: behaviour
    # looked right while every "which side" statement was inverted. So these check the two
    # halves SEPARATELY, as geometry, with no connectome and no simulation -- an escape that
    # still goes the right way cannot hide a compensating pair of errors from them.
    #
    # Arena angles run counter-clockwise, so the fly's left is +90 degrees from its heading.
    eye_encoder = LoomingEncoder(
        replace(config.encoder, hemifield_tuning=1.0), {"LC4": np.array([0, 1])}, 2,
        hemisphere=np.array([-1, 1]), preferred_azimuth=None,
        labels=["LC4:left", "LC4:right"],
    )
    base_obs = Predator2DEnvironment(config.env).reset()
    for heading_deg in (0.0, 90.0):
        h = np.deg2rad(heading_deg)
        left_of_fly = 0.1 * np.array([np.cos(h + np.pi / 2), np.sin(h + np.pi / 2)])
        w = eye_encoder._hemifield_weights(replace(
            base_obs, agent_position=np.zeros(2), agent_heading=h,
            threat_position=left_of_fly))
        require(float(w[0]) > float(w[1]),
                f"heading {heading_deg:.0f} deg: threat on the fly's left drives the LEFT "
                f"eye (left {float(w[0]):.2f}, right {float(w[1]):.2f})")

    side_decoder = GiantFiberDecoder(replace(config.decoder, neural_heading=True),
                                     {"GF": np.array([0])})
    side_decoder._side_score = -1.0    # recent evidence: the LEFT jump motor neuron led
    turned = side_decoder._neural_heading(replace(base_obs, agent_heading=0.0))
    require(turned is not None and float(turned[1]) < 0.0,
            "left jump motor neuron first (threat on the left) turns the fly RIGHT "
            f"(heading vector {None if turned is None else np.round(turned, 2).tolist()})")

    print("\n=== chased mid-flight, the fly must RE-AIM (--neural-heading) ===")
    # The circle fix froze the neural heading for the whole flight: the side reading was only
    # cleared at takeoff, and a hold rule then returned the takeoff heading. Chased at 1.0 m/s,
    # 2-3 redirects all sent ONE heading and the fly turned 0 degrees -- Ranuja: "if I come at
    # it, it never cares". The circle check above passed throughout, because a fly that never
    # turns never circles. This is its counterpart: responsiveness, not just stability.
    chase_cfg = config.with_overrides(runner={"brain_dt_ms": INTERACTIVE_BRAIN_DT_MS})
    chase_runner = build_runner(chase_cfg, connectome_kwargs=connectome_kwargs,
                                interactive=True, channels=True, retinotopy=True,
                                neural_heading=True)
    chase_dec = chase_runner.decoder
    if (len(getattr(chase_dec, "_side_left", ())) == 0
            or len(getattr(chase_dec, "_side_right", ())) == 0):
        print("  [skip] no left and right TTMn in this connectome, so the neural heading "
              "has nothing to decode")
    else:
        env = chase_runner.env
        dt = chase_runner.frame_dt_s
        pos = np.array([0.30, 0.0])
        for _ in range(60):          # warm-up; see MODEL_JOURNAL 2a
            env.set_threat_position(*pos)
            chase_runner.step()
        took_off = False
        for _ in range(3000):
            toward = np.asarray(env._fly_pos, dtype=float) - pos
            dist = float(np.linalg.norm(toward))
            if dist > 1e-6:
                pos = pos + toward / dist * 0.6 * dt
            env.set_threat_position(*pos)
            result = chase_runner.step()
            if result.command is not None and result.command.triggered_now:
                took_off = True
                break
        require(took_off, "the sweeping pointer triggers a takeoff (precondition)")
        if took_off:
            for _ in range(int(0.3 / dt)):
                env.set_threat_position(*pos)
                chase_runner.step()
            sent, turn, prev = set(), 0.0, None
            for _ in range(int(2.0 / dt)):
                toward = np.asarray(env._fly_pos, dtype=float) - pos
                dist = float(np.linalg.norm(toward))
                if dist > 1e-6:
                    pos = pos + toward / dist * 1.0 * dt
                env.set_threat_position(*pos)
                result = chase_runner.step()
                obs = result.observation
                cmd = result.command
                if cmd is not None and cmd.redirect and cmd.heading is not None:
                    sent.add(int(round(np.rad2deg(np.arctan2(cmd.heading[1], cmd.heading[0])))))
                if obs.escaped and prev is not None and obs.agent_heading is not None:
                    turn += abs((obs.agent_heading - prev + np.pi) % (2.0 * np.pi) - np.pi)
                prev = obs.agent_heading
            require(len(sent) >= 2 and np.rad2deg(turn) >= 90.0,
                    f"chased mid-flight the fly re-aims ({len(sent)} distinct redirect "
                    f"headings, {np.rad2deg(turn):.0f} deg turned)")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s) did not pass.")
        return 1
    print("All checks passed.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drosophila looming-escape reflex simulator (Starter Phase).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", type=str, default=None,
                        help="Path to a JSON config file with partial overrides.")
    parser.add_argument("--connectome", type=str, default=None,
                        choices=["mock12", "synthetic120", "flywire", "neuprint"],
                        help="Which connectome to simulate. 'flywire' loads real Codex "
                             "tables from FLYSIM_CACHE_DIR; see docs/CONNECTOME_ACCESS.md.")
    parser.add_argument("--flywire-dir", type=str, default=None, metavar="PATH",
                        help="Directory holding connections.csv and classification.csv. "
                             "Defaults to $FLYSIM_CACHE_DIR/flywire/<version>.")
    parser.add_argument("--flywire-version", type=str, default="v783",
                        help="FlyWire public release to load.")
    parser.add_argument("--postural", action="store_true",
                        help="Include the leg motor pool that aims the jump, not just the "
                             "escape reflex that fires it. Larger and slower.")
    parser.add_argument("--neural-heading", action="store_true",
                        help="Decode escape direction from which jump motor neuron fires "
                             "first, instead of from the threat's coordinates. Coarser on "
                             "purpose: the neurons supply a side, not a bearing.")
    parser.add_argument("--channels", action="store_true",
                        help="Drive LC4 on looming speed and LPLC2 on angular "
                             "size, as measured, instead of one signal for both.")
    parser.add_argument("--retinotopy", action="store_true",
                        help="Tune looming drive to the eye that can see the threat, so "
                             "direction reaches the neurons instead of being discarded.")
    parser.add_argument("--motion", action="store_true",
                        help="Also drive the T4/T5 motion detectors, so the fly can see "
                             "an object sweeping past it and not only one approaching.")
    parser.add_argument("--flywire-hops", type=int, default=1,
                        help="Synaptic steps to expand outward from the seed cell types.")
    parser.add_argument("--flywire-max-neurons", type=int, default=25_000,
                        help="Cap on subnetwork size during hop expansion.")
    parser.add_argument("--flywire-pa", type=float, default=None, metavar="PA_PER_SYN",
                        help="Picoamps per synapse. THE uncalibrated constant: a connectome "
                             "gives anatomy, not physiology. See docs/CONNECTOME_ACCESS.md.")
    parser.add_argument("--seed", type=int, default=None,
                        help="Master seed (network wiring, membrane noise).")
    parser.add_argument("--lesion-lc4", type=float, default=0.0, metavar="FRACTION",
                        help="Silence this fraction of LC4 neurons before running.")
    parser.add_argument("--predator-speed", type=float, default=None, metavar="M_PER_S",
                        help="Predator approach speed.")
    parser.add_argument("--predator-start", type=float, default=None, metavar="METRES",
                        help="Initial separation. 0 exercises the coincident-position case.")
    parser.add_argument("--brain-dt", type=float, default=None, metavar="MS",
                        help="Neural integration timestep. Cost scales as 1/dt: 0.2 halves "
                             "the work, 0.4 quarters it. The engine refuses anything above "
                             "half the fastest time constant.")
    parser.add_argument("--steps-per-frame", type=int, default=None, metavar="N",
                        help="Simulation frames per rendered frame. Higher = closer to "
                             "real time, lower = more slow-motion detail. Defaults to 5 "
                             "for --interactive, 1 otherwise.")
    parser.add_argument("--brain-view", dest="brain_view", action="store_true",
                        default=None,
                        help="Force the anatomical panel on. Default: on for scripted "
                             "runs, off for --interactive (it roughly halves the frame "
                             "rate, and responsiveness matters more when you are driving).")
    parser.add_argument("--no-brain-view", dest="brain_view", action="store_false",
                        help="Hide the anatomical panel.")
    parser.add_argument("--interactive", action="store_true",
                        help="You are the threat: the object follows your mouse. Scroll to "
                             "resize it, 'r' to reset the fly. Runs until you close it.")
    parser.add_argument("--no-show", action="store_true",
                        help="Run headless and print a summary instead of animating.")
    parser.add_argument("--save", type=str, default=None, metavar="PATH",
                        help="Write the animation to .mp4 (needs ffmpeg) or .gif.")
    parser.add_argument("--check", action="store_true",
                        help="Run the headless acceptance test; exit non-zero on failure.")
    parser.add_argument("--benchmark", type=int, default=None, metavar="N",
                        help="Measure throughput on an N-neuron sparse network (needs SciPy).")
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> SimConfig:
    config = SimConfig.from_json(args.config) if args.config else SimConfig()

    if args.connectome is not None:
        config = replace(config, connectome=args.connectome)
    if args.seed is not None:
        config = replace(config, seed=args.seed)

    if args.brain_dt is not None:
        config = config.with_overrides(runner={"brain_dt_ms": args.brain_dt})
    elif args.interactive:
        # Interactive sessions trade spike-timing resolution for responsiveness. Measured
        # on the 15k-neuron FlyWire circuit, dt=0.4 runs 4.3x faster (65 -> 278 fps) while
        # the Giant Fiber still fires within 5 ms of the same moment and the escape
        # threshold is unchanged (25.9 deg vs 26.9 deg). Scripted runs keep the finer
        # default; pass --brain-dt explicitly to override either way.
        config = config.with_overrides(runner={"brain_dt_ms": INTERACTIVE_BRAIN_DT_MS})

    env_overrides: dict[str, float] = {}
    if args.predator_speed is not None:
        env_overrides["predator_speed_ms"] = args.predator_speed
    if args.predator_start is not None:
        env_overrides["predator_start_distance_m"] = args.predator_start
    if env_overrides:
        config = config.with_overrides(env=env_overrides)

    return config


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = config_from_args(args)

    if args.benchmark is not None:
        return run_benchmark(args.benchmark, config)

    connectome_kwargs: dict = {}
    if config.connectome == "flywire":
        connectome_kwargs = {
            "directory": args.flywire_dir,
            "version": args.flywire_version,
            "hops": args.flywire_hops,
            "max_neurons": args.flywire_max_neurons,
        }
        if args.flywire_pa is not None:
            connectome_kwargs["pa_per_synapse"] = args.flywire_pa
    elif config.connectome == "neuprint":
        # The male CNS: brain plus ventral nerve cord, so the escape pathway reaches
        # motor neurons rather than terminating at the neck.
        connectome_kwargs = {"hops": args.flywire_hops,
                             "max_neurons": args.flywire_max_neurons}
        if args.postural:
            # Seeding on the leg motor pool as well as the escape reflex. Growing outward
            # from the reflex alone caught only its edge -- 2 Sternotrochanter MN of 14,
            # on 6-29 synapses of descending input, which never fire.
            from flysim.brain.neuprint_source import ESCAPE_AND_POSTURE_SEED_TYPES
            connectome_kwargs["seed_types"] = ESCAPE_AND_POSTURE_SEED_TYPES
            connectome_kwargs["max_neurons"] = max(args.flywire_max_neurons, 40_000)
        if args.flywire_pa is not None:
            connectome_kwargs["pa_per_synapse"] = args.flywire_pa

    if args.check:
        return run_check(config, connectome_kwargs)

    if args.interactive and args.no_show:
        parser_error = "--interactive needs a window; it cannot be combined with --no-show."
        print(parser_error)
        return 2

    runner = build_runner(
        config,
        lesion_lc4=args.lesion_lc4,
        connectome_kwargs=connectome_kwargs,
        interactive=args.interactive,
        motion=args.motion,
        retinotopy=args.retinotopy,
        channels=args.channels,
        neural_heading=args.neural_heading,
    )
    print(runner.brain.connectome.summary())

    if args.interactive:
        spf = args.steps_per_frame or INTERACTIVE_STEPS_PER_FRAME
        sim_ms = config.runner.frame_dt_ms * spf
        print(
            f"\nInteractive mode  (brain dt = {config.runner.brain_dt_ms} ms, "
            f"{spf} sim frames/render = {sim_ms:.0f} ms simulated per rendered frame)\n"
            "Move the mouse over the left panel to place the threat.\n"
            "  scroll = object size    r = reset fly    close the window to quit\n"
        )

    if args.no_show and not args.save:
        runner.run()
        print(json.dumps(runner.summary(), indent=2, default=str))
        return 0

    # Imported here rather than at module scope so --check, --no-show and --benchmark
    # never need a display or a Matplotlib backend.
    from flysim.viz.dashboard import Dashboard

    steps_per_frame = args.steps_per_frame
    if steps_per_frame is None:
        steps_per_frame = INTERACTIVE_STEPS_PER_FRAME if args.interactive else 1

    # Interactive sessions default the anatomical panel OFF. It roughly halves the frame
    # rate on a large connectome, and a laggy session makes the fly look frozen -- which is
    # the specific failure the steps-per-frame work went in to fix.
    show_brain = args.brain_view
    if show_brain is None:
        show_brain = not args.interactive

    dashboard = Dashboard(
        runner, config, steps_per_frame=steps_per_frame, show_brain=show_brain,
    )
    dashboard.run(save_path=args.save, show=not args.no_show)
    print(json.dumps(runner.summary(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
