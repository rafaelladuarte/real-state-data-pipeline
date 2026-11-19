"""Grava a demonstração do app (GIF para o README e MP4) com Selenium.

Uso: python docs/experiments/record_demo.py [url]
Requer o app e a API no ar (npm run dev / npm start) e `pip install pillow imageio imageio-ffmpeg`.
Saída: docs/media/demo.gif e docs/media/demo.mp4
"""
import io
import sys
import time
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173/?modo=aluguel"
OUT = Path(__file__).resolve().parents[1] / "media"
W, H = 1280, 800
FPS = 20

options = webdriver.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument(f"--window-size={W},{H}")
options.add_argument("--hide-scrollbars")
driver = webdriver.Chrome(options=options)
# Em headless parte da altura é moldura do navegador: ajusta para a área útil ser W x H
_inner = driver.execute_script("return [innerWidth, innerHeight]")
driver.set_window_size(W + (W - _inner[0]), H + (H - _inner[1]))
frames: list[tuple[Image.Image, int]] = []  # (imagem, duração em ms)


def snap(ms: int = 80) -> None:
    png = driver.get_screenshot_as_png()
    frames.append((Image.open(io.BytesIO(png)).convert("RGB"), ms))


def hold(ms: int) -> None:
    snap(ms)


def scroll(y_to: int, steps: int = 14, ms: int = 55) -> None:
    y_from = driver.execute_script("return window.scrollY")
    for i in range(1, steps + 1):
        t = i / steps
        eased = t * t * (3 - 2 * t)
        driver.execute_script("window.scrollTo(0, arguments[0])", y_from + (y_to - y_from) * eased)
        snap(ms)


def section_top(index: int) -> int:
    return driver.execute_script(
        "return Math.round(document.querySelectorAll('section.section')[arguments[0]]"
        ".getBoundingClientRect().top + window.scrollY) - 70", index)


def click(css: str, text: str | None = None, index: int = 0) -> None:
    elements = driver.find_elements(By.CSS_SELECTOR, css)
    if text:
        elements = [e for e in elements if e.text.strip() == text]
    elements[index].click()


def mouse_to(x: float, y: float) -> None:
    """Move o cursor por coordenadas da janela, sem o scroll automático do Selenium."""
    actions = ActionChains(driver)
    actions.w3c_actions.pointer_action.move_to_location(int(x), int(y))
    actions.perform()


def hover_bar(index: int) -> None:
    box = driver.execute_script(
        "const r = document.querySelectorAll('.recharts-bar-rectangle')[arguments[0]]"
        ".getBoundingClientRect(); return [r.x + r.width * 0.6, r.y + r.height / 2]",
        index,
    )
    mouse_to(*box)


def park_mouse() -> None:
    mouse_to(8, H - 8)


def wait_idle(expect_text: str | None = None) -> None:
    """Espera os dados novos (sem blocos recarregando e, opcionalmente, um texto na manchete)."""
    def ready(d):
        loading = d.find_elements(By.CSS_SELECTOR, ".block.is-loading")
        headline = d.find_element(By.CSS_SELECTOR, "h1").text
        return not loading and (expect_text is None or expect_text in headline)
    WebDriverWait(driver, 15).until(ready)
    time.sleep(0.5)


try:
    driver.get(URL)
    driver.execute_script("try{localStorage.setItem('theme','light')}catch(e){}")
    driver.get(URL)
    time.sleep(4)

    # 1) abertura: manchete e número de destaque (aluguel)
    hold(2200)

    # 2) gráfico de preço por bairro, com hover numa barra
    scroll(section_top(0))
    hold(900)
    hover_bar(2)
    time.sleep(0.5)
    hold(1700)
    park_mouse()

    # 3) a tabela equivalente do mesmo gráfico
    click(".link-btn", index=0)
    time.sleep(0.4)
    hold(1700)
    click(".link-btn", index=0)
    time.sleep(0.4)

    # 4) volta ao topo e troca para Venda: a página inteira muda
    scroll(0, steps=16)
    hold(700)
    click(".seg button", text="Venda")
    snap(250)  # o quadro mantém o conteúdo anterior enquanto carrega (sem piscar)
    wait_idle("comprar")
    hold(2400)

    # 5) mesmo gráfico, agora em venda, e a dispersão
    scroll(section_top(0))
    hold(1500)
    scroll(section_top(3), steps=22)
    hold(1700)

    # 6) tema escuro
    scroll(0, steps=22)
    click(".theme-btn")
    time.sleep(0.6)
    hold(2600)
finally:
    driver.quit()

OUT.mkdir(parents=True, exist_ok=True)

# GIF: 880 px de largura, paleta adaptativa de 128 cores, duração por quadro
gif_frames = [img.resize((880, 550), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=128)
              for img, _ in frames]
gif_frames[0].save(
    OUT / "demo.gif", save_all=True, append_images=gif_frames[1:], loop=0,
    duration=[ms for _, ms in frames], optimize=True, disposal=2,
)

# MP4: taxa constante, cada quadro repetido pelo tempo que fica na tela
with imageio.get_writer(OUT / "demo.mp4", fps=FPS, codec="libx264", quality=8,
                        macro_block_size=2, pixelformat="yuv420p") as writer:
    for img, ms in frames:
        arr = np.asarray(img)
        for _ in range(max(1, round(ms / 1000 * FPS))):
            writer.append_data(arr)

total = sum(ms for _, ms in frames) / 1000
print(f"{len(frames)} quadros, {total:.1f}s")
for name in ("demo.gif", "demo.mp4"):
    print(name, f"{(OUT / name).stat().st_size / 1e6:.2f} MB")
