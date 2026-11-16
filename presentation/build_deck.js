/**
 * Build the presentation deck for the bubble-tea shop study.
 *
 * Run: node presentation/build_deck.js
 * Output: presentation/bubble-tea-shop-simulation.pptx
 */
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const data = require("./data.json");
const ASSETS = path.join(__dirname, "assets");
// DECK_OUT lets a build go to a scratch path when the shipped file is open in
// another application; the default target is the deck that ships.
const OUT = process.env.DECK_OUT || path.join(__dirname, "bubble-tea-shop-simulation.pptx");

const W = 13.333;
const H = 7.5;

const C = {
  ink: "0F172A",
  ink2: "1E293B",
  ink3: "334155",
  teal: "0D9488",
  tealDark: "0F766E",
  mint: "ECFDF5",
  mint2: "CCFBF1",
  amber: "B45309",
  amberLight: "FEF3C7",
  slate: "64748B",
  slateLight: "94A3B8",
  line: "E2E8F0",
  bg: "F6F7F9",
  white: "FFFFFF",
  paper: "FFFFFF",
};

const FONT = "Arial";
const FONT_NUM = "Georgia";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "SYE5006 group";
pres.company = "SYE5006";
pres.subject = "Bubble-tea shop simulation: four layers, one engine";
pres.title = data.meta.title;
pres.lang = "en-US";

// ---------------------------------------------------------------- helpers
function pngSize(file) {
  const buffer = fs.readFileSync(file);
  return { w: buffer.readUInt32BE(16), h: buffer.readUInt32BE(20) };
}

function addText(slide, text, opts) {
  const options = Object.assign(
    {
      fontFace: FONT,
      fontSize: 14,
      color: C.ink,
      margin: 0,
      valign: "top",
      breakLine: false,
    },
    opts || {}
  );
  return slide.addText(text, options);
}

function addRich(slide, runs, opts) {
  return slide.addText(runs, Object.assign({ fontFace: FONT, margin: 0 }, opts || {}));
}

function bg(slide, color) {
  slide.background = { color };
}

function footer(slide, number, label) {
  addText(slide, label || "Bubble-tea shop simulation · scheduling, inventory and pricing across four layers", {
    x: 0.6,
    y: H - 0.45,
    w: 9.4,
    h: 0.25,
    fontSize: 9,
    color: C.slateLight,
  });
  addText(slide, String(number).padStart(2, "0"), {
    x: W - 1.0,
    y: H - 0.45,
    w: 0.4,
    h: 0.25,
    fontSize: 9,
    color: C.slateLight,
    align: "right",
  });
}

function kicker(slide, text, color) {
  addText(slide, text, {
    x: 0.6,
    y: 0.42,
    w: 9,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: color || C.tealDark,
    charSpacing: 2,
  });
}

function titleBlock(slide, title, sub, dark) {
  addText(slide, title, {
    x: 0.6,
    y: 0.78,
    w: 12.1,
    h: 0.62,
    fontSize: 28,
    bold: true,
    color: dark ? C.white : C.ink,
    fit: "shrink",
  });
  if (sub) {
    addText(slide, sub, {
      x: 0.6,
      y: 1.42,
      w: 12.1,
      h: 0.3,
      fontSize: 11,
      color: dark ? C.slateLight : C.slate,
      fit: "shrink",
    });
  }
}

function rule(slide, x, y, w, color) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x,
    y,
    w,
    h: 0.03,
    fill: { color: color || C.line },
    line: { color: color || C.line, width: 0 },
  });
}

function card(slide, x, y, w, h, opts) {
  const o = opts || {};
  slide.addShape(pres.shapes.RECTANGLE, {
    x,
    y,
    w,
    h,
    fill: { color: o.fill || C.paper },
    line: { color: o.line || C.line, width: o.lineWidth === undefined ? 0.75 : o.lineWidth },
    shadow: o.shadow
      ? { type: "outer", color: "000000", blur: 10, offset: 3, angle: 135, opacity: 0.08 }
      : undefined,
  });
  if (o.bar) {
    slide.addShape(pres.shapes.RECTANGLE, {
      x,
      y,
      w: 0.07,
      h,
      fill: { color: o.bar },
      line: { color: o.bar, width: 0 },
    });
  }
}

function stat(slide, x, y, w, value, unit, label, opts) {
  const o = opts || {};
  const accent = o.accent || C.teal;
  card(slide, x, y, w, o.h || 1.55, { fill: o.fill || C.paper, bar: accent, shadow: true });
  addRich(
    slide,
    [
      { text: value, options: { fontFace: FONT_NUM, fontSize: o.size || 30, bold: true, color: o.dark ? C.white : C.ink } },
      { text: unit || "", options: { fontFace: FONT, fontSize: 12, color: C.slate } },
    ],
    { x: x + 0.25, y: y + 0.22, w: w - 0.4, h: 0.55 }
  );
  addText(slide, label, {
    x: x + 0.25,
    y: y + 0.82,
    w: w - 0.4,
    h: 0.5,
    fontSize: 10.5,
    color: C.slate,
    fit: "shrink",
  });
}

function addImageFit(slide, file, x, y, w, h) {
  const size = pngSize(file);
  const ratio = Math.min(w / size.w, h / size.h);
  const nw = size.w * ratio;
  const nh = size.h * ratio;
  const nx = x + (w - nw) / 2;
  const ny = y + (h - nh) / 2;
  slide.addImage({ path: file, x: nx, y: ny, w: nw, h: nh });
  return { x: nx, y: ny, w: nw, h: nh };
}

function framedImage(slide, file, x, y, w, h, opts) {
  const o = opts || {};
  card(slide, x, y, w, h, { fill: o.fill || C.white, line: C.line, shadow: true });
  addImageFit(slide, file, x + 0.12, y + 0.12, w - 0.24, h - (o.caption ? 0.45 : 0.24));
  if (o.caption) {
    addText(slide, o.caption, {
      x: x + 0.2,
      y: y + h - 0.36,
      w: w - 0.4,
      h: 0.22,
      fontSize: 9,
      color: C.slate,
      fit: "shrink",
    });
  }
}

function notes(slide, text) {
  slide.addNotes(text);
}

const fmt = (value, digits) => Number(value).toFixed(digits === undefined ? 1 : digits);

