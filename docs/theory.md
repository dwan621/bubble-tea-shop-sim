# Theory Layer: From Lecture 1–4 to the Simulation

This document records the analytical layer of the study: the course formulas used as
*predictions*, the parameter conventions that connect them to the simulation, and the
comparison between theoretical and simulated results. It is written so that the theory
can be checked independently of the report and without access to the original course
directory.

> **中文**：本文把课程 Lecture 1–4 的公式翻译成可检验的预测，并给出与仿真结果的对照。
> 所有仿真数字均来自仓库内引擎的可重算命令；文中不引用本机路径，课程材料只用
> “Lecture 1–4” 指代。

**Companion files:** [../README.md](../README.md) for the headline results,
[experiment_log.md](experiment_log.md) for the archival AnyLogic ledger,
[reproducing.md](reproducing.md) for commands and seed conventions.

---

## 1. Purpose and scope

The project is not a simulation demo. The analysis is structured as:

1. use the course formulas to predict system behaviour;
2. test those predictions with a discrete-event simulation;
3. explain why the policy effect (Split vs Synchro) is non-obvious.

The model is deliberately simple — one queue, fixed service times per class, Poisson
arrivals — so that the gap between formula and simulation measures the modelling
assumptions rather than hidden complexity.

> **中文**：先公式预测、再仿真检验、最后解释策略差异的机制。模型刻意保持简单，
> 使“理论 vs 仿真”的偏差可归因于假设，而不是实现复杂度。

---

## 2. Model conventions

The flow unit is one customer order. Service time includes order entry plus preparation,
because the same cross-trained clerk owns both steps.

| Order class | Share (default) | Service time | Composition |
|---|---:|---:|---|
| Tea only | 0.55 | 2.500 min | order 0.5 + tea 2.0 |
| Bread only | 0.20 | 0.667 min | order 0.5 + bread 0.167 |
| Ice cream only | 0.05 | 0.833 min | order 0.5 + ice cream 0.333 |
| Mixed tea + ice cream | 0.20 | 2.833 min | order 0.5 + tea 2.0 + ice cream 0.333 |

The shared clerk pool is the only resource and therefore the bottleneck. A mixed order
is one 2.833-min job under Synchro, or two jobs (0.833 min ice component + 2.0 min tea
component) under Split; the total work is identical by construction.

The legacy fast-priority series (P-series) uses a different mix — tea 65% / bread 20% /
ice cream 15%, no mixed orders, ice-cream make time 0.33 min — and is documented
separately in [experiment_log.md](experiment_log.md).

> **中文**：流程单元是订单，服务时间含点单与制作；混合单拆分前后总工作量严格相同。
> P 系列（快品优先历史实验）使用不同订单结构的旧口径，单独记录。

---

## 3. Lecture 1 — Flow metrics and Little's Law

Course formula:

```text
I = R × T
```

* `I` — average number of customers in the store;
* `R` — throughput (customers per minute);
* `T` — average flow time (minutes).

Because the default study has no abandonment, `R` equals the arrival rate λ (up to
finite-horizon sampling noise), so `I ≈ λ × T`. Using the simulated all-order LOS from
`python -m bubble_tea_sim reproduce --reps 200` (3 clerks, paired 200 replicates,
seed stride 9001) for the mixed-order configuration:

| λ (cust/min) | Policy | Simulated T (min) | Implied I = λT |
|---:|---|---:|---:|
| 1.00 | Synchro | 2.872 | 2.87 |
| 1.00 | Split | 2.812 | 2.81 |
| 1.25 | Synchro | 4.930 | 6.16 |
| 1.25 | Split | 5.050 | 6.31 |

The λ = 1.0 rows come from `scenarios.legacy_mixed_order(1.0)` with
`stats.replicate(reps=200, seed=0, seed_stride=9001)`; the CLI's `reproduce` command
covers λ = 0.5, 0.8, 1.1 and 1.25. Both use the same configuration and estimator, so
the numbers are directly comparable with the tables in this document.

Interpretation: the policy does not create or destroy demand. A lower `T` at the same λ
means fewer customers inside the shop; that is the whole operational benefit, and it is
why waiting time is the natural intermediate variable for the economic layer.

> **中文**：Little 定律把仿真得到的流程时间 T 换算成店内人数 I。策略不改变需求，
> 只改变 T，从而改变店内堆积人数。

---

## 4. Lecture 2 — Capacity, bottleneck and utilisation

Course formulas:

```text
Capacity            = m / p
Process capacity    = capacity of the bottleneck
Flow rate           = min{demand rate, process capacity}
Utilisation         = flow rate / capacity
```

With a cross-trained clerk pool serving a mix of order types, the relevant service time
is the demand-weighted mean:

```text
p̄ = Σ share_i × p_i
  = 0.55(2.500) + 0.20(0.667) + 0.05(0.833) + 0.20(2.833)
  = 2.11665 min/customer
```

For three clerks:

```text
C = m / p̄ = 3 / 2.11665 = 1.4173 customers/min = 85.04 customers/hour
ρ(λ) = λ × p̄ / m
```

