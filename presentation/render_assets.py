"""Render report figures and a demo screenshot to PNG for the slide deck."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

FIGURES = [
    "demand_hourly",
    "variability",
    "patience",
    "tea_capacity",
    "bottleneck_utils",
    "strategy",
    "skills",
    "shifts",
    "inv_lead_time",
    "inv_ceiling",
    "econ_pricing",
    "econ_sla",
    "econ_fairness",
    "econ_manager",
    "scenario_compare",
    "baseline_policies",
]


def find_chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("no Chrome/Edge executable found")


def svg_size(text: str) -> tuple[float, float]:
    match = re.search(r'viewBox="([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)"', text)
    if match:
        width = float(match.group(3))
        height = float(match.group(4))
    else:
        width = float(re.search(r'width="([\d.]+)', text).group(1))
        height = float(re.search(r'height="([\d.]+)', text).group(1))
    return width, height


def screenshot(chrome: str, html_path: Path, out_path: Path, width: int, height: int, scale: float = 2) -> None:
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-sandbox",
        f"--force-device-scale-factor={scale}",
        f"--window-size={width},{height}",
        f"--screenshot={out_path}",
        html_path.as_uri(),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)


def render_svg(chrome: str, name: str) -> None:
    source = ROOT / "docs" / "figures-layers" / f"fig_{name}.svg"
    svg = source.read_text(encoding="utf-8")
    svg = re.sub(r"<\?xml[^>]*\?>", "", svg).strip()
    width, height = svg_size(svg)
    scale = 2
    px_w, px_h = int(width), int(height)
    html = (
        "<html><head><meta charset='utf-8'><style>"
        "html,body{margin:0;padding:0;background:#ffffff;}"
        f"svg{{display:block;width:{px_w}px;height:{px_h}px;}}"
        "</style></head><body>"
        f"{svg}</body></html>"
    )
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "figure.html"
        html_path.write_text(html, encoding="utf-8")
        out = ASSETS / f"fig_{name}.png"
        screenshot(chrome, html_path, out, px_w, px_h, scale)
    with Image.open(ASSETS / f"fig_{name}.png") as image:
        image = image.convert("RGB")
        if image.width > 2000:
            ratio = 2000 / image.width
            image = image.resize((2000, int(image.height * ratio)), Image.LANCZOS)
        image.save(ASSETS / f"fig_{name}.png", optimize=True)
    print(f"rendered fig_{name}.png")


def render_demo(chrome: str) -> None:
    demo = ROOT / "demo" / "index.html"
    out = ASSETS / "demo.png"
    screenshot(chrome, demo, out, 1600, 1040, scale=2)
    with Image.open(out) as image:
        image = image.convert("RGB")
        # trim a uniform bottom margin if the page is shorter than the viewport
        pixels = image.load()
        bottom = image.height
        for y in range(image.height - 1, 0, -1):
            row = [pixels[x, y] for x in range(0, image.width, 40)]
            if any(sum(px) < 740 * 3 for px in row):
                bottom = y + 1
                break
        image = image.crop((0, 0, image.width, bottom))
        ratio = 2200 / image.width
        image = image.resize((2200, int(image.height * ratio)), Image.LANCZOS)
        image.save(out, optimize=True)
    print(f"rendered demo.png ({Image.open(out).size})")


def copy_anylogic() -> None:
    source = ROOT / "docs" / "assets" / "slides" / "E_series" / "E3.png"
    target = ASSETS / "anylogic_e3.png"
    shutil.copyfile(source, target)
    print("copied anylogic_e3.png")


def main() -> None:
    chrome = find_chrome()
    print("chrome:", chrome)
    for name in FIGURES:
        render_svg(chrome, name)
    render_demo(chrome)
    copy_anylogic()


if __name__ == "__main__":
    main()
