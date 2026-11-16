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
const OUT = path.join(__dirname, "bubble-tea-shop-simulation.pptx");

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

const FONT = "Microsoft YaHei";
const FONT_NUM = "Georgia";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "SYE5006 group";
pres.company = "SYE5006";
pres.subject = "Bubble-tea shop simulation: four layers, one engine";
pres.title = data.meta.title;
pres.lang = "zh-CN";

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
  addText(slide, label || "奶茶店仿真 · 四层机制下的调度、库存与定价", {
    x: 0.6,
    y: H - 0.45,
    w: 8.5,
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

function titleBlock(slide, zh, en, dark) {
  addText(slide, zh, {
    x: 0.6,
    y: 0.78,
    w: 11.8,
    h: 0.62,
    fontSize: 30,
    bold: true,
    color: dark ? C.white : C.ink,
  });
  if (en) {
    addText(slide, en, {
      x: 0.6,
      y: 1.42,
      w: 11.8,
      h: 0.3,
      fontSize: 11,
      color: dark ? C.slateLight : C.slate,
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

function chip(slide, x, y, w, h, text, opts) {
  const o = opts || {};
  slide.addShape(pres.shapes.RECTANGLE, {
    x,
    y,
    w,
    h,
    fill: { color: o.fill || C.mint },
    line: { color: o.line || C.mint2, width: 0.75 },
  });
  addText(slide, text, {
    x: x + 0.12,
    y: y + (h - (o.fontSize || 10) / 72 * 1.5) / 2,
    w: w - 0.24,
    h: (o.fontSize || 10) / 72 * 1.6,
    fontSize: o.fontSize || 10,
    color: o.color || C.tealDark,
    bold: !!o.bold,
    align: o.align || "left",
    valign: "middle",
    fit: "shrink",
  });
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
      fontSize: 9.5,
      color: C.slate,
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

  addText(slide, "SYE5006 · 课程项目展示", {
    x: 0.75,
    y: 0.7,
    w: 6,
    h: 0.3,
    fontSize: 12,
    bold: true,
    color: C.teal,
    charSpacing: 2,
  });

  addText(slide, "奶茶店仿真", {
    x: 0.72,
    y: 1.55,
    w: 7.2,
    h: 0.95,
    fontSize: 50,
    bold: true,
    color: C.white,
  });
  addText(slide, "四层机制下的调度、库存与定价", {
    x: 0.75,
    y: 2.55,
    w: 7.4,
    h: 0.55,
    fontSize: 24,
    color: C.mint2,
  });
  addText(slide, "Bubble-tea shop simulation: four layers, one engine", {
    x: 0.75,
    y: 3.18,
    w: 7.2,
    h: 0.35,
    fontSize: 13,
    color: C.slateLight,
  });

  rule(slide, 0.75, 3.85, 3.2, C.teal);

  addText(
    slide,
    "16 个合成场景 · 每格 100 次重复（过载区 60） · 配对随机数 · 69 条测试 · 全部可复现",
    {
      x: 0.75,
      y: 4.05,
      w: 7.2,
      h: 0.35,
      fontSize: 11,
      color: C.slateLight,
    }
  );

  addText(slide, "6 人小组 · 2026 年 11 月", {
    x: 0.75,
    y: 5.4,
    w: 6,
    h: 0.3,
    fontSize: 12,
    color: C.white,
  });
  addText(slide, "报告  docs/index.html   ·   演示  demo/index.html   ·   代码  github.com/dwan621/bubble-tea-shop-sim", {
    x: 0.75,
    y: 5.78,
    w: 12,
    h: 0.3,
    fontSize: 9.5,
    color: C.slateLight,
  });

  const layers = [
    ["01", "需求", "Peak shape, patience, variability"],
    ["02", "网络", "Stations, skills, shifts"],
    ["03", "库存", "BOM, (s,S), shelf life"],
    ["04", "经济", "Pricing, SLA, fairness"],
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
      fontSize: 18,
      bold: true,
      color: C.white,
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
    "开场（约 30 秒）：各位老师、同学好，我们是第六组。我们研究的是一家同时卖奶茶、面包和冰淇淋的小店：当需求出现峰值、员工有分工和设备瓶颈、原料会过期、等待可以折算成钱时，调度与定价应该怎么做。今天用同一台仿真引擎回答四个层面的问题，每个结论都能复现。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 2
function slideQuestions() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "02 / 三个问题");
  titleBlock(slide, "三个问题，一个引擎", "Three operational questions, one decision model");

  const items = [
    {
      n: "01",
      q: "混合单：冰淇淋先递，还是整单一起？",
      a: "低负载几乎免费，负载接近 80% 时反转",
      stat: `λ* = ${fmt(data.baseline.breakeven_lambda, 3)} / min  ·  ρ* = ${fmt(data.baseline.breakeven_util * 100, 1)}%`,
      foot: "拆分交付把等待从混合单转移到主队列",
    },
    {
      n: "02",
      q: "面包和冰淇淋，要不要插队？",
      a: "是更强杠杆，但取决于瓶颈在哪",
      stat: `茶瓶颈 +${fmt(data.strategy.tea_fast.diff, 2)}/h  ·  冰淇淋瓶颈 +${fmt(data.strategy.ice_fast.diff, 2)}/h`,
      foot: "快品通道只在它自己的站台有富余时值钱",
    },
    {
      n: "03",
      q: "等待、承诺和公平，怎么折算成钱？",
      a: "可决策的是“服务中性”加价与尾部保护",
      stat: `定价 ×${fmt(data.pricing.service_neutral, 1)}（ε = −0.5） ·  客流保留 97.9%`,
      foot: "公平 cap 用 5.1/h 换 −11% p95；SLA 是转移支付",
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
      fontSize: 16,
      bold: true,
      color: C.ink,
      fit: "shrink",
    });
    addText(slide, item.a, {
      x: x + 0.3,
      y: 4.2,
      w: 3.2,
      h: 0.8,
      fontSize: 13,
      color: C.ink3,
      fit: "shrink",
    });
    addText(slide, item.stat, {
      x: x + 0.3,
      y: 5.2,
      w: 3.2,
      h: 0.55,
      fontSize: 11,
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

  addText(slide, "这三条结论背后是同一个离散事件引擎；下面先看模型，再看证据。", {
    x: 0.6,
    y: 6.5,
    w: 12,
    h: 0.35,
    fontSize: 11,
    color: C.slate,
  });

  notes(
    slide,
    "三个问题（约 1 分钟）：第一，混合单要不要拆分交付——低负载时几乎免费，但在约 80% 利用率处反转；第二，快品优先是否值得——它比拆分更强，但价值取决于瓶颈在茶站还是冰淇淋机；第三，等待怎么定价、SLA 与公平怎么权衡——可决策的是“服务中性”加价区间。接下来先看模型和实验设计。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 3
function slideModel() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "03 / 模型");
  titleBlock(slide, "模型：一个共享员工池，四类订单", "One cross-trained clerk pool, four order classes");

  const steps = [
    ["01", "到店", "泊松到达；日内峰型、批量到店、顾客分群"],
    ["02", "点单 + 制作", "共享员工池；点单 0.5 min，制作占用同一批员工"],
    ["03", "三类产品 + 混合单", "奶茶 2.0 min · 面包 10 s · 冰淇淋 20 s"],
    ["04", "交付与离开", "同步或拆分；等待折算为成本"],
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
      w: 2.0,
      h: 0.3,
      fontSize: 14,
      bold: true,
      color: C.ink,
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

  addText(slide, "关键假设（全部在 data/scenarios/*.json 中显式记录）", {
    x: 7.1,
    y: 1.95,
    w: 5.5,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.slate,
  });

  const rows = [
    ["员工", "3 人，跨品类"],
    ["订单结构", "奶茶 55% / 面包 20% / 冰淇淋 5% / 混合 20%"],
    ["服务时间", "点单 0.5；奶茶 2.0；面包 0.167；冰淇淋 0.333 min"],
    ["价格", "8 / 6 / 2 / 10 元"],
    ["人工与等待", "25 元/人/小时；0.5 元/顾客/分钟"],
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
      colW: [1.3, 4.3],
      rowH: 0.72,
      fontFace: FONT,
      fontSize: 9.5,
      valign: "middle",
      border: { type: "solid", color: C.line, pt: 0.75 },
      margin: 0.08,
    }
  );

  card(slide, 7.1, 6.15, 5.6, 0.62, { fill: C.mint, line: C.mint2 });
  addText(slide, "核心口径：总工作量不变时，调度只改变“谁在等”，不改变产能。", {
    x: 7.3,
    y: 6.27,
    w: 5.2,
    h: 0.38,
    fontSize: 10,
    bold: true,
    color: C.tealDark,
    fit: "shrink",
  });

  notes(
    slide,
    "模型（约 1 分钟）：顾客按泊松过程到店，四类订单；一名员工同时负责点单和制作，因此共享员工池就是瓶颈。奶茶 2 分钟、面包 10 秒、冰淇淋 20 秒，混合单是奶茶加冰淇淋。价格、工资和等待成本都显式写进场景文件，所有假设都可追溯。关键口径是：拆分或同步不改变总工作量，只改变谁在等。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 4
function slideDesign() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "04 / 实验设计");
  titleBlock(slide, "16 个场景 × 100 次重复 × 配对比较", "A scenario library, common random numbers and a validation contract");

  const groups = [
    ["校园 / 商圈", "campus_rush · cbd_commute"],
    ["商场 / 极端需求", "mall_weekend · exam_week · rainy_delivery"],
    ["小店 / 大店", "tiny_two_staff · flagship_five_staff"],
    ["设备瓶颈", "network_tea_bottleneck · ice_cream_bottleneck · bread_counter_bottleneck"],
    ["库存", "inventory_lean · inventory_generous"],
    ["定价 / SLA", "peak_pricing · strict_sla_fairness"],
    ["夜间 / 基线", "late_night_study · baseline_flat"],
    ["场景总数", "16 个 JSON，每个带 source / method / uncertainty"],
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
    ["来源可审计", "每个场景带 provenance（来源 / 方法 / 不确定性）；不冒充门店实测数据", "16 / 16 场景带来源"],
    ["统计口径", "同一随机种子下配对比较；95% 置信区间；100 次重复（过载区 60 次）", "20 万+ 次仿真"],
    ["契约验证", `${data.meta.tests} 条测试；16/16 场景流量守恒；关闭全部新层时与课程模型逐位一致`, "关闭新层 = 课程模型"],
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
    });
    addText(slide, method[1], {
      x: 9.35,
      y: y + 0.45,
      w: 3.1,
      h: 0.58,
      fontSize: 8.6,
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
    });
  });

  notes(
    slide,
    "实验设计（约 1 分钟）：我们没有只跑一个配置，而是建了 16 个场景库，覆盖校园、商圈、商场、极端需求、大小店、三种设备瓶颈、库存、定价与 SLA。每个场景都有来源和不确定性标注。统计上用公共随机数做配对比较，报 95% 置信区间；验证契约包括 69 条测试、16 个场景逐次守恒，以及“关闭全部新层时与课程模型逐位一致”。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 5
function slidePeak() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "06 / 需求侧");
  titleBlock(slide, "峰值：日均利用率会骗人", "Same daily mean, very different peak: the average hides the cost");

  stat(slide, 0.6, 2.0, 3.7, "+" + fmt(data.peak.p95_peak_abs - data.peak.p95_flat_abs, 2), " min", "p95 等待（峰型 vs 平峰）", { accent: C.amber });
  stat(slide, 0.6, 3.75, 3.7, fmt(data.peak.balk_peak * 100, 1) + "%", "", `流失率（平峰 ${fmt(data.peak.balk_flat * 100, 1)}%）`, { accent: C.amber });
  stat(slide, 0.6, 5.5, 3.7, fmt(data.peak.profit_flat - data.peak.profit_peak, 1), " /h", `利润差（平峰 ${fmt(data.peak.profit_flat, 1)} → 峰型 ${fmt(data.peak.profit_peak, 1)}）`, { accent: C.amber });

  framedImage(slide, path.join(ASSETS, "fig_demand_hourly.png"), 4.75, 1.9, 8.0, 4.6, {
    caption: "每个小时忙碌度：峰型在午峰和晚峰远超平峰，日均却更低（流失把工作带走了）",
  });

  addText(slide, "结论：排班要按峰值，不要按日均；峰值形状本身就是一个成本项。", {
    x: 4.75,
    y: 6.6,
    w: 8.0,
    h: 0.35,
    fontSize: 11,
    bold: true,
    color: C.tealDark,
  });

  notes(
    slide,
    "需求侧结论（约 1 分钟）：在日均客流完全相同的情况下，只把需求压成峰型，p95 等待增加 3.7 分钟，流失率从 6.9% 升到 15.1%，利润下降约 57 元/小时。注意日均利用率反而从 60.6% 降到 54.9%，因为流失顾客把工作带走了。所以“按日均利用率排班”会系统性地低估峰值风险。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 6
function slideVariability() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "05 / 需求侧");
  titleBlock(slide, "变异与耐心：均值看不出的风险", "Variability and patience move the tail, not the mean");

  framedImage(slide, path.join(ASSETS, "fig_variability.png"), 0.6, 1.95, 6.0, 3.9, {
    caption: "服务时间变异：指数分布（CV=1）与对数正态 CV 0.75 显著抬高 p95",
  });
  framedImage(slide, path.join(ASSETS, "fig_patience.png"), 6.85, 1.95, 5.85, 3.9, {
    caption: "顾客耐心：balk 阈值从 3 min 放宽到 12 min，流失从 29.3% 降到 3.2%",
  });

  card(slide, 0.6, 6.0, 6.0, 0.85, { fill: C.white, line: C.line, bar: C.teal });
  addText(slide, "p95 对变异最敏感：固定工时 5.5 min → CV 0.75 时 7.3 min（+33%）", {
    x: 0.82,
    y: 6.12,
    w: 5.6,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.ink,
  });
  addText(slide, "指数分布（CV=1）把它推到 10.1 min；均值只小幅变化。", {
    x: 0.82,
    y: 6.42,
    w: 5.6,
    h: 0.3,
    fontSize: 9.5,
    color: C.slate,
  });

  card(slide, 6.85, 6.0, 5.85, 0.85, { fill: C.white, line: C.line, bar: C.amber });
  addText(slide, "耐心是需求侧杠杆：balk 3 min → 29.3% 流失；12 min → 3.2%。", {
    x: 7.07,
    y: 6.12,
    w: 5.5,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.ink,
  });
  addText(slide, "在“到达即评估等待”的规则下，reneging 很少真正触发。", {
    x: 7.07,
    y: 6.42,
    w: 5.4,
    h: 0.3,
    fontSize: 9.5,
    color: C.slate,
  });

  notes(
    slide,
    "变异与耐心（约 1 分钟）：左图是服务时间变异，固定工时下 p95 是 5.5 分钟，CV 0.75 时到 7.3 分钟，指数分布（CV=1）到 10.1 分钟，但均值变化很小——所以用平均等待评估体验会低估尾部风险。右图是顾客耐心，balk 阈值从 3 分钟放宽到 12 分钟，流失率从 29.3% 降到 3.2%。在“到达即评估等待”的规则下，reneging 几乎不触发，流失主要由 balking 决定。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 7
function slideBottleneck() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "09 / 供给侧");
  titleBlock(slide, "瓶颈会迁移：加设备不等于加产能", "The bottleneck is a property of the shop and its staff plan");

  framedImage(slide, path.join(ASSETS, "fig_tea_capacity.png"), 0.6, 1.95, 7.3, 4.5, {
    caption: "茶站容量 1–4（吧台人数同步）下的 p95 与利润：存在明确的“临界容量”",
  });

  card(slide, 8.15, 1.95, 4.55, 1.75, { fill: C.white, line: C.line, bar: C.teal, shadow: true });
  addText(slide, "临界容量（再多加不再划算）", {
    x: 8.38,
    y: 2.08,
    w: 4.1,
    h: 0.3,
    fontSize: 10,
    color: C.slate,
  });
  addText(slide, "λ=0.6 → 3   ·   λ=0.9 → 3   ·   λ=1.2 → 4", {
    x: 8.38,
    y: 2.42,
    w: 4.1,
    h: 0.45,
    fontSize: 17,
    bold: true,
    color: C.ink,
  });
  addText(slide, "利润最优容量：2 / 2 / 3", {
    x: 8.38,
    y: 2.95,
    w: 4.1,
    h: 0.3,
    fontSize: 11,
    color: C.tealDark,
  });
  addText(slide, "再多加一个茶站，边际利润转负。", {
    x: 8.38,
    y: 3.28,
    w: 4.1,
    h: 0.3,
    fontSize: 9.5,
    color: C.slate,
  });

  card(slide, 8.15, 3.95, 4.55, 2.5, { fill: C.mint, line: C.mint2 });
  addText(slide, "固定人力时，约束真的搬走了", {
    x: 8.38,
    y: 4.1,
    w: 4.1,
    h: 0.35,
    fontSize: 12,
    bold: true,
    color: C.tealDark,
  });
  addText(slide, "固定 2 名吧台，只加茶站：k≥2 之后，平均等待、p95、利润逐位相同，茶站利用率却从 85% 掉到 43%——约束已经从设备变成人力池。", {
    x: 8.38,
    y: 4.5,
    w: 4.1,
    h: 1.6,
    fontSize: 9.5,
    color: C.ink3,
    fit: "shrink",
  });

  notes(
    slide,
    "供给侧（约 1.2 分钟）：把流程拆成点单台、茶站、冰淇淋机、面包柜，员工带技能和班次。左图是茶站容量扫描：临界容量在 λ=0.6/0.9 时是 3，λ=1.2 时是 4，利润最优容量分别是 2/2/3。更关键的是固定人力对照：只加茶站不加工人，k≥2 后等待和利润完全不变，茶站利用率从 85% 掉到 43%——瓶颈已经从设备迁移到共享人力池。所以“加设备”不是万能药。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 8
function slideStrategy() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "07 / 供给侧");
  titleBlock(slide, "策略取决于瓶颈：快品优先不是万能药", "Policy value depends on where the slack sits");

  framedImage(slide, path.join(ASSETS, "fig_strategy.png"), 0.6, 1.95, 7.1, 4.35, {
    caption: "四种策略对比（配对、100 次重复、95% 置信区间）在两种瓶颈下的表现",
  });

  const cells = [
    ["茶站瓶颈", `split ${fmt(data.strategy.split_values[0].profit_per_hour.diff, 2)}/h`, C.amber],
    ["茶站瓶颈", `fast +${fmt(data.strategy.tea_fast.diff, 2)}/h`, C.teal],
    ["冰淇淋机瓶颈", `split +${fmt(data.strategy.split_values[2].profit_per_hour.diff, 2)}/h`, C.teal],
    ["冰淇淋机瓶颈", `fast +${fmt(data.strategy.ice_fast.diff, 2)}/h`, C.amber],
  ];
  cells.forEach((cell, index) => {
    const col = index % 2;
    const row = Math.floor(index / 2);
    const x = 7.95 + col * 2.4;
    const y = 1.95 + row * 1.35;
    card(slide, x, y, 2.25, 1.15, { fill: C.white, line: C.line, bar: cell[2] });
    addText(slide, cell[0], {
      x: x + 0.2,
      y: y + 0.13,
      w: 1.95,
      h: 0.25,
      fontSize: 8.5,
      color: C.slate,
    });
    addText(slide, cell[1], {
      x: x + 0.2,
      y: y + 0.42,
      w: 1.95,
      h: 0.55,
      fontSize: 13,
      bold: true,
      color: C.ink,
      fit: "shrink",
    });
  });

  card(slide, 7.95, 4.8, 4.85, 1.55, { fill: C.mint, line: C.mint2 });
  addText(slide, "怎么读这张图", {
    x: 8.17,
    y: 4.93,
    w: 4.4,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.tealDark,
  });
  addText(slide, "快品优先在冰淇淋机瓶颈下价值约为茶站瓶颈的两倍；而拆分交付在茶瓶颈下是亏的（−2.0/h），在冰淇淋瓶颈下收益很大（+16.0/h）。", {
    x: 8.17,
    y: 5.27,
    w: 4.4,
    h: 0.95,
    fontSize: 9.5,
    color: C.ink3,
    fit: "shrink",
  });

  addText(slide, "法则：先找瓶颈，再谈策略；快品通道只在“它自己的站台有富余”时值钱。", {
    x: 0.6,
    y: 6.5,
    w: 12.2,
    h: 0.35,
    fontSize: 11,
    bold: true,
    color: C.tealDark,
  });

  notes(
    slide,
    "策略（约 1 分钟）：左图是四种策略在两种瓶颈下的配对结果。茶站瓶颈时，拆分交付反而亏 2 元每小时，快品优先只值 1.3 元；换成冰淇淋机瓶颈，拆分变成 +16 元，快品优先也翻倍到 1.7 元。原因是快品通道只在它自己的站台有富余时才有意义。法则就是：先找瓶颈，再谈策略。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 9
function slideSkills() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "09 / 供给侧");
  titleBlock(slide, "技能与班次：同样工资，不同产出", "Same headcount, same wage bill: skill pooling and break placement");

  card(slide, 0.6, 1.95, 6.15, 4.55, { fill: C.white, line: C.line, bar: C.teal, shadow: true });
  addText(slide, "技能矩阵：通才比专职值钱", {
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
  addText(slide, `±${fmt(data.skills.generalist.ci95, 1)}，人数与工资完全相同`, {
    x: 0.85,
    y: 3.15,
    w: 5.6,
    h: 0.3,
    fontSize: 9.5,
    color: C.slate,
  });
  addImageFit(slide, path.join(ASSETS, "fig_skills.png"), 0.85, 3.55, 5.65, 2.65);
  addText(slide, `单向交叉培训只有 +${fmt(data.skills.cross.diff, 2)}/h：弹性必须双向才有用。`, {
    x: 0.85,
    y: 6.2,
    w: 5.6,
    h: 0.3,
    fontSize: 9.5,
    color: C.ink3,
  });

  card(slide, 7.0, 1.95, 5.7, 2.15, { fill: C.white, line: C.line, bar: C.amber, shadow: true });
  addText(slide, "错峰休息：把容量从峰值挪走", {
    x: 7.22,
    y: 2.08,
    w: 5.2,
    h: 0.3,
    fontSize: 13,
    bold: true,
    color: C.ink,
  });
  addText(slide, `峰值等待 5.19 → 7.37 min；利润 ${fmt(data.shifts.break_delta.diff, 1)}/h`, {
    x: 7.22,
    y: 2.45,
    w: 5.2,
    h: 0.35,
    fontSize: 12,
    bold: true,
    color: C.amber,
  });
  addText(slide, "虽然休息不付工资（工资账单 −7.8/h），但峰值容量缺口远大于这点节省。", {
    x: 7.22,
    y: 2.85,
    w: 5.2,
    h: 0.55,
    fontSize: 9.5,
    color: C.ink3,
    fit: "shrink",
  });
  addText(slide, "休息要放在峰间，不要放在峰上。", {
    x: 7.22,
    y: 3.5,
    w: 5.2,
    h: 0.3,
    fontSize: 10,
    bold: true,
    color: C.slate,
  });

  card(slide, 7.0, 4.3, 5.7, 2.2, { fill: C.mint, line: C.mint2 });
  addText(slide, "中班加一个吧台，但没加茶机", {
    x: 7.22,
    y: 4.43,
    w: 5.2,
    h: 0.3,
    fontSize: 13,
    bold: true,
    color: C.tealDark,
  });
  addText(slide, `峰值等待变化 ${fmt(data.shifts.mid_peak_delta.diff, 2)} ± ${fmt(data.shifts.mid_peak_delta.ci95, 2)} min（不显著）`, {
    x: 7.22,
    y: 4.8,
    w: 5.2,
    h: 0.35,
    fontSize: 11.5,
    bold: true,
    color: C.ink,
  });
  addText(slide, "峰值时约束是茶站而不是人数：多出来的工资只增加成本。", {
    x: 7.22,
    y: 5.2,
    w: 5.2,
    h: 0.5,
    fontSize: 9.5,
    color: C.ink3,
  });
  addText(slide, `利润 ${fmt(data.shifts.mid_delta.diff, 1)}/h`, {
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
    "技能与班次（约 1 分钟）：同样人数、同样工资，全员通才比专职分工多赚约 84.5 元每小时；而单向交叉培训几乎为 0，说明弹性必须双向。班次方面，错峰 30 分钟休息虽然省了 7.8 元工资，但峰值等待从 5.19 升到 7.37 分钟、利润下降 49 元每小时；中班加一个吧台但不加茶机，峰值等待几乎不变（+0.06 分钟，不显著），因为峰值时约束是茶站而不是人数。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 10
function slideInventory() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "10 / 库存");
  titleBlock(slide, "库存：满足率便宜，保质期贵", "Fill rate is cheap; lead time and shelf life are not");

  stat(slide, 0.6, 1.95, 4.0, fmt(data.inventory.baseline.fill_rate * 100, 1) + "%", "", "基线满足率（inventory_lean）", { accent: C.teal });
  stat(slide, 0.6, 3.65, 4.0, fmt(data.inventory.best_fill * 100, 2) + "%", "", `最佳满足率（利润基本不变）`, { accent: C.teal });
  stat(slide, 0.6, 5.35, 4.0, fmt(data.inventory.lead_fill["120.0"] * 100, 0) + "%", "", "提前期 120 min 时的满足率（240 min → 72%）", { accent: C.amber });

  framedImage(slide, path.join(ASSETS, "fig_inv_lead_time.png"), 5.0, 1.9, 7.7, 2.4, {
    caption: "提前期是悬崖：60 min 之后满足率与利润快速下滑",
  });
  framedImage(slide, path.join(ASSETS, "fig_inv_ceiling.png"), 5.0, 4.45, 7.7, 2.4, {
    caption: "易腐品：珍珠批量超过约 100 单位后，损耗开始出现",
  });

  addText(slide, "缺货时“混合单 → 茶”替代可挽回 +14.1/h；珍珠缺货时替代无效（共享原料）。", {
    x: 0.6,
    y: 6.85,
    w: 12.2,
    h: 0.3,
    fontSize: 9.5,
    color: C.slate,
  });

  notes(
    slide,
    "库存（约 1 分钟）：把满足率从 98% 提到 99.95% 几乎不花钱，利润只差约 0.1 元每小时；真正的悬崖是提前期——120 分钟时满足率掉到 80%，240 分钟只有 72%。易腐品更敏感，珍珠批量超过约 100 单位就开始出现损耗。缺货时用茶替代混合单能挽回 14 元每小时，但珍珠短缺时替代无效，因为共享同一原料。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 11
function slidePricing() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "12 / 经济");
  titleBlock(slide, "定价：用“服务中性”乘数，不用利润边界", "Price the peak, not the average: the service-neutral multiplier");

  framedImage(slide, path.join(ASSETS, "fig_econ_pricing.png"), 0.6, 1.9, 7.6, 4.55, {
    caption: "不同需求弹性下，利润与 p95 随高峰加价倍数的变化",
  });

  stat(slide, 8.45, 1.9, 4.25, "×" + fmt(data.pricing.service_neutral, 1), "", "服务中性乘数（ε = −0.5）", { accent: C.teal });
  stat(slide, 8.45, 3.35, 4.25, "+" + fmt(20, 0) + "–" + fmt(37, 0) + "%", "", "利润提升区间，客流保留 97.9%", { accent: C.teal });
  stat(slide, 8.45, 4.8, 4.25, fmt(data.pricing.neutral_peak_p95, 1), " min", "加价后峰值 p95（与基线接近）", { accent: C.amber });

  addText(slide, "为什么利润最优总在边界？模型只对留下来的顾客计等待成本，流失顾客没有计商誉损失。", {
    x: 8.45,
    y: 6.35,
    w: 4.3,
    h: 0.65,
    fontSize: 8.8,
    color: C.slate,
    fit: "shrink",
  });

  addText(slide, "建议引用 ×1.1–1.2：既能削峰，又不把 p95 推高。", {
    x: 0.6,
    y: 6.6,
    w: 7.6,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.tealDark,
  });

  notes(
    slide,
    "定价（约 1 分钟）：高峰加价会同时改变需求和等待。我们区分“利润最优”和“可决策”的两个量：利润最优多数落在测试边界，因为模型只对留下来的顾客计等待成本；真正可引用的是服务中性乘数——最大加价幅度内 p95 基本不变，ε=−0.5 时是 1.2 倍，利润提升 20–37%，客流保留 97.9%。建议引用 1.1–1.2 区间。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 12
function slideSlaFairness() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "12 / 经济");
  titleBlock(slide, "SLA 是转移支付，公平是尾部保护", "An SLA prices the miss; a fairness cap protects the tail");

  card(slide, 0.6, 1.95, 6.0, 4.3, { fill: C.white, line: C.line, bar: C.teal, shadow: true });
  addText(slide, "SLA：把失约变成钱", {
    x: 0.85,
    y: 2.08,
    w: 5.5,
    h: 0.35,
    fontSize: 14,
    bold: true,
    color: C.ink,
  });
  const slaRows = [
    ["承诺 3 min", "41.9%", "38.4 /h"],
    ["承诺 5 min", "61.4%", "25.5 /h"],
    ["承诺 8 min", "81.9%", "11.9 /h"],
  ];
  slide.addTable(
    [
      [
        { text: "承诺", options: { bold: true } },
        { text: "达成率", options: { bold: true } },
        { text: "成本", options: { bold: true } },
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
  addText(slide, "补偿额不改变服务水平：各档 p95 完全相同。SLA 的价值是把“失约成本”显式化，方便与加人手比较。", {
    x: 0.85,
    y: 4.6,
    w: 5.4,
    h: 0.8,
    fontSize: 9.3,
    color: C.slate,
    fit: "shrink",
  });
  addText(slide, "最高达成率 81.9%，不存在 100% 达成的档位。", {
    x: 0.85,
    y: 5.5,
    w: 5.4,
    h: 0.3,
    fontSize: 9.5,
    bold: true,
    color: C.tealDark,
  });

  card(slide, 6.9, 1.95, 5.8, 4.3, { fill: C.white, line: C.line, bar: C.amber, shadow: true });
  addText(slide, "公平：尾部保护，不是“更公平”的均值", {
    x: 7.15,
    y: 2.08,
    w: 5.3,
    h: 0.35,
    fontSize: 14,
    bold: true,
    color: C.ink,
  });
  addRich(
    slide,
    [
      { text: "−" + fmt(11, 0) + "%", options: { fontFace: FONT_NUM, fontSize: 34, bold: true, color: C.teal } },
      { text: "  p95", options: { fontSize: 12, color: C.slate } },
    ],
    { x: 7.15, y: 2.55, w: 3, h: 0.6 }
  );
  addText(slide, "用 5.06/h 的利润，换整体 p95 从 9.99 降到 8.86 min。", {
    x: 7.15,
    y: 3.18,
    w: 5.25,
    h: 0.3,
    fontSize: 10,
    color: C.ink3,
  });

  const fairRows = [
    ["类间 p95 极差", "2.27 → 2.22", "略降"],
    ["类间均值极差", "1.45 → 1.78", "上升"],
    ["每小时升级次数", "54.4", "可审计"],
  ];
  fairRows.forEach((row, index) => {
    const y = 3.68 + index * 0.52;
    card(slide, 7.15, y, 5.25, 0.44, { fill: index === 1 ? C.amberLight : C.mint, line: C.line, lineWidth: 0 });
    addText(slide, row[0], { x: 7.3, y: y + 0.09, w: 1.9, h: 0.25, fontSize: 8.8, color: C.ink3 });
    addText(slide, row[1], { x: 9.2, y: y + 0.09, w: 1.9, h: 0.25, fontSize: 8.8, bold: true, color: C.ink });
    addText(slide, row[2], { x: 11.2, y: y + 0.09, w: 1.0, h: 0.25, fontSize: 8.2, color: index === 1 ? C.amber : C.tealDark });
  });

  addText(slide, "注意口径：均值型 fairness_gap 上升，所以这是尾部保护，不是“更公平”的证据。", {
    x: 7.15,
    y: 5.35,
    w: 5.25,
    h: 0.5,
    fontSize: 8.8,
    color: C.slate,
    fit: "shrink",
  });
  addText(slide, "建议 cap 1.5–3 min：尾部改善明显，利润代价约 2%。", {
    x: 7.15,
    y: 5.95,
    w: 5.25,
    h: 0.3,
    fontSize: 9.5,
    bold: true,
    color: C.amber,
  });

  notes(
    slide,
    "SLA 与公平（约 1 分钟）：SLA 这一边，承诺 3/5/8 分钟对应达成率 41.9%、61.4%、81.9%，成本分别是 38.4、25.5、11.9 元每小时；补偿额不改变任何服务水平，所以 SLA 是转移支付，价值在于把失约成本显式化。公平这一边，老化上限用 5 元每小时换整体 p95 下降 11%，但均值型 fairness_gap 反而上升，所以我们只说“尾部保护”，不说“更公平”。建议 cap 放在 1.5–3 分钟。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 13
function slideBundle() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "13 / 组合");
  titleBlock(slide, "管理组合：把四层拧成一套配置", "One bundle: capacity, pricing, SLA and a fairness cap together");

  addRich(
    slide,
    [
      { text: "+" + fmt(data.management.paired_profit_gain, 1), options: { fontFace: FONT_NUM, fontSize: 46, bold: true, color: C.teal } },
      { text: " ± " + fmt(data.management.paired_profit_gain_ci95, 1) + " /h", options: { fontSize: 16, color: C.slate } },
    ],
    { x: 0.6, y: 1.95, w: 6, h: 0.8 }
  );
  addText(slide, `相对 campus_rush 基线：${fmt(data.management.baseline.profit_per_hour, 1)} → ${fmt(data.management.good_manager.profit_per_hour, 1)} /h（+49%）`, {
    x: 0.6,
    y: 2.8,
    w: 6.2,
    h: 0.35,
    fontSize: 11,
    color: C.ink3,
  });

  const rows = [
    ["指标", "基线", "组合"],
    ["利润 /h", fmt(data.management.baseline.profit_per_hour, 1), fmt(data.management.good_manager.profit_per_hour, 1)],
    ["p95 /min", fmt(data.management.baseline.los_p95, 1), fmt(data.management.good_manager.los_p95, 1)],
    ["流失 /日", fmt(data.management.baseline.balked, 1), fmt(data.management.good_manager.balked, 1)],
    ["SLA 达成", "—", fmt(data.management.good_manager.sla_attainment * 100, 1) + "%"],
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

  addText(slide, "单杠杆排名（利润/h）", {
    x: 7.25,
    y: 1.95,
    w: 5.2,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.slate,
  });
  const levers = [
    ["加第 4 名吧台", data.management.lever_ranking_by_profit[0].profit_delta_vs_baseline, C.teal],
    ["高峰定价 ×1.2", data.management.lever_ranking_by_profit[1].profit_delta_vs_baseline, C.teal],
    ["公平 cap 1.5", data.management.lever_ranking_by_profit[2].profit_delta_vs_baseline, C.amber],
    ["SLA 5 min", data.management.lever_ranking_by_profit[3].profit_delta_vs_baseline, C.amber],
  ];
  const maxAbs = Math.max(...levers.map((lever) => Math.abs(lever[1])));
  levers.forEach((lever, index) => {
    const y = 2.4 + index * 0.95;
    addText(slide, lever[0], {
      x: 7.25,
      y,
      w: 2.2,
      h: 0.3,
      fontSize: 9.5,
      color: C.ink3,
    });
    const barW = (Math.abs(lever[1]) / maxAbs) * 2.4;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 9.55,
      y: y + 0.03,
      w: lever[1] >= 0 ? barW : 0.05,
      h: 0.28,
      fill: { color: lever[2] },
      line: { color: lever[2], width: 0 },
    });
    addText(slide, (lever[1] >= 0 ? "+" : "") + fmt(lever[1], 1), {
      x: 12.1,
      y,
      w: 0.8,
      h: 0.3,
      fontSize: 9.5,
      bold: true,
      align: "right",
      color: lever[1] >= 0 ? C.tealDark : C.amber,
    });
  });

  card(slide, 7.25, 6.15, 5.45, 0.62, { fill: C.mint, line: C.mint2 });
  addText(slide, "容量第一、定价第二；公平和 SLA 是保护尾部的低成本工具。", {
    x: 7.45,
    y: 6.27,
    w: 5.1,
    h: 0.35,
    fontSize: 10,
    bold: true,
    color: C.tealDark,
    fit: "shrink",
  });

  notes(
    slide,
    "管理组合（约 1 分钟）：把加一名吧台、温和高峰定价、SLA 和公平上限放在同一套配置里，对比 campus_rush 基线，利润从 240 元提升到 358 元每小时，配对差值 +118.1 ± 5.1 元；p95 从 11.8 降到 5.7 分钟，流失从 101.7 降到 16.2。单杠杆排名是扩容第一、定价第二，公平上限和 SLA 是保护尾部的低成本工具。这不是牺牲服务换钱，而是同时改善利润与等待。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 14
function slideRules() {
  const slide = pres.addSlide();
  bg(slide, C.ink);
  kicker(slide, "14 / 结论", C.teal);
  titleBlock(slide, "四条管理规则", "Four rules the simulation supports", true);

  const rules = [
    ["01", "按峰值配置资源", "日均利用率不是决策指标；峰值形状本身就是成本。"],
    ["02", "先找瓶颈，再谈策略", "加设备之前先问：新的约束会搬到哪里？"],
    ["03", "保护尾部，而不是均值", "公平上限与“服务中性”加价作用在 p95 上，代价很小。"],
    ["04", "把 SLA 显式计价", "SLA 不改变排队，但它决定扩容与承诺如何比较。"],
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
      fontSize: 17,
      bold: true,
      color: C.white,
    });
    addText(slide, rule[2], {
      x: x + 0.25,
      y: y + 1.15,
      w: 5.3,
      h: 0.55,
      fontSize: 11,
      color: C.slateLight,
      fit: "shrink",
    });
  });

  addText(slide, "同一台引擎、同一套 2×2 策略矩阵：我们只是把课程模型里隐含的假设逐层显式化。", {
    x: 0.6,
    y: 6.55,
    w: 12.2,
    h: 0.3,
    fontSize: 10.5,
    color: C.slateLight,
  });

  notes(
    slide,
    "结论（约 45 秒）：我们把它压缩成四条规则。第一，按峰值配置资源，不要按日均利用率。第二，先找瓶颈再谈策略，因为加设备会让约束迁移。第三，保护尾部而不是均值：公平上限和服务中性加价都作用在 p95 上，代价很小。第四，把 SLA 显式计价，它不改善排队，但让扩容和承诺可以放在同一张账上比较。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 15
function slideEvidence() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "15 / 证据");
  titleBlock(slide, "可复现：证据链与边界", "What is reproducible, and what is only an archive");

  card(slide, 0.6, 1.95, 6.0, 1.5, { fill: C.white, line: C.line, bar: C.teal, shadow: true });
  addText(slide, "Python 引擎（可复现）", {
    x: 0.85,
    y: 2.08,
    w: 5.5,
    h: 0.3,
    fontSize: 13,
    bold: true,
    color: C.ink,
  });
  addText(slide, `${data.meta.tests} 条测试 · 16 个场景可重算 · 固定随机种子 · 纯标准库`, {
    x: 0.85,
    y: 2.42,
    w: 5.5,
    h: 0.35,
    fontSize: 10.5,
    color: C.ink3,
  });
  addText(slide, "报告与 demo 完全离线：零 JS 依赖、零外链，可 file:// 打开。", {
    x: 0.85,
    y: 2.8,
    w: 5.5,
    h: 0.35,
    fontSize: 9.5,
    color: C.slate,
  });

  card(slide, 0.6, 3.65, 6.0, 1.5, { fill: C.white, line: C.line, bar: C.amber, shadow: true });
  addText(slide, "场景库（可审计）", {
    x: 0.85,
    y: 3.78,
    w: 5.5,
    h: 0.3,
    fontSize: 13,
    bold: true,
    color: C.ink,
  });
  addText(slide, "16 个合成情境，每个记录 source / method / uncertainty；不冒充门店实测数据。", {
    x: 0.85,
    y: 4.12,
    w: 5.5,
    h: 0.55,
    fontSize: 10,
    color: C.ink3,
    fit: "shrink",
  });

  card(slide, 0.6, 5.35, 6.0, 1.35, { fill: C.white, line: C.line, bar: C.slate, shadow: true });
  addText(slide, "AnyLogic 模型（存档，不可重跑）", {
    x: 0.85,
    y: 5.48,
    w: 5.5,
    h: 0.3,
    fontSize: 13,
    bold: true,
    color: C.ink,
  });
  addText(slide, "模型快照与截图保留为历史证据；它们不参与本报告的任何一个数字。", {
    x: 0.85,
    y: 5.82,
    w: 5.5,
    h: 0.55,
    fontSize: 10,
    color: C.ink3,
    fit: "shrink",
  });

  framedImage(slide, path.join(ASSETS, "anylogic_e3.png"), 7.0, 1.95, 5.7, 4.75, {
    caption: "AnyLogic 存档截图（E3）：仅作历史对照，不可重跑",
  });

  notes(
    slide,
    "证据（约 45 秒）：所有数字都能用 Python 引擎重算：69 条测试、16 个场景、固定随机种子、纯标准库；报告和 demo 完全离线、无外链。场景库每个文件都写了来源、方法和不确定性，我们不说它是门店实测数据。AnyLogic 模型只作为存档证据，不能重跑，也不参与报告里的任何数字。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 16
function slideDemo() {
  const slide = pres.addSlide();
  bg(slide, C.ink);
  kicker(slide, "16 / 现场演示", C.teal);
  titleBlock(slide, "60 秒现场演示", "Three interactions, all precomputed", true);

  card(slide, 0.6, 1.95, 7.7, 4.85, { fill: C.white, line: C.line, shadow: true });
  addImageFit(slide, path.join(ASSETS, "demo.png"), 0.72, 2.05, 7.45, 4.6);

  const steps = [
    ["1", "切换场景 × 策略", "16 个情境，联动利润与 p95"],
    ["2", "拖动需求曲线滑块", "同一日均，峰越尖，尾部越差"],
    ["3", "播放排队时间轴", "一天的 arrival / start / done"],
  ];
  steps.forEach((step, index) => {
    const y = 2.1 + index * 1.35;
    addText(slide, step[0], {
      x: 8.55,
      y,
      w: 0.5,
      h: 0.4,
      fontFace: FONT_NUM,
      fontSize: 20,
      bold: true,
      color: C.teal,
    });
    addText(slide, step[1], {
      x: 9.1,
      y: y + 0.02,
      w: 3.6,
      h: 0.35,
      fontSize: 14,
      bold: true,
      color: C.white,
    });
    addText(slide, step[2], {
      x: 9.1,
      y: y + 0.38,
      w: 3.6,
      h: 0.35,
      fontSize: 9.5,
      color: C.slateLight,
      fit: "shrink",
    });
  });

  addText(slide, "预计算数据，浏览器不跑仿真：演示与报告是同一份结果。", {
    x: 8.55,
    y: 6.25,
    w: 4.2,
    h: 0.5,
    fontSize: 9.5,
    color: C.slateLight,
    fit: "shrink",
  });

  notes(
    slide,
    "演示（约 45 秒，视现场网络决定是否真开）：页面有三件事——切换场景和策略看指标联动；拖动需求曲线滑块，看同样的日均客流在更尖的峰下尾部如何变差；播放一天的排队时间轴动画。全部是预计算数据，浏览器不跑离散事件仿真，所以它和报告里的数字是同一份结果。"
  );
  return slide;
}

// ---------------------------------------------------------------- slide 17
function slideLimits() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "17 / 局限");
  titleBlock(slide, "局限与下一步", "What this model does not claim, and what we would do next");

  const limits = [
    ["合成场景", "所有情境都是教学假设 + 来源标注，绝对水平不是门店预测。"],
    ["单日模型", "没有跨日库存结转、疲劳与学习效应；一次运行代表一天。"],
    ["等待成本简化", "只对留下顾客计等待成本，所以定价利润最优落在边界。"],
    ["技能同质", "同一技能内员工同质；休息是固定窗口，不做个性化排班。"],
  ];
  limits.forEach((limit, index) => {
    const col = index % 2;
    const row = Math.floor(index / 2);
    const x = 0.6 + col * 6.15;
    const y = 1.95 + row * 1.6;
    card(slide, x, y, 5.85, 1.4, { fill: C.white, line: C.line, bar: index % 2 ? C.amber : C.slate });
    addText(slide, limit[0], {
      x: x + 0.25,
      y: y + 0.14,
      w: 5.3,
      h: 0.3,
      fontSize: 12,
      bold: true,
      color: C.ink,
    });
    addText(slide, limit[1], {
      x: x + 0.25,
      y: y + 0.5,
      w: 5.3,
      h: 0.75,
      fontSize: 9.3,
      color: C.ink3,
      fit: "shrink",
    });
  });

  card(slide, 0.6, 5.3, 12.15, 1.5, { fill: C.mint, line: C.mint2 });
  addText(slide, "下一步", {
    x: 0.85,
    y: 5.43,
    w: 2,
    h: 0.3,
    fontSize: 12,
    bold: true,
    color: C.tealDark,
  });
  addText(
    slide,
    "用一周带时间戳的订单数据校准到来曲线与制作时长  ·  把库存与排队耦合进多日模型  ·  加入顾客行为 A/B（早交付的真实价值）  ·  用真实排班数据替代固定休息窗口",
    {
      x: 0.85,
      y: 5.8,
      w: 11.6,
      h: 0.75,
      fontSize: 10,
      color: C.ink3,
      fit: "shrink",
    }
  );

  notes(
    slide,
    "局限（约 45 秒）：要诚实说清楚边界：场景是合成的，绝对水平不能当门店预测；模型是单日的，没有跨日库存结转；等待成本只对留下的顾客计费，所以定价利润最优会在边界；技能和休息也做了简化。下一步最值钱的是拿一周带时间戳的真实订单数据校准到来曲线和制作时长，然后把库存与排队真正耦合进多日模型。"
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
  addText(slide, "谢谢 · 欢迎提问", {
    x: 0.65,
    y: 2.55,
    w: 6,
    h: 0.5,
    fontSize: 20,
    color: C.mint2,
  });
  addText(slide, "报告与代码：github.com/dwan621/bubble-tea-shop-sim", {
    x: 0.65,
    y: 3.25,
    w: 6.4,
    h: 0.35,
    fontSize: 11,
    color: C.slateLight,
  });
  addText(slide, "在线报告：dwan621.github.io/bubble-tea-shop-sim", {
    x: 0.65,
    y: 3.6,
    w: 6.4,
    h: 0.35,
    fontSize: 11,
    color: C.slateLight,
  });

  addText(slide, "讲解分工（18 分钟 + 5 分钟 Q&A）", {
    x: 7.0,
    y: 1.45,
    w: 5.7,
    h: 0.35,
    fontSize: 12,
    bold: true,
    color: C.teal,
  });
  const team = [
    ["成员 A", "1–3 页", "开场 · 三个问题 · 模型", "0:00–3:00"],
    ["成员 B", "4–5 页", "实验设计 · 峰值", "3:00–5:30"],
    ["成员 C", "6–7 页", "变异与耐心 · 瓶颈", "5:30–8:00"],
    ["成员 D", "8–9 页", "策略 · 技能与班次", "8:00–10:30"],
    ["成员 E", "10–12 页", "库存 · 定价 · SLA/公平", "10:30–13:30"],
    ["成员 F", "13–18 页", "组合 · 结论 · 证据 · demo · 局限 · Q&A", "13:30–18:00"],
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
      w: 0.8,
      h: 0.3,
      fontSize: 8.5,
      color: C.teal,
    });
    addText(slide, member[2], {
      x: 9.0,
      y: y + 0.16,
      w: 2.8,
      h: 0.3,
      fontSize: 8.5,
      color: C.slateLight,
      fit: "shrink",
    });
    addText(slide, member[3], {
      x: 11.9,
      y: y + 0.16,
      w: 0.75,
      h: 0.3,
      fontSize: 7.5,
      color: C.slateLight,
      align: "right",
    });
  });

  addText(slide, "Q&A 分工：模型 A/C · 数据 B · 策略 D · 经济 E · 综合与演示 F", {
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
    "收尾（约 30 秒）：以上就是我们的研究。六个部分分别由 A–F 负责，时间从 0 到 18 分钟，最后 5 分钟 Q&A；模型实现、数据统计、运营策略、经济公平和现场演示各有负责人。报告、代码和交互 demo 都在 GitHub 上，欢迎提问。"
  );
  return slide;
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


// Hand-drawn horizontal bars: native charts put category labels on the zero
// axis, so negative bars cover them. Drawing the bars keeps every label clear.
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


// Hand-drawn horizontal bars: native charts put category labels on the zero
// axis, so negative bars cover them. Drawing the bars keeps every label clear.
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
// Images from the report are used for the overview/demo slides, but the
// quantitative slides use native PowerPoint charts: they stay legible when the
// deck is projected and the labels never collide.
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

function slidePeak() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "05 / 需求侧");
  titleBlock(slide, "峰值：日均利用率会骗人", "Same daily mean, very different peak: the average hides the cost");

  stat(slide, 0.6, 1.95, 3.7, "+" + fmt(data.peak.p95_peak_abs - data.peak.p95_flat_abs, 2), " min", "p95 等待（峰型 vs 平峰）", { accent: C.amber, h: 1.4 });
  stat(slide, 0.6, 3.5, 3.7, fmt(data.peak.balk_peak * 100, 1) + "%", "", `流失率（平峰 ${fmt(data.peak.balk_flat * 100, 1)}%）`, { accent: C.amber, h: 1.4 });
  stat(slide, 0.6, 5.05, 3.7, fmt(data.peak.profit_flat - data.peak.profit_peak, 1), " /h", `利润差（平峰 ${fmt(data.peak.profit_flat, 1)} → 峰型 ${fmt(data.peak.profit_peak, 1)}）`, { accent: C.amber, h: 1.4 });

  card(slide, 4.75, 1.95, 8.0, 4.55, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "每小时忙碌度（busy ratio）", {
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
      { name: "峰型", labels: data.charts.hourly.labels, values: data.charts.hourly.peak },
      { name: "平峰", labels: data.charts.hourly.labels, values: data.charts.hourly.flat },
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
  addText(slide, "同一日均客流，只改形状：峰型的午峰与晚峰明显更高，但日均利用率反而更低。", {
    x: 4.95,
    y: 6.22,
    w: 7.6,
    h: 0.25,
    fontSize: 9,
    color: C.slate,
  });
  addText(slide, "结论：排班要按峰值，不要按日均；峰值形状本身就是一个成本项。", {
    x: 0.6,
    y: 6.65,
    w: 12.2,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.tealDark,
  });

  notes(
    slide,
    "需求侧结论（约 1 分钟）：在日均客流完全相同的情况下，只把需求压成峰型，p95 等待增加 3.7 分钟，流失率从 6.9% 升到 15.1%，利润下降约 57 元/小时。注意日均利用率反而从 60.6% 降到 54.9%，因为流失顾客把工作带走了。所以“按日均利用率排班”会系统性地低估峰值风险。"
  );
  return slide;
}

function slideVariability() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "06 / 需求侧");
  titleBlock(slide, "变异与耐心：均值看不出的风险", "Variability and patience move the tail, not the mean");

  card(slide, 0.6, 1.95, 6.0, 4.05, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "服务时间变异：p95（λ = 1.2）", {
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
  addText(slide, "顾客耐心：流失率（λ = 1.2）", {
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
    [{ name: "流失率", labels: data.charts.patience.labels, values: data.charts.patience.abandon }],
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
  addText(slide, "p95 对变异最敏感：固定工时 5.5 min → CV 0.75 时 7.3 min（+33%）", {
    x: 0.82,
    y: 6.27,
    w: 5.55,
    h: 0.3,
    fontSize: 10.5,
    bold: true,
    color: C.ink,
  });
  addText(slide, "指数分布（CV=1）把它推到 10.1 min；均值只小幅变化。", {
    x: 0.82,
    y: 6.57,
    w: 5.55,
    h: 0.3,
    fontSize: 9.5,
    color: C.slate,
  });
  card(slide, 6.85, 6.15, 5.85, 0.85, { fill: C.white, line: C.line, bar: C.teal });
  addText(slide, "耐心是需求侧杠杆：balk 3 min → 29.3% 流失；12 min → 3.2%。", {
    x: 7.07,
    y: 6.27,
    w: 5.4,
    h: 0.3,
    fontSize: 10.5,
    bold: true,
    color: C.ink,
  });
  addText(slide, "在“到达即评估等待”规则下，reneging 很少真正触发。", {
    x: 7.07,
    y: 6.57,
    w: 5.4,
    h: 0.3,
    fontSize: 9.5,
    color: C.slate,
  });

  notes(
    slide,
    "变异与耐心（约 1 分钟）：左图是服务时间变异，固定工时下 p95 是 8.6 分钟，指数分布（CV=1）推到 15.3 分钟，但对数正态 CV 0.75 是 10.8 分钟；均值变化很小，所以用平均等待评估体验会低估尾部风险。右图是顾客耐心，balk 阈值从 3 分钟放宽到 12 分钟，流失率从 29.3% 降到 3.2%。在“到达即评估等待”的规则下，reneging 几乎不触发，流失主要由 balking 决定。"
  );
  return slide;
}

function slideBottleneck() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "07 / 供给侧");
  titleBlock(slide, "瓶颈会迁移：加设备不等于加产能", "The bottleneck is a property of the shop and its staff plan");

  card(slide, 0.6, 1.95, 7.15, 4.6, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "茶站容量（吧台人数同步）与 p95 等待", {
    x: 0.85,
    y: 2.08,
    w: 6.4,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.ink,
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
      catAxisTitle: "茶站数",
      valAxisTitle: "p95 / min",
    }
  );

  card(slide, 8.0, 1.95, 4.75, 1.9, { fill: C.white, line: C.line, bar: C.teal, shadow: true });
  addText(slide, "临界容量（再多加不再划算）", {
    x: 8.2,
    y: 2.08,
    w: 4.35,
    h: 0.28,
    fontSize: 10,
    color: C.slate,
  });
  const critRows = [["λ = 0.6", "3 个茶站"], ["λ = 0.9", "3 个茶站"], ["λ = 1.2", "4 个茶站"]];
  critRows.forEach((row, index) => {
    addText(slide, row[0], { x: 8.2, y: 2.42 + index * 0.4, w: 1.3, h: 0.3, fontSize: 11, color: C.ink3 });
    addText(slide, row[1], { x: 9.4, y: 2.42 + index * 0.4, w: 1.6, h: 0.3, fontSize: 11, bold: true, color: C.tealDark });
  });
  addText(slide, "利润最优：2 / 2 / 3 个茶站", {
    x: 8.2,
    y: 3.62,
    w: 4.3,
    h: 0.25,
    fontSize: 9,
    color: C.slate,
  });

  card(slide, 8.0, 4.0, 4.75, 2.55, { fill: C.mint, line: C.mint2 });
  addText(slide, "固定人力时，约束真的搬走了", {
    x: 8.2,
    y: 4.13,
    w: 4.35,
    h: 0.3,
    fontSize: 12,
    bold: true,
    color: C.tealDark,
  });
  addText(
    slide,
    "固定 2 名吧台、只加茶站：k≥2 之后平均等待、p95、利润逐位相同，茶站利用率却从 85% 掉到 43%——约束已经从设备变成人力池。",
    {
      x: 8.2,
      y: 4.5,
      w: 4.35,
      h: 1.9,
      fontSize: 9.5,
      color: C.ink3,
      fit: "shrink",
    }
  );

  notes(
    slide,
    "供给侧（约 1.2 分钟）：把流程拆成点单台、茶站、冰淇淋机、面包柜，员工带技能和班次。左图是茶站容量扫描：临界容量在 λ=0.6/0.9 时是 3，λ=1.2 时是 4，利润最优容量分别是 2/2/3。更关键的是固定人力对照：只加茶站不加工人，k≥2 后等待和利润完全不变，茶站利用率从 85% 掉到 43%——瓶颈已经从设备迁移到共享人力池。所以“加设备”不是万能药。"
  );
  return slide;
}

function slideStrategy() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "08 / 供给侧");
  titleBlock(slide, "策略取决于瓶颈：快品优先不是万能药", "Policy value depends on where the slack sits");

  card(slide, 0.6, 1.95, 7.15, 4.3, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "Δ 利润 / 小时（相对同场景 synchro + plain）", {
    x: 0.85,
    y: 2.08,
    w: 6.6,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.ink,
  });
  horizontalBars(
    slide,
    data.charts.contrasts.map((row) => ({ label: row[0], value: row[1] })),
    { x: 0.85, y: 2.4, w: 6.8, h: 3.7 },
    { zeroFrac: 0.34, fontSize: 10 }
  );

  const cells = [
    ["茶站瓶颈 · 拆分交付", fmt(data.charts.contrasts[1][1], 2) + " /h", C.amber],
    ["茶站瓶颈 · 快品优先", "+" + fmt(data.charts.contrasts[0][1], 2) + " /h", C.teal],
    ["冰淇淋瓶颈 · 拆分交付", "+" + fmt(data.charts.contrasts[3][1], 2) + " /h", C.teal],
    ["冰淇淋瓶颈 · 快品优先", "+" + fmt(data.charts.contrasts[2][1], 2) + " /h", C.amber],
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
    });
  });

  addText(slide, "法则：先找瓶颈，再谈策略；快品通道只在“它自己的站台有富余”时值钱。", {
    x: 0.6,
    y: 6.45,
    w: 12.2,
    h: 0.35,
    fontSize: 11,
    bold: true,
    color: C.tealDark,
  });

  notes(
    slide,
    "策略（约 1 分钟）：这张图是四种对比在两种瓶颈下的配对结果。茶站瓶颈时，拆分交付亏 2 元每小时，快品优先只值 1.3 元；换成冰淇淋机瓶颈，拆分变成 +16 元，快品优先也到 1.7 元。原因是快品通道只在它自己的站台有富余时才有意义。法则就是：先找瓶颈，再谈策略。"
  );
  return slide;
}

function slideInventory() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "10 / 库存");
  titleBlock(slide, "库存：满足率便宜，保质期贵", "Fill rate is cheap; lead time and shelf life are not");

  stat(slide, 0.6, 1.95, 3.9, fmt(data.inventory.baseline.fill_rate * 100, 1) + "%", "", "基线满足率", { accent: C.teal, h: 1.35 });
  stat(slide, 0.6, 3.5, 3.9, fmt(data.inventory.best_fill * 100, 2) + "%", "", "最佳满足率（利润基本不变）", { accent: C.teal, h: 1.35 });
  stat(slide, 0.6, 5.05, 3.9, fmt(data.charts.lead_time.fill[2] * 100, 0) + "%", "", "提前期 120 min 时满足率（240 min → 72%）", { accent: C.amber, h: 1.35 });

  card(slide, 4.75, 1.95, 8.0, 2.2, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "满足率 vs 补货提前期", {
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
  addText(slide, "易腐珍珠：批量超过约 100 单位后出现损耗", {
    x: 4.95,
    y: 4.4,
    w: 7.5,
    h: 0.28,
    fontSize: 10,
    bold: true,
    color: C.ink,
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

  addText(slide, "缺货时“混合单 → 茶”替代可挽回 +14.1/h；珍珠缺货时替代无效（共享原料）。", {
    x: 0.6,
    y: 6.78,
    w: 12.2,
    h: 0.28,
    fontSize: 9.5,
    color: C.slate,
  });

  notes(
    slide,
    "库存（约 1 分钟）：把满足率从 98% 提到 99.95% 几乎不花钱，利润只差约 0.1 元每小时；真正的悬崖是提前期——120 分钟时满足率掉到 80%，240 分钟只有 72%。易腐品更敏感，珍珠批量超过约 100 单位就开始出现损耗。缺货时用茶替代混合单能挽回 14 元每小时，但珍珠短缺时替代无效，因为共享同一原料。"
  );
  return slide;
}

function slidePricing() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "11 / 经济");
  titleBlock(slide, "定价：用“服务中性”乘数，不用利润边界", "Price the peak, not the average: the service-neutral multiplier");

  card(slide, 0.6, 1.95, 7.3, 4.35, { fill: C.white, line: C.line, shadow: true });
  addText(slide, "利润 / 小时 vs 高峰加价倍数（ε = −0.5）", {
    x: 0.85,
    y: 2.08,
    w: 6.7,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.ink,
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

  stat(slide, 8.2, 1.85, 4.55, "×" + fmt(data.pricing.service_neutral, 1), "", "服务中性乘数（ε = −0.5）", { accent: C.teal, h: 1.3 });
  stat(slide, 8.2, 3.25, 4.55, "+20–37%", "", "利润提升区间，客流保留 97.9%", { accent: C.teal, h: 1.3 });
  stat(slide, 8.2, 4.65, 4.55, fmt(data.pricing.neutral_peak_p95, 1), " min", "加价后峰值 p95（与基线接近）", { accent: C.amber, h: 1.3 });

  card(slide, 8.2, 6.08, 4.55, 0.62, { fill: C.amberLight, line: C.amber });
  addText(slide, "利润最优常落在边界：模型只对留下顾客计等待成本。", {
    x: 8.4,
    y: 6.16,
    w: 4.2,
    h: 0.48,
    fontSize: 8.8,
    color: C.ink3,
    fit: "shrink",
  });

  addText(slide, "建议引用 ×1.1–1.2：既能削峰，又不把 p95 推高。", {
    x: 0.6,
    y: 6.6,
    w: 7.3,
    h: 0.3,
    fontSize: 11,
    bold: true,
    color: C.tealDark,
  });

  notes(
    slide,
    "定价（约 1 分钟）：高峰加价会同时改变需求和等待。我们区分“利润最优”和“可决策”的两个量：利润最优多数落在测试边界，因为模型只对留下来的顾客计等待成本；真正可引用的是服务中性乘数——最大加价幅度内 p95 基本不变，ε=−0.5 时是 1.2 倍，利润提升 20–37%，客流保留 97.9%。建议引用 1.1–1.2 区间。"
  );
  return slide;
}

function slideBundle() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "13 / 组合");
  titleBlock(slide, "管理组合：把四层拧成一套配置", "One bundle: capacity, pricing, SLA and a fairness cap together");

  addRich(
    slide,
    [
      { text: "+" + fmt(data.management.paired_profit_gain, 1), options: { fontFace: FONT_NUM, fontSize: 46, bold: true, color: C.teal } },
      { text: " ± " + fmt(data.management.paired_profit_gain_ci95, 1) + " /h", options: { fontSize: 16, color: C.slate } },
    ],
    { x: 0.6, y: 1.95, w: 6, h: 0.8 }
  );
  addText(slide, `相对 campus_rush 基线：${fmt(data.management.baseline.profit_per_hour, 1)} → ${fmt(data.management.good_manager.profit_per_hour, 1)} /h（+49%）`, {
    x: 0.6,
    y: 2.8,
    w: 6.2,
    h: 0.35,
    fontSize: 11,
    color: C.ink3,
  });

  const rows = [
    ["指标", "基线", "组合"],
    ["利润 /h", fmt(data.management.baseline.profit_per_hour, 1), fmt(data.management.good_manager.profit_per_hour, 1)],
    ["p95 /min", fmt(data.management.baseline.los_p95, 1), fmt(data.management.good_manager.los_p95, 1)],
    ["流失 /日", fmt(data.management.baseline.balked, 1), fmt(data.management.good_manager.balked, 1)],
    ["SLA 达成", "—", fmt(data.management.good_manager.sla_attainment * 100, 1) + "%"],
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
  addText(slide, "单杠杆排名（Δ 利润/h）", {
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
  addText(slide, "容量第一、定价第二；公平和 SLA 是保护尾部的低成本工具。", {
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
    "管理组合（约 1 分钟）：把加一名吧台、温和高峰定价、SLA 和公平上限放在同一套配置里，对比 campus_rush 基线，利润从 240 元提升到 358 元每小时，配对差值 +118.1 ± 5.1 元；p95 从 11.8 降到 5.7 分钟，流失从 101.7 降到 16.2。单杠杆排名是扩容第一、定价第二，公平上限和 SLA 是保护尾部的低成本工具。这不是牺牲服务换钱，而是同时改善利润与等待。"
  );
  return slide;
}

function slideDemo() {
  const slide = pres.addSlide();
  bg(slide, C.ink);
  kicker(slide, "16 / 现场演示", C.teal);
  titleBlock(slide, "60 秒现场演示", "Three interactions, all precomputed", true);

  card(slide, 0.6, 1.95, 7.6, 4.8, { fill: C.white, line: C.line, shadow: true });
  addImageFit(slide, path.join(ASSETS, "demo_crop.png"), 0.72, 2.05, 7.35, 4.55);

  const steps = [
    ["1", "切换场景 × 策略", "16 个情境，联动利润与 p95"],
    ["2", "拖动需求曲线滑块", "同一日均，峰越尖，尾部越差"],
    ["3", "播放排队时间轴", "一天的 arrival / start / done"],
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
      fontSize: 14,
      bold: true,
      color: C.white,
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

  addText(slide, "预计算数据，浏览器不跑仿真：演示与报告是同一份结果。", {
    x: 8.5,
    y: 6.35,
    w: 4.3,
    h: 0.45,
    fontSize: 9.5,
    color: C.slateLight,
    fit: "shrink",
  });

  notes(
    slide,
    "演示（约 45 秒，视现场网络决定是否真开）：页面有三件事——切换场景和策略看指标联动；拖动需求曲线滑块，看同样的日均客流在更尖的峰下尾部如何变差；播放一天的排队时间轴动画。全部是预计算数据，浏览器不跑离散事件仿真，所以它和报告里的数字是同一份结果。"
  );
  return slide;
}

function slideLimits() {
  const slide = pres.addSlide();
  bg(slide, C.bg);
  kicker(slide, "17 / 局限");
  titleBlock(slide, "局限与下一步", "What this model does not claim, and what we would do next");

  const limits = [
    ["合成场景", "所有情境都是教学假设 + 来源标注，绝对水平不是门店预测。"],
    ["单日模型", "没有跨日库存结转、疲劳与学习效应；一次运行代表一天。"],
    ["等待成本简化", "只对留下顾客计等待成本，所以定价利润最优落在边界。"],
    ["技能同质", "同一技能内员工同质；休息是固定窗口，不做个性化排班。"],
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
    });
    addText(slide, limit[1], {
      x: x + 0.25,
      y: y + 0.48,
      w: 5.3,
      h: 0.65,
      fontSize: 10,
      color: C.ink3,
      fit: "shrink",
    });
  });

  addText(slide, "下一步", {
    x: 0.6,
    y: 5.0,
    w: 2,
    h: 0.3,
    fontSize: 12,
    bold: true,
    color: C.tealDark,
  });
  const nextSteps = [
    ["真实数据校准", "一周带时间戳订单 → 到来曲线与服务时长"],
    ["多日库存 + 排班", "库存结转与真实排班替代固定休息窗口"],
    ["顾客行为 A/B", "测量“早交付”对复购与转化的真实价值"],
    ["多品类扩展", "更多产品共享设备与原料，检验瓶颈结论"],
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
    });
    addText(slide, step[1], {
      x: x + 0.18,
      y: 5.82,
      w: 2.6,
      h: 0.85,
      fontSize: 9,
      color: C.ink3,
      fit: "shrink",
    });
  });

  notes(
    slide,
    "局限（约 45 秒）：要诚实说清楚边界：场景是合成的，绝对水平不能当门店预测；模型是单日的，没有跨日库存结转；等待成本只对留下的顾客计费，所以定价利润最优会在边界；技能和休息也做了简化。下一步最值钱的是拿一周带时间戳的真实订单数据校准到来曲线和制作时长，然后把库存与排队真正耦合进多日模型。"
  );
  return slide;
}

