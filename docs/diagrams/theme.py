"""Tema visual dos diagramas: os mesmos tokens do app (app/web/src/style.css).

Papel quente, um único salmão de identidade, títulos em Fraunces e o resto em Inter.
As fontes vêm de app/web/node_modules (rode `npm install` em app/web antes).
`render()` desenha um trecho de HTML com o Chrome headless e salva um PNG nítido (2x).
"""
import io
import tempfile
from pathlib import Path

from PIL import Image
from selenium import webdriver

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "app/web/node_modules/@fontsource-variable"
IMAGES = ROOT / "docs/images"

TOKENS = """
:root {
  --page: #fbf4ee; --surface: #fffaf6; --ink: #2a1f1c; --ink-2: #6b5a54; --muted: #735f57;
  --line: #ecdcd2; --axis: #d9c4b9; --accent: #e2634d; --accent-ink: #b4412e;
  --on-accent: #2a1f1c; --wash: #fde8de; --wash-2: #fbd5c4;
}
.dark {
  --page: #1d1513; --surface: #261c19; --ink: #f6ece6; --ink-2: #c9b6ad; --muted: #9c8a82;
  --line: #382a26; --axis: #4a3a35; --accent-ink: #f08a74; --wash: #3a2520; --wash-2: #52322a;
}
"""

BASE_CSS = f"""
@font-face {{
  font-family: "Fraunces Variable"; font-weight: 100 900;
  src: url("file://{FONTS}/fraunces/files/fraunces-latin-wght-normal.woff2") format("woff2");
}}
@font-face {{
  font-family: "Inter Variable"; font-weight: 100 900;
  src: url("file://{FONTS}/inter/files/inter-latin-wght-normal.woff2") format("woff2");
}}
{TOKENS}
* {{ box-sizing: border-box; margin: 0; }}
body {{ background: var(--page); color: var(--ink); font-family: "Inter Variable", system-ui, sans-serif;
  font-size: 14px; line-height: 1.45; -webkit-font-smoothing: antialiased; }}
.serif {{ font-family: "Fraunces Variable", Georgia, serif; font-weight: 500; letter-spacing: -0.02em;
  font-variation-settings: "opsz" 72; }}
.kicker {{ font-size: 12px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--accent-ink); }}
.mono {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }}
"""


def open_browser(width: int, height: int):
    """Chrome headless com a área útil exatamente width x height (sem a moldura do navegador)."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument(f"--window-size={width},{height}")
    options.add_argument("--hide-scrollbars")
    driver = webdriver.Chrome(options=options)
    inner = driver.execute_script("return [innerWidth, innerHeight]")
    driver.set_window_size(width + (width - inner[0]), height + (height - inner[1]))
    return driver


def screenshot(driver, crop: tuple[int, int, int, int] | None = None) -> Image.Image:
    image = Image.open(io.BytesIO(driver.get_screenshot_as_png())).convert("RGB")
    return image.crop(crop) if crop else image


def page(body: str, css: str, dark: bool, width: int) -> str:
    return (
        f"<!doctype html><meta charset='utf-8'><style>{BASE_CSS}{css}</style>"
        f"<body class='{'dark' if dark else ''}'><div id='canvas' style='width:{width}px'>{body}</div>"
    )


def render(html: str, out: Path, width: int, scale: int = 2) -> tuple[int, int]:
    """Desenha o HTML no Chrome headless e salva o elemento #canvas como PNG."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument(f"--force-device-scale-factor={scale}")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--allow-file-access-from-files")
    options.add_argument(f"--window-size={width + 40},1200")
    driver = webdriver.Chrome(options=options)
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(html)
        driver.get(f"file://{f.name}")
        driver.execute_async_script("const done = arguments[0]; document.fonts.ready.then(() => done(1));")
        height = driver.execute_script("return document.getElementById('canvas').offsetHeight")
        driver.set_window_size(width + 40, height + 140)
        png = driver.find_element("id", "canvas").screenshot_as_png
    finally:
        driver.quit()
    image = Image.open(io.BytesIO(png)).convert("RGB")
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, optimize=True)
    return image.size
