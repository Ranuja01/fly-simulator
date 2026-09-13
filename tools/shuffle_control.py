"""Is the measured wiring load-bearing, or would any network with the same statistics do?

    python tools/shuffle_control.py
    python tools/shuffle_control.py --connectome flywire --values 0.02 0.01 0.005

The claim this tests is the strongest one the project makes: that the escape behaviour
comes from the anatomy rather than from the constants fitted on top of it. Stated loosely
it is easy to believe and easy to get wrong, because the obvious version of the experiment
is rigged.

**The rigged version.** Shuffle the wiring, re-run with the constants fitted for the REAL
wiring, and observe that the escape disappears. That proves very little. The constants were
chosen to make the real network work; a different network would need different constants,
and denying it those is not a fair comparison.

**The fair version, which is what this runs.** Give every wiring the same tuning budget.
Sweep ``pa_per_synapse`` across the same range for the real connectome and for each null
model, and ask what the BEST achievable behaviour is for each. If a shuffled network can be
tuned into a working escape reflex, the anatomy was not doing the work and the claim is
wrong. The comparison is between the best each wiring can manage, not between one tuned
network and several untuned ones.

**What counts as working** is taken from ``tools/calibrate_pa.py`` and is deliberately a
discrimination, not a response. Any scaling will make a circuit fire at something coming
straight at it; only a correct one also *withholds* the escape from a harmless slow drift.
A network that fires at everything has no threshold, and a network that fires at nothing is
not a reflex. A wiring passes only if it does both at the same value.

**Two null models**, because they destroy different things:

* ``degree`` — repeated double-edge swaps. In-degree and out-degree of every neuron are
  preserved exactly, as is the multiset of weights. What is destroyed is *which* neuron
  connects to which. This is the null for "the escape is just a consequence of some cells
  having many connections".
* ``type`` — edges are rewired within each (presynaptic type, postsynaptic type) block, so
  the number of connections and the weights between every pair of cell types are preserved
  exactly. What is destroyed is which individual cells within those types are wired
  together. This is the stronger null: it grants the shuffle the entire cell-type-level
  organisation of the real brain and asks whether anything is left.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flysim.brain.builders import build  # noqa: E402
from flysim.brain.connectome import Connectome  # noqa: E402
from flysim.brain.lif import LIFBrain  # noqa: E402
from flysim import calibration  # noqa: E402
from flysim.config import SimConfig  # noqa: E402
from flysim.envs.predator2d import Predator2DEnvironment  # noqa: E402
from flysim.interfaces.motor import GiantFiberDecoder  # noqa: E402
from flysim.interfaces.sensory import LoomingEncoder  # noqa: E402
from flysim.runner import SimulationRunner  # noqa: E402

THREATENING_SPEED_MS = 0.42
"""A real approach. A working reflex SHOULD fire."""

BENIGN_SPEED_MS = 0.08
"""A slow drift. A working reflex should NOT fire. This is the discriminating half."""

DEFAULT_VALUES = (0.02, 0.008, 0.004, 0.002, 0.001, 0.0004)


def _edges(connectome: Connectome):
    """Edge list ``(pre, post, weight)`` from either matrix representation."""
    w = connectome.weights
    if hasattr(w, "tocoo"):
        coo = w.tocoo()
        return (coo.row.astype(np.int64), coo.col.astype(np.int64),
                coo.data.astype(np.float32))
    pre, post = np.nonzero(w)
    return pre.astype(np.int64), post.astype(np.int64), np.asarray(w)[pre, post]


def _rebuild(connectome: Connectome, pre, post, data, name: str) -> Connectome:
    """A copy of ``connectome`` carrying a different edge set."""
    n = len(connectome.labels)
    if hasattr(connectome.weights, "tocoo"):
        import scipy.sparse as sp
        weights = sp.coo_matrix((data, (pre, post)), shape=(n, n),
                                dtype=np.float32).tocsr()
    else:
        weights = np.zeros((n, n), dtype=np.float32)
        np.add.at(weights, (pre, post), data)
    # dataclasses.replace rather than an explicit field list. A null model must differ
    # from the real network in the ONE respect under test -- which cells are wired to
    # which -- so everything else has to be carried through, and enumerating the fields
    # means every new one silently defaults to None in the nulls. That is not
    # hypothetical: `fast_weights` was added for the gap-junction latency work and an
    # explicit list dropped it, which would have deleted the escape pathway from every
    # shuffle and made them fail for a reason that has nothing to do with their wiring.
    # `hemisphere` and `preferred_azimuth` matter for the same reason: without them the
    # shuffles lose hemifield tuning and cannot express direction at all.
    return replace(
        connectome,
        name=name,
        weights=weights,
        description=f"NULL MODEL derived from {connectome.name}: {name}",
    )


def shuffle_degree(connectome: Connectome, seed: int, passes: int = 20) -> Connectome:
    """Double-edge swaps: exact in/out degrees, scrambled partners.

    Each swap takes edges ``a->b`` and ``c->d`` and rewrites them as ``a->d`` and ``c->b``.
    Every neuron keeps the number of inputs and outputs it had, and the weights travel with
    the edges, so the weight distribution is untouched.
    """
    rng = np.random.default_rng(seed)
    pre, post, data = _edges(connectome)
    m = len(pre)
    post = post.copy()
    data = data.copy()
    for _ in range(passes):
        i = rng.permutation(m)
        j = rng.permutation(m)
        # Vectorised swaps. Collisions (self-loops) are simply skipped.
        keep = (pre[i] != post[j]) & (pre[j] != post[i]) & (i != j)
        ii, jj = i[keep], j[keep]
        post[ii], post[jj] = post[jj].copy(), post[ii].copy()
        data[ii], data[jj] = data[jj].copy(), data[ii].copy()
    return _rebuild(connectome, pre, post, data, "shuffle-degree")


def shuffle_within_type(connectome: Connectome, seed: int) -> Connectome:
    """Rewire inside each (pre-type, post-type) block.

    The number of connections and the weights between any two cell types are preserved
    exactly; only which individual cells are joined changes. This hands the null model the
    whole cell-type-level architecture of the real brain, which makes it the harder test to
    pass.
    """
    rng = np.random.default_rng(seed)
    pre, post, data = _edges(connectome)

    def type_of(index: np.ndarray) -> np.ndarray:
        names = np.array([str(connectome.labels[i]).split(":", 1)[0] for i in index])
        return names

    pre_t, post_t = type_of(pre), type_of(post)
    # Cells available as a partner for each type, taken from the real network.
    by_type: dict[str, np.ndarray] = {}
    all_types = type_of(np.arange(len(connectome.labels)))
    for t in np.unique(all_types):
        by_type[t] = np.flatnonzero(all_types == t)

    new_pre, new_post = pre.copy(), post.copy()
    keys = np.char.add(np.char.add(pre_t, ">"), post_t)
    for key in np.unique(keys):
        block = np.flatnonzero(keys == key)
        a, b = key.split(">", 1)
        new_pre[block] = rng.choice(by_type[a], size=block.size, replace=True)
        new_post[block] = rng.choice(by_type[b], size=block.size, replace=True)
    ok = new_pre != new_post
    return _rebuild(connectome, new_pre[ok], new_post[ok], data[ok], "shuffle-type")


def trial(connectome: Connectome, profile, speed_ms: float, duration_s: float) -> dict:
    """One episode. Returns whether the reflex fired and at what angular size."""
    config = SimConfig().with_overrides(
        env={"predator_speed_ms": speed_ms, "duration_s": duration_s},
        encoder={"gain_pa": profile.encoder_gain_pa},
    )
    brain = LIFBrain(connectome, profile.neuron, config.runner.brain_dt_ms,
                     seed=config.seed)
    watched = profile.decoder_population
    if watched not in brain.populations:
        watched = "GF"
    from dataclasses import replace as _replace
    decoder = GiantFiberDecoder(
        _replace(config.decoder, trigger_population=watched), brain.populations
    )
    runner = SimulationRunner(
        Predator2DEnvironment(config.env), brain,
        LoomingEncoder(config.encoder, brain.populations, brain.size),
        decoder, config,
    )
    runner.run()
    s = runner.summary()
    return {"takeoffs": int(s["takeoffs"]), "deg": s["escape_angular_size_deg"]}


def evaluate(connectome: Connectome, profile, values) -> list[dict]:
    """Sweep the tuning budget, recording what each value achieves."""
    out = []
    for pa in values:
        scaled = Connectome(
            name=connectome.name,
            labels=connectome.labels,
            weights=connectome.weights * (pa / BASE_PA),
            populations=connectome.populations,
            hemisphere=connectome.hemisphere,
            param_overrides=connectome.param_overrides,
            description=connectome.description,
        )
        # Durations taken from tools/calibrate_pa.py, so this test and the tool that
        # produced the calibration are asking the same question. They matter: a 0.08 m/s
        # drift given long enough reaches contact, and firing at contact is CORRECT under
        # an expansion-rate encoder, so an over-long benign trial fails every wiring for
        # a reason that has nothing to do with wiring.
        threat = trial(scaled, profile, THREATENING_SPEED_MS, 2.4)
        benign = trial(scaled, profile, BENIGN_SPEED_MS, 6.0)
        works = threat["takeoffs"] >= 1 and benign["takeoffs"] == 0
        out.append({"pa": pa, "fires": threat["takeoffs"], "deg": threat["deg"],
                    "false_alarms": benign["takeoffs"], "discriminates": works})
    return out


def report(title: str, rows: list[dict]) -> bool:
    print(f"\n  {title}")
    print(f"    {'pA/syn':>9} {'escapes':>8} {'angle':>8} {'false alarms':>13}  verdict")
    print("    " + "-" * 62)
    any_ok = False
    for r in rows:
        deg = f"{r['deg']:6.1f}d" if r["deg"] is not None else "      -"
        verdict = "DISCRIMINATES" if r["discriminates"] else ""
        any_ok |= r["discriminates"]
        print(f"    {r['pa']:9.4f} {r['fires']:8d} {deg:>8} {r['false_alarms']:13d}"
              f"  {verdict}")
    print(f"    => best achievable: "
          f"{'a working reflex' if any_ok else 'NO value discriminates'}")
    return any_ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--connectome", default="neuprint")
    ap.add_argument("--values", type=float, nargs="+", default=list(DEFAULT_VALUES))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--wiring", default="all",
                    choices=["all", "measured", "degree", "type"],
                    help="Run one wiring at a time; the full sweep on a "
                         "22,973-neuron network does not fit one sitting.")
    ap.add_argument("--hops", type=int, default=1)
    ap.add_argument("--max-neurons", type=int, default=25_000)
    args = ap.parse_args()

    profile = calibration.for_connectome(args.connectome)
    BASE_PA = profile.pa_per_synapse or 1.0
    real = build(args.connectome, seed=3, hops=args.hops,
                 max_neurons=args.max_neurons, pa_per_synapse=BASE_PA)

    pre, post, _ = _edges(real)
    lc4 = set(real.populations["LC4"].tolist())
    gf = set(real.populations["GF"].tolist())
    direct = int(sum(1 for a, b in zip(pre, post) if a in lc4 and b in gf))
    print(f"\n  {args.connectome}: {len(real.labels):,} neurons, {len(pre):,} edges, "
          f"{direct} direct LC4->GF connections")

    wanted = {
        "measured": [("MEASURED wiring", lambda: real)],
        "degree": [("NULL: degree-preserving shuffle",
                    lambda: shuffle_degree(real, args.seed))],
        "type": [("NULL: type-preserving shuffle",
                  lambda: shuffle_within_type(real, args.seed))],
    }
    chosen = (wanted["measured"] + wanted["degree"] + wanted["type"]
              if args.wiring == "all" else wanted[args.wiring])

    results = {}
    for name, make in chosen:
        cx = make()
        p, q, _ = _edges(cx)
        d = int(sum(1 for a, b in zip(p, q) if a in lc4 and b in gf))
        results[name] = report(f"{name}  ({len(p):,} edges, {d} direct LC4->GF)",
                               evaluate(cx, profile, args.values))

    print("\n  " + "=" * 64)
    print("  Every wiring received the SAME tuning budget.")
    for name, ok in results.items():
        print(f"    {name:<34} {'works at some value' if ok else 'never works'}")
    if results["MEASURED wiring"] and not any(
        v for k, v in results.items() if k != "MEASURED wiring"
    ):
        print("\n  => The measured wiring is load-bearing: no shuffle can be tuned into\n"
              "     a reflex, so the behaviour is not a consequence of the statistics.")
    else:
        print("\n  => Claim NOT supported as stated. Read the table before repeating it.")
