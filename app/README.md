# App de visualização

Frontend React (Vite + Recharts) e API Express somente leitura sobre o Postgres tratado
(views de `scripts/etl/modeling/create_views_dash.sql`).

## Rodar localmente

Pré-requisitos: Postgres do `docker-compose` no ar (`docker compose up real_state_postgres`)
com tabelas e views criadas.

```bash
# API (http://localhost:3001) — usa DATABASE_URL ou o Postgres do docker-compose (porta 5434)
cd app/api && npm install && npm start

# Web (http://localhost:5173) — o Vite faz proxy de /api para a API
cd app/web && npm install && npm run dev
```

## Endpoints

`/api/resumo`, `/api/bairros`, `/api/preco-medio?modo=&tipo=`, `/api/tempo-mercado?modo=&tipo=`,
`/api/variacao-preco`, `/api/preco-modo-tipo`, `/api/faixa-area`, `/api/dispersao`, `/api/filtros`,
`/api/imoveis?modo=&tipo=&bairro=&quartos=`

Preço médio e tempo no mercado por bairro só consideram bairros com pelo menos 3 anúncios.
