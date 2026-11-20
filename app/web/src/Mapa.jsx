import { useMemo, useState } from "react";
import { geoMercator, geoPath } from "d3-geo";

const LARGURA = 640;
/* Mistura da cor de identidade com o papel: 5 degraus, sequencial e válido nos dois temas. */
const DEGRAUS = [26, 44, 62, 80, 98];
const corDoGrau = (g) => `color-mix(in srgb, var(--accent) ${DEGRAUS[g]}%, var(--wash))`;

/* Quantis: uma casa muito cara não apaga a diferença entre os demais bairros. */
export function faixas(valores) {
  const v = valores.filter((x) => x != null).sort((a, b) => a - b);
  if (v.length === 0) return { grau: () => null, legenda: [] };
  const cortes = [1, 2, 3, 4].map((i) => v[Math.floor((v.length * i) / 5)]);
  const grau = (x) => cortes.filter((c) => c <= x).length;
  const legenda = DEGRAUS.map((_, g) => {
    const dentro = v.filter((x) => grau(x) === g);
    return dentro.length ? { grau: g, min: dentro[0], max: dentro[dentro.length - 1] } : null;
  }).filter(Boolean);
  return { grau, legenda };
}

export function Legenda({ legenda, fmt, semValor }) {
  return (
    <ul className="legenda" aria-label="Legenda do mapa">
      {legenda.map((l) => (
        <li key={l.grau}>
          <span className="swatch" style={{ background: corDoGrau(l.grau) }} />
          {l.min === l.max ? fmt(l.min) : `${fmt(l.min)} a ${fmt(l.max)}`}
        </li>
      ))}
      <li><span className="swatch swatch--vazio" />{semValor}</li>
    </ul>
  );
}

/* Mapa de contornos desenhado em SVG (sem mapa de fundo, funciona sem rede).
   `linhas`: bairro -> { valor, quantidade }; polígonos sem linha ou sem valor ficam em cinza. */
export default function Mapa({ geo, linhas, fmt, fmtDetalhe = fmt, rotuloValor }) {
  const [ativo, setAtivo] = useState(null);
  const desenho = useMemo(() => {
    const proj = geoMercator().fitWidth(LARGURA, geo);
    const path = geoPath(proj);
    const [[, y0], [, y1]] = path.bounds(geo);
    return {
      altura: Math.ceil(y1 - Math.max(0, y0)) + 2,
      formas: geo.features.map((f) => ({
        nome: f.properties.bairro, d: path(f), centro: path.centroid(f),
      })),
    };
  }, [geo]);
  const { grau } = useMemo(() => faixas([...linhas.values()].map((l) => l.valor)), [linhas]);

  return (
    <div className="mapa" onMouseLeave={() => setAtivo(null)}>
      <svg
        viewBox={`0 0 ${LARGURA} ${desenho.altura}`} role="group"
        aria-label="Mapa de Uberlândia colorido por bairro"
      >
        {desenho.formas.map((f) => {
          const l = linhas.get(f.nome);
          const g = l?.valor != null ? grau(l.valor) : null;
          const texto = l
            ? `${f.nome}: ${l.valor != null ? fmt(l.valor) : "sem valor (poucos anúncios)"}, ${l.quantidade} anúncios`
            : `${f.nome}: sem anúncios`;
          return (
            <path
              key={f.nome} d={f.d} tabIndex={0} aria-label={texto}
              className={`bairro${ativo?.nome === f.nome ? " is-ativo" : ""}`}
              style={{ fill: g == null ? "var(--line)" : corDoGrau(g) }}
              onMouseEnter={() => setAtivo({ ...f, l })}
              onFocus={() => setAtivo({ ...f, l })}
              onBlur={() => setAtivo(null)}
            />
          );
        })}
      </svg>
      {ativo && (
        <div
          className="tip mapa-tip" role="status"
          style={{ left: `${(ativo.centro[0] / LARGURA) * 100}%`, top: `${(ativo.centro[1] / desenho.altura) * 100}%` }}
        >
          <div className="tip-value">
            {ativo.l?.valor != null ? fmtDetalhe(ativo.l.valor) : "—"}
          </div>
          <div className="tip-label">{ativo.nome}</div>
          <div className="tip-label">
            {ativo.l
              ? `${ativo.l.quantidade} anúncios${ativo.l.valor == null ? ` · ${rotuloValor} só com 3 ou mais` : ""}`
              : "sem anúncios"}
          </div>
        </div>
      )}
    </div>
  );
}
