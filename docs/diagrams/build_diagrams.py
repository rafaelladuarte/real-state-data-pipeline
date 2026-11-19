"""Gera os diagramas de arquitetura e do modelo de dados na estética do app.

Uso: python docs/diagrams/build_diagrams.py
Saída em docs/images/: arquitetura(.png|-dark.png) e modelo-de-dados(.png|-dark.png).
Requer Chrome, selenium, pillow e as fontes de app/web (npm install).
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from theme import IMAGES, page, render  # noqa: E402

# --------------------------------------------------------------------------- arquitetura

ARCH_CSS = """
.wrap { padding: 56px 56px 60px; }
.title { font-size: 46px; line-height: 1.05; margin-top: 8px; }
.sub { color: var(--ink-2); margin-top: 10px; font-size: 16px; }

.airflow { margin-top: 34px; background: var(--wash); border-radius: 20px; padding: 18px 22px; }
.af-head { display: flex; align-items: center; gap: 10px; font-size: 14px; }
.af-head b { font-size: 15px; }
.af-head .muted { color: var(--ink-2); }
.dot { width: 10px; height: 10px; border-radius: 50%; background: var(--accent); }
.dags { display: flex; align-items: stretch; gap: 14px; margin-top: 14px; }
.dag { flex: 1; background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 12px 16px; }
.dag:first-child { flex: 2.2; }
.dag-name { font-size: 13px; font-weight: 700; color: var(--accent-ink); }
.dag-steps { margin-top: 3px; color: var(--ink-2); font-size: 13px; }
.dag-arrow { align-self: center; color: var(--accent); font-weight: 700; font-size: 20px; }

.flow { display: grid; grid-template-columns: 1fr 36px 1fr 36px 1fr 36px 1fr 36px 1fr 36px 1fr; margin-top: 26px; align-items: stretch; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 20px; padding: 20px 18px 22px; }
.card.gold { border-top: 4px solid var(--accent); padding-top: 17px; }
.card.silver { background: var(--wash); border-color: transparent; }
.card-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 28px; }
.step { font-size: 12px; font-weight: 600; color: var(--muted); letter-spacing: 0.06em; text-transform: uppercase; }
.chip { font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; border-radius: 999px; padding: 3px 10px; }
.chip.bronze { border: 1.5px solid var(--accent-ink); color: var(--accent-ink); }
.chip.silver { background: var(--wash-2); color: var(--ink); }
.chip.gold { background: var(--accent); color: var(--on-accent); }
.card h3 { font-size: 24px; margin-top: 10px; line-height: 1.1; }
.card p { color: var(--ink-2); font-size: 13.5px; margin-top: 10px; }
.big { font-size: 20px; font-weight: 650; margin-top: 14px; letter-spacing: -0.02em; }
.items { list-style: none; padding: 0; margin-top: 14px; display: grid; gap: 12px; }
.items li b { display: block; font-size: 13.5px; font-weight: 650; }
.items li span { display: block; font-size: 12.5px; color: var(--ink-2); margin-top: 1px; }
.path { display: block; margin-top: 12px; font-size: 11.5px; background: var(--wash); border-radius: 8px; padding: 7px 9px; color: var(--ink); word-break: break-all; }
.note { margin-top: 16px; font-size: 12.5px; color: var(--accent-ink); font-weight: 600; }
.arrow { display: flex; align-items: center; justify-content: center; }

