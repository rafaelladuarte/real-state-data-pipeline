import express from "express";
import cors from "cors";
import pg from "pg";
import { carregarChaves, normalizar } from "./bairros.js";

const pool = new pg.Pool({
  connectionString:
    process.env.DATABASE_URL ||
    "postgresql://username:password@localhost:5434/real_state",
});

const app = express();
app.use(cors());

// Polígonos do mapa (gerados por scripts/geo/): chave do nome -> { bairro, codigo, chaves }
const POLIGONOS = carregarChaves(
  process.env.BAIRROS_GEOJSON ||
    new URL("../web/public/bairros-uberlandia.geojson", import.meta.url).pathname
);

// Consulta somente leitura sobre as views de scripts/etl/modeling/create_views_dash.sql
const q = (sql, params = []) => pool.query(sql, params).then((r) => r.rows);
const route = (path, handler) =>
  app.get(path, async (req, res) => {
    try {
      res.json(await handler(req));
    } catch (err) {
      console.error(err);
      res.status(500).json({ error: "erro ao consultar o banco" });
    }
  });

route("/api/health", () => ({ ok: true }));

route("/api/resumo", async () => {
  const [tipos, modos] = await Promise.all([
    q("SELECT tipo AS nome, quantidade::int FROM distribuicao_tipo ORDER BY 2 DESC"),
    q("SELECT modo AS nome, count::int AS quantidade FROM distribuicao_modo ORDER BY 2 DESC"),
  ]);
  return { tipos, modos };
});

route("/api/bairros", (req) =>
  q(
    `SELECT e.bairro, COUNT(*)::int AS quantidade
     FROM imovel i
     JOIN endereco e ON e.id_endereco = i.id_endereco_imovel
     JOIN modo_imovel m ON m.id_modo = i.id_modo_imovel
     WHERE e.bairro IS NOT NULL AND ($1::text IS NULL OR m.modo = $1)
     GROUP BY e.bairro ORDER BY quantidade DESC LIMIT 15`,
    [req.query.modo || null]
  )
);

route("/api/preco-medio", (req) => {
  const { modo, tipo } = req.query;
  // Mínimo de 3 anúncios por bairro para a média não refletir um único imóvel
  return q(
    `SELECT e.bairro, ROUND(AVG(i.preco))::float AS media_preco,
            COUNT(*)::int AS quantidade
     FROM imovel i
     JOIN endereco e ON e.id_endereco = i.id_endereco_imovel
     JOIN tipo_imovel t ON t.id_tipo = i.id_tipo_imovel
     JOIN modo_imovel m ON m.id_modo = i.id_modo_imovel
     WHERE e.bairro IS NOT NULL
       AND ($1::text IS NULL OR m.modo = $1)
       AND ($2::text IS NULL OR t.tipo = $2)
     GROUP BY e.bairro
     HAVING COUNT(*) >= 3
     ORDER BY media_preco DESC LIMIT 15`,
    [modo || null, tipo || null]
  );
});

// Mediana de dias entre a criação do anúncio e a última coleta (outliers pesam menos)
route("/api/tempo-mercado", (req) => {
  const { modo, tipo } = req.query;
  return q(
    `SELECT bairro,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dias_no_mercado))::int AS dias_mediana,
            COUNT(*)::int AS quantidade
     FROM imovel_ciclo_vida
     WHERE bairro IS NOT NULL AND dias_no_mercado IS NOT NULL AND dias_no_mercado >= 0
       AND ($1::text IS NULL OR modo = $1)
       AND ($2::text IS NULL OR tipo = $2)
     GROUP BY bairro
     HAVING COUNT(*) >= 3
     ORDER BY dias_mediana DESC LIMIT 15`,
    [modo || null, tipo || null]
  );
});

