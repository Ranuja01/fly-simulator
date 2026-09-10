# Production Connectome Access

How to get real *Drosophila* connectivity into this simulator: obtaining credentials,
querying the live databases, filtering down to a specific pathway (worked example: LC4 →
Giant Fiber), and converting the result into the `Connectome` object the LIF engine
already accepts.

> **Nothing in this document is required to run the Starter Phase.** `python main.py`
> works with no account, no token, and no download.

---

## 0. Install

```powershell
pip install -r requirements-connectome.txt
```

Or, if you only want connectivity and want to skip the heavy morphology stack:

```powershell
pip install neuprint-python pandas scipy pyarrow     # NeuPrint only
pip install caveclient fafbseg                        # FlyWire only
pip install navis                                     # skeletons/NBLAST (large)
```

`navis` pulls in igraph, trimesh, plotly and ncollpyde. Install it only when you actually
need morphology.

---

## 1. Which Codex dataset

Codex offers several. For the LC4 → Giant Fiber escape circuit:

| Dataset | Contents | Verdict |
|---|---|---|
| **FAFB v783 (CB)** | Female adult **brain**, 139,255 neurons, 3,732,460 connections | **Use this.** Mature LC4 and DNp01 annotations; what the loader defaults to |
| BANC v888 (CNS) | Female brain **+ nerve cord**, 158,262 neurons | Later — full CNS |
| MCNS v1.0 (CNS) | Male brain **+ nerve cord**, 166,700 neurons | Later — the "MaleCNS" dataset |
| MANC v1.2.1 (VNC) | Male **nerve cord only**, 23,665 neurons | No brain, so no LC4 |
| MAOL v1.1 (OL/R) | Male **right optic lobe only**, 52,445 neurons | Has LC4, but no Giant Fiber |

**The brain-only limitation, stated plainly:** the Giant Fiber's dendrites — where LC4
synapses onto it — are in the brain, but its axon terminals onto the TTM motor neuron and
PSI are in the ventral nerve cord. FAFB therefore gives you the *input* side of the escape
circuit and truncates the *output* side.

That is fine for this simulator as it stands, because `GiantFiberDecoder` abstracts the
motor side away: a GF spike becomes a takeoff directly, which is how the all-or-none
command actually behaves. You need a CNS dataset (BANC or MCNS) only when you want to model
muscle activation itself.

## 2. Choosing a source

| | **NeuPrint** (Janelia) | **FlyWire** (FAFB) |
|---|---|---|
| Datasets | hemibrain, MANC (ventral nerve cord), male CNS | Full adult female brain |
| Scale | hemibrain ~25k neurons; male CNS ~160k **(estimate)** | ~139k proofread neurons, ~54M synapses |
| Coverage | hemibrain is *one hemisphere*, partially truncated | Whole brain, both hemispheres |
| Credential | Auth token from a web login (minutes) | CAVE token; requires community registration first |
| Query style | Cypher / Neo4j, with a Python wrapper | Materialized tables via CAVE, or bulk CSV |
| No-credential option | no | **yes** — Codex bulk CSV download |

**Recommendation for a first real run: the FlyWire Codex bulk CSV.** It needs no token, it
is a single download, and it gives you the entire ~2.7M-edge connectome as a flat table.
Set up API access afterwards, once you know what you want to query.

---

## 3. NeuPrint: getting a token

1. Go to **https://neuprint.janelia.org** and sign in with a Google account.
2. Click your **account icon** (top right) → **Account**.
3. Copy the **Auth Token**. It is a long JWT string.
4. Store it as an environment variable — never in the repo:

```powershell
setx NEUPRINT_APPLICATION_CREDENTIALS "eyJhbGciOi...your token..."
```

Open a new terminal for `setx` to take effect.

### Connect, and discover the dataset names rather than guessing them

Dataset version strings change between releases. Enumerate them instead of hardcoding:

```python
import os
from neuprint import Client

client = Client(
    "neuprint.janelia.org",
    dataset="hemibrain:v1.2.1",              # placeholder; corrected below
    token=os.environ["NEUPRINT_APPLICATION_CREDENTIALS"],
)

# The authoritative list of what this server actually serves right now:
for name, meta in client.fetch_datasets().items():
    print(f"{name:<28} {meta.get('lastmod', '')}")
```

Pick the exact string this prints (something like `hemibrain:v1.2.1`, `manc:v1.2.1`, or a
male-CNS entry) and pass it as `dataset=`.

### Worked example: LC4 → Giant Fiber

The Giant Fiber is the descending neuron **DNp01**. LC4 is a lobula columnar visual
projection type. Both are annotated by `type` in NeuPrint.

