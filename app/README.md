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

`/api/destaques` (números do topo: medianas por modo e tipo), `/api/resumo`, `/api/bairros`, `/api/preco-medio?modo=&tipo=`, `/api/tempo-mercado?modo=&tipo=`,
`/api/mapa?modo=&tipo=` (uma linha por bairro com polígono, sem limite; média e mediana só com 3 ou mais anúncios, senão `null`), `/api/variacao-preco`, `/api/preco-modo-tipo`, `/api/faixa-area`, `/api/dispersao`, `/api/filtros`,
`/api/imoveis?modo=&tipo=&bairro=&quartos=`

Todos os endpoints aceitam `?modo=aluguel|venda` (a página inteira é filtrada pelo seletor do topo). Preço médio e tempo no mercado por bairro só consideram bairros com pelo menos 3 anúncios.

## Design

Página editorial com uma cor de identidade (salmão `#e2634d`), validada nos dois temas com o validador de paleta da skill `dataviz` (luminosidade, croma e contraste >= 3:1 para marcas; texto >= 4,5:1). Títulos em Fraunces (serifa) e todo o resto, incluindo os números, em Inter, ambas empacotadas localmente (`@fontsource-variable`), sem depender de rede. O tema segue o sistema e pode ser trocado no botão do topo.

## Demonstração em vídeo

`docs/media/demo.gif` e `docs/media/demo.mp4` são gerados por um roteiro Selenium que abre o app, troca de modo, passa o cursor nos gráficos, abre a tabela e muda o tema. Para refazer depois de mudar a tela (com a API e o app no ar):

```bash
pip install pillow imageio imageio-ffmpeg numpy selenium
PYTHONPATH=. python docs/experiments/record_demo.py
```
