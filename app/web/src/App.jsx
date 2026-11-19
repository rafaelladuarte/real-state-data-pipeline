import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis,
} from "recharts";

const brl = (v) =>
  Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const num = (v) => Number(v).toLocaleString("pt-BR");
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

/* Números dentro de títulos em serifa ficam em sans (dígitos alinhados e legíveis). */
const FIGURES = /(R\$\s?[\d.]+|\d[\d.,]*(?:%| dias)?)/g;
const figures = (text) =>
  String(text).split(FIGURES).map((part, i) => (i % 2 ? <span className="fig" key={i}>{part}</span> : part));

const MODOS = {
  aluguel: { verbo: "alugar", rotulo: "Aluguel mediano por mês" },
  venda: { verbo: "comprar", rotulo: "Preço mediano de venda" },
};

/* Mantém os dados anteriores enquanto recarrega (sem piscar nem pular o layout). */
function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, error: null, loading: true }));
    fetch(path)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((error) => alive && setState((s) => ({ ...s, error, loading: false })));
    return () => { alive = false; };
  }, [path]);
  return state;
}

function ThemeToggle() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem("theme"); } catch { return null; }
  });
  useEffect(() => {
    const root = document.documentElement;
    if (theme) root.setAttribute("data-theme", theme); else root.removeAttribute("data-theme");
    try {
      if (theme) localStorage.setItem("theme", theme); else localStorage.removeItem("theme");
    } catch { /* armazenamento indisponível: segue sem lembrar */ }
  }, [theme]);
  const effective = theme ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  return (
    <button
      className="theme-btn"
      onClick={() => setTheme(effective === "dark" ? "light" : "dark")}
      aria-label={`Mudar para o tema ${effective === "dark" ? "claro" : "escuro"}`}
    >
      {effective === "dark" ? "☀ Claro" : "☾ Escuro"}
    </button>
  );
}

/* ---------- Peças de gráfico ---------- */

function ChartTooltip({ active, payload, label, fmt }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tip">
      <div className="tip-value">{fmt(payload[0].value)}</div>
      <div className="tip-label">{label}</div>
    </div>
  );
}

function ScatterTip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tip">
      <div className="tip-value">{brl(p.preco)}</div>
      <div className="tip-label">{p.area_m2} m²</div>
    </div>
  );
}

function CategoryTick({ x, y, payload }) {
  const text = String(payload.value);
  const short = text.length > 21 ? `${text.slice(0, 20)}…` : text;
  return (
    <text x={x} y={y} dy={4} textAnchor="end" fill="var(--ink-2)" fontSize={13}>
      <title>{text}</title>
      {short}
    </text>
  );
}