// ---------------------------------------------------------------- slide 1
function slideTitle() {
  const slide = pres.addSlide();
  bg(slide, C.ink);

  addText(slide, "SYE5006 · COURSE PROJECT PRESENTATION", {
    x: 0.75,
    y: 0.7,
    w: 6.5,
    h: 0.3,
    fontSize: 12,
    bold: true,
    color: C.teal,
    charSpacing: 2,
  });

  addText(slide, "Bubble-tea shop simulation", {
    x: 0.72,
    y: 1.55,
    w: 7.9,
    h: 0.8,
    fontSize: 34,
    bold: true,
    color: C.white,
  });
  addText(slide, "Scheduling, inventory and pricing across four layers", {
    x: 0.75,
    y: 2.45,
    w: 7.9,
    h: 0.45,
    fontSize: 18,
    color: C.mint2,
  });
  addText(slide, "Demand · network · inventory · economics", {
    x: 0.75,
    y: 3.05,
    w: 7.6,
    h: 0.35,
    fontSize: 12.5,
    color: C.slateLight,
  });

  rule(slide, 0.75, 3.6, 3.2, C.teal);

  addText(slide, "16 synthetic scenarios · 100 replications per cell (60 in the overloaded region)", {
    x: 0.75,
    y: 3.85,
    w: 7.9,
    h: 0.3,
    fontSize: 10,
    color: C.slateLight,
  });
  addText(slide, "Common random numbers · 69 tests · fully reproducible", {
    x: 0.75,
    y: 4.18,
    w: 7.9,
    h: 0.3,
    fontSize: 10,
    color: C.slateLight,
  });

  addText(slide, "Six-person team · November 2026", {
    x: 0.75,
    y: 5.4,
    w: 6,
    h: 0.3,
    fontSize: 12,
    color: C.white,
  });
  addText(slide, "Report  docs/index.html   ·   Demo  demo/index.html   ·   Code  github.com/dwan621/bubble-tea-shop-sim", {
    x: 0.75,
    y: 5.78,
    w: 8.2,
    h: 0.3,
    fontSize: 9,
    color: C.slateLight,
    fit: "shrink",
  });

  const layers = [
    ["01", "Demand", "Peak shape, patience, variability"],
    ["02", "Network", "Stations, skills, shifts"],
    ["03", "Inventory", "BOM, (s,S), shelf life"],
    ["04", "Economics", "Pricing, SLA, fairness"],
  ];
  layers.forEach((layer, index) => {
    const y = 1.45 + index * 1.28;
    card(slide, 9.0, y, 3.6, 1.05, { fill: C.ink2, line: C.ink3, bar: index % 2 ? C.amber : C.teal });
    addText(slide, layer[0], {
      x: 9.25,
      y: y + 0.17,
      w: 0.6,
      h: 0.3,
      fontFace: FONT_NUM,
      fontSize: 14,
      bold: true,
      color: index % 2 ? C.amber : C.teal,
    });
    addText(slide, layer[1], {
      x: 9.85,
      y: y + 0.1,
      w: 2.4,
      h: 0.4,
      fontSize: 16,
      bold: true,
      color: C.white,
      fit: "shrink",
    });
    addText(slide, layer[2], {
      x: 9.85,
      y: y + 0.55,
      w: 2.55,
      h: 0.3,
      fontSize: 8.5,
      color: C.slateLight,
      fit: "shrink",
    });
  });

  notes(
    slide,
    "Opening (about 30 seconds): good morning everyone, we are Group 6. We study a small shop that sells bubble tea, bread and ice cream at the same time: when demand peaks, when staff have different skills and the equipment has a bottleneck, when ingredients spoil, and when waiting can be turned into money, how should scheduling and pricing be decided? Today one simulation engine answers four layers of questions, and every result can be reproduced."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 2
function slideQuestions() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "02 / THREE QUESTIONS");
  titleBlock(slide, "Three questions, one engine", "Three operational decisions, one decision model");

  const items = [
    {
      n: "01",
      q: "Hand over the ice cream first, or the whole order together?",
      a: "Almost free at low load; it flips near 80% utilisation",
      stat: `λ* = ${fmt(data.baseline.breakeven_lambda, 3)} / min  ·  ρ* = ${fmt(data.baseline.breakeven_util * 100, 1)}%`,
      foot: "Split delivery moves waiting from mixed orders to the main queue",
    },
    {
      n: "02",
      q: "Should bread and ice cream jump the queue?",
      a: "A stronger lever, but it depends on where the bottleneck is",
      stat: `Tea bottleneck +${fmt(data.strategy.tea_fast.diff, 2)}/h  ·  Ice cream +${fmt(data.strategy.ice_fast.diff, 2)}/h`,
      foot: "A fast lane pays only when its own station has slack",
    },
    {
      n: "03",
      q: "Waiting, promises and fairness: what are they worth?",
      a: "What is decidable: a service-neutral markup plus tail protection",
      stat: `Price ×${fmt(data.pricing.service_neutral, 1)} (ε = −0.5)  ·  97.9% of demand kept`,
      foot: "The fairness cap buys −11% p95 for 5.1/h; an SLA is a transfer",
    },
  ];

  items.forEach((item, index) => {
    const x = 0.6 + index * 4.12;
    card(slide, x, 2.0, 3.8, 4.25, { fill: C.white, bar: index === 1 ? C.amber : C.teal, shadow: true });
    addText(slide, item.n, {
      x: x + 0.3,
      y: 2.2,
      w: 1.2,
      h: 0.5,
      fontFace: FONT_NUM,
      fontSize: 26,
      bold: true,
      color: index === 1 ? C.amber : C.teal,
    });
    addText(slide, item.q, {
      x: x + 0.3,
      y: 2.95,
      w: 3.2,
      h: 1.05,
      fontSize: 15,
      bold: true,
      color: C.ink,
      fit: "shrink",
    });
    addText(slide, item.a, {
      x: x + 0.3,
      y: 4.2,
      w: 3.2,
      h: 0.8,
      fontSize: 12,
      color: C.ink3,
      fit: "shrink",
    });
    addText(slide, item.stat, {
      x: x + 0.3,
      y: 5.2,
      w: 3.2,
      h: 0.55,
      fontSize: 10.5,
      bold: true,
      color: C.tealDark,
      fit: "shrink",
    });
    addText(slide, item.foot, {
      x: x + 0.3,
      y: 5.78,
      w: 3.2,
      h: 0.4,
      fontSize: 9,
      color: C.slate,
      fit: "shrink",
    });
  });

  addText(slide, "All three answers come from one discrete-event engine; first the model, then the evidence.", {
    x: 0.6,
    y: 6.5,
    w: 12,
    h: 0.35,
    fontSize: 11,
    color: C.slate,
    fit: "shrink",
  });

  notes(
    slide,
    "Three questions (about 1 minute): first, should a mixed order be handed over in parts — almost free at low load, but it reverses around 80% utilisation. Second, is fast-item priority worth it — it is a stronger lever than splitting, but its value depends on whether the bottleneck is the tea station or the ice-cream machine. Third, how should waiting be priced and how should SLA and fairness be traded off — what is decidable is the service-neutral markup range. Next we look at the model and the experiment design."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 3
function slideModel() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "03 / MODEL");
  titleBlock(slide, "One clerk pool, four order classes", "One cross-trained clerk pool, four order classes");

  const steps = [
    ["01", "Arrive", "Poisson arrivals; intraday peak shape, batch arrivals, customer segments"],
    ["02", "Order + make", "Shared clerk pool; ordering takes 0.5 min, making uses the same staff"],
    ["03", "Three products + mixed", "Tea 2.0 min · bread 10 s · ice cream 20 s"],
    ["04", "Hand over + leave", "Synchronous or split; waiting is converted into cost"],
  ];
  steps.forEach((step, index) => {
    const y = 2.05 + index * 1.12;
    addText(slide, step[0], {
      x: 0.6,
      y: y + 0.08,
      w: 0.6,
      h: 0.4,
      fontFace: FONT_NUM,
      fontSize: 15,
      bold: true,
      color: C.teal,
    });
    card(slide, 1.25, y, 5.35, 0.92, { fill: C.white, line: C.line, bar: C.teal });
    addText(slide, step[1], {
      x: 1.5,
      y: y + 0.12,
      w: 3.2,
      h: 0.3,
      fontSize: 13,
      bold: true,
      color: C.ink,
      fit: "shrink",
    });
    addText(slide, step[2], {
      x: 1.5,
      y: y + 0.46,
      w: 4.9,
      h: 0.35,
      fontSize: 9.5,
      color: C.slate,
      fit: "shrink",
    });
    if (index < steps.length - 1) {
      slide.addShape(pres.shapes.LINE, {
        x: 3.9,
        y: y + 0.95,
        w: 0,
        h: 0.17,
        line: { color: C.slateLight, width: 1 },
      });
    }
  });

  addText(slide, "Key assumptions (all recorded explicitly in data/scenarios/*.json)", {
    x: 7.1,
    y: 1.95,
    w: 5.6,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.slate,
    fit: "shrink",
  });

  const rows = [
    ["Staff", "3 people, cross-trained across categories"],
    ["Order mix", "Tea 55% / bread 20% / ice cream 5% / mixed 20%"],
    ["Service time", "Order 0.5; tea 2.0; bread 0.167; ice cream 0.333 min"],
    ["Price", "8 / 6 / 2 / 10 CNY"],
    ["Labour + waiting", "25 CNY per person-hour; 0.5 CNY per customer-minute"],
  ];
  slide.addTable(
    rows.map((row, index) => [
      { text: row[0], options: { bold: true, color: C.ink, fill: { color: index % 2 ? C.white : C.bg } } },
      { text: row[1], options: { color: C.ink3, fill: { color: index % 2 ? C.white : C.bg } } },
    ]),
    {
      x: 7.1,
      y: 2.35,
      w: 5.6,
      colW: [1.35, 4.25],
      rowH: 0.72,
      fontFace: FONT,
      fontSize: 9,
      valign: "middle",
      border: { type: "solid", color: C.line, pt: 0.75 },
      margin: 0.06,
    }
  );

  card(slide, 7.1, 6.15, 5.6, 0.62, { fill: C.mint, line: C.mint2 });
  addText(slide, "Core scope: with total workload fixed, scheduling changes who waits, not capacity.", {
    x: 7.3,
    y: 6.27,
    w: 5.2,
    h: 0.4,
    fontSize: 9.5,
    bold: true,
    color: C.tealDark,
    fit: "shrink",
  });

  notes(
    slide,
    "Model (about 1 minute): customers arrive as a Poisson process with four order classes; one clerk both takes the order and makes the drink, so the shared clerk pool is the bottleneck. Tea takes 2 minutes, bread 10 seconds, ice cream 20 seconds, and a mixed order is tea plus ice cream. Prices, wages and waiting costs are all written explicitly into the scenario files, so every assumption is traceable. The key scope statement is that splitting or synchronising does not change total workload, it only changes who waits."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 4
function slideDesign() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "04 / EXPERIMENT DESIGN");
  titleBlock(slide, "16 scenarios × 100 replications × paired runs", "A scenario library, common random numbers and a validation contract");

  const groups = [
    ["Campus / downtown", "campus_rush · cbd_commute"],
    ["Mall / extreme demand", "mall_weekend · exam_week · rainy_delivery"],
    ["Small / large shop", "tiny_two_staff · flagship_five_staff"],
    ["Station bottlenecks", "network_tea_bottleneck · ice_cream_bottleneck · bread_counter_bottleneck"],
    ["Inventory", "inventory_lean · inventory_generous"],
    ["Pricing / SLA", "peak_pricing · strict_sla_fairness"],
    ["Late night / baseline", "late_night_study · baseline_flat"],
    ["Scenario library", "16 JSON files, each with source / method / uncertainty"],
  ];

  groups.forEach((group, index) => {
    const col = index % 2;
    const row = Math.floor(index / 2);
    const x = 0.6 + col * 4.35;
    const y = 2.0 + row * 1.12;
    card(slide, x, y, 4.1, 0.94, { fill: C.white, line: C.line, bar: col ? C.amber : C.teal });
    addText(slide, group[0], {
      x: x + 0.22,
      y: y + 0.13,
      w: 3.6,
      h: 0.3,
      fontSize: 12,
      bold: true,
      color: C.ink,
      fit: "shrink",
    });
    addText(slide, group[1], {
      x: x + 0.22,
      y: y + 0.47,
      w: 3.7,
      h: 0.36,
      fontSize: 8.5,
      color: C.slate,
      fit: "shrink",
    });
  });

  const methods = [
    ["Auditable provenance", "Every scenario carries source / method / uncertainty; none of it is passed off as measured shop data", "16 / 16 scenarios sourced"],
    ["Statistical protocol", "Paired comparison on common random numbers; 95% confidence intervals; 100 replications (60 in overload)", "200k+ simulated runs"],
    ["Contract checks", `${data.meta.tests} tests; 16/16 scenarios conserve flow; with every new layer off the model matches the course model bit for bit`, "new layers off = course model"],
  ];
  methods.forEach((method, index) => {
    const y = 2.0 + index * 1.55;
    card(slide, 9.15, y, 3.55, 1.32, { fill: C.mint, line: C.mint2 });
    addText(slide, method[0], {
      x: 9.35,
      y: y + 0.13,
      w: 3.1,
      h: 0.3,
      fontSize: 12,
      bold: true,
      color: C.tealDark,
      fit: "shrink",
    });
    addText(slide, method[1], {
      x: 9.35,
      y: y + 0.45,
      w: 3.1,
      h: 0.58,
      fontSize: 8.4,
      color: C.ink3,
      fit: "shrink",
    });
    addText(slide, method[2], {
      x: 9.35,
      y: y + 1.03,
      w: 3.1,
      h: 0.22,
      fontSize: 7.8,
      bold: true,
      color: C.teal,
      fit: "shrink",
    });
  });

  notes(
    slide,
    "Experiment design (about 1 minute): we did not run a single configuration; we built a library of 16 scenarios covering campus, downtown, mall, extreme demand, small and large shops, three station bottlenecks, inventory, pricing and SLA. Each scenario carries its source and its uncertainty. For the statistics we compare paired runs on common random numbers and report 95% confidence intervals. The validation contract is 69 tests, flow conservation on all 16 scenarios, and a bit-for-bit match with the course model when every new layer is switched off."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 5
function slidePeak() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "05 / DEMAND");
  titleBlock(slide, "Peak: the daily average lies", "Same daily mean, very different peak: the average hides the cost");

  stat(slide, 0.6, 1.95, 3.7, "+" + fmt(data.peak.p95_peak_abs - data.peak.p95_flat_abs, 2), " min", "p95 wait (peak shape vs flat)", { accent: C.amber, h: 1.4 });
  stat(slide, 0.6, 3.5, 3.7, fmt(data.peak.balk_peak * 100, 1) + "%", "", `Balk rate (flat ${fmt(data.peak.balk_flat * 100, 1)}%)`, { accent: C.amber, h: 1.4 });
  stat(slide, 0.6, 5.05, 3.7, fmt(data.peak.profit_flat - data.peak.profit_peak, 1), " /h", `Profit gap (flat ${fmt(data.peak.profit_flat, 1)} → peak ${fmt(data.peak.profit_peak, 1)})`, { accent: C.amber, h: 1.4 });

  card(slide, 4.75, 1.95, 8.0, 4.55, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "Busy ratio by hour", {
    x: 5.0,
    y: 2.08,
    w: 6.0,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.ink,
  });
  nativeChart(
    slide,
    pres.charts.LINE,
    [
      { name: "peak shape", labels: data.charts.hourly.labels, values: data.charts.hourly.peak },
      { name: "flat, same daily mean", labels: data.charts.hourly.labels, values: data.charts.hourly.flat },
    ],
    {
      x: 4.95,
      y: 2.42,
      w: 7.6,
      h: 3.75,
      showLegend: true,
      legendPos: "b",
      lineSize: 2.5,
      chartColors: [C.amber, C.teal],
      valAxisLabelFormatCode: "0%",
      valAxisMinVal: 0,
      valAxisMaxVal: 0.9,
    }
  );
  addText(slide, "Same daily arrivals, only the shape changes: the lunch and evening peaks are clearly higher, yet the daily utilisation is lower.", {
    x: 4.95,
    y: 6.22,
    w: 7.6,
    h: 0.25,
    fontSize: 9,
    color: C.slate,
    fit: "shrink",
  });
  addText(slide, "Conclusion: staff to the peak, not to the daily average; the peak shape is itself a cost line.", {
    x: 0.6,
    y: 6.65,
    w: 12.2,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.tealDark,
    fit: "shrink",
  });

  notes(
    slide,
    "Demand-side result (about 1 minute): with an identical daily mean, squeezing demand into a peak shape alone adds 3.7 minutes to p95 waiting, raises the balk rate from 6.9% to 15.1% and cuts profit by about 57 CNY per hour. Note that the daily utilisation actually falls from 60.6% to 54.9%, because the customers who balk take their work away with them. So staffing on the daily utilisation systematically understates peak risk."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 6
function slideVariability() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "06 / DEMAND");
  titleBlock(slide, "Variability and patience: the hidden tail", "Variability and patience move the tail, not the mean");

  card(slide, 0.6, 1.95, 6.0, 4.05, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "Service-time variability: p95 (λ = 1.2)", {
    x: 0.85,
    y: 2.08,
    w: 5.5,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.ink,
  });
  nativeChart(
    slide,
    pres.charts.BAR,
    [{ name: "p95 / min", labels: data.charts.variability.labels, values: data.charts.variability.p95 }],
    {
      x: 0.75,
      y: 2.45,
      w: 5.7,
      h: 3.4,
      barDir: "col",
      chartColors: [C.amber],
      showValue: true,
      dataLabelPosition: "outEnd",
      dataLabelFormatCode: "0.0",
      valAxisMinVal: 0,
    }
  );

  card(slide, 6.85, 1.95, 5.85, 4.05, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "Customer patience: balk rate (λ = 1.2)", {
    x: 7.1,
    y: 2.08,
    w: 5.35,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.ink,
  });
  nativeChart(
    slide,
    pres.charts.BAR,
    [{ name: "balk rate", labels: data.charts.patience.labels, values: data.charts.patience.abandon }],
    {
      x: 7.0,
      y: 2.45,
      w: 5.55,
      h: 3.4,
      barDir: "col",
      chartColors: [C.teal],
      showValue: true,
      dataLabelPosition: "outEnd",
      dataLabelFormatCode: "0%",
      valAxisMinVal: 0,
      valAxisLabelFormatCode: "0%",
    }
  );

  card(slide, 0.6, 6.15, 6.0, 0.85, { fill: C.white, line: C.line, bar: C.amber });
  addText(slide, `Variability dominates the tail: 8.6 → ${fmt(data.charts.variability.p95[4], 1)} min at CV 0.75 (+25%)`, {
    x: 0.82,
    y: 6.27,
    w: 5.55,
    h: 0.3,
    fontSize: 10,
    bold: true,
    color: C.ink,
    fit: "shrink",
  });
  addText(slide, `The exponential (CV = 1) pushes it to ${fmt(data.charts.variability.p95[1], 1)} min; the mean barely moves.`, {
    x: 0.82,
    y: 6.57,
    w: 5.55,
    h: 0.3,
    fontSize: 9.5,
    color: C.slate,
    fit: "shrink",
  });
  card(slide, 6.85, 6.15, 5.85, 0.85, { fill: C.white, line: C.line, bar: C.teal });
  addText(slide, `Patience is a demand-side lever: balk 3 min → ${fmt(data.charts.patience.abandon[0] * 100, 1)}% lost; 12 min → ${fmt(data.charts.patience.abandon[3] * 100, 1)}%.`, {
    x: 7.07,
    y: 6.27,
    w: 5.4,
    h: 0.3,
    fontSize: 10,
    bold: true,
    color: C.ink,
    fit: "shrink",
  });
  addText(slide, "Under arrive-and-assess waiting, reneging rarely triggers at all.", {
    x: 7.07,
    y: 6.57,
    w: 5.4,
    h: 0.3,
    fontSize: 9.5,
    color: C.slate,
    fit: "shrink",
  });

  notes(
    slide,
    "Variability and patience (about 1 minute): the left chart is service-time variability. With fixed service times the p95 is 8.6 minutes, the lognormal CV 0.75 case reaches 10.8 minutes and the exponential (CV = 1) reaches 15.3 minutes, while the mean barely moves — so judging experience by average waiting understates tail risk. The right chart is customer patience: relaxing the balk threshold from 3 minutes to 12 minutes cuts the lost share from 29.3% to 3.2%. Under arrive-and-assess waiting, reneging almost never triggers; balking drives the loss."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 7
function slideBottleneck() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "07 / SUPPLY SIDE");
  titleBlock(slide, "The bottleneck migrates", "The bottleneck is a property of the shop, not of the equipment list");

  card(slide, 0.6, 1.95, 7.15, 4.6, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "Tea-station capacity (baristas synced) and p95 waiting", {
    x: 0.85,
    y: 2.08,
    w: 6.4,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.ink,
    fit: "shrink",
  });
  nativeChart(
    slide,
    pres.charts.LINE,
    data.charts.tea_capacity.series.map((series) => ({
      name: series.name,
      labels: data.charts.tea_capacity.labels,
      values: series.values,
    })),
    {
      x: 0.8,
      y: 2.45,
      w: 6.75,
      h: 3.95,
      showLegend: true,
      legendPos: "b",
      lineSize: 2.5,
      chartColors: [C.teal, C.amber, "7C3AED"],
      catAxisTitle: "tea stations",
      valAxisTitle: "p95 / min",
    }
  );

  card(slide, 8.0, 1.95, 4.75, 1.9, { fill: C.white, line: C.line, bar: C.teal, shadow: true });
  addText(slide, "Critical capacity (extra stations stop paying)", {
    x: 8.2,
    y: 2.08,
    w: 4.35,
    h: 0.28,
    fontSize: 10,
    color: C.slate,
    fit: "shrink",
  });
  const critRows = [["λ = 0.6", "3 tea stations"], ["λ = 0.9", "3 tea stations"], ["λ = 1.2", "4 tea stations"]];
  critRows.forEach((row, index) => {
    addText(slide, row[0], { x: 8.2, y: 2.42 + index * 0.4, w: 1.3, h: 0.3, fontSize: 11, color: C.ink3 });
    addText(slide, row[1], { x: 9.4, y: 2.42 + index * 0.4, w: 1.7, h: 0.3, fontSize: 11, bold: true, color: C.tealDark, fit: "shrink" });
  });
  addText(slide, "Profit-optimal: 2 / 2 / 3 tea stations", {
    x: 8.2,
    y: 3.62,
    w: 4.3,
    h: 0.25,
    fontSize: 9,
    color: C.slate,
    fit: "shrink",
  });

  card(slide, 8.0, 4.0, 4.75, 2.55, { fill: C.mint, line: C.mint2 });
  addText(slide, "Hold labour fixed and the constraint really moves", {
    x: 8.2,
    y: 4.13,
    w: 4.35,
    h: 0.3,
    fontSize: 12,
    bold: true,
    color: C.tealDark,
    fit: "shrink",
  });
  addText(
    slide,
    "Fix two baristas and add only tea stations: from k ≥ 2 on, mean wait, p95 and profit are identical while tea-station utilisation falls from 85% to 43% — the constraint has moved from the equipment to the labour pool.",
    {
      x: 8.2,
      y: 4.5,
      w: 4.35,
      h: 1.9,
      fontSize: 9.3,
      color: C.ink3,
      fit: "shrink",
    }
  );

  notes(
    slide,
    "Supply side (about 1.2 minutes): we split the flow into an order counter, a tea station, an ice-cream machine and a bread counter, with staff carrying skills and shifts. The left chart sweeps tea-station capacity: the critical capacity is 3 at λ = 0.6 and 0.9, and 4 at λ = 1.2; profit-optimal capacity is 2 / 2 / 3. More important is the fixed-labour contrast: adding tea stations without adding staff leaves mean waiting, p95 and profit unchanged from k ≥ 2, while tea-station utilisation falls from 85% to 43% — the bottleneck has migrated from equipment to the shared labour pool. So adding equipment is not a universal fix."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 8
function slideStrategy() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "08 / SUPPLY SIDE");
  titleBlock(slide, "Policy value depends on the bottleneck", "Policy value depends on where the slack sits");

  card(slide, 0.6, 1.95, 7.15, 4.3, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "Δ profit / hour (vs. matched synchro + plain)", {
    x: 0.85,
    y: 2.08,
    w: 6.6,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.ink,
    fit: "shrink",
  });
  horizontalBars(
    slide,
    data.charts.contrasts.map((row) => ({ label: row[0], value: row[1] })),
    { x: 0.85, y: 2.4, w: 6.8, h: 3.7 },
    { zeroFrac: 0.34, fontSize: 10 }
  );

  const cells = [
    ["Tea bottleneck · split delivery", fmt(data.charts.contrasts[1][1], 2) + " /h", C.amber],
    ["Tea bottleneck · fast priority", "+" + fmt(data.charts.contrasts[0][1], 2) + " /h", C.teal],
    ["Ice-cream bottleneck · split", "+" + fmt(data.charts.contrasts[3][1], 2) + " /h", C.teal],
    ["Ice-cream bottleneck · fast", "+" + fmt(data.charts.contrasts[2][1], 2) + " /h", C.amber],
  ];
  cells.forEach((cell, index) => {
    const col = index % 2;
    const row = Math.floor(index / 2);
    const x = 8.0 + col * 2.35;
    const y = 1.95 + row * 1.35;
    card(slide, x, y, 2.2, 1.15, { fill: C.white, line: C.line, bar: cell[2] });
    addText(slide, cell[0], {
      x: x + 0.2,
      y: y + 0.13,
      w: 1.9,
      h: 0.45,
      fontSize: 8.5,
      color: C.slate,
      fit: "shrink",
    });
    addText(slide, cell[1], {
      x: x + 0.2,
      y: y + 0.62,
      w: 1.9,
      h: 0.4,
      fontSize: 13,
      bold: true,
      color: C.ink,
      fit: "shrink",
    });
  });

  addText(slide, "Rule: find the bottleneck first; a fast lane pays only when its own station has slack.", {
    x: 0.6,
    y: 6.45,
    w: 12.2,
    h: 0.35,
    fontSize: 11,
    bold: true,
    color: C.tealDark,
    fit: "shrink",
  });

  notes(
    slide,
    "Policy (about 1 minute): this chart shows four paired contrasts under two bottlenecks. With a tea-station bottleneck, split delivery loses 2 CNY per hour and fast-item priority is worth only 1.3; switch to an ice-cream-machine bottleneck and split delivery turns into +16 while fast priority doubles to 1.7. The reason is that a fast lane only matters when its own station has slack. The rule is: find the bottleneck first, then talk policy."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 9
function slideSkills() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "09 / SUPPLY SIDE");
  titleBlock(slide, "Skills and shifts: same wage, more output", "Same headcount, same wage bill: skill pooling and break placement");

  card(slide, 0.6, 1.95, 6.15, 4.55, { fill: C.white, line: C.line, bar: C.teal, shadow: true });
  addText(slide, "Skill matrix: generalists are worth more", {
    x: 0.85,
    y: 2.1,
    w: 5.6,
    h: 0.35,
    fontSize: 14,
    bold: true,
    color: C.ink,
  });
  addRich(
    slide,
    [
      { text: "+" + fmt(data.skills.generalist.diff, 1), options: { fontFace: FONT_NUM, fontSize: 36, bold: true, color: C.teal } },
      { text: " /h", options: { fontSize: 14, color: C.slate } },
    ],
    { x: 0.85, y: 2.55, w: 3, h: 0.6 }
  );
  addText(slide, `±${fmt(data.skills.generalist.ci95, 1)}, identical headcount and wage bill`, {
    x: 0.85,
    y: 3.15,
    w: 5.6,
    h: 0.3,
    fontSize: 9.5,
    color: C.slate,
    fit: "shrink",
  });
  addImageFit(slide, path.join(ASSETS, "fig_skills.png"), 0.85, 3.55, 5.65, 2.65);
  addText(slide, `One-way cross-training is worth only +${fmt(data.skills.cross.diff, 2)}/h: flexibility must run both ways.`, {
    x: 0.85,
    y: 6.2,
    w: 5.6,
    h: 0.3,
    fontSize: 9.5,
    color: C.ink3,
    fit: "shrink",
  });

  card(slide, 7.0, 1.95, 5.7, 2.15, { fill: C.white, line: C.line, bar: C.amber, shadow: true });
  addText(slide, "Staggered breaks: taking capacity off the peak", {
    x: 7.22,
    y: 2.08,
    w: 5.2,
    h: 0.3,
    fontSize: 13,
    bold: true,
    color: C.ink,
    fit: "shrink",
  });
  addText(slide, `Peak wait 5.19 → 7.37 min; profit ${fmt(data.shifts.break_delta.diff, 1)}/h`, {
    x: 7.22,
    y: 2.45,
    w: 5.2,
    h: 0.35,
    fontSize: 12,
    bold: true,
    color: C.amber,
    fit: "shrink",
  });
  addText(slide, "Breaks save wages (wage bill −7.8/h), but the peak capacity gap is far larger than that saving.", {
    x: 7.22,
    y: 2.85,
    w: 5.2,
    h: 0.55,
    fontSize: 9.3,
    color: C.ink3,
    fit: "shrink",
  });
  addText(slide, "Put breaks between peaks, never on them.", {
    x: 7.22,
    y: 3.5,
    w: 5.2,
    h: 0.3,
    fontSize: 10,
    bold: true,
    color: C.slate,
  });

  card(slide, 7.0, 4.3, 5.7, 2.2, { fill: C.mint, line: C.mint2 });
  addText(slide, "One extra barista on the mid shift, no extra tea machine", {
    x: 7.22,
    y: 4.43,
    w: 5.2,
    h: 0.3,
    fontSize: 12,
    bold: true,
    color: C.tealDark,
    fit: "shrink",
  });
  addText(slide, `Peak wait change +${fmt(data.shifts.mid_peak_delta.diff, 2)} ± ${fmt(data.shifts.mid_peak_delta.ci95, 2)} min (not significant)`, {
    x: 7.22,
    y: 4.8,
    w: 5.2,
    h: 0.35,
    fontSize: 11,
    bold: true,
    color: C.ink,
    fit: "shrink",
  });
  addText(slide, "At the peak the binding constraint is the tea station, not headcount: the extra wage only adds cost.", {
    x: 7.22,
    y: 5.2,
    w: 5.2,
    h: 0.5,
    fontSize: 9.3,
    color: C.ink3,
    fit: "shrink",
  });
  addText(slide, `Profit ${fmt(data.shifts.mid_delta.diff, 1)}/h`, {
    x: 7.22,
    y: 5.75,
    w: 5.2,
    h: 0.3,
    fontSize: 10,
    bold: true,
    color: C.amber,
  });

  notes(
    slide,
    "Skills and shifts (about 1 minute): with the same headcount and the same wage bill, all-generalist staffing earns about 84.5 CNY per hour more than dedicated roles, while one-way cross-training is worth almost nothing (0.17), which tells us flexibility has to run both ways. On shifts, staggering a 30-minute break saves 7.8 CNY of wages but raises peak waiting from 5.19 to 7.37 minutes and costs 49 CNY per hour of profit. Adding a barista to the mid shift without adding a tea machine leaves peak waiting essentially unchanged (+0.06 minutes, not significant), because at the peak the constraint is the tea station, not headcount."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 10
function slideInventory() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "10 / INVENTORY");
  titleBlock(slide, "Inventory: cheap fill rate, costly shelf life", "Fill rate is cheap; lead time and shelf life are not");

  stat(slide, 0.6, 1.95, 3.9, fmt(data.inventory.baseline.fill_rate * 100, 1) + "%", "", "Baseline fill rate", { accent: C.teal, h: 1.35 });
  stat(slide, 0.6, 3.5, 3.9, fmt(data.inventory.best_fill * 100, 2) + "%", "", "Best fill rate (profit essentially unchanged)", { accent: C.teal, h: 1.35 });
  stat(slide, 0.6, 5.05, 3.9, fmt(data.charts.lead_time.fill[2] * 100, 0) + "%", "", "Fill rate at 120 min lead time (240 min → 72%)", { accent: C.amber, h: 1.35 });

  card(slide, 4.75, 1.95, 8.0, 2.2, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "Fill rate vs. replenishment lead time", {
    x: 4.95,
    y: 2.05,
    w: 4.0,
    h: 0.28,
    fontSize: 10,
    bold: true,
    color: C.ink,
  });
  nativeChart(
    slide,
    pres.charts.LINE,
    [{ name: "fill rate", labels: data.charts.lead_time.labels, values: data.charts.lead_time.fill }],
    {
      x: 4.9,
      y: 2.32,
      w: 7.7,
      h: 1.75,
      lineSize: 2.5,
      chartColors: [C.teal],
      valAxisLabelFormatCode: "0%",
      valAxisMinVal: 0.6,
      valAxisMaxVal: 1.0,
      showValue: true,
      dataLabelFormatCode: "0%",
    }
  );

  card(slide, 4.75, 4.3, 8.0, 2.2, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "Perishable pearls: waste appears above roughly 100 units per batch", {
    x: 4.95,
    y: 4.4,
    w: 7.5,
    h: 0.28,
    fontSize: 10,
    bold: true,
    color: C.ink,
    fit: "shrink",
  });
  nativeChart(
    slide,
    pres.charts.BAR,
    [{ name: "waste units / day", labels: data.charts.ceiling.labels, values: data.charts.ceiling.waste }],
    {
      x: 4.9,
      y: 4.67,
      w: 7.7,
      h: 1.7,
      barDir: "col",
      chartColors: [C.amber],
      showValue: true,
      dataLabelPosition: "outEnd",
      dataLabelFontSize: 8,
      dataLabelFormatCode: "0.0",
    }
  );

  addText(slide, "When ice cream is short, substituting mixed order → tea recovers +14.1/h; a pearl shortage cannot be substituted (shared input).", {
    x: 0.6,
    y: 6.78,
    w: 12.2,
    h: 0.28,
    fontSize: 9.5,
    color: C.slate,
    fit: "shrink",
  });

  notes(
    slide,
    "Inventory (about 1 minute): lifting the fill rate from 98% to 99.95% is nearly free — profit differs by about 0.1 CNY per hour; the real cliff is lead time, where 120 minutes drops the fill rate to 80% and 240 minutes to 72%. Perishables are more sensitive: pearl batches above roughly 100 units start to generate waste. When ice cream is short, substituting a mixed order with tea recovers 14 CNY per hour, but a pearl shortage cannot be substituted because the input is shared."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 11
function slidePricing() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "11 / ECONOMICS");
  titleBlock(slide, "Pricing: use the service-neutral multiplier", "Price the peak, not the average: the service-neutral multiplier");

  card(slide, 0.6, 1.95, 7.3, 4.35, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "Profit / hour vs. peak markup multiplier (ε = −0.5)", {
    x: 0.85,
    y: 2.08,
    w: 6.7,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.ink,
    fit: "shrink",
  });
  nativeChart(
    slide,
    pres.charts.LINE,
    [{ name: "profit / h", labels: data.charts.pricing.labels, values: data.charts.pricing.profit }],
    {
      x: 0.8,
      y: 2.4,
      w: 6.95,
      h: 3.7,
      lineSize: 2.5,
      chartColors: [C.teal],
      catAxisTitle: "price multiplier",
      valAxisTitle: "profit / h",
    }
  );

  stat(slide, 8.2, 1.85, 4.55, "×" + fmt(data.pricing.service_neutral, 1), "", "Service-neutral multiplier (ε = −0.5)", { accent: C.teal, h: 1.3 });
  stat(slide, 8.2, 3.25, 4.55, "+20–37%", "", "Profit uplift, with 97.9% of demand retained", { accent: C.teal, h: 1.3 });
  stat(slide, 8.2, 4.65, 4.55, fmt(data.pricing.neutral_peak_p95, 1), " min", "Peak p95 after the markup (close to baseline)", { accent: C.amber, h: 1.3 });

  card(slide, 8.2, 6.08, 4.55, 0.62, { fill: C.amberLight, line: C.amber });
  addText(slide, "The profit optimum sits at the boundary: only customers who stay are charged waiting cost.", {
    x: 8.4,
    y: 6.14,
    w: 4.2,
    h: 0.5,
    fontSize: 8.6,
    color: C.ink3,
    fit: "shrink",
  });

  addText(slide, "Recommend quoting ×1.1–1.2: it shaves the peak without pushing p95 up.", {
    x: 0.6,
    y: 6.6,
    w: 7.3,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.tealDark,
    fit: "shrink",
  });

  notes(
    slide,
    "Pricing (about 1 minute): a peak markup changes demand and waiting at the same time. We separate two quantities — the profit optimum and what is genuinely decidable. The profit optimum usually sits at the tested boundary, because the model only charges waiting cost to the customers who stay; what can actually be quoted is the service-neutral multiplier — the largest markup that leaves p95 essentially unchanged. At ε = −0.5 that is 1.2, with profit up 20–37% and 97.9% of demand retained. We recommend quoting in the 1.1–1.2 range."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 12
function slideSlaFairness() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "12 / ECONOMICS");
  titleBlock(slide, "An SLA is a transfer; fairness is tail protection", "An SLA prices the miss; a fairness cap protects the tail");

  card(slide, 0.6, 1.95, 6.0, 4.3, { fill: C.white, line: C.line, bar: C.teal, shadow: true });
  addText(slide, "SLA: turning a missed promise into money", {
    x: 0.85,
    y: 2.08,
    w: 5.5,
    h: 0.35,
    fontSize: 14,
    bold: true,
    color: C.ink,
    fit: "shrink",
  });
  const slaRows = [
    ["3 min promise", "41.9%", "38.4 /h"],
    ["5 min promise", "61.4%", "25.5 /h"],
    ["8 min promise", "81.9%", "11.9 /h"],
  ];
  slide.addTable(
    [
      [
        { text: "Promise", options: { bold: true } },
        { text: "Attainment", options: { bold: true } },
        { text: "Cost", options: { bold: true } },
      ],
      ...slaRows,
    ],
    {
      x: 0.85,
      y: 2.55,
      w: 5.4,
      colW: [2.0, 1.7, 1.7],
      rowH: 0.52,
      fontFace: FONT,
      fontSize: 10,
      color: C.ink3,
      border: { type: "solid", color: C.line, pt: 0.75 },
      fill: { color: C.white },
      valign: "middle",
    }
  );
  addText(slide, "Compensation does not change service: p95 is identical at every tier. The value of an SLA is that it makes the cost of a miss explicit, so it can be compared with extra staff.", {
    x: 0.85,
    y: 4.78,
    w: 5.4,
    h: 0.75,
    fontSize: 9.2,
    color: C.slate,
    fit: "shrink",
  });
  addText(slide, "Top attainment is 81.9%: no tier reaches 100%.", {
    x: 0.85,
    y: 5.68,
    w: 5.4,
    h: 0.3,
    fontSize: 9.5,
    bold: true,
    color: C.tealDark,
  });

  card(slide, 6.9, 1.95, 5.8, 4.3, { fill: C.white, line: C.line, bar: C.amber, shadow: true });
  addText(slide, "Fairness: protecting the tail, not a fairer mean", {
    x: 7.15,
    y: 2.08,
    w: 5.3,
    h: 0.35,
    fontSize: 14,
    bold: true,
    color: C.ink,
    fit: "shrink",
  });
  addRich(
    slide,
    [
      { text: "−" + fmt(11, 0) + "%", options: { fontFace: FONT_NUM, fontSize: 34, bold: true, color: C.teal } },
      { text: "  p95", options: { fontSize: 12, color: C.slate } },
    ],
    { x: 7.15, y: 2.55, w: 3, h: 0.6 }
  );
  addText(slide, "Spend 5.06/h of profit to move overall p95 from 9.99 to 8.86 min.", {
    x: 7.15,
    y: 3.18,
    w: 5.25,
    h: 0.3,
    fontSize: 9.5,
    color: C.ink3,
    fit: "shrink",
  });

  const fairRows = [
    ["Cross-class p95 spread", "2.27 → 2.22", "slightly down"],
    ["Cross-class mean spread", "1.45 → 1.78", "up"],
    ["Escalations per hour", "54.4", "auditable"],
  ];
  fairRows.forEach((row, index) => {
    const y = 3.68 + index * 0.52;
    card(slide, 7.15, y, 5.25, 0.44, { fill: index === 1 ? C.amberLight : C.mint, line: C.line, lineWidth: 0 });
    addText(slide, row[0], { x: 7.3, y: y + 0.09, w: 1.95, h: 0.25, fontSize: 8.6, color: C.ink3, fit: "shrink" });
    addText(slide, row[1], { x: 9.25, y: y + 0.09, w: 1.8, h: 0.25, fontSize: 8.6, bold: true, color: C.ink });
    addText(slide, row[2], { x: 11.05, y: y + 0.09, w: 1.2, h: 0.25, fontSize: 8.2, color: index === 1 ? C.amber : C.tealDark, fit: "shrink" });
  });

  addText(slide, "Mind the metric: the mean-based fairness_gap rises, so this is tail protection, not evidence of a fairer outcome.", {
    x: 7.15,
    y: 5.35,
    w: 5.25,
    h: 0.5,
    fontSize: 8.6,
    color: C.slate,
    fit: "shrink",
  });
  addText(slide, "Recommend a cap of 1.5–3 min: the tail improves markedly for about 2% of profit.", {
    x: 7.15,
    y: 5.95,
    w: 5.25,
    h: 0.3,
    fontSize: 9,
    bold: true,
    color: C.amber,
    fit: "shrink",
  });

  notes(
    slide,
    "SLA and fairness (about 1 minute): on the SLA side, promises of 3, 5 and 8 minutes attain 41.9%, 61.4% and 81.9%, costing 38.4, 25.5 and 11.9 CNY per hour; compensation changes no service level at all, so an SLA is a transfer payment, and its value is making the cost of a miss explicit. On the fairness side, an ageing cap trades 5 CNY per hour for an 11% cut in overall p95, but the mean-based fairness_gap rises, so we claim tail protection and not a fairer outcome. We recommend a cap of 1.5–3 minutes."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 13
function slideBundle() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "13 / BUNDLE");
  titleBlock(slide, "One bundle: four layers, one configuration", "One bundle: capacity, pricing, SLA and a fairness cap together");

  addRich(
    slide,
    [
      { text: "+" + fmt(data.management.paired_profit_gain, 1), options: { fontFace: FONT_NUM, fontSize: 46, bold: true, color: C.teal } },
      { text: " ± " + fmt(data.management.paired_profit_gain_ci95, 1) + " /h", options: { fontSize: 16, color: C.slate } },
    ],
    { x: 0.6, y: 1.95, w: 6, h: 0.8 }
  );
  addText(slide, `Against the campus_rush baseline: ${fmt(data.management.baseline.profit_per_hour, 1)} → ${fmt(data.management.good_manager.profit_per_hour, 1)} /h (+49%)`, {
    x: 0.6,
    y: 2.8,
    w: 6.2,
    h: 0.35,
    fontSize: 10.5,
    color: C.ink3,
    fit: "shrink",
  });

  const rows = [
    ["Metric", "Baseline", "Bundle"],
    ["Profit /h", fmt(data.management.baseline.profit_per_hour, 1), fmt(data.management.good_manager.profit_per_hour, 1)],
    ["p95 /min", fmt(data.management.baseline.los_p95, 1), fmt(data.management.good_manager.los_p95, 1)],
    ["Balked /day", fmt(data.management.baseline.balked, 1), fmt(data.management.good_manager.balked, 1)],
    ["SLA attainment", "—", fmt(data.management.good_manager.sla_attainment * 100, 1) + "%"],
  ];
  slide.addTable(
    rows.map((row, index) => row.map((cell) => ({
      text: cell,
      options: {
        bold: index === 0,
        color: index === 0 ? C.white : C.ink3,
        fill: { color: index === 0 ? C.ink : index % 2 ? C.white : C.bg },
      },
    }))),
    {
      x: 0.6,
      y: 3.35,
      w: 6.2,
      colW: [2.2, 2.0, 2.0],
      rowH: 0.52,
      fontFace: FONT,
      fontSize: 10,
      border: { type: "solid", color: C.line, pt: 0.75 },
      valign: "middle",
    }
  );

  card(slide, 7.1, 1.95, 5.65, 3.9, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "Single-lever ranking (Δ profit/h)", {
    x: 7.3,
    y: 2.05,
    w: 4.0,
    h: 0.28,
    fontSize: 10.5,
    bold: true,
    color: C.ink,
  });
  horizontalBars(
    slide,
    data.charts.levers.map((row) => ({ label: row[0], value: row[1] })),
    { x: 7.2, y: 2.35, w: 5.4, h: 3.45 },
    { zeroFrac: 0.46, fontSize: 9 }
  );

  card(slide, 7.1, 6.0, 5.65, 0.6, { fill: C.mint, line: C.mint2 });
  addText(slide, "Capacity first, pricing second; fairness and SLA are low-cost tail protectors.", {
    x: 7.3,
    y: 6.12,
    w: 5.25,
    h: 0.35,
    fontSize: 9.5,
    bold: true,
    color: C.tealDark,
    fit: "shrink",
  });

  notes(
    slide,
    "Bundle (about 1 minute): put an extra barista, a modest peak markup, an SLA and a fairness cap into one configuration. Against the campus_rush baseline, profit rises from 240 to 358 CNY per hour, a paired difference of +118.1 ± 5.1; p95 falls from 11.8 to 5.7 minutes and balking from 101.7 to 16.2. The single-lever ranking is capacity first, pricing second, with the fairness cap and the SLA as low-cost tail protectors. This does not trade service for money: profit and waiting improve together."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 14
function slideRules() {
  const slide = pres.addSlide();
  bg(slide, C.ink);
  kicker(slide, "14 / CONCLUSIONS", C.teal);
  titleBlock(slide, "Four management rules", "Four rules the simulation supports", true);

  const rules = [
    ["01", "Staff to the peak", "Daily utilisation is not a decision metric; the peak shape is itself a cost."],
    ["02", "Find the bottleneck first", "Before adding equipment, ask where the new constraint will move to."],
    ["03", "Protect the tail, not the mean", "A fairness cap and a service-neutral markup both act on p95 and cost little."],
    ["04", "Price the SLA explicitly", "An SLA does not change queueing, but it decides how capacity and promises compare."],
  ];
  rules.forEach((rule, index) => {
    const col = index % 2;
    const row = Math.floor(index / 2);
    const x = 0.6 + col * 6.15;
    const y = 2.05 + row * 2.15;
    card(slide, x, y, 5.85, 1.85, { fill: C.ink2, line: C.ink3, bar: index % 2 ? C.amber : C.teal });
    addText(slide, rule[0], {
      x: x + 0.25,
      y: y + 0.2,
      w: 0.9,
      h: 0.4,
      fontFace: FONT_NUM,
      fontSize: 18,
      bold: true,
      color: index % 2 ? C.amber : C.teal,
    });
    addText(slide, rule[1], {
      x: x + 0.25,
      y: y + 0.66,
      w: 5.3,
      h: 0.4,
      fontSize: 16,
      bold: true,
      color: C.white,
      fit: "shrink",
    });
    addText(slide, rule[2], {
      x: x + 0.25,
      y: y + 1.15,
      w: 5.3,
      h: 0.55,
      fontSize: 10.5,
      color: C.slateLight,
      fit: "shrink",
    });
  });

  addText(slide, "One engine, one 2×2 policy matrix: we only made the course model's implicit assumptions explicit, layer by layer.", {
    x: 0.6,
    y: 6.55,
    w: 12.2,
    h: 0.3,
    fontSize: 10.5,
    color: C.slateLight,
    fit: "shrink",
  });

  notes(
    slide,
    "Conclusions (about 45 seconds): we compress the study into four rules. First, staff to the peak, not to the daily utilisation. Second, find the bottleneck before choosing a policy, because adding equipment moves the constraint. Third, protect the tail rather than the mean: the fairness cap and the service-neutral markup both act on p95 and cost little. Fourth, price the SLA explicitly — it does not improve the queue, but it puts capacity and promises on the same ledger."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 15
function slideEvidence() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "15 / EVIDENCE");
  titleBlock(slide, "Reproducible: the evidence chain and its edges", "What is reproducible, and what is only an archive");

  card(slide, 0.6, 1.95, 6.0, 1.5, { fill: C.white, line: C.line, bar: C.teal, shadow: true });
  addText(slide, "Python engine (reproducible)", {
    x: 0.85,
    y: 2.08,
    w: 5.5,
    h: 0.3,
    fontSize: 13,
    bold: true,
    color: C.ink,
  });
  addText(slide, `${data.meta.tests} tests · 16 recomputable scenarios · fixed seeds · standard library only`, {
    x: 0.85,
    y: 2.42,
    w: 5.5,
    h: 0.35,
    fontSize: 10,
    color: C.ink3,
    fit: "shrink",
  });
  addText(slide, "Report and demo run fully offline: no JS dependencies, no external links, openable over file://.", {
    x: 0.85,
    y: 2.8,
    w: 5.5,
    h: 0.35,
    fontSize: 9.3,
    color: C.slate,
    fit: "shrink",
  });

  card(slide, 0.6, 3.65, 6.0, 1.5, { fill: C.white, line: C.line, bar: C.amber, shadow: true });
  addText(slide, "Scenario library (auditable)", {
    x: 0.85,
    y: 3.78,
    w: 5.5,
    h: 0.3,
    fontSize: 13,
    bold: true,
    color: C.ink,
  });
  addText(slide, "16 synthetic contexts, each recording source / method / uncertainty; never presented as measured shop data.", {
    x: 0.85,
    y: 4.12,
    w: 5.5,
    h: 0.55,
    fontSize: 9.8,
    color: C.ink3,
    fit: "shrink",
  });

  card(slide, 0.6, 5.35, 6.0, 1.35, { fill: C.white, line: C.line, bar: C.slate, shadow: true });
  addText(slide, "AnyLogic model (archive, not rerunnable)", {
    x: 0.85,
    y: 5.48,
    w: 5.5,
    h: 0.3,
    fontSize: 13,
    bold: true,
    color: C.ink,
    fit: "shrink",
  });
  addText(slide, "The model snapshot and screenshots are kept as historical evidence; they feed no number in this report.", {
    x: 0.85,
    y: 5.82,
    w: 5.5,
    h: 0.55,
    fontSize: 9.8,
    color: C.ink3,
    fit: "shrink",
  });

  framedImage(slide, path.join(ASSETS, "anylogic_e3.png"), 7.0, 1.95, 5.7, 4.75, {
    caption: "AnyLogic archive screenshot (E3): historical reference only, not rerunnable",
  });

  notes(
    slide,
    "Evidence (about 45 seconds): every number can be recomputed with the Python engine — 69 tests, 16 scenarios, fixed random seeds, standard library only; the report and the demo run entirely offline with no external links. Every scenario file records its source, method and uncertainty, and we never present it as measured shop data. The AnyLogic model is archive evidence only: it cannot be rerun, and it feeds no number in the report."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 16
function slideDemo() {
  const slide = pres.addSlide();
  bg(slide, C.ink);
  kicker(slide, "16 / LIVE DEMO", C.teal);
  titleBlock(slide, "60-second live demo", "Three interactions, all precomputed", true);

  card(slide, 0.6, 1.95, 7.6, 4.8, { fill: C.white, line: C.line, shadow: true });
  addImageFit(slide, path.join(ASSETS, "demo_crop.png"), 0.72, 2.05, 7.35, 4.55);

  const steps = [
    ["1", "Switch scenario × policy", "16 contexts; profit and p95 move together"],
    ["2", "Drag the demand-curve slider", "Same daily mean, sharper peak, worse tail"],
    ["3", "Play the queue timeline", "One day of arrival / start / done"],
  ];
  steps.forEach((step, index) => {
    const y = 2.05 + index * 1.45;
    addText(slide, step[0], {
      x: 8.5,
      y,
      w: 0.5,
      h: 0.4,
      fontFace: FONT_NUM,
      fontSize: 20,
      bold: true,
      color: C.teal,
    });
    addText(slide, step[1], {
      x: 9.05,
      y: y + 0.02,
      w: 3.6,
      h: 0.35,
      fontSize: 13,
      bold: true,
      color: C.white,
      fit: "shrink",
    });
    addText(slide, step[2], {
      x: 9.05,
      y: y + 0.4,
      w: 3.6,
      h: 0.35,
      fontSize: 9.5,
      color: C.slateLight,
      fit: "shrink",
    });
  });

  addText(slide, "Precomputed data: the browser runs no simulation, so the demo and the report share one result set.", {
    x: 8.5,
    y: 6.35,
    w: 4.3,
    h: 0.45,
    fontSize: 9.3,
    color: C.slateLight,
    fit: "shrink",
  });

  notes(
    slide,
    "Demo (about 45 seconds; open it live only if the network allows): the page does three things — switch scenario and policy to watch the metrics move together; drag the demand-curve slider to see how the same daily arrivals produce a worse tail under a sharper peak; and play the one-day queue timeline. Everything is precomputed, the browser runs no discrete-event simulation, so it is the same result set as the report."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 17
function slideLimits() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "17 / LIMITS");
  titleBlock(slide, "Limits and next steps", "What this model does not claim, and what we would do next");

  const limits = [
    ["Synthetic scenarios", "Every context is a teaching assumption with a documented source; absolute levels are not a shop forecast."],
    ["Single-day model", "No day-to-day inventory carry-over, fatigue or learning effects; one run represents one day."],
    ["Simplified waiting cost", "Waiting cost is charged only to customers who stay, so the profit optimum lands on the boundary."],
    ["Homogeneous skills", "Staff are identical within a skill; breaks are fixed windows, not personalised rosters."],
  ];
  limits.forEach((limit, index) => {
    const col = index % 2;
    const row = Math.floor(index / 2);
    const x = 0.6 + col * 6.15;
    const y = 1.95 + row * 1.45;
    card(slide, x, y, 5.85, 1.25, { fill: C.white, line: C.line, bar: index % 2 ? C.amber : C.slate });
    addText(slide, limit[0], {
      x: x + 0.25,
      y: y + 0.13,
      w: 5.3,
      h: 0.3,
      fontSize: 12,
      bold: true,
      color: C.ink,
      fit: "shrink",
    });
    addText(slide, limit[1], {
      x: x + 0.25,
      y: y + 0.48,
      w: 5.3,
      h: 0.65,
      fontSize: 9.8,
      color: C.ink3,
      fit: "shrink",
    });
  });

  addText(slide, "Next steps", {
    x: 0.6,
    y: 5.0,
    w: 2,
    h: 0.3,
    fontSize: 12,
    bold: true,
    color: C.tealDark,
  });
  const nextSteps = [
    ["Real-data calibration", "One week of timestamped orders → arrival curve and service times"],
    ["Multi-day inventory + rosters", "Carry-over stock and real rosters in place of fixed break windows"],
    ["Customer behaviour A/B", "Measure what early handover is really worth in repeat visits"],
    ["More categories", "More products sharing stations and inputs, to test the bottleneck result"],
  ];
  nextSteps.forEach((step, index) => {
    const x = 0.6 + index * 3.12;
    card(slide, x, 5.35, 2.95, 1.45, { fill: C.mint, line: C.mint2 });
    addText(slide, step[0], {
      x: x + 0.18,
      y: 5.48,
      w: 2.6,
      h: 0.3,
      fontSize: 10.5,
      bold: true,
      color: C.tealDark,
      fit: "shrink",
    });
    addText(slide, step[1], {
      x: x + 0.18,
      y: 5.82,
      w: 2.6,
      h: 0.85,
      fontSize: 8.8,
      color: C.ink3,
      fit: "shrink",
    });
  });

  notes(
    slide,
    "Limits (about 45 seconds): we should be honest about the boundary. The scenarios are synthetic, so absolute levels cannot be read as a shop forecast; the model covers a single day, with no inventory carry-over; waiting cost is charged only to the customers who stay, which is why the profit optimum sits on the boundary; and skills and breaks are simplified. The most valuable next step is to calibrate the arrival curve and the service times on a week of timestamped real orders, then couple inventory and queueing in a genuine multi-day model."
  );
  return slide;
}

// ---------------------------------------------------------------- slide 18
function slideTeam() {
  const slide = pres.addSlide();
  bg(slide, C.ink);
  addText(slide, "Q&A", {
    x: 0.6,
    y: 1.5,
    w: 6,
    h: 1.0,
    fontFace: FONT_NUM,
    fontSize: 60,
    bold: true,
    color: C.white,
  });
  addText(slide, "Thank you · questions welcome", {
    x: 0.65,
    y: 2.55,
    w: 6.2,
    h: 0.5,
    fontSize: 20,
    color: C.mint2,
  });
  addText(slide, "Report and code: github.com/dwan621/bubble-tea-shop-sim", {
    x: 0.65,
    y: 3.25,
    w: 6.4,
    h: 0.35,
    fontSize: 11,
    color: C.slateLight,
    fit: "shrink",
  });
  addText(slide, "Online report: dwan621.github.io/bubble-tea-shop-sim", {
    x: 0.65,
    y: 3.6,
    w: 6.4,
    h: 0.35,
    fontSize: 11,
    color: C.slateLight,
    fit: "shrink",
  });

  addText(slide, "Speaking plan (18 min + 5 min Q&A)", {
    x: 7.0,
    y: 1.45,
    w: 5.7,
    h: 0.35,
    fontSize: 12,
    bold: true,
    color: C.teal,
  });
  const team = [
    ["Member A", "pp. 1–3", "Opening · three questions · model", "0:00–3:00"],
    ["Member B", "pp. 4–5", "Design · peak cost", "3:00–5:30"],
    ["Member C", "pp. 6–7", "Variability · bottleneck", "5:30–8:00"],
    ["Member D", "pp. 8–9", "Policy · skills and shifts", "8:00–10:30"],
    ["Member E", "pp. 10–12", "Inventory · pricing · SLA/fairness", "10:30–13:30"],
    ["Member F", "pp. 13–18", "Bundle · rules · evidence · demo · limits · Q&A", "13:30–18:00"],
  ];
  team.forEach((member, index) => {
    const y = 1.9 + index * 0.78;
    card(slide, 7.0, y, 5.75, 0.68, { fill: C.ink2, line: C.ink3, bar: index % 2 ? C.amber : C.teal });
    addText(slide, member[0], {
      x: 7.2,
      y: y + 0.15,
      w: 1.0,
      h: 0.35,
      fontSize: 11,
      bold: true,
      color: C.white,
    });
    addText(slide, member[1], {
      x: 8.2,
      y: y + 0.16,
      w: 0.85,
      h: 0.3,
      fontSize: 8.5,
      color: C.teal,
      fit: "shrink",
    });
    addText(slide, member[2], {
      x: 9.1,
      y: y + 0.16,
      w: 2.7,
      h: 0.3,
      fontSize: 8.5,
      color: C.slateLight,
      fit: "shrink",
    });
    addText(slide, member[3], {
      x: 11.85,
      y: y + 0.16,
      w: 0.8,
      h: 0.3,
      fontSize: 7.5,
      color: C.slateLight,
      align: "right",
    });
  });

  addText(slide, "Q&A ownership: model A and C · data B · policy D · economics E · integration and demo F", {
    x: 0.65,
    y: 4.35,
    w: 6.3,
    h: 0.9,
    fontSize: 9.5,
    color: C.slateLight,
    fit: "shrink",
  });

  notes(
    slide,
    "Closing (about 30 seconds): that is our study. The six sections are owned by members A to F, running from minute 0 to minute 18, with the last 5 minutes for Q&A; model implementation, statistics, operating policy, economics and fairness, and the live demo each have an owner. The report, the code and the interactive demo are all on GitHub. Questions are welcome."
  );
  return slide;
}

// ---------------------------------------------------------------- hand-drawn bars
// Native charts put category labels on the zero axis, so negative bars cover
// them. Drawing the bars keeps every label clear.
function horizontalBars(slide, rows, box, opts) {
  const o = opts || {};
  const zeroFrac = o.zeroFrac === undefined ? 0.35 : o.zeroFrac;
  const zeroX = box.x + zeroFrac * box.w;
  const maxAbs = Math.max.apply(null, rows.map((row) => Math.abs(row.value)));
  const positiveSpace = box.x + box.w - zeroX - 0.3;
  const negativeSpace = zeroX - box.x - 0.3;
  const scale = Math.min(positiveSpace, negativeSpace) / maxAbs;
  slide.addShape(pres.shapes.LINE, {
    x: zeroX,
    y: box.y,
    w: 0,
    h: box.h,
    line: { color: C.slateLight, width: 1 },
  });
  const rowH = box.h / rows.length;
  rows.forEach((row, index) => {
    const top = box.y + index * rowH;
    const sign = row.value >= 0 ? "+" : "−";
    addText(slide, `${row.label}   ${sign}${Math.abs(row.value).toFixed(1)}`, {
      x: box.x,
      y: top + 0.02,
      w: box.w,
      h: 0.26,
      fontSize: o.fontSize || 9.5,
      color: C.ink3,
      fit: "shrink",
    });
    const barWidth = Math.max(Math.abs(row.value) * scale, 0.04);
    slide.addShape(pres.shapes.RECTANGLE, {
      x: row.value >= 0 ? zeroX : zeroX - barWidth,
      y: top + 0.36,
      w: barWidth,
      h: 0.18,
      fill: { color: row.value >= 0 ? (o.positive || C.teal) : (o.negative || C.amber) },
      line: { color: row.value >= 0 ? (o.positive || C.teal) : (o.negative || C.amber), width: 0 },
    });
  });
}

// ---------------------------------------------------------------- native charts
// The quantitative slides use native PowerPoint charts: they stay legible when
// the deck is projected and the labels never collide.
function nativeChart(slide, type, series, opts) {
  slide.addChart(
    type,
    series,
    Object.assign(
      {
        x: 0.9,
        y: 2.6,
        w: 5.6,
        h: 3.1,
        fontFace: FONT,
        catAxisLabelFontSize: 10,
        valAxisLabelFontSize: 9,
        legendFontSize: 9,
        dataLabelFontSize: 9,
        showLegend: false,
        catGridLine: { style: "none" },
        valGridLine: { color: C.line, size: 0.5 },
        chartArea: { fill: { color: C.white } },
      },
      opts || {}
    )
  );
}

// ---------------------------------------------------------------- build
const deckSlides = [
  slideTitle(),
  slideQuestions(),
  slideModel(),
  slideDesign(),
  slidePeak(),
  slideVariability(),
  slideBottleneck(),
  slideStrategy(),
  slideSkills(),
  slideInventory(),
  slidePricing(),
  slideSlaFairness(),
  slideBundle(),
  slideRules(),
  slideEvidence(),
  slideDemo(),
  slideLimits(),
  slideTeam(),
];
deckSlides.forEach((slide, index) => {
  if (index > 0) footer(slide, index + 1);
});
kicker(deckSlides[17], "18 / Q&A", C.teal);

pres.writeFile({ fileName: OUT }).then(() => {
  console.log("wrote", OUT);
});
