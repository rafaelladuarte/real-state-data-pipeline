# Real Estate Data Pipeline

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Airflow" src="https://img.shields.io/badge/Airflow-2.7-017CEE?style=for-the-badge&logo=apacheairflow&logoColor=white">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-compose-2496ED?style=for-the-badge&logo=docker&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-13-4169E1?style=for-the-badge&logo=postgresql&logoColor=white">
  <img alt="MongoDB" src="https://img.shields.io/badge/MongoDB-7-47A248?style=for-the-badge&logo=mongodb&logoColor=white">
  <img alt="React" src="https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black">
  <img alt="Status" src="https://img.shields.io/static/v1?label=Status&message=Concluido&color=green&style=for-the-badge">
  <a href="https://github.com/rafaelladuarte/real_state_data_pipeline/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/rafaelladuarte/real_state_data_pipeline/ci.yml?style=for-the-badge&label=CI"></a>
</p>

<p align="center">
  <img src="docs/images/imoveis.jpeg" alt="Real Estate Data Pipeline">
</p>

Pipeline de dados **ponta a ponta** que coleta anúncios de imóveis de Uberlândia/MG, trata e modela os dados e os entrega em um app web interativo. O projeto de portfólio foca em **coletar em escala com responsabilidade**, **reprocessar sem recoletar** e **carregar de forma idempotente**.

## Destaques

- **Coleta paralela com limite global:** workers compartilham uma fila com reserva atômica e um limitador de requisições (≈ 0,8 anúncio/s no total), com retentativa e backoff exponencial.
- **Camada bruta reprocessável:** o HTML de cada página é guardado comprimido em storage S3-compatível. Se o site mudar, basta reparsear; não é preciso coletar tudo de novo.
- **Parsers estáveis e testados:** extração por JSON-LD e atributos `data-testid`, com testes sobre HTML de exemplo versionado.
- **Carga idempotente no Postgres:** upsert em uma única transação; reexecutar não duplica nada e, se algo falha, nada é aplicado.
- **Histórico de preço e ciclo de vida:** cada coleta gera um snapshot, o que permite medir variação de preço e tempo no mercado.
- **Orquestração com Airflow:** DAGs em `DockerOperator`, tarefas mapeadas por worker e alerta de falha.
- **App web:** API Express somente leitura sobre as views do Postgres e frontend React com gráficos e listagem filtrável.
- **Coleta responsável:** ritmo limitado, sem contornar proteções do site e sem envio de dados fictícios a formulários.

## Arquitetura

<p align="center">
  <img src="docs/images/diagram_real_state_data_pipeline.png" alt="Diagrama da arquitetura">
</p>

```
Airflow ─▶ descoberta de links ─▶ fila (Mongo, reserva atômica)
        ─▶ N workers (Selenium) ─▶ HTML bruto comprimido (storage S3)        BRONZE
        ─▶ parsing reprocessável ─▶ raw_* ─▶ treat_* (Mongo, com hash)       SILVER
        ─▶ staging ─▶ upsert transacional ─▶ Postgres (fatos, dimensões,     GOLD
           snapshots de preço e views) ─▶ API Express ─▶ app React
```

| Camada | Onde | O que guarda |
|---|---|---|
| Bronze | Storage S3-compatível (RustFS) | HTML comprimido de listagens e anúncios (`anuncio/AAAA-MM-DD/<id>.html.gz`) |
| Silver | MongoDB | `links_imoveis` (fila), `raw_imoveis`, `raw_imobiliarias`, `treat_*`, `snapshots_imoveis` |
| Gold | PostgreSQL | Dimensões, fato `imovel`, histórico `imovel_snapshot` e views de análise |

As decisões de arquitetura e as alternativas descartadas estão em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Resultados medidos

**HTTP simples ou Selenium?** A Cloudflare responde 403 a clientes HTTP simples, então o Selenium fica. O experimento está em [`docs/experiments/http_vs_selenium.py`](docs/experiments/http_vs_selenium.py).