// Histórico de preço: datas de coleta e anúncios com variação
route("/api/variacao-preco", async (req) => {
  const modo = req.query.modo || null;
  const [coletas, variacoes] = await Promise.all([
    q(`SELECT TO_CHAR(s.data_coleta, 'DD/MM/YYYY') AS data, COUNT(*)::int AS quantidade
       FROM imovel_snapshot s
       JOIN imovel i ON i.id_imovel = s.id_imovel
       JOIN modo_imovel m ON m.id_modo = i.id_modo_imovel
       WHERE ($1::text IS NULL OR m.modo = $1)
       GROUP BY s.data_coleta ORDER BY s.data_coleta`, [modo]),
    q(`SELECT c.id_imovel, i.titulo_imovel AS titulo, c.bairro, c.tipo,
               c.preco_inicial, c.preco_atual, c.variacao_pct::float AS variacao_pct,
               c.mudancas_preco::int AS mudancas
        FROM imovel_ciclo_vida c JOIN imovel i ON i.id_imovel = c.id_imovel
        WHERE c.mudancas_preco > 0 AND ($1::text IS NULL OR c.modo = $1)
        ORDER BY ABS(c.variacao_pct) DESC LIMIT 20`, [modo]),
  ]);
  return { coletas, variacoes };
});

// Números de destaque da página (do modo pedido, ou o mais frequente; medianas, não médias)
route("/api/destaques", async (req) => {
  const [top] = await q(
    `SELECT m.modo FROM imovel i JOIN modo_imovel m ON m.id_modo = i.id_modo_imovel
     WHERE ($1::text IS NULL OR m.modo = $1)
     GROUP BY m.modo ORDER BY COUNT(*) DESC LIMIT 1`,
    [req.query.modo || null]
  );
  if (!top) return { modo: null };
  const [geral] = await q(
    `SELECT COUNT(*)::int AS total,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY i.preco))::int AS preco_mediano,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY i.custo_m2))::int AS preco_m2_mediano,
            COUNT(DISTINCT e.bairro)::int AS bairros
     FROM imovel i
     JOIN endereco e ON e.id_endereco = i.id_endereco_imovel
     JOIN modo_imovel m ON m.id_modo = i.id_modo_imovel
     WHERE m.modo = $1`,
    [top.modo]
  );
  const porTipo = await q(
    `SELECT t.tipo,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY i.preco))::int AS mediana,
            COUNT(*)::int AS quantidade
     FROM imovel i
     JOIN tipo_imovel t ON t.id_tipo = i.id_tipo_imovel
     JOIN modo_imovel m ON m.id_modo = i.id_modo_imovel
     WHERE m.modo = $1
     GROUP BY t.tipo ORDER BY quantidade DESC`,
    [top.modo]
  );
  const [tempo] = await q(
    `SELECT ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dias_no_mercado))::int AS dias_mediana
     FROM imovel_ciclo_vida WHERE modo = $1 AND dias_no_mercado >= 0`,
    [top.modo]
  );
  const [coleta] = await q(
    `SELECT TO_CHAR(MAX(data_coleta), 'DD/MM/YYYY') AS coletado_em FROM imovel_snapshot`
  );
  return {
    modo: top.modo, ...geral, por_tipo: porTipo,
    dias_mediana: tempo?.dias_mediana ?? null, coletado_em: coleta?.coletado_em ?? null,
  };
});

