"""Captura as ferramentas reais (storage, Mongo, Postgres) e as coloca em molduras do app.

Uso: python docs/diagrams/build_captures.py
Requer, no ar: RustFS (9001), Mongo Express (8082) e Adminer (8083), apontando para os bancos
do projeto (veja o README). Saída em docs/images/capturas/.
"""
import base64
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from selenium.webdriver.common.by import By  # noqa: E402
from theme import IMAGES, open_browser, page, render, screenshot  # noqa: E402

OUT = IMAGES / "capturas"
ADMINER = "http://localhost:8083/?pgsql=host.docker.internal%3A5434&username=username&db=real_state"

# Saída real de uma execução (19/11/2026), usada na imagem de terminal
TERMINAL = [
    ("cmd", "docker ps"),
    ("dim", "NAMES                 IMAGE           STATUS"),
    ("out", "real_state_postgres   postgres:13     Up 2 hours"),
    ("out", "real_state_mongo      mongo:7.0       Up 2 hours"),
    ("out", "real_state_minio      rustfs/rustfs   Up About an hour"),
    ("gap", ""),
    ("cmd", "WORKER_ID=w1 python scripts/etl/extraction/property.py &"),
    ("cmd", "WORKER_ID=w2 python scripts/etl/extraction/property.py &"),
    ("out", "15:48:10 INFO  Worker w1 iniciado"),
    ("out", "15:48:12 INFO  [w2] anuncio/2026-11-19/2912557103.html.gz"),
    ("out", "15:48:16 INFO  [w1] anuncio/2026-11-19/2912889421.html.gz"),
    ("out", "15:48:19 INFO  [w2] anuncio/2026-11-19/2904909009.html.gz"),
    ("out", "15:48:21 INFO  [w1] anuncio/2026-11-19/2905368929.html.gz"),
    ("gap", ""),
    ("cmd", "python scripts/etl/extraction/parse_property.py"),
    ("out", "INFO  147 HTMLs para processar (reprocess=False)"),
    ("ok", "INFO  Qualidade: 147 ok, 0 erros, nulos {}"),
    ("gap", ""),
    ("cmd", "python scripts/etl/load/model.py"),
    ("ok", "INFO  Modelagem aplicada"),
]

FIGURES = [
    ("storage-s3", "Bronze · storage S3", "HTML bruto, comprimido",
     "344 objetos e 52 MiB no bucket real-state-html. Cada anúncio vira um arquivo "
     "anuncio/AAAA-MM-DD/&lt;id&gt;.html.gz, o que permite reparsear sem coletar de novo.", "RustFS · localhost:9001"),
    ("mongo-colecoes", "Silver · MongoDB", "Coleções da camada tratada",
     "A fila de links, os documentos brutos e tratados, os snapshots de preço e as métricas de execução.",
     "Mongo Express · localhost:8082"),
    ("mongo-qualidade", "Silver · qualidade", "Cada execução deixa suas métricas",
     "O parsing registra o total, os erros e a taxa de campos vazios antes de gravar. "
     "Aqui: 125 e 147 anúncios, 0 erros e 0% de nulos.", "Mongo Express · run_metrics"),
    ("postgres-tabelas", "Gold · PostgreSQL", "Tabelas e views do modelo",
     "Dimensões, o fato imovel, o histórico imovel_snapshot, o staging _treat_* e as 9 views de análise.",
     "Adminer · schema public"),
    ("postgres-view", "Gold · PostgreSQL", "A view imovel_ciclo_vida",
     "Calcula primeira e última coleta, dias no mercado e variação de preço de cada anúncio (438 registros).",
     "Adminer · imovel_ciclo_vida"),
]

FIG_CSS = """
.fig { padding: 40px 44px 48px; }
.fig h3 { font-size: 30px; line-height: 1.1; margin-top: 6px; }
.fig p { color: var(--ink-2); margin: 8px 0 22px; max-width: 78ch; font-size: 15px; }
.win { border: 1px solid var(--line); border-radius: 16px; overflow: hidden; background: #fff;
  box-shadow: 0 20px 56px rgba(80, 40, 25, 0.16); }
.bar { height: 38px; background: var(--wash); display: flex; align-items: center; gap: 8px; padding: 0 16px; }
.bar i { width: 11px; height: 11px; border-radius: 50%; background: var(--axis); }
.bar span { margin-left: 14px; font-size: 12.5px; color: var(--ink-2); }
.win img { display: block; width: 100%; }
.term { background: #1d1513; border-radius: 16px; overflow: hidden; box-shadow: 0 20px 56px rgba(80, 40, 25, 0.22); }
.term .bar { background: #2b201d; }
.term .bar i { background: #4a3a35; }
.term .bar span { color: #c9b6ad; }
.term pre { margin: 0; padding: 22px 26px 26px; font-size: 14px; line-height: 1.7; color: #f6ece6; }
.term .cmd::before { content: "$ "; color: #e2634d; font-weight: 700; }
.term .cmd { color: #fff; font-weight: 600; }
.term .dim { color: #9c8a82; }
.term .ok { color: #f08a74; }
"""


