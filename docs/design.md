# Engine design

This page explains how the simulation engine is put together, so contributors can
extend it without reverse-engineering the event loop.

## Data model

| Concept | Code | Meaning |
|---|---|---|
| Order class | `params.TEA / BREAD / ICE / MIX` | What the customer buys |
| Job | `engine.Job` | One uninterruptible block of clerk time (order + make) |
| Customer | `engine.Customer` | One visit; holds arrival, component completion and departure times |
| Metrics | `engine.Metrics` | Aggregated statistics for one replicate (LOS, util, money, abandonment) |
| Config | `params.SimConfig` | Workers, load, mix, service times, policy, economics |

A pure order is a single job. A mixed order becomes:

* synchronised delivery — one job of `order + tea + ice` (the customer waits for
  the tea and receives everything at once);
* split delivery — two jobs: `order + ice` (handed over immediately, priority 0
  by default) and `tea` (queued normally). The customer leaves when the tea is
  done. Total clerk-minutes are identical, which is why utilisation is invariant.

`ServiceTimes.for_kind()` builds that mapping; `Policy.mix_ice_priority` decides
whether the mixed-order ice component jumps immediately (`jump`), never (`fcfs`)
or only after it has waited `dynamic_priority_threshold` minutes (`dynamic`).

## Event loop

```text
schedule every Poisson arrival up front          # RNG stream independent of behaviour
while events remain:
    advance to the earliest event time
    process completions (free clerks, record component finish)
    process arrivals   (balk check, create jobs, schedule renege deadline)
    dispatch ready jobs to free clerks (priority, then FIFO)
    process renege deadlines (customers who never started service)
```

Dispatch is a simple greedy rule: at a moment when at least one clerk is free,
pick the ready job with the lowest effective priority (ties broken by creation
sequence, i.e. FIFO), and start it on the clerk that has been free the longest.
There is no preemption. This is exactly the scheduling rule of the original
course scripts, which is why the unified engine reproduces them bit-for-bit.

## Utilisation is a window ratio

`Metrics.util` is `busy clerk-minutes / (workers x sim_minutes)`, exactly as in
the original course scripts. In a stable shop (demand below capacity) that is the usual
utilisation and stays below 1. In an over-loaded configuration the backlog is
served after the 480-minute window, so the ratio can exceed 1: it is "work
accomplished per clerk-minute available in the window", not a capacity bound.
The 2-worker stress cases in the ledger show 100.8% for the same reason. Treat
values above ~95% as "overloaded, waiting dominates", not as a modelling error.

## Safety valve

The event loop stops if the next event lies beyond `10 x sim_minutes + 10,000`
minutes. This only triggers for deliberately absurd overloads; in that case the
customers still queued are *censored* (they have no departure time and are not
counted as served, balked or reneged). Normal studies stay far below the limit.

## Determinism contract
* Arrivals are generated before the event loop starts: `expovariate(rate)` then
  one uniform draw for the order class. This mirrors the original course scripts and keeps
  the random stream independent of behaviour mechanisms.
* Service times are fixed by configuration (no random draws), so dispatch order
  cannot influence randomness.
* Behaviour mechanisms (balking, reneging, dynamic priority) change the schedule
  but not the arrival stream. Two runs with the same seed always produce
  identical metrics.

## Validation strategy

1. **Golden anchors** — `tests/test_anchors.py` pins the engine to the
   numbers in `docs/experiment_log.md` (M2 mixed-order table, P-series
   fast-priority table) with tight tolerances. If the engine semantics drift, the
   tests fail loudly.
2. **Invariants** — flow conservation, non-negative timings, utilisation
   invariance across delivery policies, warm-up handling.
3. **Directional tests** — the study's headline statements (split helps at low
   load and hurts at high load; fast priority is a strong high-load lever) are
   executable assertions with paired 95% confidence intervals.
4. **Cross-model check** — `analysis/reproduce_anylogic_ledger.py` reimplements
   the AnyLogic E-series and reports deviations against the archived figures
   (see `docs/experiments.md` for the honest caveats).

## mechanism layers

the four-layer model keeps the baseline event loop and adds four opt-in layers. A configuration that uses
none of them takes the `baseline_compat` path and reproduces baseline bit-for-bit; the
regression test pins `data/scenarios/baseline_flat.json` to the original anchors.

| Layer | What it adds | Code | Tests |
|---|---|---|---|
| 1. Demand | intra-day demand curve (piecewise constant), batch arrivals, customer classes with own mix and patience distributions, service-time variability | `data_spec.DemandProfile/BatchSpec/PatienceSpec/CustomerClass/MixSpec/ServiceVariability` | `tests/test_layers.py` |
| 2. Supply network | stations with finite capacity, staff roles/skills, shift windows, breaks, staged order -> make -> hand-over, routing | `data_spec.StationSpec/StaffSpec/ShiftWindow/NetworkSpec` | same |
| 3. Inventory / BOM | recipes, FIFO lots, (s, S) replenishment with lead time, shelf life, waste, lost-sale or substitution | `data_spec.Ingredient/Recipe/InventorySpec` | same |
| 4. Economics / fairness | time-of-day pricing with demand elasticity, SLA compensation, starvation cap (aging) | `data_spec.PricingSpec/SlaSpec`, `params.Policy.starvation_cap` | same |