.foot { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 22px; }
.fchip { border: 1px dashed var(--axis); border-radius: 16px; padding: 14px 18px; }
.fchip b { font-size: 14px; }
.fchip span { display: block; color: var(--ink-2); font-size: 13px; margin-top: 3px; }
"""

ARROW = (
    '<div class="arrow"><svg width="36" height="24" viewBox="0 0 36 24" fill="none" stroke="var(--accent)" '
    'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12H29"/>'
    '<path d="M22 5l8 7-8 7"/></svg></div>'
)


def items(rows: list[tuple[str, str]]) -> str:
    return "<ul class='items'>" + "".join(f"<li><b>{t}</b><span>{d}</span></li>" for t, d in rows) + "</ul>"


def card(step: str, title: str, body: str, layer: str | None = None) -> str:
    chip = f"<span class='chip {layer}'>{layer.capitalize()}</span>" if layer else ""
    return (
        f"<div class='card {layer or ''}'><div class='card-top'><span class='step'>{step}</span>{chip}</div>"
        f"<h3 class='serif'>{title}</h3>{body}</div>"
    )


def architecture() -> str:
    cards = [
        card("1 · origem", "Fonte", (
            "<div class='big'>ZAP Imóveis</div>"
            "<p>Anúncios públicos de aluguel e venda de casas e apartamentos em Uberlândia.</p>"
            "<div class='note'>Proteção anti-bot (Cloudflare): não é contornada.</div>"
        )),
        card("2 · extração", "Coleta", items([
            ("Descoberta de links", "listagens em JSON-LD"),
            ("Fila com reserva atômica", "MongoDB · links_imoveis"),
            ("Workers Selenium ×N", "limite global ≈ 0,8 req/s"),
            ("Disjuntor anti-bloqueio", "para após 3 desafios seguidos"),
        ])),
        card("3 · bruta", "HTML", (
            "<div class='big'>Storage S3</div><p>RustFS. Cada página guardada comprimida.</p>"
            "<code class='path mono'>anuncio/AAAA-MM-DD/<br>&lt;id&gt;.html.gz</code>"
            "<div class='note'>Se o site mudar, reparseia sem recoletar.</div>"
        ), "bronze"),
        card("4 · tratamento", "Documentos", items([
            ("Parsing + gate de qualidade", "nulos ≤ 5% · erros ≤ 20%"),
            ("raw_imoveis → treat_imoveis", "MongoDB · dedupe por hash"),
            ("snapshots_imoveis", "preço a cada coleta"),
            ("run_metrics", "métricas por execução"),
        ]), "silver"),
        card("5 · carga", "Modelo", items([
            ("Staging → upsert", "uma transação, idempotente"),
            ("Dimensões e fato", "tipo, modo, endereço, imobiliária, imóvel"),
            ("imovel_snapshot", "histórico de preço"),
            ("9 views de análise", "ciclo de vida, médias, dispersão"),
        ]), "gold"),
        card("6 · consumo", "App", items([
            ("API Express", "somente leitura · ?modo="),
            ("App React", "aluguel e venda · claro e escuro"),
            ("Tabela equivalente", "em cada gráfico"),
        ])),
    ]
    flow = ARROW.join(cards)
    return f"""
<div class="wrap">
  <div class="kicker">Arquitetura</div>
  <h1 class="serif title">Do anúncio ao gráfico</h1>
  <p class="sub">Coleta responsável, camada bruta reprocessável e carga idempotente, orquestradas pelo Airflow.</p>
  <div class="airflow">
    <div class="af-head"><span class="dot"></span><b>Apache Airflow</b>
      <span class="muted">uma DAG por etapa, cada tarefa em um container</span></div>
    <div class="dags">
      <div class="dag"><div class="dag-name mono">extraction</div>
        <div class="dag-steps">requeue → links → workers ×N → parse → agências</div></div>
      <div class="dag-arrow">→</div>
      <div class="dag"><div class="dag-name mono">treatment</div>
        <div class="dag-steps">imóveis → imobiliárias</div></div>
      <div class="dag-arrow">→</div>
      <div class="dag"><div class="dag-name mono">load</div><div class="dag-steps">migrate → model</div></div>
    </div>
  </div>
  <div class="flow">{flow}</div>
  <div class="foot">
    <div class="fchip"><b>Qualidade e alertas</b><span>Gate de nulos e erros antes de gravar · run_metrics · webhook de falha</span></div>
    <div class="fchip"><b>Integração contínua</b><span>GitHub Actions: ruff · pytest com Mongo e Postgres · build do app e da imagem</span></div>
    <div class="fchip"><b>Coleta responsável</b><span>Ritmo limitado · retentativa com backoff · sem contornar proteções</span></div>
  </div>
</div>"""


# --------------------------------------------------------------------------- modelo de dados

ER_CSS = """
.er { position: relative; height: 1040px; }
.head { position: absolute; left: 60px; top: 44px; }
.title { font-size: 46px; line-height: 1.05; margin-top: 8px; }
.sub { color: var(--ink-2); margin-top: 10px; font-size: 16px; }
.t { position: absolute; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; overflow: hidden; }
.t.fact { border: 2px solid var(--accent); }
.th { height: 44px; display: flex; align-items: center; justify-content: space-between; padding: 0 14px;
  background: var(--wash); }
.th b { font-size: 15px; font-weight: 700; letter-spacing: -0.01em; }
.th em { font-style: normal; font-size: 10.5px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--accent-ink); }
.r { height: 28px; display: flex; align-items: center; gap: 7px; padding: 0 14px; border-top: 1px solid var(--line); }
.r .n { font-size: 13px; }
.r .ty { margin-left: auto; font-size: 11.5px; color: var(--muted); }
.r i { font-style: normal; font-size: 9.5px; font-weight: 800; letter-spacing: 0.04em; border-radius: 5px; padding: 1px 5px; }
.pk { background: var(--accent); color: var(--on-accent); }
.fk { border: 1.5px solid var(--accent-ink); color: var(--accent-ink); }
.uq { background: var(--wash-2); color: var(--ink); }
.more { height: 32px; display: flex; align-items: center; padding: 0 14px; border-top: 1px solid var(--line);
  color: var(--muted); font-size: 12px; }