def capture(raw: dict[str, "Image"]) -> None:  # noqa: F821
    # RustFS: login e listagem dos arquivos do bucket
    d = open_browser(1440, 900)
    try:
        d.get("http://localhost:9001/rustfs/console/")
        time.sleep(3)
        d.find_element(By.CSS_SELECTOR, "input[name=accessKey]").send_keys("username")
        d.find_element(By.CSS_SELECTOR, "input[name=secretKey]").send_keys("password")
        next(b for b in d.find_elements(By.CSS_SELECTOR, "button") if "Conecte" in b.text).click()
        time.sleep(4)

        def click_text(text: str, exact: bool = False) -> None:
            """Espera e clica no elemento com esse texto que parece um link (cursor de mão)."""
            xp = (f"//*[normalize-space(text())='{text}']" if exact
                  else f"//*[contains(normalize-space(text()),'{text}')]")
            before = d.current_url

            def candidates():
                return [e for e in d.find_elements(By.XPATH, xp)
                        if d.execute_script("return getComputedStyle(arguments[0]).cursor", e) == "pointer"]

            deadline = time.time() + 20
            while not candidates():
                if time.time() > deadline:
                    raise RuntimeError(f"'{text}' não apareceu")
                time.sleep(0.5)
            time.sleep(2)  # a página renderiza em partes: deixa assentar antes de escolher o link
            # O primeiro candidato pode ser só a legenda de um gráfico, e o clique nativo não aciona o
            # link deste console; o clique via JavaScript aciona.
            d.execute_script("arguments[0].click()", candidates()[-1])
            for _ in range(24):  # a navegação do console é assíncrona: espera a URL mudar
                if d.current_url != before:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError(f"o clique em '{text}' não navegou")
            time.sleep(2)

        click_text("real-state-html", exact=True)
        click_text("anuncio/")
        click_text("2026-")
        raw["storage-s3"] = screenshot(d, (224, 0, 1440, 900))
    finally:
        d.quit()

    # Mongo Express: coleções e métricas de qualidade
    d = open_browser(1280, 900)
    try:
        d.get("http://localhost:8082/db/real_state")
        time.sleep(3)
        raw["mongo-colecoes"] = screenshot(d, (0, 0, 1280, 745))
        d.get("http://localhost:8082/db/real_state/run_metrics")
        time.sleep(3)
        raw["mongo-qualidade"] = screenshot(d, (60, 385, 1220, 900))
    finally:
        d.quit()

    # Adminer: tabelas e a view de ciclo de vida
    d = open_browser(1500, 900)
    try:
        d.get(ADMINER)
        time.sleep(1.5)
        d.find_element(By.NAME, "auth[password]").send_keys("password")
        d.find_element(By.CSS_SELECTOR, "input[type=submit]").click()
        time.sleep(2)
        d.get(ADMINER + "&ns=public")
        time.sleep(1.5)
        raw["postgres-tabelas"] = screenshot(d, (0, 0, 1500, 760))
        d.get(ADMINER + "&ns=public&select=imovel_ciclo_vida&limit=8")
        time.sleep(2)
        raw["postgres-view"] = screenshot(d, (0, 0, 1500, 620))
    finally:
        d.quit()


def data_uri(image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def figure_html(kicker: str, title: str, text: str, url: str, body: str) -> str:
    return (
        f"<div class='fig'><div class='kicker'>{kicker}</div><h3 class='serif'>{title}</h3><p>{text}</p>{body}</div>"
    )


def main() -> None:
    raw: dict = {}
    capture(raw)
    width = 1240
    for name, kicker, title, text, url in FIGURES:
        body = (
            f"<div class='win'><div class='bar'><i></i><i></i><i></i><span class='mono'>{url}</span></div>"
            f"<img src='{data_uri(raw[name])}'></div>"
        )
        size = render(page(figure_html(kicker, title, text, url, body), FIG_CSS, False, width),
                      OUT / f"{name}.png", width, scale=1.5)
        print(OUT.relative_to(IMAGES.parent.parent) / f"{name}.png", size)

    lines = "\n".join(
        f"<span class='{kind}'>{text}</span>" if kind != "gap" else "" for kind, text in TERMINAL
    )
    body = (
        "<div class='term'><div class='bar'><i></i><i></i><i></i><span class='mono'>terminal · saída real de "
        f"uma execução</span></div><pre class='mono'>{lines}</pre></div>"
    )
    text = ("Dois workers em paralelo guardam o HTML, o parsing passa pelo gate de qualidade e a modelagem "
            "é aplicada em uma transação.")
    size = render(page(figure_html("Orquestração", "A esteira em execução", text, "", body), FIG_CSS, False, width),
                  OUT / "terminal-pipeline.png", width, scale=1.5)
    print(OUT.relative_to(IMAGES.parent.parent) / "terminal-pipeline.png", size)


if __name__ == "__main__":
    main()
