"""Does the directional flip survive a shuffle?

    python tools/direction_control.py


Hemifield tuning makes a right-side threat fire the right Giant Fiber first. The question
is whether the MEASURED WIRING is what carries that, or whether the tuning alone produces
it and the anatomy is along for the ride.

The type-preserving shuffle reassigns partners within each (pre-type, post-type) block
without respecting hemisphere, so it scrambles the perfectly ipsilateral organisation the
flip depends on while preserving every type-level statistic. If the flip survives that, the
anatomy is not carrying direction.

Note the prediction as first registered said the shuffle must stop reproducing "the
behaviour". That was imprecise: the escape only needs enough total drive to reach the Giant
Fiber, and scrambling partners need not prevent it. The sharp claim is about the FLIP.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from dataclasses import replace
from flysim.brain.builders import build
from flysim.brain.lif import LIFBrain
from flysim import calibration
from flysim.config import SimConfig
from flysim.envs.interactive2d import InteractiveEnvironment
from flysim.interfaces.motor import GiantFiberDecoder
from flysim.interfaces.sensory import LoomingEncoder
from flysim.runner import SimulationRunner
from shuffle_control import shuffle_within_type, shuffle_degree

SPF = 5
from flysim.brain.loaders import cache_root  # noqa: E402
CACHE = cache_root() / "neuprint" / "male-cns-v1.0"
n = pd.read_parquet(
    CACHE / "LC4-LPLC2-DNp01-TTMn-PSI_h1_s5_n25000.neurons.parquet")
side_of = dict(zip(n.bodyId.astype(str), n.side.astype(str)))

profile = calibration.for_connectome("neuprint")
real = build("neuprint", seed=3, hops=1, max_neurons=25_000,
             pa_per_synapse=profile.pa_per_synapse)


def make_runner(cx):
    cfg = SimConfig().with_overrides(
        encoder={"gain_pa": profile.encoder_gain_pa, "hemifield_tuning": 1.0})
    brain = LIFBrain(cx, profile.neuron, cfg.runner.brain_dt_ms, seed=cfg.seed)
    watched = profile.decoder_population
    if watched not in brain.populations:
        watched = "GF"
    enc = LoomingEncoder(cfg.encoder, brain.populations, brain.size,
                         hemisphere=cx.hemisphere)
    dec = GiantFiberDecoder(replace(cfg.decoder, trigger_population=watched),
                            brain.populations)
    return SimulationRunner(InteractiveEnvironment(cfg.env), brain, enc, dec, cfg)


def flip(runner, bearing_deg, rep):
    env = runner.env
    env._rng = np.random.default_rng(11 + rep)
    runner.reset()
    env._threat_size = 0.060
    frame_s = SPF * runner.frame_dt_s
    labels = runner.brain.connectome.labels
    watch = {}
    for i, lb in enumerate(labels):
        name, _, body = str(lb).partition(":")
        if name == "DNp01":
            watch[i] = side_of.get(body, "?")
    ang = np.deg2rad(bearing_deg)
    unit = np.array([np.cos(ang), np.sin(ang)])
    first = {}
    for f in range(150):
        env._fly_pos[:] = 0.0
        env._fly_vel[:] = 0.0
        env._walk._heading = 0.0
        d = 0.35 - 0.8 * f * frame_s
        if d < 0.01:
            break
        env.set_threat_position(float(unit[0] * d), float(unit[1] * d))
        for _ in range(SPF):
            r = runner.step()
            if r.frame_spikes is None:
                continue
            for i in np.flatnonzero(r.frame_spikes):
                if int(i) in watch and int(i) not in first:
                    first[int(i)] = r.observation.t * 1000.0
    L = [first[i] for i, s in watch.items() if s == "L" and i in first]
    R = [first[i] for i, s in watch.items() if s == "R" and i in first]
    return None if not L or not R else min(L) - min(R)


print("\n  DNp01 left-minus-right first spike (ms), hemifield tuning ON")
print("  negative = LEFT leads, positive = RIGHT leads. The FLIP is the signal.\n")
print(f"  {'wiring':<28} {'threat RIGHT':>26} {'threat LEFT':>22}   flips?")
print("  " + "-" * 86)
for name, cx in (("MEASURED", real),
                 ("type-preserving shuffle", shuffle_within_type(real, 7)),
                 ("degree-preserving shuffle", shuffle_degree(real, 7))):
    runner = make_runner(cx)
    rights = [flip(runner, 90, r) for r in range(2)]
    lefts = [flip(runner, -90, r) for r in range(2)]
    fmt = lambda v: "    -    " if v is None else f"{v:+9.1f}"
    ok = (all(v is not None and v > 0 for v in rights)
          and all(v is not None and v < 0 for v in lefts))
    print(f"  {name:<28} {''.join(fmt(v) for v in rights):>26} "
          f"{''.join(fmt(v) for v in lefts):>22}   {'YES' if ok else 'no'}")
