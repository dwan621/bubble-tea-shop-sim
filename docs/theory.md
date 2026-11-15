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

## References

* Course 5006 lecture material, Lecture 1 (flow metrics and Little's Law),
  Lecture 2 (process flow and capacity analysis), Lecture 3 (service operations and
  queueing), Lecture 4 (master production scheduling, MRP and capacity requirements).
* AnyLogic model archive and experiment ledger, preserved in
  [experiment_log.md](experiment_log.md) (archival, not re-runnable).
* Reproducible numbers: `src/bubble_tea_sim/` plus the commands in
  [reproducing.md](reproducing.md).