Scenarios are data, not code: `data/scenarios/*.json` with a `provenance` block
(source / method / uncertainty), loaded by `bubble_tea_sim.library` and validated
in `tests/test_layers.py`.

## Resource model (layer configurations)

A configuration with a `network` uses an event-driven scheduler instead of
the baseline future-reservation rule:

* **Staff units** carry a role, a skill set (`"all"` means any), and availability
  windows (empty = all day). A break splits one unit's window into two spans; a
  second barista joining mid-day is simply another window.
* **Stations** have a capacity and an optional required skill. Jobs routed to a
  station occupy one slot for their whole duration.
* **Staged processing**: when stations exist, the order step (cashier) and the
  make step (barista/station) are separate jobs. The make jobs are created when
  the order finishes, so order-queue waiting and production-queue waiting are
  distinguishable. Synchronised mixed orders chain tea -> ice; split orders
  release the ice and tea jobs in parallel.
* **Dispatch rule**: at every event (arrival, completion, restock, shift
  boundary) the scheduler starts ready jobs in `(effective priority, sequence)`
  order as long as both a skilled staff unit and a station slot are free and the
  job finishes inside the staff member's window. No preemption, no future
  reservation.

## Inventory model

Ingredients are FIFO lots with an expiry time. Consumption happens when the order
is accepted (BOM reservation). With (s, S) continuous review, an order is placed
when the inventory position (stock + on order) drops to the reorder point and
arrives after the lead time; purchases (including the opening stock) are costed
at `unit_cost`. Expired lots are recorded as waste. Stock-out either loses the
sale (`"lose"`) or serves a substitute product (`"substitute"`).

## Pricing, SLA and fairness

* Price multiplier windows raise the ticket price inside peak windows; demand
  inside a window is scaled by `price_multiplier ** elasticity`.
* The SLA records the share of customers whose LOS exceeds `target_minutes` and
  charges `compensation` for each of them.
* The fairness cap ages any job that has waited longer than
  `Policy.starvation_cap` to the top priority class. `Metrics.fairness_gap` is
  the spread of mean LOS across customer classes.

## Determinism contract (layer configurations)

* The arrival stream is generated up front. With a demand curve the engine uses
  thinning: candidates arrive at `lambda_max`, and each candidate is accepted
  with probability `rate(t) / lambda_max`. Batch size, customer class and the
  per-customer patience thresholds are drawn in a fixed order for every accepted
  arrival.
* Service durations are drawn when the job is created, in component order.
  Behaviour (balking/reneging/priority) changes the schedule but never the
  random stream, so two runs with the same seed are identical.
* **Balking estimate**: a customer decides from `in_system * p_bar / staff`,
  where `staff` counts only the units on shift at that moment (shift windows and
  breaks included). A late-joining barista therefore does not make the queue look
  shorter than it is before they arrive.
* Runs that leave customers in the shop at closing time mark them `closed`
  (`Metrics.stranded`) instead of dropping them; flow conservation holds.

## Validation strategy (layer configurations)

1. **Degenerate equivalence** — `baseline_flat` must equal the baseline anchors
   exactly; tests compare full metric dictionaries.
2. **Invariants** — flow conservation on every scenario file, non-negative
   timings, utilisation invariance across delivery policies, staged jobs always
   have an order completion before production.
3. **Directional tests** — variability increases the tail, a cap ages the low
   priority queue, a stock-out loses sales, over-ordering a perishable wastes
   it, pricing with negative elasticity lowers peak demand.
4. **Internal consistency only** — these are not field validations. The
   scenario provenance block is the honest boundary: synthetic assumptions with
   explicit uncertainty.

## Extension points

* **New behaviour rule**: add a field to `Policy`, apply it in
  `_handle_arrival` / `_dispatch` / `_handle_renege`, and add a directional test.
* **New metric**: add it in `Metrics` and `_build_metrics()`, then to
  `stats.flatten_metrics()` so sweeps pick it up automatically.
* **New scenario**: add a JSON file under `data/scenarios/` with a provenance
  block; `tests/test_layers.py` automatically runs it.
* **New station/route**: add a `StationSpec` and a route in the scenario file;
  no engine code is needed.
* **New layer**: prefer a new `data_spec` dataclass plus a `SimConfig` field, so
  the baseline path stays untouched and `baseline_compat` keeps its guarantee.