```python
import pandas as pd
from neuprint import Client, fetch_neurons, fetch_adjacencies
from neuprint import NeuronCriteria as NC

# 1. Find the cells. NeuronCriteria matches on type, status, ROI, side, etc.
lc4_df, _ = fetch_neurons(NC(type="LC4", status="Traced"))
gf_df, _ = fetch_neurons(NC(type="DNp01", status="Traced"))
print(f"{len(lc4_df)} LC4, {len(gf_df)} DNp01")

# 2. Fetch the connections between exactly those two sets.
#    `neuron_df` is per-neuron metadata; `conn_df` is the edge list.
neuron_df, conn_df = fetch_adjacencies(
    sources=NC(bodyId=lc4_df.bodyId.tolist()),
    targets=NC(bodyId=gf_df.bodyId.tolist()),
)

# fetch_adjacencies returns per-ROI rows; sum across ROIs for a whole-cell weight.
edges = (
    conn_df.groupby(["bodyId_pre", "bodyId_post"], as_index=False)["weight"]
    .sum()
    .sort_values("weight", ascending=False)
)
print(edges.head(10))
print(f"total LC4->GF synapses: {edges.weight.sum()}")
```

The equivalent raw Cypher, so you are not locked into the wrapper:

```python
q = """
MATCH (pre:Neuron)-[c:ConnectsTo]->(post:Neuron)
WHERE pre.type = "LC4" AND post.type = "DNp01"
RETURN pre.bodyId AS pre, post.bodyId AS post, c.weight AS weight
ORDER BY weight DESC
"""
edges = client.fetch_custom(q)
```

`fetch_custom` takes arbitrary Cypher, which is how you express anything the convenience
functions do not cover (multi-hop paths, ROI restrictions, neurotransmitter filters).

---

## 4. FlyWire: two routes

### Route A — bulk CSV, no credential (recommended first)

FlyWire publishes each public release as flat tables through **Codex**
(`codex.flywire.ai` → Downloads). The page offers ~20 files totalling ~16 GB. You need
**five, totalling ~72 MB**:

| File | Size | Why |
|---|---|---|
| **Connections (Filtered)** | 68 MB | The edge list, already thresholded. **Essential** |
| **Cell Types** | 900 KB | Makes LC4 / LPLC2 / DNp01 findable. **Essential** |
| **Neurotransmitter Type Predictions** | 1.7 MB | Signs each edge. **Essential** |
| Classification / Hierarchical Annotations | 930 KB | Adds side, super-class. Recommended |
| Visual Neuron Annotations | 630 KB | LC4 subtypes. Recommended |

Deliberately skip:

| File | Size | Why not |
|---|---|---|
| Connections (Unfiltered) | 277 MB | Sub-threshold pairs dominated by segmentation error |
| Synapse Table | **2.7 GB** | Per-synapse; only for spatial/compartment analysis |
| Neuron Skeletons | **13 GB** | Morphology only |
| Anything "[Original Version Prior To July 2025]" | — | Superseded |

Put all five in one directory under the cache root, *not* in the repo, keeping the
original filenames:

```powershell
mkdir E:\FlyConnectome\cache\flywire\v783
# download the five files into it, then:
setx FLYSIM_CACHE_DIR "E:\FlyConnectome\cache"
python main.py --connectome flywire
```

That is the whole procedure. `flysim/brain/loaders.py` identifies each file by content
rather than by name, merges every per-neuron annotation table on the root-id column, skips
the ones that are not per-neuron annotations, prefers the filtered edge list over the
unfiltered one, and caches Parquet copies on first load. Verified output:

```
  skipping cell_size_measurements.csv (not a per-neuron annotation)
  skipping synapse_coordinates.csv (not a per-neuron annotation)
  using connections_filtered.csv for connections
  merged cell_types.csv (782 rows)
  merged classification_hierarchical_annotations.csv (782 rows)
  merged neurotransmitter_type_predictions.csv (782 rows)
```

If you would rather drive it by hand, the tables are ordinary DataFrames:

```python
from flysim.brain.loaders import load_codex_tables
conn, ann = load_codex_tables(version="v783")

type_of = ann.set_index("root_id")["cell_type"]
lc4_ids = set(type_of[type_of == "LC4"].index)
gf_ids = set(type_of[type_of == "DNp01"].index)

pathway = conn[conn.pre_root_id.isin(lc4_ids) & conn.post_root_id.isin(gf_ids)]
print(pathway.groupby("neuropil").syn_count.sum())
```

Column names vary between releases — `COLUMN_ALIASES` in the loader absorbs the variants,
and raises a message naming your actual columns if it meets a new one.

### Route B — live CAVE queries (needs registration + token)

FlyWire requires **community registration and agreement to the data terms** before a token
will work. That approval is a manual step on their side, so **start it early** if you want
this route; it is the long pole in the whole project.

```python
from caveclient import CAVEclient

# One-time: opens a browser page that displays your token.
client = CAVEclient()
client.auth.setup_token(make_new=True)      # prints a URL — visit it, copy the token
client.auth.save_token(token="PASTE_TOKEN_HERE")
```

The token is written to `~/.cloudvolume/secrets/cave-secret.json`. After that:

```python
from caveclient import CAVEclient

client = CAVEclient("flywire_fafb_public")   # read-only public datastack
print(client.materialize.get_versions())      # e.g. [783]

syn = client.materialize.query_table(
    "synapses_nt_v1",
    filter_in_dict={"pre_pt_root_id": list(lc4_ids)},
    limit=100_000,
)
```

Or via the `fafbseg` convenience layer:

```python
from fafbseg import flywire
edges = flywire.get_connectivity(lc4_ids, upstream=False, downstream=True)
```

**Datastack names and table names change between releases.** Call
`client.materialize.get_tables()` and `client.info.get_datastacks()` rather than trusting
any string in this document.

---

## 5. Converting anything into a `Connectome`

**This is already implemented.** `flysim/brain/loaders.py` does the whole conversion, and
the CLI is wired to it:

```powershell
setx FLYSIM_CACHE_DIR "E:\FlyConnectome\cache"
# put connections.csv + classification.csv in E:\FlyConnectome\cache\flywire\v783\
python main.py --connectome flywire
```

Verified output on a table with the real Codex schema:

```
Loading FlyWire tables from ...\flywire\v783
  cached connections.parquet (0.1 MiB)
  20,903 raw edges, 782 classified neurons
  seeds: 242 neurons matching ['DNP01', 'LC4', 'LPLC2']
  hop 1: 482 neurons
  built connectome: 482 neurons, 16,353 edges (GF=2, INH=106, LC4=240, PMN=134)
```

and it then runs through the **unchanged** environment, encoder, LIF engine, decoder and
dashboard.

### What the loader handles for you

| Concern | How |
|---|---|
| Column-name drift between releases | `COLUMN_ALIASES` maps logical fields to every spelling seen in the wild; a miss raises a message naming the columns your table actually has |
| CSV → Parquet caching | Converted on first load, beside the CSV. Later loads are ~10× faster |
| Synapse threshold | `min_synapses=5`, the field convention |
| Sign of an edge | From the presynaptic neuron's transmitter (Dale's principle), not per-edge |
| Modulatory neurons | Aminergic edges map to sign 0 and are dropped, with a count reported |
| Subnetwork extraction | `select_pathway()` grows N hops from seed cell types, with a `max_neurons` cap so one hop off a descending neuron cannot pull in the whole brain |
| Dense vs sparse | Chosen automatically at 3000 neurons |
| Duplicate edges | Accumulated, not overwritten — two synapses between a pair add their currents |

### Neurotransmitter → sign

```python
NT_SIGN = {"ACH": +1.0, "GABA": -1.0, "GLUT": -1.0,
           "DA": 0.0, "SER": 0.0, "OCT": 0.0, "UNK": +1.0}
```

Acetylcholine is the main fast excitatory transmitter in *Drosophila*; **both** GABA and
glutamate are typically inhibitory (glutamate largely via the GluCl chloride channel,
unlike the vertebrate case). Two honest caveats: these are per-neuron ML predictions with
real error rates, not measurements; and mapping aminergic neurons to zero means they
contribute *nothing* rather than something slow and diffuse, which is a modelling gap
rather than an accuracy claim.

### Functional population mapping

Real data carries hundreds of cell types; the engine's populations are four functional
roles. `assign_population()` maps `LC4`/`LPLC2` → `LC4`, `DNp01` → `GF`, inhibitory
others → `INH`, excitatory others → `PMN`. This is a deliberate coarsening so the existing
encoder and decoder have something to bind to. **The true per-neuron cell type is preserved
in `Connectome.labels`**, so nothing is lost — a real study would group by those instead.

### Calling it directly

```python
from flysim.brain.loaders import build_flywire, load_codex_tables, select_pathway

cx = build_flywire(hops=1, seed_types=("LC4", "LPLC2", "DNp01"))

# or, for control over each stage:
conn, cls = load_codex_tables(version="v783")
keep = select_pathway(conn, cls, seed_types=("LC4", "DNp01"), hops=2, max_neurons=8000)
```

### The honest caveat about `PA_PER_SYNAPSE`

**A connectome gives you anatomy, not physiology.** Synapse count correlates with
functional strength, but the constant relating them is not measured for most cell types,
varies by neurotransmitter and receptor, and ignores gap junctions entirely — which
matters enormously here, because the Giant Fiber's input includes **electrical** synapses
that EM connectomics does not resolve the same way as chemical ones.

Treat a linear scaling as a starting point to be fitted against physiological recordings,
not as ground truth. Say so in any figure caption. The simulator will happily produce
confident-looking spike trains from a badly chosen constant.

---

## 6. Where credentials live

| Secret | Location | In repo? |
|---|---|---|
| NeuPrint token | `NEUPRINT_APPLICATION_CREDENTIALS` env var | **never** |
| CAVE token | `~/.cloudvolume/secrets/cave-secret.json` | **never** |
| Cache path | `FLYSIM_CACHE_DIR` env var | path only, set by you |

`.gitignore` already excludes `.env`, `*.token`, `data/`, `cache/`, and every bulk data
extension. Verify with `git status` before your first commit.
