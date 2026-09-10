"""Calibrate picoamps-per-synapse against the real connectome.

    python tools/calibrate_pa.py
    python tools/calibrate_pa.py --values 0.05 0.02 0.01 --hops 2

A connectome gives you anatomy, not physiology. The one number it cannot supply is how
much current one synapse delivers, and that number is not cosmetic: it decides whether the
circuit behaves like a reflex or like a threshold-free amplifier.

This sweeps the constant and measures two things per value:

1. **Escape threshold** — the angular size of the threat when the Giant Fiber fires.
2. **Gating** — does a slow, non-threatening approach correctly fail to trigger an escape?

(2) is the one that matters. Any scaling will produce an escape from a fast-approaching
predator; only a correctly-scaled one *withholds* the escape from a harmless object. A
circuit that fires for everything has no threshold at all.

The connectome tables are loaded once and reused across the sweep, so the large read
happens a single time.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running as `python tools/calibrate_pa.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flysim.brain import loaders  # noqa: E402
from flysim.brain.lif import LIFBrain  # noqa: E402
from flysim.config import SimConfig  # noqa: E402
from flysim.envs.predator2d import Predator2DEnvironment  # noqa: E402
from flysim.interfaces.motor import GiantFiberDecoder  # noqa: E402
from flysim.interfaces.sensory import LoomingEncoder  # noqa: E402
from flysim.runner import SimulationRunner  # noqa: E402

DEFAULT_VALUES = (0.6, 0.2, 0.08, 0.04, 0.02, 0.01, 0.005)

THREATENING_SPEED_MS = 0.42
"""A real approach. The reflex SHOULD fire."""

BENIGN_SPEED_MS = 0.08
"""A slow drift. The reflex should NOT fire — this is the discriminating test."""


def run_trial(connectome, speed_ms: float, duration_s: float) -> dict:
    """Run one episode against a given connectome and approach speed."""
    config = SimConfig().with_overrides(
        env={"predator_speed_ms": speed_ms, "duration_s": duration_s}
    )
    brain = LIFBrain(connectome, config.neuron, config.runner.brain_dt_ms, seed=config.seed)
    environment = Predator2DEnvironment(config.env)
    encoder = LoomingEncoder(config.encoder, brain.populations, brain.size)
    decoder = GiantFiberDecoder(config.decoder, brain.populations)

    runner = SimulationRunner(environment, brain, encoder, decoder, config)
    runner.run()
    return runner.summary()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=str, default=None,
                        help="Codex download directory. Defaults to $FLYSIM_CACHE_DIR.")
    parser.add_argument("--version", type=str, default="v783")
    parser.add_argument("--hops", type=int, default=1)
    parser.add_argument("--max-neurons", type=int, default=25_000)
    parser.add_argument("--values", type=float, nargs="+", default=list(DEFAULT_VALUES),
                        help="pA-per-synapse values to sweep.")
    args = parser.parse_args(argv)

    print("Loading connectome tables once ...")
    connections, annotations, _ = loaders.load_codex_tables(args.dir, args.version)
    keep = loaders.select_pathway(
        connections, annotations, hops=args.hops, max_neurons=args.max_neurons
    )
    print()

    header = (
        f"{'pA/syn':>8} {'escape theta':>13} {'takeoffs':>9} {'outcome':>10} │ "
        f"{'slow: GF?':>10} {'outcome':>11}   verdict"
    )
    print(header)
    print("─" * len(header))

    results = []
    for pa in args.values:
        started = time.time()
        connectome = loaders.connectome_from_tables(
            connections, annotations, keep_ids=keep,
            name=f"flywire-{args.version}-pa{pa}", pa_per_synapse=pa,
        )
        threatening = run_trial(connectome, THREATENING_SPEED_MS, 2.4)
        benign = run_trial(connectome, BENIGN_SPEED_MS, 6.0)

        theta = threatening["escape_angular_size_deg"]
        escaped = threatening["outcome"] == "escaped"
        fired_on_benign = benign["first_spike_ms"]["GF"] is not None

        if not escaped:
            verdict = "FAIL: no escape"
        elif fired_on_benign:
            verdict = "FAIL: ungated"
        else:
            verdict = "pass"

        results.append((pa, theta, verdict))
        print(
            f"{pa:>8} {(f'{theta:.1f}' if theta else '--'):>13} "
            f"{threatening['takeoffs']:>9} {threatening['outcome']:>10} │ "
            f"{('YES' if fired_on_benign else 'no'):>10} {benign['outcome']:>11}   "
            f"{verdict}   [{time.time() - started:.0f}s]"
        )

    passing = [r for r in results if r[2] == "pass"]
    print()
    if passing:
        print(f"Working range: {min(r[0] for r in passing)} to "
              f"{max(r[0] for r in passing)} pA/synapse.")
        print("Within it, pick the value whose escape threshold matches your reference "
              "measurement. Currently that reference is the hand-tuned mock circuit "
              "(24.6 deg), which is a consistency check, not physiology.")
    else:
        print("No value in this sweep produced a correctly gated reflex.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