// Mapa por bairro: uma linha por polígono com anúncios. Bairros do anúncio que não casam com
// nenhum polígono ficam fora (ver scripts/geo/relatorio_cobertura.py). Média e mediana seguem
// a regra dos gráficos: só com 3 ou mais anúncios, senão null.
route("/api/mapa", async (req) => {
  const { modo, tipo } = req.query;
  const nomes = await q("SELECT DISTINCT bairro FROM endereco WHERE bairro IS NOT NULL");
  const mapeamento = nomes.flatMap(({ bairro }) => {
    const p = POLIGONOS.get(normalizar(bairro));
    return p ? [{ bairro, poligono: p.bairro }] : [];
  });
  const params = [modo || null, tipo || null, JSON.stringify(mapeamento)];
  const [precos, tempos] = await Promise.all([
    q(
      `WITH m AS (SELECT * FROM json_to_recordset($3::json) AS m(bairro text, poligono text))
       SELECT m.poligono AS bairro, COUNT(*)::int AS quantidade,
              ROUND(AVG(i.preco))::float AS preco_medio
       FROM imovel i
       JOIN endereco e ON e.id_endereco = i.id_endereco_imovel
       JOIN m ON m.bairro = e.bairro
       JOIN tipo_imovel t ON t.id_tipo = i.id_tipo_imovel
       JOIN modo_imovel mo ON mo.id_modo = i.id_modo_imovel
       WHERE ($1::text IS NULL OR mo.modo = $1) AND ($2::text IS NULL OR t.tipo = $2)
       GROUP BY m.poligono`,
      params
    ),
    q(
      `WITH m AS (SELECT * FROM json_to_recordset($3::json) AS m(bairro text, poligono text))
       SELECT m.poligono AS bairro, COUNT(*)::int AS quantidade,
              ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY c.dias_no_mercado))::int AS dias_mediana
       FROM imovel_ciclo_vida c JOIN m ON m.bairro = c.bairro
       WHERE c.dias_no_mercado >= 0
         AND ($1::text IS NULL OR c.modo = $1) AND ($2::text IS NULL OR c.tipo = $2)
       GROUP BY m.poligono`,
      params
    ),
  ]);
  const dias = new Map(tempos.map((t) => [t.bairro, t]));
  return precos
    .map((p) => {
      const t = dias.get(p.bairro);
      return {
        bairro: p.bairro,
        chave: normalizar(p.bairro),
        quantidade: p.quantidade,
        media_preco: p.quantidade >= 3 ? p.preco_medio : null,
        dias_mediana: t && t.quantidade >= 3 ? t.dias_mediana : null,
      };
    })
    .sort((a, b) => b.quantidade - a.quantidade);
});

route("/api/preco-modo-tipo", () =>
  q("SELECT tipo, modo, media_preco::float AS media_preco FROM media_preco_modo_tipo")
);

route("/api/faixa-area", () =>
  q("SELECT faixa_area, modo, tipo, count::int AS quantidade FROM dispersao_faixa_area_modo_tipo")
);

route("/api/dispersao", (req) =>
  q(
    `SELECT i.preco, i.area_m2
     FROM imovel i JOIN modo_imovel m ON m.id_modo = i.id_modo_imovel
     WHERE i.preco IS NOT NULL AND i.area_m2 > 0 AND ($1::text IS NULL OR m.modo = $1)
     LIMIT 1000`,
    [req.query.modo || null]
  )
);

route("/api/filtros", async () => ({
  modos: (await q(`SELECT DISTINCT m.modo FROM imovel i
                   JOIN modo_imovel m ON m.id_modo = i.id_modo_imovel ORDER BY 1`)).map((r) => r.modo),
  tipos: (await q(`SELECT DISTINCT t.tipo FROM imovel i
                   JOIN tipo_imovel t ON t.id_tipo = i.id_tipo_imovel ORDER BY 1`)).map((r) => r.tipo),
}));

route("/api/imoveis", (req) => {
  const { modo, tipo, bairro, quartos } = req.query;
  return q(
    `SELECT i.id_imovel, i.titulo_imovel AS titulo, i.preco, i.area_m2,
            i.quantidade_quartos AS quartos, e.bairro, t.tipo, m.modo
     FROM imovel i
     JOIN endereco e ON e.id_endereco = i.id_endereco_imovel
     JOIN tipo_imovel t ON t.id_tipo = i.id_tipo_imovel
     JOIN modo_imovel m ON m.id_modo = i.id_modo_imovel
     WHERE ($1::text IS NULL OR m.modo = $1)
       AND ($2::text IS NULL OR t.tipo = $2)
       AND ($3::text IS NULL OR e.bairro ILIKE '%' || $3 || '%')
       AND ($4::int IS NULL OR i.quantidade_quartos >= $4::int)
     ORDER BY i.data_atualizacao_imovel DESC NULLS LAST
     LIMIT 50`,
    [modo || null, tipo || null, bairro || null, quartos || null]
  );
});

const port = process.env.PORT || 3001;
app.listen(port, () => console.log(`API em http://localhost:${port}`));
