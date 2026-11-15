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
the legacy scripts. In a stable shop (demand below capacity) that is the usual
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
  one uniform draw for the order class. This mirrors the legacy scripts and keeps
  the random stream independent of behaviour mechanisms.
* Service times are fixed by configuration (no random draws), so dispatch order
  cannot influence randomness.
* Behaviour mechanisms (balking, reneging, dynamic priority) change the schedule
  but not the arrival stream. Two runs with the same seed always produce
  identical metrics.

## Validation strategy

1. **Golden anchors** — `tests/test_legacy_anchors.py` pins the engine to the
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

## Extension points

* **New behaviour rule**: add a field to `Policy`, apply it in
  `_handle_arrival` / `_dispatch` / `_handle_renege`, and add a directional test.
* **New metric**: add it in `Metrics` and `_build_metrics()`, then to
  `stats.flatten_metrics()` so sweeps pick it up automatically.
* **New study**: add a builder to `scenarios.py` and a CLI subcommand (or an
  `analysis/` script that imports the package).
* **New distribution**: service times are currently deterministic; a
  distribution hook belongs in `_create_jobs()` and must consume RNG in a
  documented order (update the determinism contract above).
