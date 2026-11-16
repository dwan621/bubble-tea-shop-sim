# 展示材料 / Presentation

- **幻灯片**：`bubble-tea-shop-simulation.pptx`（18 页，16:9，中文为主，每页带演讲备注）
- **PDF 版**：`bubble-tea-shop-simulation.pdf`（便于分发与打印）
- **六人分工与讲稿**：`speaker-plan.md`
- **生成脚本**：`build_deck.js`（PptxGenJS）、`extract_data.py`（从 `results/*.json` 取数）、`render_assets.py`（把报告 SVG 与 demo 截图渲染成 PNG）

## 页面结构（18 页 / 18 分钟 + 5 分钟 Q&A）

| 页 | 内容 | 讲解人 |
|---|---|---|
| 1 | 标题与四层机制 | 成员 A |
| 2 | 三个问题、一个引擎 | 成员 A |
| 3 | 模型：共享员工池与四类订单 | 成员 A |
| 4 | 16 个场景 × 100 次重复 × 配对比较 | 成员 B |
| 5 | 峰值：日均利用率会骗人 | 成员 B |
| 6 | 变异与耐心 | 成员 C |
| 7 | 瓶颈会迁移 | 成员 C |
| 8 | 策略取决于瓶颈 | 成员 D |
| 9 | 技能与班次 | 成员 D |
| 10 | 库存：满足率便宜、保质期贵 | 成员 E |
| 11 | 定价：服务中性乘数 | 成员 E |
| 12 | SLA 与公平 | 成员 E |
| 13 | 管理组合 | 成员 F |
| 14 | 四条管理规则 | 成员 F |
| 15 | 可复现与证据边界 | 成员 F |
| 16 | 60 秒现场 demo | 成员 F |
| 17 | 局限与下一步 | 成员 F |
| 18 | Q&A 与分工 | 成员 F |

## 重新生成

```powershell
# 1) 数据（读取仓库根目录的 results/*.json）
python presentation/extract_data.py

# 2) 图表与截图（需要 Chrome/Edge；生成到 presentation/assets/）
python presentation/render_assets.py

# 3) 生成 PPTX（需要 Node + pptxgenjs）
node presentation/build_deck.js
```

`presentation/assets/` 与 `presentation/slide-png/` 是生成缓存，已加入 `.gitignore`；PPTX 与 PDF 已内嵌所需图片，无需这些目录也能打开。

## 注意

- 第 18 页的“成员 A–F”是占位符，请替换为真实姓名（`build_deck.js` 中 `slideTeam()` 与 `speaker-plan.md` 同步修改）。
- 所有数字来自 `results/*.json`；如果研究数字更新，重跑 `extract_data.py` 再生成即可。
- 默认语言为中文（术语保留英文），时长 18 分钟 + 5 分钟 Q&A；可在 `speaker-plan.md` 中按课程要求调整。