Theoretical and observed utilisation agree closely. Observed values are from the
200-replicate mixed-order runs above (utilisation = busy clerk-minutes / (3 × 480)):

| λ | Demand (cust/hour) | Required clerk-min/hour | Theoretical ρ | Observed ρ |
|---:|---:|---:|---:|---:|
| 0.50 | 30.0 | 63.50 | 35.3% | 35.4% |
| 0.80 | 48.0 | 101.60 | 56.4% | 56.6% |
| 1.00 | 60.0 | 127.00 | 70.6% | 70.7% |
| 1.10 | 66.0 | 139.70 | 77.6% | 77.6% |
| 1.25 | 75.0 | 158.75 | 88.2% | 88.2% |

Key theoretical point: Split and Synchro have the same total workload — a mixed order is
either one 2.833-min job or two jobs summing to 2.833 min. Therefore utilisation is
*not* a decision metric; the policies only redistribute waiting. The simulation confirms
this exactly: utilisation is identical to three decimals between the paired policies at
every load in the M2 table.

> **中文**：加权平均服务时间 p̄=2.11665 min，3 人产能 1.4173 人/min（85.0 人/h）。
> 理论利用率与仿真利用率吻合；拆分/同步的总工作量相同，因此利用率不能作为决策指标。

---

## 5. Lecture 3 — Multi-server queueing approximation

Course concepts:

```text
CV_a = σ_a / a          (arrival-process variability)
CV_p = σ_p / p          (service-time variability)
U    = p / (a × m) = λ p / m
```

The multi-server waiting-time approximation used in the course:

```text
T_q = (p / m)
      × U^[sqrt(2(m + 1)) − 1]
      × (CV_a² + CV_p²) / 2
      × 1 / (1 − U)
```

For this model: arrivals are Poisson (`CV_a = 1`), `m = 3`, and service times are fixed
within a class but vary across the order mix, so the service-time distribution is a
four-point mixture:

```text
p̄     = 2.11665 min
σ_p   = 0.82834 min      (mixture standard deviation)
CV_p  = 0.39134
```

Using `p = p̄`, `U = λ p̄ / 3`:

| λ | U | Predicted Tq (min) | Predicted Tflow = Tq + p̄ | Predicted I = λTflow |
|---:|---:|---:|---:|---:|
| 0.40 | 28.2% | 0.056 | 2.173 | 0.87 |
| 0.60 | 42.3% | 0.146 | 2.263 | 1.36 |
| 0.80 | 56.4% | 0.328 | 2.445 | 1.96 |
| 1.00 | 70.6% | 0.730 | 2.847 | 2.85 |
| 1.10 | 77.6% | 1.143 | 3.260 | 3.59 |
| 1.25 | 88.2% | 2.739 | 4.855 | 6.07 |

### Theory vs simulation

The approximation predicts an FCFS/Synchro baseline. Comparing it with the mixed-order
Synchro runs from `reproduce --reps 200`:

| λ | Theory Tflow | Simulated Tflow | Difference |
|---:|---:|---:|---:|
| 0.50 | 2.210 | 2.196 | −0.6% |
| 0.80 | 2.445 | 2.441 | −0.2% |
| 1.10 | 3.260 | 3.303 | +1.3% |
| 1.25 | 4.855 | 4.931 | +1.6% |

This is the main validation of the simulation: the engine is not just telling a
convenient story, it reproduces the course queueing prediction within about 1.6% —
including the sharp non-linearity as `U → 1`, which is exactly the mechanism behind the
high-load trade-off.

Caveats:

* the approximation ignores priority classes, so it predicts the FCFS/Synchro baseline
  only, not Split or fast priority;
* service times are deterministic within a class, so all variability enters through the
  order mix; real shops will have more variability and longer queues;
* with finite 480-min runs and a 60-min warm-up, simulation estimates carry sampling
  error (the reported tables use 200 paired replicates to keep it small).

> **中文**：Lecture 3 的多服务台近似以泊松到达、4 点混合服务时间分布代入，预测的
> 流程时间与 200 次仿真在 λ=0.5–1.25 区间内相差约 0.2%–1.6%，验证了仿真机制。
> 该近似只对应 FCFS/同步基线，不预测优先级效应。

---

## 6. Why Split is non-trivial

For a mixed order:

```text
Synchro departure  = completion of the single 2.833-min mixed job (all components ready together)
Split departure    = completion of the tea component
Split ice hand-off = completion of the ice component (about 2 min earlier)
```

So the customer's departure definition is essentially unchanged, yet the arrival-level
LOS can move in either direction. Split is not "hand it over earlier" in a vacuum: it
changes *when the shared clerks start which job*.

Three hypotheses explain the effect:

1. **Capacity invariance.** Total workload and utilisation are unchanged (Section 4).
   Nothing is gained or lost in aggregate capacity.
2. **Queue redistribution.** Giving the short ice component jump priority moves waiting
   from mixed-order customers onto the mainstream tea/bread queue. At low load the
   system has slack, so the redistribution is almost free; at high load the mainstream
   queue is already strained and absorbs the cost.