/* Barras finas, ponta arredondada, valor na ponta; sem eixo X (todo valor está rotulado). */
function HBar({ data, x, y, fmt = num }) {
  return (
    <ResponsiveContainer width="100%" height={data.length * 32 + 8}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 76, bottom: 0, left: 0 }}>
        <XAxis type="number" hide domain={[0, "dataMax"]} />
        <YAxis
          type="category" dataKey={y} width={150} interval={0}
          axisLine={false} tickLine={false} tick={<CategoryTick />}
        />
        <Tooltip cursor={{ fill: "var(--wash)" }} content={<ChartTooltip fmt={fmt} />} />
        <Bar
          dataKey={x} fill="var(--accent)" barSize={14} radius={[0, 4, 4, 0]}
          activeBar={{ fill: "var(--accent-hover)" }} isAnimationActive={false}
        >
          <LabelList
            dataKey={x} position="right" formatter={fmt}
            style={{ fill: "var(--ink-2)", fontSize: 12.5, fontWeight: 600 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* Ponto com anel na cor da superfície e área de toque maior que a marca. */
function Dot({ cx, cy }) {
  if (cx == null || cy == null) return null;
  return (
    <g>
      <circle cx={cx} cy={cy} r={14} fill="transparent" />
      <circle
        cx={cx} cy={cy} r={4.5} fill="var(--accent)" fillOpacity={0.88}
        stroke="var(--surface)" strokeWidth={2}
      />
    </g>
  );
}

function DataTable({ rows, columns, caption }) {
  return (
    <div className="scroll">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>{columns.map((c) => <th key={c.key} className={c.num ? "num" : undefined}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key} className={c.num ? "num" : undefined}>
                  {c.fmt ? c.fmt(r[c.key]) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* Gráfico com a tabela equivalente a um clique (o gráfico nunca é a única forma de ler o dado). */
function ChartBlock({ state, columns, caption, children }) {
  const [asTable, setAsTable] = useState(false);
  const { data, error, loading } = state;
  if (error && !data) return <p className="msg">Não foi possível carregar.</p>;
  if (!data) return <p className="msg">Carregando…</p>;
  if (data.length === 0) return <p className="msg">Sem dados para mostrar.</p>;
  return (
    <div className={`block${loading ? " is-loading" : ""}`}>
      <div className="block-tools">
        <button className="link-btn" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}>
          {asTable ? "Ver gráfico" : "Ver como tabela"}
        </button>
      </div>
      {asTable ? <DataTable rows={data} columns={columns} caption={caption} /> : children(data)}
    </div>
  );
}

/* ---------- Estrutura editorial ---------- */

function Section({ kicker, title, lede, aside, children }) {
  return (
    <section className="section">
      <div className="split">
        <div className="split-text">
          <span className="kicker">{kicker}</span>
          <h2>{figures(title)}</h2>
          {lede && <p className="lede">{lede}</p>}
          {aside}
        </div>
        <div className="split-body">{children}</div>
      </div>
    </section>
  );
}

function FullSection({ kicker, title, lede, children }) {
  return (
    <section className="section section--full">
      <div className="head">
        <span className="kicker">{kicker}</span>
        <h2>{figures(title)}</h2>
        {lede && <p className="lede">{lede}</p>}
      </div>
      {children}
    </section>
  );
}

function Masthead({ destaques }) {
  const d = destaques.data;
  const modo = MODOS[d?.modo] ?? MODOS.aluguel;
  const tiles = d?.modo
    ? [
        ...d.por_tipo.map((t) => ({
          label: `${cap(t.tipo)} · mediana`, value: brl(t.mediana), note: `${num(t.quantidade)} anúncios`,
        })),
        { label: "Por metro quadrado", value: brl(d.preco_m2_mediano), note: "mediana" },
        {
          label: "Idade do anúncio", value: d.dias_mediana == null ? "—" : `${d.dias_mediana} dias`,
          note: "mediana na data da coleta",
        },
      ]
    : [];
  return (
    <header className="masthead">
      <span className="kicker">Uberlândia · MG</span>
      <h1 className="headline">Quanto custa {modo.verbo} em Uberlândia?</h1>
      {d?.modo && (
        <p className="dek">
          {num(d.total)} anúncios de {d.por_tipo.map((t) => t.tipo).join(" e ")}, coletados em {d.coletado_em}.
          Uma amostra das primeiras páginas de cada busca, não o mercado inteiro.
        </p>
      )}
      <div className="hero">
        <div>
          <div className="hero-label">{modo.rotulo}</div>
          <div className="hero-number">{d?.modo ? brl(d.preco_mediano) : "—"}</div>
          <p className="hero-note">Metade dos anúncios custa menos que isso, metade custa mais.</p>
        </div>
        <div className="tiles">
          {tiles.map((t) => (
            <div className="tile" key={t.label}>
              <div className="tile-label">{t.label}</div>
              <div className="tile-value">{t.value}</div>
              <div className="tile-note">{t.note}</div>
            </div>
          ))}
        </div>
      </div>
    </header>
  );
}

/* ---------- Seções de conteúdo ---------- */

function PrecoPorBairro() {
  const filtros = useApi("/api/filtros");
  const [modo, setModo] = useState("");
  const [tipo, setTipo] = useState("");
  const qs = new URLSearchParams({ ...(modo && { modo }), ...(tipo && { tipo }) });
  const state = useApi(`/api/preco-medio?${qs}`);
  const f = filtros.data || { modos: [], tipos: [] };
  const top = state.data?.[0];
  return (
    <Section
      kicker="01 · Preço"
      title={top ? `${top.bairro} lidera, com média de ${brl(top.media_preco)}` : "Onde o preço pesa mais"}
      lede="Preço médio por bairro, só com 3 ou mais anúncios, para um imóvel isolado não distorcer o resultado."
      aside={(
        <div className="filters">
          <select aria-label="Modo" value={modo} onChange={(e) => setModo(e.target.value)}>
            <option value="">Todos os modos</option>
            {f.modos.map((m) => <option key={m} value={m}>{cap(m)}</option>)}
          </select>
          <select aria-label="Tipo" value={tipo} onChange={(e) => setTipo(e.target.value)}>
            <option value="">Todos os tipos</option>
            {f.tipos.map((t) => <option key={t} value={t}>{cap(t)}</option>)}
          </select>
        </div>
      )}
    >
      <ChartBlock
        state={state}
        caption="Preço médio por bairro"
        columns={[
          { key: "bairro", label: "Bairro" },
          { key: "media_preco", label: "Preço médio", fmt: brl, num: true },
          { key: "quantidade", label: "Anúncios", num: true },
        ]}
      >
        {(data) => <HBar data={data} x="media_preco" y="bairro" fmt={brl} />}
      </ChartBlock>
    </Section>
  );
}

function Anuncios({ total }) {
  const state = useApi("/api/bairros");
  const top = state.data?.[0];
  const share = top && total ? Math.round((100 * top.quantidade) / total) : null;
  return (
    <Section
      kicker="02 · Oferta"
      title={top ? `${top.bairro} concentra ${share ?? "boa parte"}${share ? "%" : ""} dos anúncios` : "Onde estão os anúncios"}
      lede="Os 15 bairros com mais anúncios na amostra. A ordem das páginas do site influencia esse ranking."
    >
      <ChartBlock
        state={state}
        caption="Anúncios por bairro"
        columns={[{ key: "bairro", label: "Bairro" }, { key: "quantidade", label: "Anúncios", num: true }]}
      >
        {(data) => <HBar data={data} x="quantidade" y="bairro" />}
      </ChartBlock>
    </Section>
  );
}

function IdadeDoAnuncio({ mediana }) {
  const state = useApi("/api/tempo-mercado");
  return (
    <Section
      kicker="03 · Tempo"
      title={mediana == null ? "Quanto tempo um anúncio fica no ar" : `Metade dos anúncios tem até ${mediana} dias`}
      lede="Dias entre a criação do anúncio e a coleta, mediana por bairro (3 ou mais anúncios). Mede a idade do anúncio, não quanto tempo ele leva para sair."
    >
      <ChartBlock
        state={state}
        caption="Idade mediana do anúncio por bairro"
        columns={[
          { key: "bairro", label: "Bairro" },
          { key: "dias_mediana", label: "Dias (mediana)", num: true },
          { key: "quantidade", label: "Anúncios", num: true },
        ]}
      >
        {(data) => <HBar data={data} x="dias_mediana" y="bairro" fmt={(v) => `${v} dias`} />}
      </ChartBlock>
    </Section>
  );
}

function PrecoETamanho() {
  const state = useApi("/api/dispersao");
  return (
    <FullSection
      kicker="04 · Tamanho"
      title="Preço e metragem, anúncio por anúncio"
      lede="Cada ponto é um anúncio. Passe o cursor para ver o valor e a área."
    >
      <ChartBlock
        state={state}
        caption="Preço e área de cada anúncio"
        columns={[
          { key: "area_m2", label: "Área", fmt: (v) => `${v} m²`, num: true },
          { key: "preco", label: "Preço", fmt: brl, num: true },
        ]}
      >
        {(data) => (
          <ResponsiveContainer width="100%" height={380}>
            <ScatterChart margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--line)" />
              <XAxis
                type="number" dataKey="area_m2" name="Área" domain={[0, "dataMax"]}
                tickFormatter={(v) => `${v} m²`} tickLine={false} stroke="var(--axis)"
                tick={{ fill: "var(--ink-2)", fontSize: 12 }}
              />
              <YAxis
                type="number" dataKey="preco" name="Preço" tickFormatter={brl} width={84}
                axisLine={false} tickLine={false} tick={{ fill: "var(--ink-2)", fontSize: 12 }}
              />
              <Tooltip cursor={false} content={<ScatterTip />} />
              <Scatter data={data} shape={<Dot />} isAnimationActive={false} />
            </ScatterChart>
          </ResponsiveContainer>
        )}
      </ChartBlock>
    </FullSection>
  );
}

function VariacaoDePreco() {
  const state = useApi("/api/variacao-preco");
  const d = state.data;
  const coletas = d?.coletas.length ?? 0;
  const varia = d?.variacoes ?? [];
  const title = !d
    ? "O preço muda com o tempo?"
    : coletas < 2
      ? "O preço muda? Ainda é cedo para dizer"
      : varia.length === 0
        ? `Nenhum anúncio mudou de preço em ${coletas} coletas`
        : `${varia.length} anúncios mudaram de preço`;
  return (
    <FullSection
      kicker="05 · Variação"
      title={title}
      lede="Cada nova coleta guarda o preço do anúncio naquele dia, o que permite acompanhar reajustes."
    >
      {state.error && !d ? <p className="msg">Não foi possível carregar.</p> : !d ? <p className="msg">Carregando…</p> : coletas < 2 ? (
        <div className="note">
          Só há {coletas} coleta{coletas === 1 ? "" : "s"} até agora{d.coletas[0] ? `, de ${d.coletas[0].data}` : ""}.
          A variação aparece a partir da segunda coleta.
          <small>Os anúncios coletados há mais de 7 dias entram de novo na fila automaticamente.</small>
        </div>
      ) : varia.length > 0 ? (
        <DataTable
          caption="Anúncios com variação de preço entre coletas"
          rows={varia}
          columns={[
            { key: "titulo", label: "Anúncio" },
            { key: "bairro", label: "Bairro" },
            { key: "preco_inicial", label: "Antes", fmt: brl, num: true },
            { key: "preco_atual", label: "Agora", fmt: brl, num: true },
            { key: "variacao_pct", label: "Variação", fmt: (v) => `${v > 0 ? "+" : ""}${v}%`, num: true },
          ]}
        />
      ) : null}
    </FullSection>
  );
}

function ListaDeAnuncios() {
  const [bairro, setBairro] = useState("");
  const [quartos, setQuartos] = useState("");
  const [busca, setBusca] = useState({});
  useEffect(() => {
    const t = setTimeout(() => setBusca({ bairro, quartos }), 300);
    return () => clearTimeout(t);
  }, [bairro, quartos]);
  const qs = new URLSearchParams(Object.entries(busca).filter(([, v]) => v));
  const state = useApi(`/api/imoveis?${qs}`);
  const rows = state.data ?? [];
  return (
    <FullSection kicker="06 · Anúncios" title="Veja os anúncios, um a um" lede="Os 50 mais recentemente atualizados que combinam com a busca.">
      <div className="filters" style={{ marginTop: 0, marginBottom: 20 }}>
        <input aria-label="Buscar por bairro" placeholder="Buscar bairro" value={bairro} onChange={(e) => setBairro(e.target.value)} />
        <input
          aria-label="Mínimo de quartos" placeholder="Mín. quartos" type="number" min="0"
          value={quartos} onChange={(e) => setQuartos(e.target.value)}
        />
      </div>
      {state.error && !state.data ? <p className="msg">Não foi possível carregar.</p>
        : !state.data ? <p className="msg">Carregando…</p>
        : rows.length === 0 ? <p className="msg">Nenhum anúncio encontrado.</p>
        : (
          <div className={`block${state.loading ? " is-loading" : ""}`}>
            <DataTable
              caption={`${rows.length} anúncios`}
              rows={rows}
              columns={[
                { key: "titulo", label: "Anúncio" },
                { key: "bairro", label: "Bairro" },
                { key: "tipo", label: "Tipo", fmt: (v) => <span className="tag">{cap(v)}</span> },
                { key: "quartos", label: "Quartos", fmt: (v) => v ?? "—", num: true },
                { key: "area_m2", label: "Área", fmt: (v) => (v ? `${v} m²` : "—"), num: true },
                { key: "preco", label: "Preço", fmt: (v) => <strong>{brl(v)}</strong>, num: true },
              ]}
            />
          </div>
        )}
    </FullSection>
  );
}

export default function App() {
  const destaques = useApi("/api/destaques");
  const d = destaques.data;
  return (
    <div className="wrap">
      <div className="topbar">
        <span className="brand">Mercado imobiliário</span>
        <ThemeToggle />
      </div>
      <Masthead destaques={destaques} />
      <main>
        <PrecoPorBairro />
        <Anuncios total={d?.total} />
        <IdadeDoAnuncio mediana={d?.dias_mediana} />
        <PrecoETamanho />
        <VariacaoDePreco />
        <ListaDeAnuncios />
      </main>
      <footer className="footer">
        <p>
          Dados de anúncios públicos coletados e tratados por um pipeline de ETL próprio: coleta com ritmo limitado,
          HTML bruto guardado, carga idempotente no PostgreSQL. É uma amostra das primeiras páginas de cada busca,
          então os números descrevem a amostra, não o mercado inteiro.{" "}
          <a href="https://github.com/rafaelladuarte/real_state_data_pipeline">Código no GitHub</a>.
        </p>
      </footer>
    </div>
  );
}
