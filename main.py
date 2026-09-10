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
from flysim.config import SimConfig
from flysim.envs.interactive2d import InteractiveEnvironment
from flysim.envs.predator2d import Predator2DEnvironment
from flysim.interfaces.motor import GiantFiberDecoder
from flysim.interfaces.sensory import LoomingEncoder
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
    config = config.with_overrides(encoder={"gain_pa": profile.encoder_gain_pa})
    neuron_params = profile.neuron
    print(calibration.describe(profile))

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
    encoder = LoomingEncoder(config.encoder, brain.populations, brain.size)

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
    decoder = GiantFiberDecoder(decoder_params, brain.populations)

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

    first = s["first_spike_ms"]
    require(first["LC4"] is not None, "LC4 fires")
    require(first["GF"] is not None, "GF fires")
    if first["LC4"] is not None and first["GF"] is not None:
        require(first["GF"] > first["LC4"],
                f"GF ({first['GF']:.1f} ms) fires after LC4 ({first['LC4']:.1f} ms)")
    if first.get("PMN") is not None and first["GF"] is not None:
        require(first["GF"] > first["PMN"],
                f"GF fires after the premotor pool ({first['PMN']:.1f} ms)")

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
    require(slow_summary["first_spike_ms"]["GF"] is None,
            "feedforward inhibition suppresses GF for a slow approach")

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