| Cliente | Sucesso | Latência média |
|---|---|---|
| `requests` | 0/6 (403) | 0,11 s |
| `httpx` | 0/6 (403) | 0,09 s |
| Selenium (Chrome headless) | 6/6 | 1,87 s |

**Escala com workers** (20 anúncios por rodada, requisições reais, intervalo global de 1,25 s), em [`docs/experiments/parallel_scaling.py`](docs/experiments/parallel_scaling.py):

| Workers | Erros | Tempo | Anúncios/s |
|---|---|---|---|
| 1 | 0 | 40,8 s | 0,49 |
| 2 | 0 | 26,3 s | 0,76 |
| 4 | 0 | 26,6 s | 0,75 |

Com 2 workers o teto global já é atingido; mais workers só aumentam o uso de memória. Em relação à coleta serial original (~5 s por anúncio), a taxa é cerca de 3,8× maior. Nenhum anúncio foi coletado duas vezes.

## App

<p align="center">
  <img src="docs/images/app.png" alt="App no tema claro" width="49%">
  <img src="docs/images/app-dark.png" alt="App no tema escuro" width="49%">
</p>

Uma página editorial em vez de um painel de relatório: a manchete pergunta *quanto custa alugar em Uberlândia?* e responde com um número de destaque (a **mediana** do aluguel), seguido de seções cujos títulos enunciam a conclusão do gráfico. Preço médio e idade mediana do anúncio por bairro (só com 3 ou mais anúncios, para um imóvel isolado não distorcer), oferta por bairro, dispersão preço × metragem, variação de preço entre coletas e uma lista filtrável de anúncios.

- **Identidade visual:** um único salmão (`#e2634d`), validado nos temas claro e escuro quanto a faixa de luminosidade, croma e contraste; títulos em serifa e números sempre em sans.
- **Acessível por padrão:** cada gráfico tem a tabela equivalente a um clique ("Ver como tabela"), foco visível, tema claro/escuro e respeito a `prefers-reduced-motion`.
- **Gráficos leves:** barras finas com o valor na ponta, grade em fio, tooltip próprio e pontos com área de toque maior que a marca.

Detalhes em [app/README.md](app/README.md).

> Os números do app vêm de uma **amostra** de aluguel coletada em 19/11/2026 (169 imóveis, 26 imobiliárias, primeiras páginas de cada busca). Não representam o mercado inteiro.

## Modelo de dados

<p align="center">
  <img src="docs/images/diagram_er.png" alt="Diagrama entidade-relacionamento" width="700">
</p>

- **Dimensões:** `tipo_imovel`, `modo_imovel`, `endereco` (único por texto), `imobiliaria`.
- **Fato:** `imovel`, com triggers que calculam custo por m² e faixa de área.
- **Histórico:** `imovel_snapshot` (preço por imóvel e data de coleta); o preço atual de `imovel` vem do snapshot mais recente.
- **Views:** distribuições por tipo, modo e bairro; preço médio por bairro, modo e tipo; dispersão; e `imovel_ciclo_vida` (primeira e última coleta, dias no mercado, variação de preço).

## Stack

| Área | Tecnologias |
|---|---|
| Linguagem | Python 3.12, JavaScript |
| Coleta | Selenium, selenium-stealth, BeautifulSoup + lxml |
| Orquestração | Apache Airflow 2.7 (`DockerOperator`, dynamic task mapping) |
| Armazenamento | MongoDB (silver), PostgreSQL (gold), storage S3-compatível RustFS (bronze) |
| App | Express, React, Vite, Recharts |
| Infra | Docker, Docker Compose |
| Qualidade | pytest, ruff |

## Estrutura do repositório

