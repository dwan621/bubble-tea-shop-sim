# Scenario library

`data/scenarios/*.json` holds the **input data** of the v2 study: one file per
shop context. The loader is `bubble_tea_sim.library.load_scenario(name)`.

## Provenance discipline

Every file must carry a `provenance` block:

```json
"provenance": {
  "source": "where the numbers come from (course notes, industry range, literature, synthetic)",
  "method": "how they were chosen (assumption / benchmark midpoint / fitted / design-of-experiments)",
  "uncertainty": "low | medium | high",
  "notes": "anything a reader must know before trusting the scenario"
}
```

Rules:

1. **Never claim field data you do not have.** If a number is an assumption, say
   so. "Synthetic, anchored on the course assumptions" is a fine answer.
2. **Separate the layers.** A scenario may use only the layers it needs; missing
   keys mean "v1 behaviour for that layer".
3. **Keep the daily mean honest.** When `demand.normalize_daily_mean` is set, the
   loader rescales `arrival_rate` so that the *daily average* equals the quoted
   rate. Peak-vs-average comparisons then differ only in shape, not in total
   demand.
4. **Cite ranges, not pseudo-precision.** `2.0 min` with `uncertainty: high` is
   better than `1.97 min` invented to look measured.

## Schema

| Key | Meaning |
|---|---|
| `name`, `title`, `provenance` | identity + trust metadata |
| `base` | `workers`, `arrival_rate` (customers/min), `sim_minutes`, `warmup_minutes` |
| `mix`, `times`, `economics`, `policy` | v1 core parameters (optional overrides) |
| `demand.segments` | `[[start_minute, multiplier], ...]`, piecewise constant |
| `demand.normalize_daily_mean` | `1.0` = rescale rate so the daily mean stays as quoted |
| `batches` | `probability` and `sizes` (`[[size, weight], ...]`) |
| `classes` | customer segments: `name`, `weight`, optional `mix`, `patience`, `priority`, `delivery` |
| `variability` | `kind` (`fixed/exponential/lognormal/gamma`) and per-component CVs |
| `network` | `stations` (`name`, `capacity`, `skill`), `staff` (`roles`, `counts`, `skills`, `windows`, `breaks`), `routes` (`component → station`) |
| `inventory` | `ingredients` (stock, `reorder_point`, `order_quantity`, lead time, cost, shelf life) and `recipes` (product → ingredient quantities) |
| `pricing` | `peak_segments`, `peak_price_multiplier`, `elasticity` |
| `sla` | `target_minutes`, `compensation`, `fairness_cap_minutes` |

A file with none of the v2 layers reproduces the v1 model exactly; that is
intentional (see `baseline_flat.json`).
