import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, CartesianGrid,
} from "recharts";

const ACCENT = "#2f6fed";
const brl = (v) => Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

function useApi(path) {
  const [state, setState] = useState({ data: null, error: null });
  useEffect(() => {
    let alive = true;
    setState({ data: null, error: null });
    fetch(path)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
      .then((data) => alive && setState({ data, error: null }))
      .catch((error) => alive && setState({ data: null, error }));
    return () => { alive = false; };
  }, [path]);
  return state;
}

function Card({ title, state, className = "", children }) {
  return (
    <section className={`card ${className}`}>
      <h2>{title}</h2>
      {state.error ? <p className="msg">Falha ao carregar.</p>
        : !state.data ? <p className="msg">Carregando…</p>
        : state.data.length === 0 ? <p className="msg">Sem dados.</p>
        : children(state.data)}
    </section>
  );
}

function HBar({ data, x, y, fmt }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, data.length * 26)}>
      <BarChart data={data} layout="vertical" margin={{ left: 40 }}>
        <XAxis type="number" tickFormatter={fmt} />
        <YAxis type="category" dataKey={y} width={110} />
        <Tooltip formatter={fmt} />
        <Bar dataKey={x} fill={ACCENT} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function PrecoMedio() {
  const filtros = useApi("/api/filtros");
  const [modo, setModo] = useState("");
  const [tipo, setTipo] = useState("");
  const qs = new URLSearchParams({ ...(modo && { modo }), ...(tipo && { tipo }) });
  const state = useApi(`/api/preco-medio?${qs}`);
  const f = filtros.data || { modos: [], tipos: [] };
  return (
    <Card title="Preço médio por bairro (top 15)" state={state} className="full">
      {(data) => (
        <>
          <div className="filters">
            <select value={modo} onChange={(e) => setModo(e.target.value)}>
              <option value="">Todos os modos</option>
              {f.modos.map((m) => <option key={m}>{m}</option>)}
            </select>
            <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="">Todos os tipos</option>
              {f.tipos.map((t) => <option key={t}>{t}</option>)}
            </select>
          </div>
          <HBar data={data} x="media_preco" y="bairro" fmt={brl} />
        </>
      )}
    </Card>
  );
}

function Imoveis() {
  const [bairro, setBairro] = useState("");
  const [quartos, setQuartos] = useState("");
  const [busca, setBusca] = useState({});
  useEffect(() => {
    const t = setTimeout(() => setBusca({ bairro, quartos }), 300);
    return () => clearTimeout(t);
  }, [bairro, quartos]);
  const qs = new URLSearchParams(Object.entries(busca).filter(([, v]) => v));
  const state = useApi(`/api/imoveis?${qs}`);
  return (
    <section className="card full">
      <h2>Imóveis</h2>
      <div className="filters">
        <input placeholder="Bairro" value={bairro} onChange={(e) => setBairro(e.target.value)} />
        <input placeholder="Mín. quartos" type="number" min="0" value={quartos} onChange={(e) => setQuartos(e.target.value)} />
      </div>
      {state.error ? <p className="msg">Falha ao carregar.</p>
        : !state.data ? <p className="msg">Carregando…</p>
        : state.data.length === 0 ? <p className="msg">Nenhum imóvel encontrado.</p>
        : (
          <div className="scroll">
            <table>
              <thead><tr><th>Título</th><th>Bairro</th><th>Tipo</th><th>Modo</th><th>Quartos</th><th>Área</th><th>Preço</th></tr></thead>
              <tbody>
                {state.data.map((i) => (
                  <tr key={i.id_imovel}>
                    <td>{i.titulo}</td><td>{i.bairro}</td><td>{i.tipo}</td><td>{i.modo}</td>
                    <td>{i.quartos ?? "—"}</td><td>{i.area_m2 ? `${i.area_m2} m²` : "—"}</td><td>{brl(i.preco)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </section>
  );
}

export default function App() {
  const bairros = useApi("/api/bairros");
  const resumo = useApi("/api/resumo");
  const dispersao = useApi("/api/dispersao");
  return (
    <>
      <header>
        <h1>Mercado imobiliário — Uberlândia/MG</h1>
        <p className="sub">Dados coletados por scraping e tratados no pipeline de ETL.</p>
      </header>
      <main className="grid">
        <PrecoMedio />
        <Card title="Imóveis por bairro (top 15)" state={bairros}>
          {(d) => <HBar data={d} x="quantidade" y="bairro" />}
        </Card>
        <Card title="Distribuição por tipo" state={{ ...resumo, data: resumo.data?.tipos }}>
          {(d) => <HBar data={d} x="quantidade" y="nome" />}
        </Card>
        <Card title="Preço × área (m²)" state={dispersao} className="full">
          {(d) => (
            <ResponsiveContainer width="100%" height={320}>
              <ScatterChart>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" dataKey="area_m2" name="Área" unit=" m²" />
                <YAxis type="number" dataKey="preco" name="Preço" tickFormatter={brl} width={90} />
                <Tooltip formatter={(v, n) => (n === "Preço" ? brl(v) : v)} />
                <Scatter data={d} fill={ACCENT} />
              </ScatterChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Imoveis />
      </main>
    </>
  );
}