```
├── dags/                       # DAGs do Airflow: extraction, treatment, load
├── scripts/
│   ├── etl/
│   │   ├── extraction/         # links, property (worker), parse_property, parsers, real_estate, requeue
│   │   ├── treatment/          # tratamento, snapshots de preço e imagens
│   │   ├── load/               # migrate (staging) e model (upsert transacional)
│   │   └── modeling/           # SQL: tabelas, funções, triggers, inserts e views
│   ├── infra/                  # Mongo, Postgres, object store, fila e limitador, segredos
│   ├── utility/                # logging e funções de extração/tratamento de texto
│   ├── backup/                 # backup e restauração do Mongo
│   ├── Dockerfile              # imagem de ETL (Chrome + chromedriver)
│   └── requirements.txt
├── app/
│   ├── api/                    # API Express somente leitura
│   └── web/                    # Frontend React (Vite)
├── tests/                      # pytest (unidade e integração) e HTML de exemplo
├── docs/                       # arquitetura, backlog, experimentos, imagens e diagramas
├── docker-compose.yml
├── Dockerfile.airflow
└── .env.example
```

## Como executar

### Pré-requisitos

Docker e Docker Compose, Python 3.12, Node.js 18+ e Google Chrome (para a coleta fora de container).

### 1. Infraestrutura de dados

```bash
cp .env.example .env
docker compose up -d real_state_postgres mongo object_store
```

Sobe Postgres (porta 5434), MongoDB (27017) e o storage S3 (9000, console em 9001). Todos usam `username` / `password` no ambiente local.

### 2. Ambiente Python e variáveis

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt

