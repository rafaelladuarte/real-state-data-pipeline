import express from "express";
import cors from "cors";
import pg from "pg";

const pool = new pg.Pool({
  connectionString:
    process.env.DATABASE_URL ||
    "postgresql://username:password@localhost:5434/real_state",
});

const app = express();
app.use(cors());

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

route("/api/bairros", () =>
  q(`SELECT bairro, count::int AS quantidade FROM distribuicao_bairro
     WHERE bairro IS NOT NULL ORDER BY 2 DESC LIMIT 15`)
);

route("/api/preco-medio", (req) => {
  const { modo, tipo } = req.query;
  return q(
    `SELECT bairro, media_preco::float AS media_preco
     FROM media_preco_bairro_modo_tipo
     WHERE bairro IS NOT NULL
       AND ($1::text IS NULL OR modo = $1)
       AND ($2::text IS NULL OR tipo = $2)
     ORDER BY media_preco DESC LIMIT 15`,
    [modo || null, tipo || null]
  );
});

route("/api/preco-modo-tipo", () =>
  q("SELECT tipo, modo, media_preco::float AS media_preco FROM media_preco_modo_tipo")
);

route("/api/faixa-area", () =>
  q("SELECT faixa_area, modo, tipo, count::int AS quantidade FROM dispersao_faixa_area_modo_tipo")
);

route("/api/dispersao", () =>
  q(`SELECT preco, area_m2 FROM dispersao_preco_quartos_area
     WHERE area_m2 IS NOT NULL AND area_m2 > 0 LIMIT 1000`)
);

route("/api/filtros", async () => ({
  modos: (await q("SELECT modo FROM modo_imovel ORDER BY 1")).map((r) => r.modo),
  tipos: (await q("SELECT tipo FROM tipo_imovel ORDER BY 1")).map((r) => r.tipo),
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
