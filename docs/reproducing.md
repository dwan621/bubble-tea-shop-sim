# Reproducing the study

Everything in this repository except the AnyLogic archive is reproducible with a
stock Python 3.10+ interpreter and **no third-party runtime dependencies**.

The repository has two generations of the study:

* **v1** (`results/*.json`, `archive/report-v1.html`): the original course model,
  one clerk pool, fixed service times, flat demand.
* **v2** (`results/v2/*.json`, `docs/index.html`): the same engine extended with
  four layers - demand, supply network, inventory and economics/fairness. v1 is
  kept as the regression baseline, and `data/scenarios/baseline_flat.json` proves
  that the v2 engine still reproduces it bit-for-bit.

## 1. Environment

```powershell
python --version          # 3.10 or newer
python -m pip install -e ".[dev]"
python -m pytest -q       # 69 tests, ~35 s on an 8-core laptop
```

`pip install -e .` puts `bubble_tea_sim` on the path and installs the
`bubble-tea` console script; `[dev]` only adds `pytest`.

## 2. v1 numbers

```powershell
# Legacy anchors: M2 mixed-order table + P-series fast-priority table
python -m bubble_tea_sim reproduce --reps 200 --out results/legacy_anchors.json

# Everything else committed under results/ (v1) is produced by the v1 analysis scripts:
python analysis/run_policy_sweep.py          # -> results/policy_sweep.json   (~4 min)
python analysis/run_breakeven.py             # -> results/breakeven.json      (~4 min)
python analysis/run_sensitivity.py           # -> results/sensitivity.json    (~35 s)
python analysis/run_behaviour.py             # -> results/behaviour.json      (~30 s)
python analysis/reproduce_anylogic_ledger.py # -> results/anylogic_ledger.json (~11 s)
python analysis/build_report.py              # -> archive/report-v1.html + docs/experiments.md (v1 tables)
```

The bare CLI also has `sweep` and `breakeven` subcommands for quick inspection,
but their JSON is a compact schema (no provenance block, no paired-difference
table); do **not** write them over `results/*.json`, because the report builder
expects the analysis schema. Pass `--out` to a scratch path instead.

## 3. v2 scenarios and layers

`data/scenarios/*.json` are the input data of the v2 study: one file per shop
context (campus rush, CBD lunch, mall weekend, delivery-heavy, bottleneck shop,
lean inventory, pricing/SLA scenarios, ...). Every file carries a `provenance`
block with `source`, `method` and `uncertainty`; see `data/README.md`.

```powershell
# list the library (name, legacy flag, uncertainty, utilisation, title)
python -m bubble_tea_sim scenarios

# run one scenario from the library (prints headline metrics, optional JSON)
python -m bubble_tea_sim scenario --name campus_rush --reps 100

# regenerate every committed v2 result and the report
python analysis/v2_demand_network.py   # -> results/v2/{demand_study,network_study,scenario_library}.json (~8 min)
python analysis/v2_inventory_econ.py   # -> results/v2/{inventory_study,economics_study}.json        (~6 min)
python analysis/build_report_v2.py     # -> docs/index.html, docs/experiments-v2.md, docs/figures-v2/
python analysis/build_demo_data.py     # -> demo/data/*.json (precomputed traces for the interactive demo)
```

The v2 engine (*not* a second model) supports four independent layers; a
configuration that leaves all of them off takes the `legacy_compat` path and
reproduces v1 exactly:

| Layer | Scenario keys | What it adds |
|---|---|---|
| Demand | `demand`, `batches`, `classes`, `variability` | intra-day curve, group arrivals, segments with own mix/patience, lognormal/exponential/gamma make times |
| Supply network | `network` | stations with capacity, staff roles/skills, shift windows, breaks, staged order -> make processing |
| Inventory | `inventory` | BOM recipes, FIFO lots, (s, S) replenishment, lead time, shelf life, waste, stock-out policy |
| Economics/fairness | `pricing`, `sla`, `policy.starvation_cap` | peak pricing with elasticity, SLA compensation, aging cap |

## 4. What "reproducible" means here

| Artifact | Reproducible? | How |
|---|---|---|
| v1 numbers (`results/*.json`) | Yes | `python -m bubble_tea_sim reproduce` + v1 analysis scripts |
| v2 numbers (`results/v2/*.json`) | Yes | fixed seeds, deterministic engine; regenerate with the v2 analysis scripts |
| Scenario library (`data/scenarios/*.json`) | Yes | plain JSON, validated by `tests/test_v2_layers.py` |
| AnyLogic screenshots and E1-E6 ledger | **No** | Archived; model requires AnyLogic (see `archive/anylogic/`) |
| Reports `docs/index.html` (v2) / `archive/report-v1.html` | Yes | rebuilt from the committed `results/` JSON |

Byte-for-byte equality of the generated report and demo files is verified on one
platform (the committed files are normalised to LF by `.gitattributes`; a fresh
checkout on Windows may write CRLF into regenerated JSON, so compare after
`git diff` rather than raw bytes across platforms).

## 5. Seeds and estimators

* Every replicate seed is explicit (`seed = first_seed + i * stride`). Legacy
  anchors keep the original strides: `9001` (mixed order) and `7001`
  (bread priority).
* Policy comparisons use **common random numbers**: the same seed is reused for
  both policies, so differences are paired and the 95% confidence intervals are
  much tighter than independent sampling would give.
* `stats.replicate()` averages per-replicate means; `stats.pooled_los()`
  reproduces the legacy pooled-customer estimator. Both are defined in
  `docs/theory.md`.
* v2 uses seeds `0, 1, 2, ...` (stride 1) for every experiment; the seed and
  replicate count are written into each `results/v2/*.json` `meta` block.

## 6. Runtime expectations

| Command | Typical runtime (single core) |
|---|---|
| `pytest` | 40 s |
| `reproduce --reps 200` | 5-10 s |
| `scenario --reps 100` (one v2 scenario) | 5-20 s |
| `analysis/v2_demand_network.py` | 6-10 min |
| `analysis/v2_inventory_econ.py` | 4-8 min |
| `analysis/build_report_v2.py` | < 5 s |
| v1 `sweep` (5 workers × 6 loads × 4 policies × 200 reps) | 3-5 min |

If you only want to check the code, run `pytest`; if you want the figures, run
the analysis scripts once and commit the regenerated `results/` and `docs/`.