3. **Non-linear queue response.** `Tq` grows like `U^1.83 / (1 − U)` (Section 5), so the
   marginal cost of extra waiting rises steeply near saturation. This is why the sign of
   the Split effect can reverse as λ increases even though average workload is fixed.

Observed pattern (mixed-order M2, 3 clerks, `reproduce --reps 200`):

| λ | Δ all-order LOS (Split − Synchro) | Δ mixed-order LOS | Δ ice hand-off | Δ bread LOS |
|---:|---:|---:|---:|---:|
| 0.50 | −0.14 min | −0.68 min | −2.03 min | +0.01 min |
| 0.80 | −0.10 min | −0.56 min | −2.17 min | +0.02 min |
| 1.10 | −0.02 min | −0.44 min | −2.89 min | +0.08 min |
| 1.25 | +0.12 min | −0.30 min | −4.41 min | +0.22 min |

*Negative = Split is better for that metric.* The ice hand-off always improves; the
all-order and bread columns flip sign between λ = 1.10 and 1.25. That flip is the
empirical content of hypotheses 2 and 3.

> **中文**：拆分并不改变顾客离开时间的定义，而是改变共享员工“先做哪个任务”的顺序。
> 三个假设：产能不变、等待在品类间重新分配、排队对利用率的非线性响应。
> 仿真显示冰淇淋到手始终提前，但全店等待在 λ≈1.1–1.25 之间由改善转为恶化。

---

## 7. Lecture 4 — MPS, BOM, MRP and CRP

The service model connects to the production-planning layer through material and
capacity requirements. At the default λ = 1.25 customers/min (75 customers/hour):

### 7.1 Master production schedule (MPS)

```text
MPS_i per hour = 60 × λ × share_i
```

| Product group | Orders/hour |
|---|---:|
| Tea only | 41.25 |
| Bread only | 15.00 |
| Ice cream only | 3.75 |
| Mixed tea + ice cream | 15.00 |

### 7.2 BOM and gross requirements

Using simplified kits until real recipes are collected:

| Kit | Used by |
|---|---|
| Tea kit | tea-only order + tea component of a mixed order |
| Ice-cream kit | ice-only order + ice component of a mixed order |
| Bread unit | bread-only order |

```text
Gross requirement_j = Σ_i MPS_i × BOM_ij
```

| Item | Gross requirement/hour |
|---|---:|
| Tea kit | 41.25 + 15.00 = 56.25 |
| Ice-cream kit | 3.75 + 15.00 = 18.75 |
| Bread unit | 15.00 |

### 7.3 MRP logic

Under lot-for-lot:

```text
Net requirement_t = max(0, gross requirement_t + safety stock
                           − projected on-hand inventory_t
                           − scheduled receipts_t)
Planned order release_t = net requirement_(t + lead time)
```

The repository does not simulate inventory; MRP is included to show that the order mix
determines ingredient demand, not to claim a validated replenishment policy. Real
recipes, lead times and safety stocks are required before the numbers mean anything.

### 7.4 Capacity requirements planning (CRP)

```text
Required clerk-min/hour = Σ_i MPS_i × p_i
Available clerk-min/hour = m × 60
```

| Order class | Orders/hour | Service time (min) | Required clerk-min/hour |
|---|---:|---:|---:|
| Tea | 41.25 | 2.500 | 103.125 |
| Bread | 15.00 | 0.667 | 10.000 |
| Ice cream | 3.75 | 0.833 | 3.125 |
| Mixed | 15.00 | 2.833 | 42.500 |
| **Total** | | | **158.750** |

```text
Available = 3 × 60 = 180 clerk-min/hour
ρ = 158.75 / 180 = 88.2%
```

This is identical to the Lecture 2 utilisation calculation by construction: CRP and
process-capacity analysis must agree when the same order mix and the same time standards
are used.

> **中文**：在 λ=1.25 下，MPS 为奶茶 41.25、面包 15、冰淇淋 3.75、混合单 15 单/小时；
> 物料毛需求为奶茶套件 56.25、冰淇淋套件 18.75、面包 15；所需员工分钟 158.75，
> 可用 180，利用率 88.2%，与 Lecture 2 的产能分析一致。

---

## 8. Economic layer

If every order is served and the order mix is fixed, revenue and wage cost are the same
under both delivery policies. The only channel through which the policies differ is
waiting, so the economic layer prices waiting.

### 8.1 Textbook form

```text
Profit/hour = R × weighted price
              − workers × wage per worker-hour
              − c_w × I
```

Substituting Little's Law `I = R × T`:

```text
Profit/hour = R × weighted price − workers × wage − c_w × R × T
```

With the default assumptions:

```text
weighted price = 0.55(8) + 0.20(6) + 0.05(2) + 0.20(10) = 7.70
wage           = 3 × 25 = 75 per hour
c_w            = 0.5 per customer-minute = 30 per customer-hour
```

Because revenue and wage cancel in a paired comparison, the profit difference is:

```text
ΔProfit/hour = c_w × (I_synchro − I_split)
             = 30 × λ × (T_synchro − T_split)
```

Using the simulated T values from Section 3:

| λ | I Synchro | I Split | ΔProfit/hour (Split − Synchro) |
|---:|---:|---:|---:|
| 0.50 | 1.100 | 1.030 | +2.10 |
| 0.80 | 1.952 | 1.872 | +2.40 |
| 1.10 | 3.630 | 3.608 | +0.66 |
| 1.25 | 6.162 | 6.312 | −4.50 |

So the analytical crossing lies between λ = 1.10 and 1.25, and the engine narrows it
down. `analysis/run_breakeven.py` (3 clerks, 200 paired replicates on a 0.05 load grid,
bisection tolerance 0.01) writes `results/breakeven.json`:

```text
λ* = 1.1469 customers/min   ρ* = 80.9%   identification band: λ ∈ [1.10, 1.20]
```

The profit and mean-LOS roots coincide exactly, as the algebra above requires; the same
script gives λ* ≈ 0.671 with 2 clerks and λ* ≈ 1.623 with 4.

### 8.2 How the engine actually computes profit

The engine reports `profit_per_hour` as:

```text
profit_per_hour = (revenue_after_warmup − wage_total − c_w × flow_time_total)
                  / (sim_minutes / 60)
```

