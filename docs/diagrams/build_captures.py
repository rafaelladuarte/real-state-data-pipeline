"""Captura as ferramentas reais (storage, Mongo, Postgres) e as coloca em molduras do app.

Uso: python docs/diagrams/build_captures.py
Requer, no ar e com dados: RustFS (9001), Mongo Express (8082) e pgAdmin (5050), todos do
docker-compose.yml (`docker compose --profile tools up -d`). Saída em docs/images/capturas/.
Todas as imagens são capturas reais da tela dessas ferramentas, dentro de uma moldura do app.
"""
import base64
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from selenium.webdriver.common.action_chains import ActionChains  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from theme import IMAGES, open_browser, page, render, screenshot  # noqa: E402

OUT = IMAGES / "capturas"
PGADMIN = "http://localhost:5050"
PG_SERVER = "real_state (gold)"

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
    ("postgres-tabelas", "Gold · PostgreSQL", "Tabelas do modelo",
     "Dimensões, o fato imovel, o histórico imovel_snapshot e o staging _treat_*, com a contagem de "
     "linhas de cada tabela (438 imóveis, 62 imobiliárias).",
     "pgAdmin · localhost:5050"),
    ("postgres-view", "Gold · PostgreSQL", "A view imovel_ciclo_vida",
     "Calcula dias no mercado e variação de preço de cada anúncio. Aqui, os 10 anúncios há mais tempo "
     "no mercado, consultados no Query Tool.",
     "pgAdmin · Query Tool"),
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

    # pgAdmin: estatísticas das tabelas e a view de ciclo de vida (Query Tool)
    d = open_browser(1700, 1200)
    try:
        d.get(f"{PGADMIN}/login")
        time.sleep(4)
        d.find_element(By.NAME, "email").send_keys("admin@email.com")
        d.find_element(By.NAME, "password").send_keys("admin")
        d.find_element(By.CSS_SELECTOR, "button[type=submit]").click()
        time.sleep(8)

        def row(label: str, exact: bool = False):
            xp = (f"//*[normalize-space(text())='{label}']" if exact
                  else f"//*[starts-with(normalize-space(text()),'{label}')]")
            deadline = time.time() + 20
            while time.time() < deadline:
                found = [e for e in d.find_elements(By.XPATH, xp) if e.is_displayed()]
                if found:
                    return found[0]
                time.sleep(0.5)
            raise RuntimeError(f"'{label}' não apareceu no pgAdmin")

        def open_node(label: str, exact: bool = False) -> None:
            row(label, exact).click()
            time.sleep(1)
            ActionChains(d).send_keys(Keys.ARROW_RIGHT).perform()
            time.sleep(3)

        open_node("Servers", exact=True)
        ActionChains(d).double_click(row(PG_SERVER, exact=True)).perform()
        time.sleep(3)
        if d.find_elements(By.XPATH, "//*[normalize-space(text())='Connect to Server']"):
            ActionChains(d).send_keys("password").send_keys(Keys.ENTER).perform()  # senha local do compose
            time.sleep(5)
        row("Login/Group Roles").click()
        ActionChains(d).send_keys(Keys.ARROW_LEFT).perform()
        time.sleep(1)
        open_node("Databases")
        open_node("real_state", exact=True)
        open_node("Schemas")
        open_node("public", exact=True)
        open_node("Tables")
        row("Tables").click()
        time.sleep(2)
        d.find_element(By.XPATH, "//*[normalize-space(text())='Statistics']").click()
        time.sleep(3)
        raw["postgres-tabelas"] = screenshot(d, (0, 0, 1700, 640))

        # Query Tool sobre o banco real_state
        row("real_state", exact=True).click()
        time.sleep(1)
        d.find_element(By.XPATH, "//*[normalize-space(text())='Tools']").click()
        time.sleep(1)
        d.find_element(By.XPATH, "//*[normalize-space(text())='Query Tool']").click()
        time.sleep(6)
        sql = ("SELECT bairro, modo, preco_atual, variacao_pct, dias_no_mercado FROM imovel_ciclo_vida "
               "ORDER BY dias_no_mercado DESC NULLS LAST LIMIT 10;")
        ActionChains(d).send_keys(sql).perform()
        time.sleep(1)
        ActionChains(d).send_keys(Keys.F5).perform()
        time.sleep(5)
        raw["postgres-view"] = screenshot(d, (0, 0, 1700, 1130))
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


if __name__ == "__main__":
    main()
