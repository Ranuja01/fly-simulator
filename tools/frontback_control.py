"""Does DNp04's 124 ms front/rear separation survive repeats?

Front (0 deg) and rear (180 deg) are both on the midline, so the left/right effect is
excluded and any difference is front/back. Five seeds per condition; the noise floor
measured earlier is 30-40 ms.
"""
import sys
from pathlib import Path
from dataclasses import replace
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flysim.config import SimConfig
from main import build_runner, INTERACTIVE_STEPS_PER_FRAME as SPF

from flysim.brain.loaders import cache_root  # noqa: E402
CACHE = cache_root() / "neuprint" / "male-cns-v1.0"
n = pd.read_parquet(
    CACHE / "LC4-LPLC2-DNp01-TTMn-PSI_h1_s5_n25000.neurons.parquet")
side_of = dict(zip(n.bodyId.astype(str), n.side.astype(str)))
runner = build_runner(replace(SimConfig(), connectome="neuprint"),
                      connectome_kwargs={"hops": 1, "max_neurons": 25000},
                      interactive=True, retinotopy=True)
env, labels = runner.env, runner.brain.connectome.labels
WATCH = ("DNp01", "DNp04", "DNp103", "DNp11")
idx = {}
for i, lb in enumerate(labels):
    nm, _, body = str(lb).partition(":")
    if nm in WATCH:
        idx[i] = nm


def trial(bearing_deg, rep):
    env._rng = np.random.default_rng(100 + rep)
    runner.reset()
    env._threat_size = 0.060
    fs = SPF * runner.frame_dt_s
    a = np.deg2rad(bearing_deg)
    u = np.array([np.cos(a), np.sin(a)])
    first = {}
    for f in range(150):
        env._fly_pos[:] = 0.0
        env._fly_vel[:] = 0.0
        env._walk._heading = 0.0
        d = 0.35 - 0.8 * f * fs
        if d < 0.01:
            break
        env.set_threat_position(float(u[0] * d), float(u[1] * d))
        for _ in range(SPF):
            r = runner.step()
            if r.frame_spikes is None:
                continue
            for i in np.flatnonzero(r.frame_spikes):
                if int(i) in idx and idx[int(i)] not in first:
                    first[idx[int(i)]] = r.observation.t * 1000.0
    return first


REPS = 5
res = {w: {"front": [], "rear": []} for w in WATCH}
for rep in range(REPS):
    for bearing, key in ((0, "front"), (180, "rear")):
        f = trial(bearing, rep)
        for w in WATCH:
            res[w][key].append(f.get(w))

print(f"\n  First spike (ms), {REPS} seeds. Noise floor measured earlier: 30-40 ms.\n")
print(f"  {'pair':<9} {'front (mean+-sd)':>20} {'rear (mean+-sd)':>20} "
      f"{'diff':>8}  verdict")
print("  " + "-" * 72)
for w in WATCH:
    fr = [v for v in res[w]["front"] if v is not None]
    re_ = [v for v in res[w]["rear"] if v is not None]
    if len(fr) < 3 or len(re_) < 3:
        print(f"  {w:<9} too often silent "
              f"(front {len(fr)}/{REPS}, rear {len(re_)}/{REPS})")
        continue
    mf, sf = np.mean(fr), np.std(fr)
    mr, sr = np.mean(re_), np.std(re_)
    diff = mf - mr
    pooled = np.hypot(sf, sr)
    verdict = ("SEPARATES" if abs(diff) > max(40.0, 2 * pooled)
               else "inside noise")
    print(f"  {w:<9} {mf:>13.0f} +-{sf:<5.0f} {mr:>13.0f} +-{sr:<5.0f} "
          f"{diff:>+8.0f}  {verdict}")
