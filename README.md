# Bubble-Tea Shop Simulation

**Does fast-item triage pay off? A discrete-event study of order delivery and priority in a small tea shop.**

[![CI](https://github.com/dwan621/bubble-tea-shop-sim/actions/workflows/ci.yml/badge.svg)](https://github.com/dwan621/bubble-tea-shop-sim/actions/workflows/ci.yml)

This repository contains a dependency-free Python discrete-event simulation (DES) of a
three-clerk bubble-tea shop, the experiment ledger behind the study, and a cleaned-up
reproduction of the original course project. It answers three operational questions:
should a mixed tea + ice-cream order be delivered *split* (ice cream first) or
*synchronised* (everything together), should fast items jump the queue, and how do those
choices interact with load and with the shop's economics?

The headline answer is conditional. Split delivery is close to free at low load and
cuts the ice-cream hand-off by about two minutes, but the advantage reverses near
80% utilisation; fast-item priority is the stronger and more robust lever, at the
price of a small delay for the mainstream tea queue. Total workload and utilisation are
identical under both delivery policies — the decision is about *where* customers wait,
not *how much* work the shop does.

All Python numbers below are reproduced by the commands shown in
[Quick start](#quick-start) and are stored in the machine-generated JSON files under
`results/`; the AnyLogic material is archival and explicitly marked
[archive, not re-runnable](#reproducibility-python-vs-anylogic-archive).

---

## 中文摘要 / Chinese summary

本项目是一个奶茶店离散事件仿真研究：3 名员工共享，奶茶/面包/冰淇淋/混合单（奶茶+冰淇淋）
四类订单，核心比较 **同步交付（Synchro）vs 拆分交付（Split）** 与 **快品优先（fast-item
priority）** 两种调度策略，并把等待折算成成本做经济比较。

- **拆分是否值得取决于负载**：低负载（λ=0.5，利用率 35.4%）拆分让全店等待从 2.20 min
  降到 2.06 min、冰淇淋提前约 2.03 min 到手，面包代价仅 +0.01 min；λ=1.25（利用率
  88.2%）时拆分反而让全店等待变差（4.93→5.05 min），但混合单等待从 5.65 降到 5.35 min、
  冰淇淋提前约 4.41 min 到手。两种策略的**总工作量与利用率完全相同**。
- **快品优先是更强杠杆**：3 员工下，面包等待在 λ=1.0/1.3/1.5 分别下降 0.15/0.77/3.02 min
  （−14%/−41%/−70%），奶茶代价仅 +0.03/+0.15/+0.49 min。
- **经济层**：在默认价格与等待成本（0.5 元/顾客/分钟）下，Split 相对 Synchro 的利润差在
  λ=0.8 时约 +2.1 元/小时，λ=1.25 时约 −3.3 元/小时；盈亏平衡点约 **λ=1.147 人/分钟**
  （ρ≈80.9%，识别带 1.10–1.20）。
- **利用率不是决策指标**：两种交付策略的总工作量相同，利用率理论上完全一致；真正的差异是
  等待在奶茶队列与混合单冰淇淋组件之间的重新分配。
- 复现：`pip install -e ".[dev]"`、`python -m bubble_tea_sim reproduce --reps 200`、
  `python -m pytest -q`。AnyLogic 截图与 E 系列数字是**存档证据，不可重跑**，仅供历史对照。

> 英文正文为准；数量级与结论以本仓库 Python 引擎可重算结果为准。

---

## Research questions

1. **Delivery strategy.** For a mixed order (tea + ice cream made by the same clerk),
   is *Synchro* (one atomic 2.833-min job, everything handed over together) or *Split*
   (ice cream handed over after 0.833 min, tea after 2.0 min, customer leaves when the
   tea is ready) better?
2. **Fast-item priority.** Should the short bread and ice-cream jobs preempt the
   long tea jobs in the shared clerk queue?
3. **Economics.** When waiting is priced at 0.5 per customer-minute, which policy earns
   more profit per hour, and at what load does the ranking flip?

A fourth question ties the study to the course material: **why is Split non-trivial at
all?** Both policies have the same capacity, so the answer must come from queueing
dynamics, not from workload.

---

## Headline results

### 1. Split delivery: helpful at low load, costly near saturation

`python -m bubble_tea_sim reproduce --reps 200` (3 clerks, 200 paired replicates,
common arrival streams, seed stride 9001; estimator = mean of per-replicate means; the
`--out` flag writes the table to `results/legacy_anchors.json`):

| λ (cust/min) | Delivery | All-order LOS (min) | Mixed-order LOS (min) | Ice-cream hand-off (min) | Bread LOS (min) | Observed utilisation |
|---:|---|---:|---:|---:|---:|---:|
| 0.50 | Synchro | 2.20 | 2.91 | 2.91 | 0.74 | 35.4% |
| 0.50 | **Split** | **2.06** | **2.23** | **0.88** | 0.75 | 35.4% |
| 0.80 | Synchro | 2.44 | 3.15 | 3.15 | 1.00 | 56.6% |
| 0.80 | **Split** | **2.34** | **2.59** | **0.98** | 1.02 | 56.6% |
| 1.10 | Synchro | 3.30 | 4.02 | 4.02 | **1.85** | 77.6% |
| 1.10 | **Split** | **3.28** | **3.58** | **1.13** | 1.93 | 77.6% |
| 1.25 | Synchro | **4.93** | 5.65 | 5.65 | **3.49** | 88.2% |
| 1.25 | Split | 5.05 | **5.35** | **1.24** | 3.72 | 88.2% |

Reading the table:

* At λ ≤ 1.10 Split lowers all-order waiting and removes 2.0–2.9 min from the
  ice-cream hand-off, with a bread penalty of at most 0.08 min.
* At λ = 1.25 the all-order and bread columns favour Synchro, while mixed-order
  customers and the ice-cream component still favour Split. That is the trade-off:
  Split moves waiting from mixed customers to the mainstream queue.
* Utilisation is identical to three decimals in every pair — total work is conserved.

### 2. Fast-item priority: the stronger lever

`python -m bubble_tea_sim reproduce --reps 200` (3 clerks, P-series parameterisation:
tea 65% / bread 20% / ice cream 15%, no mixed orders; pooled-customer estimator over
6 replicates, seed stride 7001; same `results/legacy_anchors.json` output):

| λ | Policy | Tea LOS | Bread LOS | Ice-cream LOS | All LOS | Utilisation |
|---:|---|---:|---:|---:|---:|---:|
| 1.0 | FCFS | 2.92 | 1.04 | 1.22 | 2.30 | 63.6% |
| 1.0 | Fast priority | 2.95 | **0.89** (−14%) | **1.05** | 2.26 | 63.6% |
| 1.3 | FCFS | 3.70 | 1.88 | 2.11 | 3.11 | 82.5% |
| 1.3 | Fast priority | 3.85 | **1.11** (−41%) | **1.26** | 2.93 | 82.5% |
| 1.5 | FCFS | 6.21 | 4.34 | 4.46 | 5.57 | 93.6% |
| 1.5 | Fast priority | 6.70 | **1.32** (−70%) | **1.45** | 4.84 | 93.6% |

The benefit grows with load and is much larger than the Split effect; the tea penalty
grows more slowly (+0.03 → +0.15 → +0.49 min). At very high utilisation the priority
rule protects the fast classes but cannot create capacity.

### 3. Economics: profit per hour and break-even

`python -m bubble_tea_sim sweep --workers-list 3 --lambdas 0.4,0.6,0.8,1.0,1.2,1.25 --reps 200`
(study configuration, 3 clerks, default prices, wage and waiting cost; profit per hour
as defined in the [economic layer](docs/theory.md#8-economic-layer); the workers = 3
rows of `results/policy_sweep.json`):

| λ | Observed ρ | Synchro | Synchro + fast | Split | Split + fast |
|---:|---:|---:|---:|---:|---:|
| 0.4 | 28.7% | 66.5 | 66.5 | **68.0** | **68.0** |
| 0.6 | 42.7% | 133.9 | 134.0 | **135.9** | **136.0** |
| 0.8 | 56.8% | 198.6 | 199.0 | **200.7** | **201.2** |
| 1.0 | 70.9% | 255.8 | 257.7 | **257.4** | **259.6** |
| 1.2 | 84.8% | 282.6 | 290.6 | 281.3 | **290.4** |
| 1.25 | 88.4% | 272.9 | 285.6 | 269.6 | **283.7** |

The Split−Synchro profit difference is small and positive at low load (+1.5 to +2.1
per hour), crosses zero between λ = 1.10 and 1.20, and is clearly negative at λ = 1.25
(−3.3 per hour without fast priority). Fast priority is worth +8.1 to +14.0 per hour
at high load, in both delivery modes.

`analysis/run_breakeven.py` solves the crossing with paired common random numbers
(200 replicates on the load grid, bisection tolerance 0.01 in λ) and writes
`results/breakeven.json`. For 3 clerks:

```text
λ* = 1.1469 customers/min   ρ* = 80.9%   identification band: λ ∈ [1.10, 1.20]
```

The profit and mean-LOS roots coincide to the bisection tolerance (revenue is
policy-invariant and waiting cost is linear in flow time), and the same script gives
λ* ≈ 0.671 (71.0% utilisation) with 2 clerks and λ* ≈ 1.623 (85.9%) with 4. The bare CLI
run with 60 replicates gives 1.141, within one grid step of the committed value; use the
analysis script when the exact number matters.

Treat the point estimate as approximate: it is a simulation-based crossing, not a
closed form, and it depends on the assumed prices and waiting-cost weight.

---

## Quick start

Requires Python 3.10+ and nothing beyond the standard library at runtime.

```powershell
python -m pip install -e ".[dev]"        # installs the package + pytest
python -m pytest -q                      # 52 tests, about 30 s on the dev laptop

# direct CLI: one configuration, a narrow sweep, the anchors and a break-even run
python -m bubble_tea_sim run --lam 1.25 --workers 3 --split --fast --seed 0
python -m bubble_tea_sim sweep --workers-list 3 `
    --lambdas 0.4,0.6,0.8,1.0,1.2,1.25 --reps 200
python -m bubble_tea_sim breakeven --workers 3 --lower 0.5 --upper 1.3 --reps 60
python -m bubble_tea_sim reproduce --reps 200 --out results/legacy_anchors.json

# regenerate the committed results and the static report
python analysis/run_policy_sweep.py        # full grid: 1-5 workers x lambda 0.30-1.30
python analysis/run_breakeven.py           # 2-4 workers, profit + mean-LOS roots
python analysis/reproduce_anylogic_ledger.py
python analysis/build_report.py            # docs/experiments.md + docs/index.html
```

`pip install -e .` also installs a `bubble-tea` console script with the same
subcommands, e.g. `bubble-tea run --lam 1.0 --split`.

Example single-run output (one seed, so it is noisier than any table above):

```text
$ python -m bubble_tea_sim run --lam 1.25 --workers 3 --split --fast
{ "policy": "split+fast-priority", "served": 531, "mean_los": 4.84, ...
  "mix_los": 5.78, "mix_ice_hand": 1.43, "util": 0.881,
  "profit_per_hour": 276.08, "balked": 0, "reneged": 0 }
```

Outputs are JSON (`--out FILE`) so reports and figures can be regenerated without
re-running the simulation. Command details, seed conventions and expected runtimes
are in [docs/reproducing.md](docs/reproducing.md).

---

## Repository layout

```text
bubble-tea-shop-sim/
├── .github/workflows/
│   ├── ci.yml                     # pytest + reproduce smoke test, 2 OS x 3 Python
│   └── pages.yml                  # GitHub Pages deployment for the static report
├── analysis/                      # reproducible experiment runners
│   ├── common.py                  # shared JSON/statistics plumbing
│   ├── svgchart.py                # dependency-free SVG charts for the report
│   ├── run_policy_sweep.py        # -> results/policy_sweep.json
│   ├── run_breakeven.py           # -> results/breakeven.json
│   ├── run_behaviour.py           # -> results/behaviour.json
│   ├── run_sensitivity.py         # -> results/sensitivity.json
│   ├── reproduce_anylogic_ledger.py  # -> results/anylogic_ledger.json
│   └── build_report.py            # -> docs/experiments.md + docs/index.html
├── archive/anylogic/              # frozen AnyLogic model snapshot (not re-runnable)
│   ├── MIXUE_Model.alp
│   ├── 3d/person.dae
│   └── README.md
├── legacy/                        # verbatim original course scripts (provenance only)
│   ├── mixed_order_sim.py
│   ├── bread_priority_sim.py
│   ├── icecream_strategy_sim.py
│   └── README.md
├── docs/
│   ├── theory.md                  # Lecture 1-4 formulas, assumptions, validation
│   ├── experiment_log.md          # archival AnyLogic ledger + v2 engine re-checks
│   ├── design.md                  # engine design, determinism contract, extensions
│   ├── reproducing.md             # environment, commands, runtimes, seed rules
│   ├── experiments.md             # generated result tables (from results/*.json)
│   ├── index.html                 # generated static report
│   ├── figures/                   # generated SVG figures used by the report
│   └── assets/slides/             # archived AnyLogic screenshots (A/B/C/M3/E)
├── results/                       # committed JSON outputs of the analysis scripts
│   ├── policy_sweep.json
│   ├── breakeven.json
│   ├── behaviour.json
│   ├── sensitivity.json
│   ├── anylogic_ledger.json
│   └── legacy_anchors.json
├── src/bubble_tea_sim/
│   ├── params.py                  # order mix, service times, policy, economics
│   ├── engine.py                  # event loop, scheduling, per-run metrics
│   ├── scenarios.py               # legacy and study configurations
│   ├── stats.py                   # replicates, paired differences, break-even
│   ├── cli.py                     # run / sweep / breakeven / reproduce
│   ├── __main__.py                # python -m bubble_tea_sim
│   └── __init__.py
├── tests/
│   ├── test_legacy_anchors.py     # pins the archived M2/P-series numbers
│   ├── test_params.py             # analytical layer (capacity, prices, validation)
│   ├── test_engine_invariants.py  # flow conservation, determinism, edge cases
│   ├── test_edge_cases.py         # overload/utilization conventions, boundary cases
│   ├── test_policies.py           # scheduling-policy behaviour
│   ├── test_behaviour.py          # balking, reneging, dynamic priority
│   ├── test_stats.py              # estimators, confidence intervals, break-even
│   └── test_cli.py                # command-line contract and JSON output
├── conftest.py                    # makes src/ importable for plain pytest
├── pyproject.toml
├── CITATION.cff                   # machine-readable citation metadata
├── LICENSE                        # MIT
└── README.md
```

The Python package is intentionally small: one event loop, explicit configuration
objects, no third-party runtime dependencies. [`docs/design.md`](docs/design.md)
documents the event loop, the determinism contract and the extension points.

---

## Model and parameter assumptions

**Process.** One queueing system: a pool of three cross-trained clerks serves four
order classes. A *job* is one uninterruptible block of clerk time. A pure order is a
single job (`order + make`). A mixed order is either one 2.833-min job (Synchro) or two
jobs totalling the same 2.833 min (Split: 0.833 min ice component with jump priority,
2.0 min tea component in the normal queue). The customer leaves when the last component
is finished; the ice-cream hand-off is recorded separately.

**Scheduling.** Strict priority classes, otherwise first-come-first-served by job
sequence. `fast_priority` moves bread and pure ice cream to the high-priority class; the
split ice component jumps the queue by default (`mix_ice_priority="jump"`) and can
instead be held back or escalated after a threshold (`"fcfs"` / `"dynamic"` with
`dynamic_priority_threshold`). Balking and reneging are available as optional mechanisms
but are off by default, so the default study has no abandonment.

**Randomness.** Poisson arrivals with rate λ; the arrival stream is generated up front
from a seeded `random.Random`, so runs are deterministic given the seed. Service times
are fixed within an order class (no make-time variability), which makes the model a
clean test bed for the queueing theory but understates real-world waiting.

**Parameters (defaults, all assumed until field data are collected):**

| Item | Value | Notes |
|---|---|---|
| Clerks | 3 | shared queue, cross-trained |
| Arrival rate | 1.25 customers/min in examples | Poisson; demand range 0.4–1.5 explored |
| Shop day | 480 min | 60-min warm-up excluded from statistics |
| Order mix | tea 55% / bread 20% / ice cream 5% / mixed 20% | `OrderMix` |
| Order-taking | 0.5 min | once per order, owned by the same clerk |
| Tea / bread / ice make | 2.0 / 0.167 / 0.333 min | `ServiceTimes` |
| Mixed order | 2.833 min Synchro; 0.833 + 2.0 min Split | total work identical |
| Prices | tea 8, bread 6, ice cream 2, mixed 10 | arbitrary currency units |
| Wage | 25 per clerk-hour | 75 per hour with 3 clerks |
| Waiting cost | 0.5 per customer-minute | 30 per customer-hour |

The P-series legacy configuration (used for the fast-priority table) differs: no mixed
orders, order mix tea 65% / bread 20% / ice cream 15%, and ice-cream make time 0.33 min.
Both configurations are defined in [`src/bubble_tea_sim/scenarios.py`](src/bubble_tea_sim/scenarios.py).

---

## Reproducibility: Python vs AnyLogic archive

Only the Python engine is a reproducible simulation. The AnyLogic project snapshot is
archived at [`archive/anylogic/`](archive/anylogic/) for provenance, but it is **not
re-runnable here**: it requires proprietary AnyLogic and was run manually with single
seeds and a different horizon. The screenshots under
[`docs/assets/slides/`](docs/assets/slides/) are archived here as **evidence, not
re-runnable artifacts**. Archived numbers are labelled `archival, not re-runnable`
wherever they appear and are kept for historical context and direction-of-effect
comparisons. The original Python scripts are kept verbatim under
[`legacy/`](legacy/) for the same reason; they are superseded by the package.

| Artifact | Reproducible? | How |
|---|---|---|
| Python engine and CLI | **Yes** | fixed seeds, deterministic event loop, standard library only |
| `reproduce` M2/P-series anchor tables | **Yes** | `python -m bubble_tea_sim reproduce --reps 200` |
| Policy sweep, break-even, behavior studies | **Yes** | `sweep` / `breakeven` / `run` subcommands |
| AnyLogic E-series re-check (archived 1000-min settings) | **Yes** | `python analysis/reproduce_anylogic_ledger.py` → `results/anylogic_ledger.json` |
| [`docs/experiments.md`](docs/experiments.md), [`docs/index.html`](docs/index.html), `results/*.json` | **Yes** | regenerated by the `analysis/` scripts from `results/*.json` |
| AnyLogic model (`archive/anylogic/MIXUE_Model.alp`), screenshot evidence and E-series ledger | **No** | archived evidence; see [docs/experiment_log.md](docs/experiment_log.md) |

The engine can go one step further than "the archive is not re-runnable": the archived
E-series configurations are re-implemented at their own settings (3 clerks, 1000-min
horizon, no warm-up, seed 1, 200 replicates) and compared like-for-like. The archived
profit per hour is reproduced within +3.4% / −8.6% across all six runs, with the
E5–E6 ordering swapping places; the check and its caveats are in
[experiment_log.md §4](docs/experiment_log.md#4-v2-engine-re-check-of-the-archive).

**Statistical conventions.** Policy comparisons use common random numbers: the same
seed is reused for every policy being compared, so differences are paired. The default
study uses seeds `0, 1, 2, …` (stride 1); legacy anchors keep the original strides
(9001 for the mixed-order study, 7001 for the bread-priority study). M2 tables average
per-replicate means; P-series tables pool the customer list, matching the original
scripts. `python -m pytest -q` pins both estimators against the recorded anchors.

**What changed in this cleaned-up version.** The legacy Python scripts were merged into
one configuration-driven engine (the originals are kept verbatim under `legacy/`); the
regression suite pins the legacy anchors; the AnyLogic model is preserved as an archive
under `archive/anylogic/` rather than as executable code; and local course-directory
references were replaced by relative links and lecture numbers.

---

## How this maps to the course theory (Lectures 1–4)

The project was written for course 5006. The formulas are used as *predictions* that
the simulation then tests, not as a separate theory review. Derivations and the full
numerical comparison live in [docs/theory.md](docs/theory.md).

| Lecture | Concept / formula | Prediction before simulation | What the model tests |
|---|---|---|---|
| 1 | `I = R × T` (Little's Law) | At fixed demand, lower average flow time means fewer customers inside. | Converts simulated LOS into store inventory for Synchro vs Split. |
| 2 | `Capacity = m / p̄`, `Utilisation = Flow Rate / Capacity` | Split and Synchro have identical total workload, so utilisation must not change. | Confirms equal utilisation and identifies the clerk pool as the bottleneck. |
| 3 | Multi-server `Tq` approximation with `CV_a`, `CV_p` | Queue delay rises sharply as `U → 1`, so priority effects get stronger at high load. | Compares analytical `Tflow` with the simulation (≈0.2% at λ=1.0, ≈1.6% at λ=1.25). |
| 4 | MPS / BOM / MRP / CRP | Ingredient gross requirements and required clerk-minutes follow the order mix. | Checks capacity feasibility: 158.75 required vs 180 available clerk-min/hour at λ=1.25. |

The theory also explains why Split is not a trivial "hand it over earlier" change:
capacity is invariant, waiting is redistributed between job classes, and the queueing
response is non-linear in utilisation. See
[why Split is non-trivial](docs/theory.md#6-why-split-is-non-trivial).

---

## Limitations

* **Assumed parameters.** Prices, wages, waiting cost, order mix and service times are
  course assumptions, not measured field data. The economic ranking inherits that.
* **Deterministic service times.** No make-time variability and no order-size mixtures,
  so real queues are likely worse than the model at the same utilisation.
* **Poisson arrivals, one queue.** No batch arrivals, no delivery orders, no
  ingredient stock-outs, no staff breaks or shift changes, no balking/reneging in the
  default experiments (they exist in the engine but are off).
* **Balking heuristic.** The optional balk rule estimates waiting as
  `in_system × p̄ / workers`; it is a modelling device, not a calibrated customer model.
* **Split motivation is not priced.** The study does not model melting or the value of
  an earlier ice-cream hand-off; that benefit must be argued qualitatively.
* **Warm-up accounting.** Profit per hour excludes customers who arrive during the
  first 60 minutes but divides by the full 480-minute day, so the effective throughput
  is below λ × 60. This is stated in [docs/theory.md](docs/theory.md#8-economic-layer)
  and keeps all reported profits internally consistent, but it means the default
  480-min study profits should not be compared with the archived 1000-min AnyLogic
  E-series values. The ledger script performs that comparison at the archived settings
  instead.
* **Archival AnyLogic evidence.** Single-seed, manually collected, different horizon
  and parameter lineage. The ledger re-check matches profit within −8.6% to +3.4%, but
  individual LOS values at high load differ by 25–43%; the archive is historical
  evidence, not a validation target for absolute times.

Next steps: calibrate the parameters with real shop data, add service-time
distributions and day/shift structure, model ingredient inventory and reorder points
(Lecture 4), and estimate the economic value of early hand-off with customer data.

---

## License

MIT — see [LICENSE](LICENSE). The archived AnyLogic screenshots and the frozen model
snapshot under `archive/anylogic/` are included as course evidence; the MIT license
applies to the code and documentation in this repository, not to third-party AnyLogic
software or its 3D asset.

## Citation

Machine-readable metadata is in [CITATION.cff](CITATION.cff):

```bibtex
@misc{bubbleteashop2026,
  author       = {dwan621},
  title        = {Bubble-Tea Shop Simulation: Is Fast-Item Triage Worth It?},
  year         = {2026},
  howpublished = {\url{https://github.com/dwan621/bubble-tea-shop-sim}},
  note         = {Course project for 5006; discrete-event simulation study}
}
```

## Acknowledgements

This work started as a course project for **5006** (operations management / service
operations). The queueing and capacity-planning material follows the course lectures
(Lecture 1: flow metrics and Little's Law; Lecture 2: process capacity and
utilisation; Lecture 3: service operations and queueing; Lecture 4: MPS/BOM/MRP/CRP).
The original AnyLogic model was built in AnyLogic Personal Learning Edition; its
screenshots are archived here with the experiment ledger.