where `revenue_after_warmup` and `flow_time_total` include only customers who arrive
after the 60-min warm-up, while the denominator is the full 480-min shop day. This keeps
every reported profit internally consistent, but it makes the effective throughput lower
than `λ × 60`, so the default 480-min study profits (for example 272.9 at λ = 1.25,
3 clerks, Synchro) are **not** directly comparable with the archived AnyLogic E-series
profit figures, which used 1000-minute runs with no warm-up. The analysis script
`analysis/reproduce_anylogic_ledger.py` re-runs the engine at the archived settings and
reports the like-for-like deviation: archived profit is reproduced within +3.4% / −8.6%
across E1–E6 (see [experiment_log.md §4](experiment_log.md#4-v2-engine-re-check-of-the-archive)).
The sign and break-even location are unaffected.

> **中文**：经济层只通过等待成本区分策略：ΔProfit/h = 30 × λ × (T_sync − T_split)。
> 用仿真 T 代入得到低负载下 Split 略赚、λ=1.25 时亏损，解析平衡点在 1.10–1.25 之间，
> 引擎二分得到 λ*≈1.147（约 80.9% 利用率，识别带 1.10–1.20）。引擎的利润实现按“预热后收入 + 全天 8 小时”
> 计算，因此利润绝对水平不能与 AnyLogic 存档数字直接比较。

---

## 9. Theory-to-test map

The analytical claims are executable: `python -m pytest -q` pins them.

| Claim | Where tested |
|---|---|
| `p̄ = 2.11665`, capacity `1.4173`/min | `tests/test_params.py::test_default_mean_service_time_and_capacity` |
| `ρ(λ=1.0) = 0.7056`, `ρ(1.25) = 0.8818` | `tests/test_params.py::test_lecture2_utilization` |
| weighted price `7.70`, waiting cost `0.5` | `tests/test_params.py::test_economic_parameters` |
| Simulated M2 anchors (LOS, ice hand-off, utilisation) | `tests/test_legacy_anchors.py` (8 parameterised cases) |
| P-series pooled anchors | `tests/test_legacy_anchors.py` (6 parameterised cases) |
| Directional conclusions (Split better at λ=0.5, worse at λ=1.25) | `tests/test_legacy_anchors.py::test_mixed_order_conclusions_hold` |
| Flow conservation, determinism, scheduling invariants | `tests/test_engine_invariants.py`, `tests/test_policies.py`, `tests/test_behaviour.py` |

The analytical tables in Sections 3–8 are regenerated with the commands in
[reproducing.md](reproducing.md); the sections that are pure algebra can be checked by
hand from the parameter table in Section 2.

---

## 10. Limitations of the analytical layer

* The `Tq` approximation is a two-moment (Allen–Cunneen-style) approximation, not an
  exact result; it is used because the course teaches it and because it is accurate
  enough for this model.
* It describes one FCFS queue with a single service-time distribution; it does not model
  priority classes, so it cannot predict the Split or fast-priority effects directly.
* The service-time mixture treats order classes as independent draws; real orders arrive
  in bursts and correlate with time of day.
* All economic parameters (prices, wage, waiting cost) are assumptions.
* The archived AnyLogic runs and the Python engine have different horizons and parameter
  lineages; only direction-of-effect comparisons are meaningful across them.

> **中文**：解析层的局限在于两矩近似、只覆盖 FCFS 基线、服务时间独立同分布假设，
> 以及价格/工资/等待成本均为假设值；AnyLogic 存档只能做方向性对照。

---

## 11. v2 layer 1 — non-stationary demand

### 11.1 The piecewise-constant profile

v1 assumes one stationary Poisson rate λ. v2 replaces it with a piecewise-constant
multiplier m(t) ≥ 0 and a base rate λ₀:

```text
λ(t) = λ₀ · m(t),     t ∈ [0, T]
m̄ = (1/T) ∫₀ᵀ m(t) dt                       (daily mean multiplier)
```

Scenarios that quote a daily mean set `demand.normalize_daily_mean = 1`; the loader then
chooses λ₀ = λ_quoted / m̄, so the **daily mean demand is exactly λ_quoted** and only the
shape changes. Define the peak ratio

```text
P = max_t m(t) / m̄
```

Then the *time-average* load and the *peak-hour* load are separated by exactly that
factor:

```text
ρ̄     = λ_quoted · p̄ / m            (what the day averages, m = staff/clerks)
ρ_peak = P · ρ̄                        (what the peak hour feels)
```

Queueing delay is convex in load, so moving the same daily demand into a peak must raise
the tail. The engine demonstrates it at constant daily demand (campus_rush,
`results/v2/demand_study.json`):

| | Flat, same daily mean | Peak shape | Difference |
|---|---:|---:|---:|
| Daily utilisation | 60.6% | 54.9% | −5.7 pp |
| Peak-hour busy ratio | 66.0% | 77.7% | +11.7 pp |
| p95 time in system | 8.05 min | 11.77 min | +3.71 ± 0.37 min |
| Walk-away rate | 6.9% | 15.1% | +8.1 pp |
| Profit / hour | 296.0 | 239.3 | −56.9 ± 6.0 |

The daily utilisation *falls* even though the peak gets worse because abandoning
customers remove work from the system. This is Little's law applied to a loss system:
the realised flow is below offered demand, so `ρ = realised flow × p̄ / m` is not the
load the shop experiences during the peak. Raising the shape further (multiplier
`m(t)**factor`, daily mean fixed, from ×1.49 to ×1.85 peak-to-mean) adds another 1.89
minutes of p95, +11.5 points of walk-away and −72.3 /h of profit: the cost of peakiness
is J-shaped.

> **中文**：v2 用分段常数乘数把“日均需求”和“峰值形状”分开：λ(t)=λ₀·m(t)，当归一化日均时
> λ₀=λ_quoted/m̄。于是日均利用率 ρ̄=λ·p̄/m，峰值小时利用率 ρ_peak=P·ρ̄（P 为峰均比）。
> 由于排队延迟对负载是凸函数，同样的日均需求一旦集中到峰值，尾部必然变差。仿真实证：
> 日均利用率 60.6%→54.9%（因为流失减少工作量）、峰值繁忙度 66.0%→77.7%、p95 8.05→11.77 分钟、
> 流失率 6.9%→15.1%、利润 296.0→239.3。结论：**按峰值配置，不要按日均配置**。

### 11.2 Peak-factor sweep

The sweep raises the multiplier shape as `m(t)**factor` and re-normalises so the daily
mean is unchanged. It isolates the pure variability cost from any demand increase, and
it is the empirical counterpart of `ρ_peak = P·ρ̄` with P growing while `ρ̄` is fixed.

---

## 12. v2 layer 1 — service-time variability, patience and batching

### 12.1 Variability

Service times are drawn from a distribution with mean p and coefficient of variation
`CV_p = σ_p / p`. The engine supports `fixed` (v1), `exponential` (forced to CV = 1),
`lognormal` and `gamma` with explicit CVs per component. The standard two-moment
approximation (Section 5) already shows the mechanism:

```text
Tq ≈ (p/m) · U^[√(2(m+1)) − 1] · (CV_a² + CV_p²) / 2 / (1 − U)
```

Variability scales the whole queue term; its derivative with respect to `CV_p` grows as
`U → 1`, so the same CV change hurts much more at high load and shows up in the tail far
more than in the mean. v2 measures it directly: across fixed/exponential/lognormal
variants the p95 range is 4.62 min at λ = 1.0 and 6.71 min at λ = 1.2, while the mean LOS
range at λ = 1.2 is only 2.21 min; the p95 ratio at lognormal CV = 0.75 versus
deterministic is 1.25× at λ = 1.2.

### 12.2 Patience

Each customer draws a balking threshold `b` and a reneging threshold `r` from lognormal
distributions (mean, CV). At arrival the engine compares `b` with an estimate of the
expected wait

```text
Ŵ = n_in_system · p̄ / staff_on_duty
```

and the customer leaves immediately if `Ŵ > b`; otherwise, if service has not started
within `r`, the customer leaves at `r` (reneging). v2 uses **staff on duty** in the
denominator (not nominal headcount), which is the correct denominator once shifts exist.

Two consequences are visible in the data. First, with arrival-time balking active,
reneging almost never binds: the customer who would renege has usually balked already,
so the balk threshold decides who leaves (abandonment 29.3% at a 3-minute threshold
versus 3.2% at 12 minutes, λ = 1.2). Second, abandonment is a lost sale, not a queue:
`served = arrivals × (1 − abandonment)` and utilisation falls with it.

### 12.3 Group arrivals

A batch draw turns one arrival event into `n` customers. There are two conventions and
they answer different questions:

```text
E[size] = (1 − q)·1 + q · E[S]          (customer/event ratio)
fixed event rate:      λ_customers = λ_events · E[size]
fixed customer mean:   λ_events = λ_customers / E[size]
```

With the event rate fixed, batching is mostly a demand increase, because each event
brings several customers; with the daily customer mean fixed, only the burstiness
remains (walk-away 7.5% → 9.3% and profit 235.4 → 219.8 at q = 0.3). Burstiness is real
but second-order next to the peak shape.

> **中文**：服务时间变异通过 `(CV_a²+CV_p²)` 放大整个排队项，且在 U→1 时放大倍数更大，所以
> 它主要抬高尾部而非均值；引擎对 `exponential` 强制 CV=1。耐心机制方面，到达即评估等待的
> balking 会“吞掉”reneging（3 分钟阈值下流失 29.3%，12 分钟阈值下 3.2%），因为会 renege 的
> 顾客通常已经先 balk 了；v2 的等待估计分母改为**在班人力**。批量到达必须区分口径：固定到达
> 事件率时批量化主要是需求增加，固定日均顾客数后只剩突发性效应（流失 7.5%→9.3%，利润
> 235.4→219.8），量级明显小于峰型效应。

---

## 13. v2 layer 2 — the station network and bottleneck migration

### 13.1 Station and pool utilisation

With a network of stations `s` and staff roles `r`:

```text
ρ_s   = busy_minutes_s / (capacity_s · T)                      (station utilisation)
ρ_r   = Σ_{s ∈ skill(r)} busy_minutes_s / Σ_{windows of r} (end − start)   (labour pool)
```

The two denominators are different on purpose: a station is limited by equipment slots,
a role by paid shift minutes. v1's single number `U = λ p̄ / m` is the special case where
all work goes through one pool.

### 13.2 The bottleneck and its migration

The binding station is `argmax_s ρ_s`, and the capacity of a staged process is set by the
busiest station in the chain. Adding one unit of capacity at station `s` pays only while
the *system* is constrained by `s`; once `ρ_s` falls below the next resource, the marginal
station is idle. v2 makes this operational with a paired marginal profit:

```text
Δ(k) = Profit(k stations) − Profit(k − 1 stations)     (common random numbers)
critical capacity = min { k : Δ(k) ≤ 0 }
```

Empirically (tea stations 1–4, staff synced to stations, λ = 0.6/0.9/1.2):
tea utilisation falls from 84.2%/94.0%/99.5% at one station to 22.3%/33.6%/42.6% at four,
and the critical capacity is 3 at λ = 0.6 and 0.9, 4 at λ = 1.2. Beyond it the shared
barista pool and the order counter, not the tea station, decide the queue. The *station*
bottleneck never literally moves (tea stays the busiest station), but its *marginal
value* does — which is why the marginal-profit definition is the right one.

### 13.3 Skills, pooling and shifts

With two dedicated pools (cashier, barista) the waiting is the sum of two independent
queues; with one cross-trained pool it is a single queue with the same total work, which
is smaller by the pooling effect (the classic result that `M/M/1` with two half-loaded
servers beats two `M/M/1`s with one loaded server). The v2 skill experiment confirms it
at equal headcount and equal wage: generalists beat dedicated staff by +84.5 ± 5.1 /h,
while one-way cross-training into the under-loaded pool is worth +0.17 ± 0.22 /h — the
flexibility must be able to move in the direction the queue needs.

Shifts change the denominator of `ρ_r`: a break removes capacity from the window, so a
break placed near the peak raises peak-hour waiting even though the wage bill falls.
A mid-shift barista adds headcount but not station capacity; when the tea station is the
binding resource, the extra headcount cannot shorten the peak queue (measured
peak-hour Δ = +0.06 ± 0.08 min versus no shift).

> **中文**：站台利用率按设备容量计，人力池利用率按排班分钟计；v1 的单一 U 只是特例。瓶颈迁移
> 用“配对边际利润”定义：Δ(k)=Profit(k)−Profit(k−1)，临界容量为第一个 Δ≤0 的 k。茶站实验显示
> 茶站始终是最忙站台（1 站时 84–99%，4 站时 22–43%），但临界容量为 3/3/4（λ=0.6/0.9/1.2），
> 超过后真正决定排队的是共享吧台池与下单台。技能方面，同样人数与工资下“全员通才”比“专职分工”
> 高 +84.5±5.1 元/小时（池化收益），单向交叉培训几乎无效；班次方面，休息把容量从峰值移走，
> 中班吧台在茶站瓶颈时无法缩短峰值队列（+0.06±0.08 分钟）。

---

## 14. v2 layer 3 — inventory (s, S), fill rate and service level

### 14.1 Replenishment

Each ingredient is a sequence of FIFO lots with an optional expiry. The inventory
position is

```text
IP = on_hand + on_order
```

and an order of size `Q` (the scenario's `order_quantity`) is placed whenever `IP ≤ s`
(the reorder point) and nothing is already on order; it arrives after lead time `L`.
Consumption follows the recipes (BOM): a product's component requirements are
subtracted when the order is accepted.

### 14.2 Fill rate, stock-outs and service level

```text
fill_rate = (arrivals − stockout_losses) / arrivals
service_level(target) = P(no stock-out during the replenishment cycle)
```

The study reports both a realised fill rate and the stock-out count. Lead time enters
through the lead-time demand `D_L = λ_product · L`: with `s` fixed, a longer `L` means a
larger `D_L`, hence a higher probability that demand arrives before the delivery. The
measured fill rates are 100% at L = 30, 98.0% at 60, 80.4% at 120 and 71.6% at 240
minutes: the service threshold in the study is `L ≤ 60` minutes for 95% fill.

### 14.3 Shelf life and waste

A lot with shelf life `τ` that is not consumed within `τ` expires and is counted as
waste. For a perishable with replenishment quantity `Q` and daily consumption `d`, the
waste-free condition is roughly `Q / d ≤ τ`; once the order quantity exceeds the demand
over the shelf life, waste appears. The study's waste-free shelf-life threshold is 240
minutes — below it the same (s, S) setting starts to waste pearls, and above it the
reorder point, not the shelf life, is the binding constraint. Waste responds to shelf
life and order quantity, not to the reorder point alone.

### 14.4 Substitution

When a component is short, the stock-out policy either loses the sale or substitutes a
product the shop can still make (`mix → tea`, `ice → bread` in this study). The expected
gain is

```text
E[gain] = P(shortage) · λ_affected · E[price_target − price_substitute] · (1 − cost_adjustment)
```

and it is positive only when the shortage is in a component that has a substitute: with
ice short, routing mix orders to tea recovers +14.11 /h; with pearls short, all three
policies collapse onto the same lost sales, because no product avoids the pearl BOM.

> **中文**：库存位置 IP=在库+在途，当 IP≤s 且无在途时按 Q 补货，提前期 L 后到货；BOM 决定每个
> 产品的原料消耗。满足率 β=(到达−缺货)/到达，服务水平由补货周期内的缺货概率决定；提前期通过
> 提前期需求 D_L=λ·L 影响缺货概率（实测 L=30 时 100%、60 时 98.0%、120 时 80.4%、240 时 71.6%）。
> 保质期决定损耗下限：Q/d>τ 时开始出现浪费，本研究的“无浪费保质期阈值”为 240 分钟。替代策略只在
> “存在可替代产品”时有效：缺冰时 mix→tea 挽回 +14.11 元/小时，缺珍珠时三种策略都无差别。

---

## 15. v2 layer 4 — pricing elasticity, SLA and fairness

### 15.1 Constant-elasticity pricing

A peak window with multiplier `m` changes demand by

```text
D(m) = D₀ · m^ε,      ε < 0
Revenue(m) = p · m · D₀ · m^ε = p · D₀ · m^(1+ε)
```

so revenue keeps rising with `m` while `ε > −1`, and the profit maximum inside a tested
range is often at the boundary. The engine's profit also prices the waiting cost of
customers who stay, but it does **not** charge for customers who abandon, which biases
the optimum upward; the report therefore treats the profit-maximising multiplier as a
modelling artefact.

The decision-useful quantity is the **service-neutral multiplier**: the largest `m`
whose peak-hour p95 stays within the baseline band,

```text
m_sn = max { m : p95_peak(m) ≤ p95_peak(1) + δ }
```

For campus_rush at ε = −0.5 the study finds ×1.2: 97.9% of demand retained, peak p95
11.51 min, profit 318.45 /h (versus 240.07 /h at m = 1 under the study's pricing
configuration).

### 15.2 SLA compensation

An SLA with target `T_sla` and compensation `c` changes the objective by the expected
compensation:

```text
Attainment A = P(T ≤ T_sla)
E[compensation per hour] = c · λ · (1 − A)
```

Crucially the SLA does not enter the queue: `A` is fixed by the operations, so the SLA is
a transfer that makes the cost of a miss explicit. Measured attainments are 41.9%,
61.4% and 81.9% for 3-, 5- and 8-minute targets; the cheapest compensation that achieves
each is 38.38, 25.48 and 11.92 per hour respectively. No tested setting reaches 100%
attainment.

### 15.3 Fairness and the starvation cap

Jobs carry a priority; a starvation cap `Ω` escalates any job whose readiness time is more
than `Ω` minutes old to the top priority (the engine counts these escalations). For
customer classes `c`:

```text
fairness_gap      = max_c mean_LOS_c − min_c mean_LOS_c        (mean-based)
class_p95_spread  = max_c p95_c      − min_c p95_c             (tail-based)
```

The cap lowers every class's p95 and slightly narrows the tail spread, but it makes the
**mean** spread wider, because it equalises tails rather than averages:

| | No cap | Best tail cap (1.5 min) |
|---|---:|---:|
| Overall p95 | 9.99 min | 8.86 min |
| Class p95 spread | 2.27 min | 2.22 min |
| Mean fairness gap | 1.45 min | 1.78 min |
| Profit / hour | 268.7 | 263.6 |

This is why the v2 study records a flag (`mean_gap_widens_while_tail_gap_narrows = true`)
and the report describes the cap as tail protection rather than proof of a fairer
average. The cap is cheap (5.06 /h) and auditable (escalations per hour are recorded).

> **中文**：常弹性定价下 D(m)=D₀m^ε、Revenue=pD₀m^(1+ε)，在 ε>−1 时收入随加价单调上升，
> 因此利润最优常落在测试区间边界；又因为模型只对“留下来的顾客”计等待成本，利润最优会被高估，
> 所以真正可用的量是“服务中性乘数” m_sn（ε=−0.5 时为 ×1.2，保留 97.9% 需求）。SLA 只是转移
> 支付：达成率由运营决定（3/5/8 分钟目标分别 41.9%/61.4%/81.9%），补偿把失约成本显式化，但
> 不改变排队。公平约束用老化升级（starvation cap）保护尾部：它降低各客群 p95、类间 p95 极差
> 略降，但**均值型** fairness_gap 会上升（1.45→1.78 分钟）——因此文献/报告必须说明口径，
> 不能把“尾部改善”直接称为“更公平”。

---

## 16. v2 theory-to-test map

The v2 analytical claims are executable as well; the simulation is the referee where no
closed form exists (network of queues, time-varying arrivals, inventory + queueing).

| Claim | Analytical form | Evidence |
|---|---|---|
| Peak load scales with the peak ratio at fixed daily mean | `ρ_peak = P · ρ̄` | `demand_study.peak_vs_flat`: +11.7 pp peak busy, p95 ×1.46 |
| Variability hits the tail, not the mean | two-moment `Tq` in §5 | `demand_study.variability`: p95 range 4.62/6.71 min vs mean 2.21 min |
| Balking dominates reneging when both are active | `Ŵ = n·p̄/staff` | `demand_study.patience`: abandonment 29.3% vs 3.2%; reneging binds only without balking |
| Bottleneck migration | `ρ_s`, paired marginal profit | `network_study.bottleneck_migration`: critical capacity 3/3/4 |
| Pooling gain | single pooled queue vs two dedicated queues | `network_study.skill_matrix`: +84.5 ± 5.1 /h generalists |
| Fill rate shrinks with lead-time demand | `D_L = λL`, `β(L)` | `inventory_study.decision_summary.lead_time_effect`: 100% → 71.6% |
| Waste floor is set by shelf life, not reorder point | `Q/d ≤ τ` | `inventory_study.tradeoff`: waste-free shelf life 240 min |
| Substitution recovers revenue only with a substitute | expected-gain formula | `inventory_study`: +14.11 /h for ice shortage, 0 for pearls |
| Service-neutral pricing | `m^(1+ε)`, `m_sn` | `economics_study.pricing_optima`: ×1.2 at ε = −0.5 |
| SLA is a transfer, not a lever | `A = P(T ≤ T_sla)` | `economics_study.sla_summary.service_is_unchanged_by_sla = true` |
| Tail protection can widen the mean gap | `fairness_gap` vs `class_p95_spread` | `economics_study.fairness_summary`: 1.45 → 1.78 mean, 2.27 → 2.22 tail |
| Layer-off equivalence | v1 as the special case | `tests/test_v2_layers.py::test_baseline_flat_scenario_is_bit_exact_v1` and the report builder |

**Limitations of the v2 analytical layer.** There is no closed form for a time-varying
arrival process feeding a network of finite stations with skills and shifts; the layer
formulas above are bookkeeping identities (Little's law, utilisation, inventory
position), not predictive queueing approximations. For those mechanisms the simulation is
the model, and the report is careful to present differences as *measured* effects with
paired confidence intervals, not as analytical predictions. The inventory formulas ignore
the interaction between stock-outs and the queue (a stock-out removes a customer before
they queue); the fairness formula treats classes as fixed rather than as a function of
observed wait; and the pricing formula assumes a constant elasticity that the shop may not
have.

> **中文**：v2 的解析层主要是“记账恒等式”（Little 定律、利用率、库存位置、稀缺性定价），
> 真正的预测仍由仿真给出：带班次与技能的有限站台网络、时变到达、库存与排队的耦合都没有闭式解。
> 因此报告把 v2 的层间差异表述为“带配对置信区间的实测效应”，而不是解析预测；同时明确各公式的
> 适用边界（库存公式忽略缺货与排队的交互，公平公式把客群视为固定分组，定价公式假设常弹性）。

---

## References

* Course 5006 lecture material, Lecture 1 (flow metrics and Little's Law),
  Lecture 2 (process flow and capacity analysis), Lecture 3 (service operations and
  queueing), Lecture 4 (master production scheduling, MRP and capacity requirements).
* AnyLogic model archive and experiment ledger, preserved in
  [experiment_log.md](experiment_log.md) (archival, not re-runnable).
* Reproducible numbers: `src/bubble_tea_sim/` plus the commands in
  [reproducing.md](reproducing.md).