.v { height: 26px; display: flex; align-items: center; gap: 9px; padding: 0 14px; border-top: 1px solid var(--line); font-size: 12px; }
.v::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--accent); flex: none; }
.tr { padding: 9px 14px; border-top: 1px solid var(--line); }
.tr b { font-size: 12.5px; }
.tr span { display: block; color: var(--ink-2); font-size: 12px; }
svg.lines { position: absolute; left: 0; top: 0; }
.pill { position: absolute; transform: translate(-50%, -50%); background: var(--accent); color: var(--on-accent);
  font-size: 10.5px; font-weight: 800; border-radius: 999px; padding: 1px 7px; line-height: 1.5; }
"""

ROW_H, HEAD_H = 28, 44

TABLES = {
    "tipo_imovel": dict(x=60, y=190, w=300, tag="dimensão", rows=[
        ("id_tipo", "serial", "pk"), ("tipo", "varchar(50)", "uq")]),
    "modo_imovel": dict(x=60, y=370, w=300, tag="dimensão", rows=[
        ("id_modo", "serial", "pk"), ("modo", "varchar(50)", "uq")]),
    "imovel": dict(x=620, y=150, w=480, tag="fato", fact=True, more="+ 4 colunas: imagens, telefones, outros e migração", rows=[
        ("id_imovel", "text · hash do anúncio", "pk"), ("id_imobiliaria", "int", "fk"),
        ("id_endereco_imovel", "int", "fk"), ("id_tipo_imovel", "int", "fk"), ("id_modo_imovel", "int", "fk"),
        ("titulo_imovel", "varchar(255)", ""), ("descricao_imovel", "text", ""), ("preco", "int", ""),
        ("quantidade_quartos", "int", ""), ("quantidade_banheiros", "int", ""), ("quantidade_vagas", "int", ""),
        ("quantidade_suites", "int", ""), ("area_m2", "int", ""), ("custo_m2", "numeric · trigger", ""),
        ("faixa_area", "varchar(50) · trigger", ""), ("data_cadastro_imovel", "date", ""),
        ("data_atualizacao_imovel", "date", ""), ("data_coleta_imovel", "date", "")]),
    "imobiliaria": dict(x=1340, y=150, w=320, tag="dimensão", rows=[
        ("id_imobiliaria", "serial", "pk"), ("id_endereco_imobiliaria", "int", "fk"),
        ("nome_imobiliaria", "varchar(255)", ""), ("credencial_imobiliaria", "varchar(100)", ""),
        ("quantidade_imovel", "int", ""), ("data_cadastro_imobiliaria", "date", ""),
        ("telefone_imobiliaria", "varchar(20)", ""), ("data_coleta_imobiliaria", "date", "")]),
    "endereco": dict(x=1340, y=510, w=320, tag="dimensão", rows=[
        ("id_endereco", "serial", "pk"), ("endereco", "varchar(250)", "uq"), ("bairro", "varchar(100)", ""),
        ("cidade", "varchar(100)", ""), ("estado", "varchar(2)", ""), ("cep", "varchar(10)", ""),
        ("rua", "varchar(100)", ""), ("numero", "int", "")]),
    "imovel_snapshot": dict(x=620, y=790, w=480, tag="histórico", rows=[
        ("id_imovel", "text", "pk fk"), ("data_coleta", "date", "pk"), ("preco", "int", ""),
        ("condominio", "int", ""), ("iptu", "int", "")]),
}

VIEWS = [
    "imovel_ciclo_vida", "media_preco_bairro_modo_tipo", "media_preco_modo_tipo", "distribuicao_bairro",
    "distribuicao_bairro_modo", "distribuicao_tipo", "distribuicao_modo", "dispersao_preco_quartos_area",
    "dispersao_faixa_area_modo_tipo",
]


def table_html(name: str, t: dict) -> str:
    badges = {"pk": "<i class='pk'>PK</i>", "fk": "<i class='fk'>FK</i>", "uq": "<i class='uq'>UQ</i>"}
    rows = "".join(
        f"<div class='r'><span class='n'>{col}</span>{''.join(badges[b] for b in flags.split())}"
        f"<span class='ty'>{ty}</span></div>"
        for col, ty, flags in t["rows"]
    )
    more = f"<div class='more'>{t['more']}</div>" if t.get("more") else ""
    return (
        f"<div class='t{' fact' if t.get('fact') else ''}' style='left:{t['x']}px;top:{t['y']}px;width:{t['w']}px'>"
        f"<div class='th'><b>{name}</b><em>{t['tag']}</em></div>{rows}{more}</div>"
    )


def row_y(name: str, column: str) -> float:
    t = TABLES[name]
    index = [c for c, _, _ in t["rows"]].index(column)
    return t["y"] + HEAD_H + index * ROW_H + ROW_H / 2


def modelo() -> str:
    cards = "".join(table_html(n, t) for n, t in TABLES.items())

    views = "".join(f"<div class='v mono'>{v}</div>" for v in VIEWS)
    cards += (
        "<div class='t' style='left:60px;top:560px;width:300px'>"
        "<div class='th'><b>Views de análise</b><em>9</em></div>" + views + "</div>"
    )
    cards += (
        "<div class='t' style='left:1340px;top:830px;width:320px'>"
        "<div class='th'><b>Triggers</b><em>em imovel</em></div>"
        "<div class='tr'><b class='mono'>atualiza_custo_m2</b><span>preço ÷ área, a cada insert e update</span></div>"
        "<div class='tr'><b class='mono'>calcular_faixa_area</b><span>faixas até 50 m² … acima de 200 m²</span></div></div>"
    )

    imovel, snap = TABLES["imovel"], TABLES["imovel_snapshot"]
    left, right = imovel["x"], imovel["x"] + imovel["w"]
    bottom = imovel["y"] + HEAD_H + len(imovel["rows"]) * ROW_H + 32
    paths, pills = [], []

    def link(points: list[tuple[float, float]]) -> None:
        paths.append("M" + " L".join(f"{x},{y}" for x, y in points))

    def pill(x: float, y: float, text: str) -> None:
        pills.append(f"<span class='pill' style='left:{x}px;top:{y}px'>{text}</span>")

    # imóvel -> tipo e modo (lado esquerdo)
    for target, fk, mid in (("tipo_imovel", "id_tipo_imovel", 490), ("modo_imovel", "id_modo_imovel", 490)):
        y_fk = row_y("imovel", fk)
        t = TABLES[target]
        y_pk = row_y(target, t["rows"][0][0])
        edge = t["x"] + t["w"]
        link([(left, y_fk), (mid, y_fk), (mid, y_pk), (edge, y_pk)])
        pill(left - 18, y_fk, "N")
        pill(edge + 18, y_pk, "1")

    # imóvel -> imobiliária e endereço (lado direito)
    for target, fk, mid in (("imobiliaria", "id_imobiliaria", 1220), ("endereco", "id_endereco_imovel", 1260)):
        y_fk = row_y("imovel", fk)
        t = TABLES[target]
        y_pk = row_y(target, t["rows"][0][0])
        link([(right, y_fk), (mid, y_fk), (mid, y_pk), (t["x"], y_pk)])
        pill(right + 18, y_fk, "N")
        pill(t["x"] - 18, y_pk, "1")

    # imobiliária -> endereço
    imob, end = TABLES["imobiliaria"], TABLES["endereco"]
    imob_bottom = imob["y"] + HEAD_H + len(imob["rows"]) * ROW_H
    link([(1500, imob_bottom), (1500, end["y"])])
    pill(1500, imob_bottom + 16, "N")
    pill(1500, end["y"] - 16, "1")

    # snapshot -> imóvel
    link([(860, bottom), (860, snap["y"])])
    pill(860, bottom + 16, "1")
    pill(860, snap["y"] - 16, "N")

    svg = (
        "<svg class='lines' width='1720' height='1040'><g fill='none' stroke='var(--accent)' stroke-width='2' "
        "stroke-linejoin='round' stroke-linecap='round'>"
        + "".join(f"<path d='{d}'/>" for d in paths) + "</g></svg>"
    )
    return f"""
<div class="er">
  <div class="head"><div class="kicker">PostgreSQL · camada gold</div>
    <h1 class="serif title">Modelo de dados</h1>
    <p class="sub">Dimensões, fato e histórico de preço. As views alimentam o app.</p></div>
  {svg}{cards}{''.join(pills)}
</div>"""


def main() -> None:
    jobs = {
        "arquitetura": (architecture(), ARCH_CSS, 1720),
        "modelo-de-dados": (modelo(), ER_CSS, 1720),
    }
    for name, (body, css, width) in jobs.items():
        for dark in (False, True):
            out = IMAGES / f"{name}{'-dark' if dark else ''}.png"
            size = render(page(body, css, dark, width), out, width)
            print(out.relative_to(IMAGES.parent.parent), size)


if __name__ == "__main__":
    main()
