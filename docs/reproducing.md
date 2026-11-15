# Reproducing the study

Everything in this repository except the AnyLogic archive is reproducible with a
stock Python 3.10+ interpreter and **no third-party runtime dependencies**.

## 1. Environment

```powershell
python --version          # 3.10 or newer
python -m pip install -e ".[dev]"
python -m pytest -q       # 52 tests, ~30 s on an 8-core laptop
```

`pip install -e .` puts `bubble_tea_sim` on the path and installs the
`bubble-tea` console script; `[dev]` only adds `pytest`.

## 2. Recompute the numbers cited in the report

```powershell
# Legacy anchors: M2 mixed-order table + P-series fast-priority table
python -m bubble_tea_sim reproduce --reps 200 --out results/legacy_anchors.json

# Everything else that is committed under results/ (and the report) is produced
# by the analysis scripts, which also add provenance metadata and paired stats:
python analysis/run_policy_sweep.py          # -> results/policy_sweep.json   (~4 min)
python analysis/run_breakeven.py             # -> results/breakeven.json      (~4 min)
python analysis/run_sensitivity.py           # -> results/sensitivity.json    (~35 s)
python analysis/run_behaviour.py             # -> results/behaviour.json      (~30 s)
python analysis/reproduce_anylogic_ledger.py # -> results/anylogic_ledger.json (~11 s)
python analysis/build_report.py              # -> docs/experiments.md + docs/index.html
```

The bare CLI also has `sweep` and `breakeven` subcommands for quick inspection,
but their JSON is a compact schema (no provenance block, no paired-difference
table); do **not** write them over `results/*.json`, because `build_report.py`
expects the analysis schema. Pass `--out` to a scratch path instead:

```powershell
python -m bubble_tea_sim sweep --workers-list 3 --lambdas 0.8,1.0 --reps 50
python -m bubble_tea_sim breakeven --workers 3 --reps 30
```

The `analysis/` scripts wrap these commands into the JSON files under
`results/`, regenerate the tables in `docs/experiments.md`, and rebuild the
static report at `docs/index.html`. They are ordinary scripts; run them with
`python analysis/<script>.py`.

## 3. What "reproducible" means here

| Artifact | Reproducible? | How |
|---|---|---|
| Python simulation numbers (`results/*.json`) | Yes | Fixed seeds, deterministic engine |
| Legacy anchor tables (M2, P-series) | Yes | `python -m bubble_tea_sim reproduce` |
| AnyLogic screenshots and E1-E6 ledger | **No** | Archived; model requires AnyLogic (see `archive/anylogic/`) |
| Report page `docs/index.html` | Yes | `analysis/build_report.py` rebuilds it from `results/*.json` |

## 4. Seeds and estimators

* Every replicate seed is explicit. Legacy anchors use the original strides:
  `9001` for the mixed-order study (`seed = 9001 * rep`) and `7001` for the
  bread-priority study.
* Policy comparisons use **common random numbers**: the same seed is reused for
  both policies, so differences are paired and the 95% confidence intervals are
  much tighter than independent sampling would give.
* `stats.replicate()` averages per-replicate means;
  `stats.pooled_los()` reproduces the legacy pooled-customer estimator. Both are
  defined in `docs/theory.md`.

## 5. Runtime expectations

| Command | Typical runtime (single core) |
|---|---|
| `pytest` | 30 s |
| `reproduce --reps 200` | 5-10 s |
| `sweep` (5 workers × 6 loads × 4 policies × 200 reps) | 3-5 min |
| `breakeven --reps 60` | 1-2 min |

If you only want to check the code, run `pytest`; if you want the figures, run
the `analysis/` scripts once and commit the regenerated `results/` and `docs/`.
