# Reproducing the study

Everything in this repository except the AnyLogic archive is reproducible with a
stock Python 3.10+ interpreter and **no third-party runtime dependencies**.

The repository has two generations of the study:

* **baseline** (`results/*.json`, `archive/report-2026-11.html`): the original course model,
  one clerk pool, fixed service times, flat demand.
* **layer results** (`results/*.json`, `docs/index.html`): the same engine layered with
  four layers - demand, supply network, inventory and economics/fairness. baseline is
  kept as the regression baseline, and `data/scenarios/baseline_flat.json` proves
  that the engine still reproduces it bit-for-bit.

## 1. Environment

```powershell
python --version          # 3.10 or newer
python -m pip install -e ".[dev]"
python -m pytest -q       # 69 tests, ~35 s on an 8-core laptop
```

`pip install -e .` puts `bubble_tea_sim` on the path and installs the
`bubble-tea` console script; `[dev]` only adds `pytest`.

## 2. baseline numbers

```powershell
# Baseline anchors: M2 mixed-order table + P-series fast-priority table
python -m bubble_tea_sim reproduce --reps 200 --out results/anchors.json

# Everything else committed under results/ (baseline) is produced by the baseline analysis scripts:
python analysis/run_policy_sweep.py          # -> results/policy_sweep.json   (~4 min)
python analysis/run_breakeven.py             # -> results/breakeven.json      (~4 min)
python analysis/run_sensitivity.py           # -> results/sensitivity.json    (~35 s)
python analysis/run_behaviour.py             # -> results/behaviour.json      (~30 s)
python analysis/reproduce_anylogic_ledger.py # -> results/anylogic_ledger.json (~11 s)
python analysis/build_report.py              # -> archive/report-2026-11.html + docs/experiments.md (baseline tables)
```

The bare CLI also has `sweep` and `breakeven` subcommands for quick inspection,
but their JSON is a compact schema (no provenance block, no paired-difference
table); do **not** write them over `results/*.json`, because the report builder
expects the analysis schema. Pass `--out` to a scratch path instead.

## 3. layer scenarios and layers

`data/scenarios/*.json` are the input data of the layer study: one file per shop
context (campus rush, CBD lunch, mall weekend, delivery-heavy, bottleneck shop,
lean inventory, pricing/SLA scenarios, ...). Every file carries a `provenance`
block with `source`, `method` and `uncertainty`; see `data/README.md`.

```powershell
# list the library (name, original flag, uncertainty, utilisation, title)
python -m bubble_tea_sim scenarios

# run one scenario from the library (prints headline metrics, optional JSON)
python -m bubble_tea_sim scenario --name campus_rush --reps 100

# regenerate every committed result and the report
python analysis/run_demand_network.py   # -> results/{demand_study,network_study,scenario_library}.json (~8 min)
python analysis/run_inventory_econ.py   # -> results/{inventory_study,economics_study}.json        (~6 min)
python analysis/build_report.py     # -> docs/index.html, docs/experiments-layers.md, docs/figures-layers/
python analysis/build_demo_data.py     # -> demo/data/*.json (precomputed traces for the interactive demo)
```

The engine (*not* a second model) supports four independent layers; a
configuration that leaves all of them off takes the `baseline_compat` path and
reproduces baseline exactly:

| Layer | Scenario keys | What it adds |
|---|---|---|
| Demand | `demand`, `batches`, `classes`, `variability` | intra-day curve, group arrivals, segments with own mix/patience, lognormal/exponential/gamma make times |
| Supply network | `network` | stations with capacity, staff roles/skills, shift windows, breaks, staged order -> make processing |
| Inventory | `inventory` | BOM recipes, FIFO lots, (s, S) replenishment, lead time, shelf life, waste, stock-out policy |
| Economics/fairness | `pricing`, `sla`, `policy.starvation_cap` | peak pricing with elasticity, SLA compensation, aging cap |

## 4. What "reproducible" means here

| Artifact | Reproducible? | How |
|---|---|---|
| baseline numbers (`results/*.json`) | Yes | `python -m bubble_tea_sim reproduce` + baseline analysis scripts |
| layer numbers (`results/*.json`) | Yes | fixed seeds, deterministic engine; regenerate with the layer analysis scripts |
| Scenario library (`data/scenarios/*.json`) | Yes | plain JSON, validated by `tests/test_layers.py` |
| AnyLogic screenshots and E1-E6 ledger | **No** | Archived; model requires AnyLogic (see `archive/anylogic/`) |
| Reports `docs/index.html` / `archive/report-2026-11.html` | Yes | rebuilt from the committed `results/` JSON |

Byte-for-byte equality of the generated report and demo files is verified on one
platform (the committed files are normalised to LF by `.gitattributes`; a fresh
checkout on Windows may write CRLF into regenerated JSON, so compare after
`git diff` rather than raw bytes across platforms).

## 5. Seeds and estimators

* Every replicate seed is explicit (`seed = first_seed + i * stride`). Baseline
  anchors keep the original strides: `9001` (mixed order) and `7001`
  (bread priority).
* Policy comparisons use **common random numbers**: the same seed is reused for
  both policies, so differences are paired and the 95% confidence intervals are
  much tighter than independent sampling would give.
* `stats.replicate()` averages per-replicate means; `stats.pooled_los()`
  reproduces the original pooled-customer estimator. Both are defined in
  `docs/theory.md`.
* The study uses seeds `0, 1, 2, ...` (stride 1) for every experiment; the seed and
  replicate count are written into each `results/*.json` `meta` block.

## 6. Runtime expectations

| Command | Typical runtime (single core) |
|---|---|
| `pytest` | 40 s |
| `reproduce --reps 200` | 5-10 s |
| `scenario --reps 100` (one scenario) | 5-20 s |
| `analysis/run_demand_network.py` | 6-10 min |
| `analysis/run_inventory_econ.py` | 4-8 min |
| `analysis/build_report.py` | < 5 s |
| baseline `sweep` (5 workers × 6 loads × 4 policies × 200 reps) | 3-5 min |

If you only want to check the code, run `pytest`; if you want the figures, run
the analysis scripts once and commit the regenerated `results/` and `docs/`.
