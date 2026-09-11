"""Draw which cells light up for a threat at each bearing.

Cells are drawn at their INPUT CENTROID -- where in the columnar sheet they draw from --
because their somata sit in a rind and do not predict what they look at (measured: 1.03x
neighbour similarity against 3-4x for the columnar types).

Diagnostic, not decorative: a real map lights a coherent contiguous region per bearing. A
scatter means the azimuth assignment is noise.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flysim.brain.builders import build  # noqa: E402
from flysim.brain.loaders import cache_root  # noqa: E402

CACHE = cache_root() / "neuprint" / "male-cns-v1.0"
BASE = str(CACHE / "LC4-LPLC2-DNp01-TTMn-PSI_h1_s5_n25000")
n = pd.read_parquet(BASE + ".neurons.parquet")
c = pd.read_parquet(BASE + ".connections.parquet")
t = dict(zip(n.bodyId.astype(int), n.type.astype(str)))
pos = {int(b): np.array([x, y, z], float)
       for b, x, y, z in zip(n.bodyId, n.x, n.y, n.z) if np.isfinite(x)}

cx = build("neuprint", seed=3, hops=1, max_neurons=25000, pa_per_synapse=0.002)
az = cx.preferred_azimuth
lc4 = cx.populations["LC4"]
body_of = {i: int(str(cx.labels[i]).partition(":")[2]) for i in lc4}

def is_col(b):
    ty = t.get(b, ""); return ty[:2] in ("T4", "T5") or ty.startswith("Tm")
inc = {}
for pre, post, w in zip(c.pre.to_numpy(), c.post.to_numpy(), c.weight.to_numpy()):
    pre = int(pre)
    if is_col(pre) and pre in pos:
        inc.setdefault(int(post), []).append((pre, float(w)))
cent = {}
for body, g in inc.items():
    if len(g) >= 10:
        P = np.array([pos[p] for p, _ in g]); W = np.array([w for _, w in g])
        cent[body] = (P * W[:, None]).sum(0) / W.sum()

idx = [i for i in lc4 if np.isfinite(az[i]) and body_of[i] in cent]
X = np.array([cent[body_of[i]] for i in idx])
A = np.array([az[i] for i in idx])
mu = X.mean(0); V = np.linalg.svd(X - mu, full_matrices=False)[2]
UV = (X - mu) @ V[:2].T
print(f"  {len(idx)} cells drawn in input-centroid space")

FLOOR = 0.25
fig, axes = plt.subplots(1, 4, figsize=(17, 4.6))
for ax, (bearing, name) in zip(axes, ((0, "front (0 deg)"), (90, "right (+90)"),
                                      (180, "rear (180)"), (-90, "left (-90)"))):
    b = np.deg2rad(bearing)
    w = FLOOR + (1 - FLOOR) * 0.5 * (1 + np.cos(b - A))
    sc = ax.scatter(UV[:, 0], UV[:, 1], c=w, s=26, cmap="inferno",
                    vmin=FLOOR, vmax=1.0, linewidths=0)
    ax.set_title(f"threat {name}", fontsize=11)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect("equal")
    ax.text(0.02, 0.02, f"driven >0.8: {int((w > 0.8).sum())} cells",
            transform=ax.transAxes, fontsize=8, color="0.35")
fig.colorbar(sc, ax=axes, fraction=0.015, label="relative drive")
fig.suptitle("Which visual cells the threat drives, by bearing "
             "(cells placed at their columnar input centroid)", fontsize=12)
out = str(Path(__file__).resolve().parent.parent / "docs"
          / "field_by_bearing.png")
fig.savefig(out, dpi=110, bbox_inches="tight")
print(f"  saved {out}")

# Measured WITHIN each hemisphere: a frontal threat lights cells in both eyes, so two
# tight clusters look diffuse if spread is taken from a single centroid.
side_arr = cx.hemisphere[idx]
for bearing in (0, 90, 180, -90):
    b = np.deg2rad(bearing)
    w = FLOOR + (1 - FLOOR) * 0.5 * (1 + np.cos(b - A))
    lit = w > 0.8
    parts = []
    for sd, nm in ((-1, 'L'), (1, 'R')):
        m = lit & (side_arr == sd)
        base = side_arr == sd
        if m.sum() < 5:
            parts.append(f'{nm}: {int(m.sum())} lit')
            continue
        d_lit = np.linalg.norm(UV[m] - UV[m].mean(0), axis=1).mean()
        d_all = np.linalg.norm(UV[base] - UV[base].mean(0), axis=1).mean()
        parts.append(f'{nm}: {int(m.sum()):>3} lit, {d_lit/d_all:.2f}x')
    print(f'  bearing {bearing:>4}   ' + '   '.join(parts))
print('')
print('  ratio below 1 = lit cells occupy a sub-region of that eye field.')