export PYTHONPATH=.
export MONGO_URI="mongodb://username:password@localhost:27017/?authSource=admin"
export POSTGRESQL_URI="postgresql+psycopg2://username:password@localhost:5434/real_state"
```

O storage S3 usa `localhost:9000`, `username` / `password` por padrão (veja as variáveis `S3_*` abaixo).

### 3. Executar o pipeline, etapa por etapa

```bash
python scripts/etl/extraction/links.py          # descobre links e guarda as listagens
python scripts/etl/extraction/property.py       # worker: busca o HTML dos anúncios
python scripts/etl/extraction/parse_property.py # parseia o HTML guardado -> raw_imoveis
python scripts/etl/extraction/real_estate.py    # monta raw_imobiliarias
python scripts/etl/treatment/property.py        # limpa anúncios e gera snapshots de preço
python scripts/etl/treatment/real_state.py      # limpa imobiliárias
python scripts/etl/load/migrate.py              # copia a camada tratada para o staging do Postgres
python scripts/etl/load/model.py                # aplica a modelagem (upsert, transação única)
```

Para paralelizar a coleta, abra vários terminais com `WORKER_ID=w1 python scripts/etl/extraction/property.py`, `WORKER_ID=w2 ...`: todos consomem a mesma fila e dividem o limite global de requisições.

Para **reprocessar o parsing** depois de mudar um parser, sem acessar o site:

```bash
REPROCESS=true python scripts/etl/extraction/parse_property.py
```

### 4. App

```bash
cd app/api && npm install && npm start      # http://localhost:3001
cd app/web && npm install && npm run dev   # http://localhost:5173
```

A API lê o Postgres em `localhost:5434`; use `DATABASE_URL` para apontar para outro banco.

### 5. Executar pelo Airflow

```bash
docker build -t etl-scripts scripts
docker compose up -d
```

As DAGs `extraction` → `treatment` → `load` rodam os mesmos scripts em containers `etl-scripts` na rede `real_state_airflow`. Elas leem `MONGO_URI`, `POSTGRESQL_URI` e `S3_*` das Variables do Airflow (veja `.env.example`). A DAG `extraction` roda diariamente e reenfileira links coletados há mais de 7 dias, o que alimenta o histórico de preço.

> A pilha do Airflow ainda não foi validada de ponta a ponta; os scripts e os serviços de dados foram testados individualmente.

### 6. Testes

```bash
pip install pytest ruff
pytest          # testes de unidade
ruff check .    # lint
```

Os testes de integração (fila, limitador e carga no Postgres) rodam quando há servidores disponíveis:

```bash
MONGO_TEST_URI="mongodb://username:password@localhost:27017/?authSource=admin" \
POSTGRES_TEST_URI="postgresql+psycopg2://username:password@localhost:5434/postgres" \
pytest
```

## Qualidade e observabilidade

- **Controle de qualidade na coleta:** antes de gravar, o parsing mede a taxa de campos vazios (críticos até 5%, importantes até 30%) e de erros (até 20%). Se o parser quebrar, por exemplo porque o site mudou, a execução **falha sem gravar nada** nem marcar links como processados. Depois de corrigir o parser, basta rodar de novo sobre o HTML guardado. Os limites estão em [`scripts/etl/quality.py`](scripts/etl/quality.py).
- **Bloqueio do site:** um worker com muitos erros seguidos também falha a task, em vez de seguir em silêncio.
- **Métricas por execução:** cada etapa registra total, erros, taxas e violações na coleção `run_metrics` do Mongo.
- **Alertas:** as DAGs usam `on_failure_callback` e enviam a falha para o webhook definido em `ALERT_WEBHOOK_URL` (formato Slack); sem a variável, só registram em log.
- **CI (GitHub Actions):** lint com ruff, testes com Mongo e Postgres como serviços, build do frontend e build da imagem de ETL com um teste rápido dentro dela. O fluxo está em [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Configuração

| Variável | Padrão | Uso |
|---|---|---|
| `MONGO_URI`, `POSTGRESQL_URI` | – | Conexões (obrigatórias) |
| `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_SECURE` | `localhost:9000`, `username`, `password`, `real-state-html`, `false` | Storage da camada bruta |
| `MAX_PAGES` | `3` | Páginas de listagem por busca (~30 anúncios cada) |
| `MIN_INTERVAL_SECONDS` | `1.25` | Intervalo mínimo **global** entre requisições |
| `SCRAPER_WORKERS` | `3` | Workers paralelos na DAG `extraction` |
| `MAX_ATTEMPTS` | `3` | Tentativas por link antes de desistir |
| `RECRAWL_AFTER_DAYS` | `7` | Idade a partir da qual um link é recoletado |
| `REPROCESS` | `false` | Reparseia todo o HTML guardado |
| `ALERT_WEBHOOK_URL` | vazio | Webhook para alertas de falha das DAGs |
| `CRED_PATH`, `FOLDER_ID` | – | Opcionais: upload de imagens no Google Drive (sem eles, mantém as URLs originais) |

## Coleta responsável

- O ritmo é limitado globalmente e há pausa e retentativa com backoff.
- Proteções do site, como a Cloudflare, **não** são contornadas. Páginas protegidas ficam fora do escopo.
- O telefone das imobiliárias **não** é coletado, porque exigiria enviar contatos fictícios ao formulário do site.
- O projeto tem fins educacionais e de portfólio. Verifique os termos de uso do site antes de qualquer outra utilização.

## Limitações conhecidas

- **Cobertura:** a coleta atual é uma amostra (primeiras páginas de aluguel de casas e apartamentos). A ordenação do site enviesa os rankings por bairro.
- **Imobiliárias:** a página pública da imobiliária fica atrás da Cloudflare, então nome, quantidade de imóveis e data de cadastro vêm do anúncio; credencial, endereço e telefone não estão disponíveis.
- **Variação de preço:** só aparece a partir da segunda coleta em outro dia; até lá o app informa isso.
- **Remoção de anúncios:** não ter sido visto na última coleta não prova que o anúncio saiu do ar, porque a coleta cobre só parte das páginas.

## Documentação

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): arquitetura alvo, decisões, experimentos e limitações.
- [docs/BACKLOG.md](docs/BACKLOG.md): melhorias em andamento e planejadas.
- [app/README.md](app/README.md): app de visualização e endpoints da API.

## Autor

Desenvolvido por **Rafaella Duarte**. Sugestões e contribuições são bem-vindas: abra uma issue ou envie um pull request.
