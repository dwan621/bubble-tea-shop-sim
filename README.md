# Bubble-Tea Shop Simulation: four layers, one engine

**Does fast-item triage pay off — and what changes when the shop has peaks, stations, stock, a price list and an SLA?**

[![CI](https://github.com/dwan621/bubble-tea-shop-sim/actions/workflows/ci.yml/badge.svg)](https://github.com/dwan621/bubble-tea-shop-sim/actions/workflows/ci.yml)

**main report:** [docs/index.html](docs/index.html) · **Offline demo:** [demo/index.html](demo/index.html) · **All layer tables:** [docs/experiments-layers.md](docs/experiments-layers.md) · **earlier report (archived):** [archive/report-2026-11.html](archive/report-2026-11.html)

This repository contains a dependency-free Python discrete-event simulation (DES) of a
small bubble-tea shop, the experiment ledger behind the study, and a cleaned-up
reproduction of the original course project.

**baseline** asked two operational questions with one cross-trained clerk pool, flat Poisson
demand and fixed service times: should a mixed tea + ice-cream order be delivered
*split* (ice cream first) or *synchronised* (everything together), and should fast
items jump the queue? **the four-layer model keeps that model as the exact special case it always was**
and adds four optional layers around it: an intra-day demand profile, a station network
with skills and shifts, an inventory bill of materials with shelf life, and an economics
layer with pricing, SLA compensation and a fairness cap. It then re-asks the questions
across a library of **16 shop contexts**.

The baseline answers survive where its assumptions still hold — fast-item priority remains the
stronger lever at the baseline operating point, and split delivery still stops paying as load
rises. What moves is the *boundary condition*: the peak shape rather than the daily mean
decides abandonment, triage is worth far less when the tea station is the bottleneck, and
stock, price, SLA and fairness are first-order levers the one-pool model could not see.

All Python numbers below are reproduced by the commands shown in
[Quick start](#quick-start) and stored in machine-generated JSON under `results/`
(baseline: `results/`). The AnyLogic material is archival and explicitly marked
[archive, not re-runnable](#reproducibility-python-vs-anylogic-archive).

---

## 中文摘要 / Chinese summary

本项目是一个奶茶店离散事件仿真研究。**baseline** 用“单一员工池 + 平稳泊松到达 + 固定服务时间”
回答两个调度问题：混合单的 **同步交付（Synchro）vs 拆分交付（Split）**，以及
**快品优先（fast-item priority）**。**四层机制** 把这套模型保留为“关闭全部新层”的退化特例
（`baseline_flat` 与 baseline 配置逐位一致，由测试与构建脚本双重验证），再叠加四层：

- **需求侧**：日内峰型、批量到达、客群与耐心分布。日均客流相同时，峰值形状把峰值时段繁忙度
  从 66.0% 推到 77.7%、p95 乘以 1.46、流失率从 6.9% 升到 15.1%、利润从 296.0 降到 239.3 元/小时；
  而**日均利用率反而下降**（60.6% → 54.9%），因为流失顾客带走了工作量。
- **供给侧网络**：站台容量、技能、班次。茶站容量从 1 加到 4 时，瓶颈会迁移：临界容量在
  λ=0.6/0.9 时为 3、λ=1.2 时为 4；超过后新增设备不再赚钱。快品优先在“茶站瓶颈”下只值
  +1.33±0.99 元/小时（synchro），在“冰淇淋机瓶颈”下约为其两倍。同样人数同样工资下，
  全员通才比专职分工多赚 +84.5±5.1 元/小时；单向交叉培训几乎无效（+0.17±0.22）。
- **库存/物料清单**：(s,S) 补货、提前期、保质期。基线满足率 98.0%，把 (s,S) 提到最高满足率
  99.95% 几乎不损失利润；真正的约束是珍珠 4 小时保质期与提前期，缺冰时“混合单→茶”替代可挽回
  +14.11 元/小时。
- **经济与公平**：高峰定价、SLA、公平老化上限。“店长组合”（加人手 + 温和高峰定价 + SLA +
  公平上限）相对 campus_rush 基线 **+118.1±5.1 元/小时**，p95 从 11.81 降到 5.73 分钟。
  注意口径：SLA 不改变排队（只把失约变成钱，最高达成率 81.9%）；公平上限降低各客群 p95、
  类间 p95 极差略降，但类间均值极差（class mean spread）从 1.45 升到 1.78 分钟、引擎
  fairness_gap 从 1.48 升到 1.78 分钟，因此它只是尾部保护，
  不是“更公平”的唯一证据。
- **baseline 基线**：拆分交付盈亏平衡点 λ* = 1.1469（ρ* = 80.9%，3 员工）；λ=1.25 时快品优先
  +12.66±1.19 元/小时。这些数字保留为基线章节，AnyLogic 台账仍是**存档、不可重跑**。

复现：`pip install -e ".[dev]"`、`python analysis/run_demand_network.py`、
`python analysis/run_inventory_econ.py`、`python analysis/build_report.py`、
`python analysis/build_demo_data.py`、`python -m pytest -q`（68 个测试）。
交互演示 demo/index.html 为**预计算数据**，浏览器不运行 DES。

> 英文正文为准；数量级与结论以本仓库 Python 引擎可重算结果为准。

---

## Research questions

The baseline questions (still answered, still the baseline):

1. **Delivery strategy.** For a mixed order (tea + ice cream made by the same clerk),
   is *Synchro* (one atomic 2.833-min job, everything handed over together) or *Split*
   (ice cream handed over after 0.833 min, tea after 2.0 min, customer leaves when the
   tea is ready) better?
2. **Fast-item priority.** Should the short bread and ice-cream jobs preempt the
   long tea jobs in the shared clerk queue?
3. **Economics.** When waiting is priced at 0.5 per customer-minute, which policy earns
   more profit per hour, and at what load does the ranking flip?

The layer questions, one per layer:

4. **Demand shape.** With the *same daily mean*, what does an intra-day peak do to
   utilisation, tail waiting, abandonment and profit? What do service-time variability,
   finite patience and group arrivals add?
5. **Supply network.** When the shop is a set of stations with skills and shifts, where
   does the bottleneck sit, when does it migrate, and do the baseline policy answers survive?
6. **Inventory.** How do (s, S) reorder points, lead time and shelf life trade fill rate
   against waste and profit, and what is a stock-out substitution worth?
7. **Economics and fairness.** What do peak pricing, SLA compensation and a starvation
   cap cost or buy, and what does a combined "good manager" configuration deliver?

A further question ties the study to the course material: **why is Split non-trivial at
all?** Both policies have the same capacity, so the answer must come from queueing
dynamics, not from workload. the model generalises that question to every layer: each mechanism
must move a *queue*, not just the total work.

---

## Headline results

### 1. Split delivery: helpful at low load, costly near saturation

`python -m bubble_tea_sim reproduce --reps 200` (3 clerks, 200 paired replicates,
common arrival streams, seed stride 9001; estimator = mean of per-replicate means; the
`--out` flag writes the table to `results/anchors.json`):

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
6 replicates, seed stride 7001; same `results/anchors.json` output):

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

## layer results: four layers, one engine

The layer study re-uses the same engine and adds the four optional layers documented in
[`src/bubble_tea_sim/data_spec.py`](src/bubble_tea_sim/data_spec.py). Results live in
`results/*.json` and are rendered in the main report
([docs/index.html](docs/index.html)) and the complete table dump
([docs/experiments-layers.md](docs/experiments-layers.md)). The layer studies use 100
replicates per cell (60 at estimated peak loads above 95%), seed 0, stride 1, with
paired differences on common random numbers.

### 4. Demand shape: peaks are expensive even when the daily mean is fixed

`results/demand_study.json` (campus_rush peak profile versus a flat profile with the
same daily mean; peak cells 60 replicates, flat 100):

| Profile | Peak-to-mean | Daily util | Peak-hour busy | p95 LOS | Walk-away | Profit / h |
|---|---:|---:|---:|---:|---:|---:|
| Campus peak shape | ×1.49 | 54.9% | 77.7% | 11.77 min | 15.1% | 239.3 |
| Flat, same daily mean | ×1.00 | 60.6% | 66.0% | 8.05 min | 6.9% | 296.0 |

The paired difference is unambiguous: peak-hour busy ratio +11.7 points, p95 +3.71 ± 0.37
minutes, walk-away +8.1 points, served −21.9 customers, profit −56.9 ± 6.0 per hour —
while the daily utilisation actually *falls* by 5.7 points, because abandoning customers
remove work from the system. Raising the peak multiplier further from ×1.49 to ×1.85
(the “peak factor” sweep, daily mean still fixed) adds another 1.89 minutes of p95,
+11.5 points of walk-away and −72.3 per hour of profit.

Service-time variability moves the tail much more than the mean (p95 range 4.62 min at
λ = 1.0 and 6.71 min at λ = 1.2 across fixed/exponential/lognormal variants, versus a
2.21-min range in mean LOS); the engine forces exponential sampling (CV = 1) whenever
the variability kind is `exponential`. Patience is a demand-side lever: at λ = 1.2 the
abandonment rate is 29.3% with a 3-minute balk threshold and 3.2% with a 12-minute one,
and with arrival-time balking active reneging almost never binds. Batch arrivals matter
less: holding the daily customer mean fixed, a 30% batch probability raises walk-away
from 7.5% to 9.3% and lowers profit from 235.4 to 219.8 /h.

### 5. Supply network: the bottleneck migrates

`results/network_study.json` sweeps tea-station capacity 1–4 with baristas synced to
stations, at λ = 0.6/0.9/1.2. The tea station remains the busiest station at every
capacity, but each extra station pays for itself only up to the study's **critical
capacity**: 3 at λ = 0.6 and 0.9, 4 at λ = 1.2 (paired marginal profit ≤ 0). Beyond it
the shared barista pool and the order counter decide the queue.

The baseline policy matrix behaves differently against different bottlenecks. Fast-item
priority is worth +1.33 ± 0.99 /h in the tea-bottleneck scenario (synchro) and
+1.70 ± 0.76 /h in the ice-cream-bottleneck scenario; with split delivery the values are
+2.31 ± 0.60 and +3.01 ± 0.71 /h. Split delivery itself is *negative* in the tea
bottleneck (−2.01 ± 1.31 /h, FCFS). Skills are a first-order lever at equal headcount and
equal wage: four generalists beat four dedicated staff by **+84.5 ± 5.1 /h**, while
one-way cross-training is worth +0.17 ± 0.22 /h (nothing measurable). Unpaid staggered
breaks are not free: peak-hour LOS rises from 5.19 to 7.37 minutes because the break
removes capacity exactly at the peak (Δ profit −49.4 /h); a mid-shift barista adds
headcount but leaves the peak-hour wait essentially unchanged (+0.06 ± 0.08 min), since
the tea station — not headcount — is the binding resource then.

### 6. Inventory: fill rate is cheap, shelf life is not

`results/inventory_study.json` (lean scenario: 3 clerks, quoted 1.15/min, four
ingredients, 60–90 min lead times, four-hour pearl shelf life):

| Metric | Lean baseline |
|---|---:|
| Fill rate (all arrivals) | 98.0% |
| Stock-out losses / day | 11.18 |
| Waste units / day | 0.0 |
| Purchase cost / day | 1038.1 |
| Profit / hour | 144.9 |

Raising (s, S) to the study's recommended setting gives fill rate **99.88%** for
+0.13 /h of profit — fill rate is almost free. Waste is set by shelf life, not by the
reorder point: the study's waste-free shelf-life threshold is 240 minutes, and its
lead-time service threshold is 60 minutes. Substitution is the revenue lever when a
*substitutable* ingredient is short: with ice short, routing mix orders to tea recovers
**+14.11 /h** versus losing the sale; with pearls short, all three stock-out policies
collapse onto the same lost sales.

### 7. Economics and fairness: the management bundle

`results/economics_study.json` (campus_rush: served 528.8, balk 101.7, mean LOS
4.68 min, p95 11.81 min, profit 240.07 /h). Peak pricing with elasticity moves both
revenue and profit, but the profit optimum sits at the boundary of the tested range
because the model charges waiting cost only to served customers; the decision-useful
number is the **service-neutral multiplier** (×1.2 at ε = −0.5: 97.9% of demand retained,
peak p95 11.51 min, profit 318.45/h). No SLA setting reaches 100% attainment — the
attainments are 41.9% / 61.4% / 81.9% for 3/5/8-minute targets, and the study confirms
that SLA compensation does not change the queue at all
(`service_is_unchanged_by_sla = true`).

A starvation cap lowers the overall p95 from 9.99 to 8.86 minutes and lowers every
customer class's p95, at a profit cost of 5.06 /h. Read the fairness metric carefully:
the class-to-class **p95** spread narrows only slightly (2.27 → 2.22 min), while the
**class mean spread** widens (1.45 → 1.78 min) and the engine's `fairness_gap`
(max−min of class means, per replicate, then averaged) widens too (1.48 → 1.78 min).
The study records this as
`mean_gap_widens_while_tail_gap_narrows = true`; the cap is tail protection, not proof of
a fairer average.

Combining the levers — one extra barista, a modest peak multiplier with elasticity, an
SLA with compensation, and the fairness cap — gives a paired **+118.1 ± 5.1 profit per
hour** (+49%) over the campus baseline and cuts p95 by **6.09 minutes** (11.81 → 5.73).
The lever ranking is capacity first, pricing second; SLA and fairness are cheap
tail-protection add-ons.

---

## Quick start

Requires Python 3.10+ and nothing beyond the standard library at runtime.

```powershell
python -m pip install -e ".[dev]"        # installs the package + pytest
python -m pytest -q                      # 69 tests, about 40 s on the dev laptop

# direct CLI: one configuration, a narrow sweep, the anchors and a break-even run
python -m bubble_tea_sim run --lam 1.25 --workers 3 --split --fast --seed 0
python -m bubble_tea_sim sweep --workers-list 3 `
    --lambdas 0.4,0.6,0.8,1.0,1.2,1.25 --reps 200
python -m bubble_tea_sim breakeven --workers 3 --lower 0.5 --upper 1.3 --reps 60
python -m bubble_tea_sim reproduce --reps 200 --out results/anchors.json

# regenerate the committed baseline results and the earlier report
python analysis/run_policy_sweep.py        # full grid: 1-5 workers x lambda 0.30-1.30
python analysis/run_breakeven.py           # 2-4 workers, profit + mean-LOS roots
python analysis/reproduce_anylogic_ledger.py
python analysis/build_report.py            # archive/report-2026-11.html + docs/experiments.md + docs/figures/

# regenerate the layer results (four layers) and the main report + demo
python analysis/run_demand_network.py       # scenario library + layer 1 + layer 2
python analysis/run_inventory_econ.py       # layer 3 + layer 4
python analysis/build_report.py         # docs/index.html, docs/experiments-layers.md, docs/figures-layers/
python analysis/build_demo_data.py         # demo/data/*.json (offline demo)
```

The earlier report is preserved at [archive/report-2026-11.html](archive/report-2026-11.html); the
current report is the current one at [docs/index.html](docs/index.html). The offline demo at
[demo/index.html](demo/index.html) replays precomputed data from
[demo/data/](demo/data/) — it opens directly from `file://`, makes no network calls and
does not run the simulation in the browser (browsers also block `fetch()` on `file://`,
so the page loads `demo/data/bundle.js`, a generated mirror of the JSON files).

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
│   ├── common.py                  # shared JSON/statistics plumbing (baseline studies)
│   ├── study_common.py               # shared harness: schema, seeds, replicate/paired helpers
│   ├── svgchart.py                # dependency-free SVG charts for both reports
│   ├── run_policy_sweep.py        # -> results/policy_sweep.json
│   ├── run_breakeven.py           # -> results/breakeven.json
│   ├── run_behaviour.py           # -> results/behaviour.json
│   ├── run_sensitivity.py         # -> results/sensitivity.json
│   ├── reproduce_anylogic_ledger.py  # -> results/anylogic_ledger.json
│   ├── build_report.py            # -> archive/report-2026-11.html + docs/experiments.md (baseline tables) + docs/figures/
│   ├── run_demand_network.py       # -> results/scenario_library.json, demand_study.json, network_study.json
│   ├── run_inventory_econ.py       # -> results/inventory_study.json, economics_study.json
│   ├── build_report.py         # -> docs/index.html + docs/experiments-layers.md + docs/figures-layers/
│   └── build_demo_data.py         # -> demo/data/*.json + demo/data/bundle.js
├── archive/
│   ├── anylogic/                  # frozen AnyLogic model snapshot (not re-runnable)
│   │   ├── MIXUE_Model.alp
│   │   ├── 3d/person.dae
│   │   └── README.md
│   └── report-2026-11.html             # earlier report (regenerated byte-for-byte by analysis/build_report.py)
├── data/
│   ├── README.md                  # scenario schema + provenance rules
│   └── scenarios/*.json           # 16 shop contexts, each with a provenance block
├── demo/
│   ├── index.html                 # offline interactive demo (vanilla JS, no CDN, no build step)
│   └── data/                      # precomputed demo data (JSON + bundle.js mirror)
├── original/                        # verbatim original course scripts (provenance only)
│   ├── mixed_order_sim.py
│   ├── bread_priority_sim.py
│   ├── icecream_strategy_sim.py
│   └── README.md
├── docs/
│   ├── theory.md                  # Lecture 1-4 formulas + the mechanism layer formulas
│   ├── experiment_log.md          # archival AnyLogic ledger + baseline anchors + layer result index
│   ├── design.md                  # engine design, determinism contract, extensions
│   ├── reproducing.md             # environment, commands, runtimes, seed rules
│   ├── experiments.md             # generated baseline result tables
│   ├── experiments-layers.md          # generated layer result tables (all five studies)
│   ├── index.html                 # generated static report
│   ├── figures/                   # generated baseline SVG figures
│   ├── figures-layers/                # generated SVG figures
│   └── assets/slides/             # archived AnyLogic screenshots (A/B/C/M3/E)
├── results/                       # committed JSON outputs of the analysis scripts
│   ├── policy_sweep.json
│   ├── breakeven.json
│   ├── behaviour.json
│   ├── sensitivity.json
│   ├── anylogic_ledger.json
│   ├── anchors.json
│   ├── scenario_library.json
│   ├── demand_study.json
│   ├── network_study.json
│   ├── inventory_study.json
│   └── economics_study.json
├── src/bubble_tea_sim/
│   ├── params.py                  # order mix, service times, policy, economics, SimConfig
│   ├── data_spec.py               # mechanism layer specifications (demand, network, inventory, pricing, SLA)
│   ├── library.py                 # scenario loader: data/scenarios/*.json -> SimConfig
│   ├── engine.py                  # event loop, scheduling, stations/staff, per-run metrics
│   ├── scenarios.py               # original and study configurations
│   ├── stats.py                   # replicates, paired differences, break-even
│   ├── cli.py                     # run / sweep / breakeven / reproduce
│   ├── __main__.py                # python -m bubble_tea_sim
│   └── __init__.py
├── tests/
│   ├── test_anchors.py     # pins the archived M2/P-series numbers
│   ├── test_layers.py          # degenerate equivalence + layer mechanism invariants
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
documents the event loop, the determinism contract and the extension points; the layer
configurations are specified in [`src/bubble_tea_sim/data_spec.py`](src/bubble_tea_sim/data_spec.py)
and the scenario file format in [`data/README.md`](data/README.md).

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

The P-series original configuration (used for the fast-priority table) differs: no mixed
orders, order mix tea 65% / bread 20% / ice cream 15%, and ice-cream make time 0.33 min.
Both configurations are defined in [`src/bubble_tea_sim/scenarios.py`](src/bubble_tea_sim/scenarios.py).

### mechanism layer assumptions

The mechanism layers are opt-in; a scenario JSON enables the ones it needs. Each scenario file
carries a provenance block (`source`, `method`, `uncertainty`, `notes`) and every entry
in the current library is marked `uncertainty: high` — they are **synthetic teaching
cases anchored on the course assumptions, not field data**.

| Layer | Main assumptions | Where it is defined |
|---|---|---|
| Demand | Piecewise-constant intra-day multipliers, group arrivals (2–4 customers), customer classes with their own mix and lognormal patience; daily mean optionally normalised | `data_spec.DemandProfile`, `BatchSpec`, `MixSpec`, `PatienceSpec` |
| Network | Stations with finite capacity, staff roles with skills, shift windows and staggered breaks, component → station routing | `data_spec.NetworkSpec`, `StaffSpec`, `StationSpec` |
| Inventory | Ingredients with (s, S) replenishment, lead time, shelf life, recipes per product, stock-out policy `lose` or `substitute` | `data_spec.InventorySpec`, `Ingredient`, `Recipe` |
| Pricing / SLA / fairness | Peak windows with a price multiplier and constant elasticity, SLA target + fixed compensation, starvation cap (aging escalation) | `data_spec.PricingSpec`, `SlaSpec`, `Policy.starvation_cap` |

The 16 scenario files live in [`data/scenarios/`](data/scenarios/); the schema and
provenance rules are documented in [`data/README.md`](data/README.md). The main report's
scenario table is the authoritative list.

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
[`original/`](original/) for the same reason; they are superseded by the package.

| Artifact | Reproducible? | How |
|---|---|---|
| Python engine and CLI | **Yes** | fixed seeds, deterministic event loop, standard library only |
| `reproduce` M2/P-series anchor tables | **Yes** | `python -m bubble_tea_sim reproduce --reps 200` |
| Policy sweep, break-even, behavior studies (baseline) | **Yes** | `sweep` / `breakeven` / `run` subcommands |
| AnyLogic E-series re-check (archived 1000-min settings) | **Yes** | `python analysis/reproduce_anylogic_ledger.py` → `results/anylogic_ledger.json` |
| scenario library + four layer studies | **Yes** | `analysis/run_demand_network.py`, `analysis/run_inventory_econ.py` → `results/*.json` |
| main report, table dump and figures | **Yes** | `python analysis/build_report.py` → `docs/index.html`, `docs/experiments-layers.md`, `docs/figures-layers/` |
| Offline demo data | **Yes** | `python analysis/build_demo_data.py` → `demo/data/*.json` + `demo/data/bundle.js` |
| [`docs/experiments.md`](docs/experiments.md) (baseline tables), [`docs/figures/`](docs/figures/) | **Yes** | regenerated by `analysis/build_report.py` from `results/*.json` |
| [`archive/report-2026-11.html`](archive/report-2026-11.html) (earlier report) | **Yes** | regenerated byte-for-byte by `analysis/build_report.py` (it writes the archive copy, never the main report) |
| AnyLogic model (`archive/anylogic/MIXUE_Model.alp`), screenshot evidence and E-series ledger | **No** | archived evidence; see [docs/experiment_log.md](docs/experiment_log.md) |

The engine can go one step further than "the archive is not re-runnable": the archived
E-series configurations are re-implemented at their own settings (3 clerks, 1000-min
horizon, no warm-up, seed 1, 200 replicates) and compared like-for-like. The archived
profit per hour is reproduced within +3.4% / −8.6% across all six runs, with the
E5–E6 ordering swapping places; the check and its caveats are in
[experiment_log.md §4](docs/experiment_log.md#4-baseline-engine-re-check-of-the-archive).

**Statistical conventions.** Policy and layer comparisons use common random numbers:
the same seed is reused for every configuration being compared, so differences are
paired. The default studies use seeds `0, 1, 2, …` (stride 1) with 100 replicates per
cell (60 at estimated peak loads above 95%); original anchors keep the original strides
(9001 for the mixed-order study, 7001 for the bread-priority study). The main report also
re-runs three cheap contract checks at build time (layer-off equivalence against the baseline
configuration, determinism, flow conservation across all scenarios) and prints their
result instead of asking the reader to trust them. `python -m pytest -q` pins the baseline
anchors and the mechanism layer invariants (69 tests).

**What changed in this cleaned-up version.** The original Python scripts were merged into
one configuration-driven engine (the originals are kept verbatim under `original/`); the
regression suite pins the original anchors; the AnyLogic model is preserved as an archive
under `archive/anylogic/` rather than as executable code; local course-directory
references were replaced by relative links and lecture numbers. Here, the same engine
gained four optional layers (`data_spec.py`), a provenance-carrying scenario library
(`data/scenarios/`), a machine-readable experiment harness (`analysis/study_common.py`) and
a static, script-free report plus an offline demo.

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
| 3 (layer) | Non-stationary demand: peak ratio, peak-hour utilisation, tail amplification | The daily mean is not the planning number: the same mean with a peak raises p95 and abandonment. | Tests it: +11.7 points peak-hour busy, p95 ×1.46 and +8.1 points walk-away at constant daily demand. |
| 3 (layer) | Variability queues: `CV_p`, `CV_a` and the tail | Variability moves the upper tail much more than the mean. | Service-time scan: p95 range 4.62 / 6.71 min at λ = 1.0 / 1.2 while mean LOS moves only 2.21 min. |
| 2 (layer) | Bottleneck in a staged network: minimal station capacity, marginal profit | Adding equipment pays only until another resource binds. | Tea-capacity sweep: critical capacity 3 (λ = 0.6, 0.9) and 4 (λ = 1.2). |
| 4 (layer) | `(s, S)` inventory, fill rate, lead time and shelf life | Safety stock trades fill rate against waste; a perishable sets a floor on waste. | Inventory grid: 98.0% baseline fill, 99.95% best fill at almost no profit change; 240-min waste-free shelf-life threshold. |
| 4 (layer) | Constant-elasticity pricing, `m^ε`, and the service-neutral multiplier | Price moves both demand and the tail; the useful number is the largest move that keeps service intact. | Pricing grid: ×1.2 service-neutral multiplier at ε = −0.5 keeps 97.9% of demand. |

Full derivations and the numerical checks live in
[docs/theory.md](docs/theory.md); the mechanism layer formulas are in its sections 11–16.

The theory also explains why Split is not a trivial "hand it over earlier" change:
capacity is invariant, waiting is redistributed between job classes, and the queueing
response is non-linear in utilisation. See
[why Split is non-trivial](docs/theory.md#6-why-split-is-non-trivial).

---

## Limitations

* **Assumed parameters.** Prices, wages, waiting cost, order mix and service times are
  course assumptions, not measured field data. The economic ranking inherits that.
* **Synthetic scenarios (layer scenarios).** All 16 shop contexts are synthetic teaching cases with
  `uncertainty: high`. They are a disciplined way to compare mechanisms, not calibrated
  forecasts; absolute profit and LOS levels should not be quoted as predictions.
* **Deterministic service times in baseline.** No make-time variability in the baseline studies, so
  real queues are likely worse than the original model at the same utilisation. The model demand
  layer adds variability as an optional layer and shows it moves the tail, not the mean.
* **Poisson arrivals, one queue (baseline).** No batch arrivals, no delivery orders, no
  ingredient stock-outs, no staff breaks or shift changes, no balking/reneging in the
  default baseline experiments (they exist in the engine but are off). The mechanism layers add all
  of these, but only where a scenario enables them.
* **Balking heuristic.** The balk rule estimates waiting from the customers in the shop
  and the staff on duty (the engine counts only staff who are on shift); it is a
  modelling device, not a calibrated customer model.
* **Split motivation is not priced.** The study does not model melting or the value of
  an earlier ice-cream hand-off; that benefit must be argued qualitatively.
* **Single-day model.** 480 simulated minutes, 60-minute warm-up; there is no
  day-to-day stock carry-over, fatigue or learning. A run is one representative day.
* **Pricing optimum is a boundary artefact.** The model charges waiting cost only to
  customers who stay, so raising price looks profitable partly because abandoning
  customers are free. Treat the profit-maximising multiplier as a modelling limit and use
  the service-neutral multiplier for decisions.
* **Fairness metric caveat.** `fairness_gap` is the max−min spread of class means
  (per replicate, then averaged); the study also reports `class_mean_spread`
  (1.45 → 1.78 min). The starvation cap lowers every class's p95 and slightly narrows the
  p95 spread, but both mean-based spreads rise; the report says this explicitly rather
  than calling the cap "fairer".
* **Fill-rate denominator.** `fill_rate` counts all arrivals (including the warm-up
  hour) while money and served metrics are post-warm-up; the inventory study records this
  as a caveat.
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

Next steps: calibrate the scenario library with real shop data (arrival profiles, mix,
make times, patience), add multi-day inventory carry-over and rosters, model the value of
an early hand-off, and estimate price elasticities from transaction data.

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
