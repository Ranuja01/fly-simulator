"""Fit the two feature channels against two published targets, not one.

    python tools/calibrate_channels.py --probe
    python tools/calibrate_channels.py
    python tools/calibrate_channels.py --velocity 3 4 5 --size-gain 60 90 --width 12 18 24

Ache et al. 2019 measured LC4 and LPLC2 as different feature detectors: LC4 encodes looming
SPEED, LPLC2 encodes angular SIZE, and the giant fiber sums a linear function of angular
velocity with a Gaussian function of angular size peaking near 42 degrees. ``--channels``
implements that split, but its three parameters -- the velocity gain, the size gain and the
Gaussian's width -- were fitted against a single published number, the ~39 degree takeoff
threshold. Three unknowns against one equation is under-determined.

This sweeps all three and scores each setting against **two** independent targets:

1. **Threshold** -- the intact escape fires at 39 +/- 3 degrees (von Reyn et al. 2014).
2. **Lesion** -- silencing LPLC2 near-abolishes the escape, because it removes the size
   component and leaves velocity (Ache et al. 2019). The pre-split model could not do this:
   with no size channel, silencing LPLC2 merely removed generic drive.

The lesion is what makes the fit determined. The threshold constrains the two channels'
SUM; the lesion constrains their RATIO.

Deliberately does NOT go through ``main.build_runner``, which overwrites ``gain_pa`` from
the calibration profile. That silently invalidated an entire earlier sweep -- every run used
26.0 while reporting the swept value -- so this assembles the four layers directly and
prints the gain it actually ran with.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flysim import calibration  # noqa: E402
from flysim.brain.builders import build  # noqa: E402
from flysim.brain.lif import LIFBrain  # noqa: E402
from flysim.config import SimConfig  # noqa: E402
from flysim.envs.predator2d import Predator2DEnvironment  # noqa: E402
from flysim.interfaces.motor import GiantFiberDecoder  # noqa: E402
from flysim.interfaces.sensory import LoomingEncoder  # noqa: E402
from flysim.runner import SimulationRunner  # noqa: E402

TARGET_DEG = 39.0
"""von Reyn et al. 2014, GF-mediated takeoff threshold."""

TOLERANCE_DEG = 3.0
"""Half-width of the passing band. Set before measuring."""

APPROACH_SPEED_MS = 0.42
"""The same approach speed the pA sweep used, so thresholds stay comparable."""

DURATION_S = 3.0


def lplc2_indices(connectome) -> np.ndarray:
    """Every LPLC2 cell, by label.

    Labels carry ``TYPE:bodyid``. Matching on the type prefix rather than on a population
    because LC4 and LPLC2 share the ``LC4`` population -- the population is the injection
    target, not the cell type.
    """
    out = [
        i for i, label in enumerate(connectome.labels)
        if str(label).split(":", 1)[0].upper().startswith("LPLC2")
    ]
    return np.asarray(out, dtype=np.int64)


def run_trial(connectome, profile, *, velocity_gain, size_gain, width_deg,
              lesion=None, hemifield=0.0, form="linear") -> dict:
    """One episode at one parameter setting."""
    config = SimConfig().with_overrides(
        env={"predator_speed_ms": APPROACH_SPEED_MS, "duration_s": DURATION_S},
        encoder={
            "split_feature_channels": True,
            "gain_pa": velocity_gain,
            "size_gain_pa": size_gain,
            "size_width_deg": width_deg,
            "size_log_width": width_deg,
            "size_tuning_form": form,
            "hemifield_tuning": hemifield,
        },
    )
    brain = LIFBrain(connectome, params=profile.neuron,
                     dt_ms=config.runner.brain_dt_ms, seed=config.seed)
    if lesion is not None and lesion.size:
        brain.silence(lesion)

    environment = Predator2DEnvironment(config.env)
    encoder = LoomingEncoder(
        config.encoder, brain.populations, brain.size,
        hemisphere=getattr(connectome, "hemisphere", None),
        preferred_azimuth=getattr(connectome, "preferred_azimuth", None),
        labels=connectome.labels,
    )
    # The profile decides which population the takeoff is READ from, and on this dataset
    # that is MOTOR, not GF. Using the DecoderParams default would fit the threshold at
    # giant-fiber firing while every real run reports it ~6 ms later at the muscle -- a
    # fit to a quantity nothing else measures.
    watched = profile.decoder_population
    if watched not in brain.populations:
        watched = "GF"
    decoder = GiantFiberDecoder(replace(config.decoder, trigger_population=watched),
                                brain.populations)
    runner = SimulationRunner(environment, brain, encoder, decoder, config)
    runner.run()
    return runner.summary()


def score(intact: dict, lesioned: dict):
    """Both published targets, judged separately so a partial pass is visible."""
    theta = intact.get("escape_angular_size_deg")
    hit_threshold = theta is not None and abs(theta - TARGET_DEG) <= TOLERANCE_DEG

    # "Near-abolished" means the reflex stopped working, not that it shifted a little.
    lesion_theta = lesioned.get("escape_angular_size_deg")
    abolished = lesioned.get("takeoffs", 0) == 0 or lesion_theta is None
    lesion_note = "abolished" if abolished else "%.1f deg" % lesion_theta

    if hit_threshold and abolished:
        verdict = "PASS"
    elif hit_threshold:
        verdict = "threshold only"
    elif abolished:
        verdict = "lesion only"
    else:
        verdict = "-"
    return hit_threshold, abolished, "%s (%s)" % (verdict, lesion_note)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--velocity", type=float, nargs="+",
                        default=[2.0, 3.0, 4.0, 5.0, 7.0])
    parser.add_argument("--size-gain", type=float, nargs="+",
                        default=[45.0, 90.0, 135.0])
    parser.add_argument("--width", type=float, nargs="+",
                        default=[9.0, 18.0, 27.0])
    parser.add_argument("--probe", action="store_true",
                        help="Time a single trial and exit, before committing to a grid.")
    parser.add_argument("--form", type=str, default="linear",
                        choices=["linear", "log"],
                        help="Size-tuning functional form. --width is read in degrees for "
                             "'linear' and in natural-log units for 'log'.")
    parser.add_argument("--hemifield", type=float, default=0.0,
                        help="Hemifield tuning for every trial in the sweep. The fit is "
                             "condition-specific: tuning scales drive by bearing, so a "
                             "fit made with it off does not transfer to a run with it on.")
    parser.add_argument("--retinotopy-check", action="store_true",
                        help="Re-measure the best setting with hemifield tuning on.")
    args = parser.parse_args(argv)

    profile = calibration.for_connectome("neuprint")
    print("Building the neuprint connectome once ...")
    # max_neurons matches the cached subnetwork, so this reads from disk rather than
    # hitting the NeuPrint API.
    connectome = build("neuprint", seed=SimConfig().seed,
                       pa_per_synapse=profile.pa_per_synapse,
                       hops=1, max_neurons=25_000)
    lesion = lplc2_indices(connectome)
    print("  %d neurons, %d LPLC2 cells for the lesion" % (connectome.size, lesion.size))
    # The condition is part of the result. A fit reported without saying whether hemifield
    # tuning was on is not reproducible -- it moves the threshold by ~5 degrees.
    print("  target %.0f +/- %.0f deg at %.2f m/s, %.1fs episodes, hemifield tuning %.1f, "
          "%s size tuning\n"
          % (TARGET_DEG, TOLERANCE_DEG, APPROACH_SPEED_MS, DURATION_S,
             args.hemifield, args.form))

    if args.probe:
        started = time.time()
        # Reads the sweep's own arguments. Hardcoding them made --probe report the linear
        # form's threshold while the banner said "log" -- a result labelled as a condition
        # it was not run in.
        summary = run_trial(connectome, profile, velocity_gain=args.velocity[0],
                            size_gain=args.size_gain[0], width_deg=args.width[0],
                            hemifield=args.hemifield, form=args.form)
        elapsed = time.time() - started
        print("one trial: %.1fs  ->  theta %s, takeoffs %s, %s"
              % (elapsed, summary.get("escape_angular_size_deg"),
                 summary.get("takeoffs"), summary.get("outcome")))
        total = len(args.velocity) * len(args.size_gain) * len(args.width) * 2
        print("full grid is %d trials, about %.0f min" % (total, total * elapsed / 60))
        return 0

    header = ("%6s %6s %6s | %7s %9s | %22s"
              % ("vel", "size", "width", "theta", "takeoffs", "lesioned"))
    print(header)
    print("-" * len(header))

    passing = []
    grid = 0
    for v in args.velocity:
        for g in args.size_gain:
            for w in args.width:
                grid += 1
                intact = run_trial(connectome, profile, velocity_gain=v,
                                   size_gain=g, width_deg=w, hemifield=args.hemifield,
                                   form=args.form)
                lesioned = run_trial(connectome, profile, velocity_gain=v,
                                     size_gain=g, width_deg=w, lesion=lesion,
                                     hemifield=args.hemifield, form=args.form)
                hit, abolished, note = score(intact, lesioned)
                theta = intact.get("escape_angular_size_deg")
                if hit and abolished:
                    passing.append((v, g, w, theta))
                print("%6s %6s %6s | %7s %9s | %22s"
                      % (v, g, w, ("%.1f" % theta) if theta else "--",
                         intact.get("takeoffs", 0), note))

    print()
    if not passing:
        print("NO setting satisfied both targets. That is the result: the split as "
              "implemented cannot reproduce the threshold and the lesion at once.")
        return 0

    print("%d of %d settings satisfied both targets:" % (len(passing), grid))
    for v, g, w, theta in passing:
        print("  velocity %s, size %s, width %s  ->  %.1f deg" % (v, g, w, theta))
    if len(passing) == 1:
        print("\nA single passing point is weak evidence -- it may be a grid coincidence. "
              "Re-run with a finer grid around it before adopting the values.")

    if args.retinotopy_check:
        v, g, w, theta = min(passing, key=lambda r: abs(r[3] - TARGET_DEG))
        tuned = run_trial(connectome, profile, velocity_gain=v, size_gain=g,
                          width_deg=w, hemifield=1.0)
        print("\nhemifield tuning on, at the best point: %s deg against %.1f off. "
              "Reported as a shift, not folded into the fit."
              % (tuned.get("escape_angular_size_deg"), theta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
