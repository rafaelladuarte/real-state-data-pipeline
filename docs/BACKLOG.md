# Backlog

Objetivo: evoluir o projeto de uma esteira funcional para uma vitrine de **coleta em escala e pipeline completo**, com resultados mensuráveis.

Como ler:

- **A ordem das fases é a prioridade.** Dentro de cada fase, a ordem listada é a de execução.
- **Os números dos itens são identificadores estáveis** (outros documentos os citam), por isso não seguem a ordem do arquivo.
- Esforço: **P** (horas) · **M** (1–2 dias) · **G** (vários dias).
- Status: ✅ feito · 🔁 em andamento (parte feita) · ⬜ a fazer.

Restrições que pesam nas prioridades:

- **Disco limitado:** a máquina não comporta 10 GB de HTML bruto. A base inteira de Uberlândia (28.722 anúncios) geraria 5,2 GB por coleta ([ESCALA.md](ESCALA.md)), então a coleta em escala depende de apagar o HTML por lote.
- **Coleta responsável:** ritmo limitado, sem contornar proteções do site (ver [Riscos e restrições](#riscos-e-restrições)).

---

## Visão geral

| Fase | # | Item | Esforço | Status | Depende de |
|---|---|---|---|---|---|
| 1. Operação contínua | 4 | Airflow de ponta a ponta | M | 🔁 | – |
| | 9 | Subida em um comando | M | 🔁 | 4 |
| | 10 | Segredos fora da imagem Docker | P | ✅ | – |
| | 15 | Fechar o mapa (termos do IBGE) | P | 🔁 | – |
| 2. Coleta em escala | 21 | Carga incremental no Postgres | M | ⬜ | – |
| | 22 | Remoção segura do HTML e quarentena | M | ⬜ | – |
| | 23 | Coleta em lotes por página | G | ⬜ | 21, 22 |
| | 24 | Validar em escala e atualizar o ESCALA.md | M | ⬜ | 23 |
| | 8 | Ampliar a cobertura da coleta | P | 🔁 | 21 a 23 (base inteira) |
| 3. App e dados | 16 | Ligar o mapa à lista e comparar por preço/m² | M | ⬜ | – |
| | 18 | Chave do polígono gravada no ETL | M | ⬜ | – |
| | 19 | Testes do app e CI com build | M | ⬜ | – |
| | 17 | Evolução no tempo | M | ⬜ | 4 |
| | 20 | Publicar uma versão somente leitura | G | ⬜ | 10 |
| 4. Engenharia e apresentação | 11 | Armazenamento de imagens | P | 🔁 | – |
| | 12 | Monitoramento da execução | M | 🔁 | – |
| | 13 | Documentação para a vitrine | P | 🔁 | 4 |
| | 14 | Aposentar o `dev_pipeline` e scripts soltos | P | ⬜ | – |
| Ideias | 25 | Atualizar preços pela listagem | M | ⬜ | 23 |

**Por que essa ordem:** sem coleta recorrente (fase 1) o app não acumula histórico, e o item 17 e a vitrine dependem dele. A coleta em escala (fase 2) vem antes de evoluir o app porque mais dados melhoram o mapa e as médias por bairro, e porque o item 21 já reduz o custo da carga hoje.

---

## Entregue

Detalhes técnicos e decisões em [ARCHITECTURE.md](ARCHITECTURE.md); o histórico completo está no git.

| # | Item | Resultado |
|---|---|---|
| 1 | HTML bruto guardado e parsing separado | HTML comprimido em storage S3-compatível, reprocessável sem acessar o site (`REPROCESS=true`). Decisão D1. |
| 2 | HTTP simples vs. Selenium | HTTP recebe 403 da Cloudflare (0/6); Selenium 6/6. Mantém-se o Selenium e o ganho vem de paralelizar. Decisão D3. |
| 3 | Coleta paralela com fila e reserva atômica | Benchmark com 1, 2 e 4 workers: 0,49, 0,76 e 0,75 anúncio/s; o teto global é atingido com 2 workers. Decisão D2. |
| 5 | Histórico de preço e ciclo de vida | Snapshot por coleta, datas de primeira e última aparição, telas de variação e tempo no mercado. Decisão D4. |
| 6 | Qualidade dos dados e alerta de quebra do scraper | Taxa de nulos por execução, DAG falha acima do limite, testes de contrato e webhook de alerta. Decisão D6. |
| 7 | Carga idempotente no Postgres | Upsert em uma transação; reexecutar não duplica. Decisão D5. |

Outras entregas:

- ✅ DAG `extraction` com agendamento diário, encadeamento com `treatment` e `load` e dynamic task mapping (`.expand`) por worker.
- ✅ Scrapers reescritos para o novo HTML do ZAP Imóveis (parsers puros, sem o formulário de telefone).
- ✅ `logging` no lugar de `print`, remoção de arquivos de terceiros e da DAG de exemplo, e correções de SQL (função `calcular_faixa_area`, triggers reexecutáveis, views e insert).
- ✅ Testes (`pytest`) dos utilitários, dos parsers de HTML, da fila, da carga e do mapa, e CI no GitHub Actions (lint, testes, build do frontend e da imagem de ETL).
- ✅ App de visualização (API Express + React) com os temas claro e escuro e as tabelas equivalentes aos gráficos.
- ✅ Primeira coleta real: 438 anúncios (aluguel e venda de casas e apartamentos, 3 páginas por busca), em 19/11/2026.
- ✅ `.dockerignore` nos contextos de build da imagem de ETL e do Airflow (item 10).
- ✅ Mapa de Uberlândia por bairro: contorno do IBGE (`scripts/geo/`), rota `/api/mapa` e seção no app. Spec em [spec/mapa-por-bairro.md](spec/mapa-por-bairro.md).
- ✅ Índice de seções no topo do app, com links diretos (`#mapa`) e menu em telas menores.
- ✅ Análise de escala da base inteira em [ESCALA.md](ESCALA.md).

---

## Fase 1 — Operação contínua e segurança

### 4. Airflow executando de ponta a ponta — M
**Por quê:** sem a coleta rodando sozinha, o app não acumula histórico: a seção "Variação" fica em "Só há 1 coleta". As DAGs nunca foram exercitadas de ponta a ponta; a coleta foi rodada por scripts diretos.
**Aceite:**
- ✅ Variáveis documentadas no `.env.example`, nome da imagem alinhado (`etl-scripts`), rede entre containers e `.expand` nas DAGs.
- ✅ DAG `load` com caminhos corretos (`DockerOperator`).
- ⬜ A DAG `extraction` roda inteira no Airflow (coleta, parse, tratamento e carga) e a execução seguinte, em outro dia, gera a segunda coleta.
- ⬜ Captura da DAG executando no Airflow (usada no item 13).

### 9. CI e subida em um comando — M (depende do item 4)
**Por quê:** hoje subir o projeto exige vários comandos manuais.
**Aceite:**
- ✅ GitHub Actions com lint (ruff), `pytest` e build do frontend e da imagem de ETL.
- ⬜ `make up` (ou equivalente) sobe Postgres, Mongo, storage, Airflow e o app.
- ⬜ `.env.example` completo para essa subida.

### 10. ✅ Segredos fora da imagem Docker — P
**Por quê:** é pré-requisito para publicar qualquer coisa (item 20).
**Aceite:**
- ✅ `requirements.txt` das imagens versionado, com `beautifulsoup4` e `lxml`; segredos das DAGs vêm das Variables do Airflow.
- ✅ `scripts/.dockerignore` impede que `.env`, `client_secrets.json`, chaves e `__pycache__` entrem na imagem de ETL (o `Dockerfile` faz `COPY . /app/scripts`), e `.dockerignore` na raiz faz o mesmo para o contexto do Airflow, que só usa `dags/`. Testado exportando o contexto com arquivos secretos plantados, inclusive em subpastas.
- ✅ Varredura da imagem `etl-scripts` já construída: nenhuma credencial (19/11/2026). A imagem do Airflow não foi construída nesta máquina, mas só copia `dags/`.

### 15. Fechar o mapa por bairro — P
**Por quê:** o código, a documentação e as capturas estão prontos. Falta só a licença do contorno.
**Aceite:**
- ✅ Fonte (IBGE, Censo 2022) citada no app, no README e na arquitetura (D7); capturas, GIF e MP4 refeitos.
- ⬜ Termos formais de redistribuição do IBGE lidos: o catálogo de metadados responde com desafio anti-bot, então a leitura de "Informações Técnicas e Legais" fica para uma checagem manual.

---

## Fase 2 — Coleta em escala

Spec: [spec/coleta-em-lotes.md](spec/coleta-em-lotes.md). A solução é processar a coleta em lotes de uma página e apagar o HTML de cada lote depois da carga, o que mantém o disco abaixo de 0,5 GB na primeira coleta. Os itens 21 a 24 são etapas independentes, nesta ordem.

### 21. Carga incremental no Postgres — M
**Por quê:** `migrate.py` recria o staging com a coleção inteira a cada execução. Com um lote por página isso copiaria cerca de 13,8 milhões de linhas no total, em vez de 28.722. Já reduz o custo da carga hoje, mesmo sem os lotes.
**Aceite:**
- Documentos tratados e snapshots carregam um `batch_id`; o staging contém só o lote.
- Concorrência resolvida (tabelas `TEMP` na mesma transação ou lock), validada com os SQL de `scripts/etl/modeling`.
- Teste de equivalência: carregar em N lotes e de uma vez deixa o Postgres no mesmo estado; reexecutar um lote não duplica nada.

### 22. Remoção segura do HTML e quarentena — M
**Por quê:** o HTML bruto cresce 268 GB por ano se recoletar toda semana, e o disco não comporta isso.
**Aceite:**
- `ObjectStore.delete` e `delete_many`.
- O HTML só é apagado depois de parse, qualidade, tratamento e carga bem-sucedidos; se algo falha, ele fica guardado (teste que força a falha).
- Quarentena com limites (`QUARANTINE_MAX_BATCHES`, `QUARANTINE_CONSECUTIVE`) que param a coleta, e limpeza por idade (`HTML_QUARANTINE_DAYS`).
- `PURGE_HTML=false` mantém o comportamento atual.

### 23. Coleta em lotes por página — G (depende dos itens 21 e 22)
**Por quê:** hoje nada chega ao Postgres até o fim da coleta (11 a 56 h na base inteira) e um bloqueio no meio atrasa o parse, o tratamento e a carga de tudo.
**Aceite:**
- Coleção `lotes_coleta` com reserva atômica e retomada; a descoberta passa a ser só 4 requisições.
- Ciclo completo por lote em `scripts/etl/extraction/pipeline_lotes.py`, com todas as requisições pelo limitador global.
- DAG `extraction` com `.expand` sobre intervalos de páginas (`PAGES_PER_TASK`), sem disparar `treatment` e `load` a cada lote.
- Checagem de qualidade por lote (só quebra evidente) e por execução (limites atuais).
- Depois do primeiro lote, o Postgres já tem os anúncios dele e o app os mostra.
- Decisões em aberto da spec resolvidas: imobiliárias por lote ou no fim, e os valores finais dos limites.

### 24. Validar a coleta em escala e atualizar o ESCALA.md — M (depende do item 23)
**Por quê:** os tempos e tamanhos do `ESCALA.md` são estimativas; falta confirmar com coleta real e verificar se o site entrega todas as páginas.
**Aceite:**
- Execução com `MAX_PAGES` pequeno, depois uma busca inteira (por exemplo, aluguel de casas, 77 páginas), medindo disco, tempo, bloqueios e quarentena.
- Confirmado se as 378 páginas de venda de casas existem; se o site limitar a profundidade, buscas segmentadas (por bairro ou faixa de preço) definidas.
- Primeira coleta completa dentro de 0,5 GB de disco.
- `ESCALA.md` atualizado com os números medidos.

### 8. Ampliar a cobertura da coleta — P (depende dos itens 21 a 23 para a base inteira)
**Por quê:** hoje é uma amostra (438 anúncios, 3 páginas por busca; uma fração dos 28.722 listados). Sem os itens 21 a 23 o HTML bruto da base inteira não cabe no disco.
**Aceite:**
- ✅ `MAX_PAGES` configurável por variável de ambiente; venda habilitada; cobertura real e viés de ordenação do site registrados no README.
- ⬜ Modos e tipos configuráveis por variável de ambiente ou parâmetro da DAG (hoje estão fixos em `links.py`).
- ⬜ Demais tipos habilitados (studio, quitinete, casa de condomínio, cobertura), hoje comentados.

---

## Fase 3 — Evolução do app e dos dados

### 16. Ligar o mapa à lista e comparar por preço/m² — M
**Por quê:** o mapa e a lista de anúncios são seções separadas, e o preço bruto compara mal imóveis de tamanhos diferentes. O banco já guarda `custo_m2`.
**Aceite:**
- Clicar em um bairro filtra a lista da seção "Anúncios" (e a URL guarda o bairro).
- Nova métrica "Preço por m²" no mapa, com a mesma regra de 3 ou mais anúncios.
- Teste de integração da rota `/api/mapa` (hoje conferida só à mão).

### 18. Chave do polígono gravada no ETL — M
**Por quê:** a normalização de nomes existe em Python (`scripts/geo/nomes.py`) e em JavaScript (`app/api/bairros.js`) e precisa ser mantida igual à mão.
**Aceite:**
- O tratamento grava o código do bairro do IBGE em `endereco` (ou tabela de apoio) usando `scripts/geo/nomes.py`.
- A API lê esse campo e deixa de normalizar nomes; `app/api/bairros.js` perde a duplicação.
- O relatório de cobertura (`scripts/geo/relatorio_cobertura.py`) roda no fim da carga e alerta se ficar abaixo de 90%.

### 19. Testes do app e CI com build — M
**Por quê:** a API e o front não têm testes, e as conferências do mapa e do índice foram feitas por scripts avulsos.
**Aceite:**
- Testes da API (rotas, filtros, regra de 3 anúncios) contra um Postgres descartável.
- Teste de fumaça no navegador (Playwright): abre o app, troca de modo, abre o mapa e o menu de seções.
- O workflow do CI roda esses testes (o `vite build` já roda).

### 17. Evolução no tempo — M (depende do item 4)
**Por quê:** a seção "Variação" mostra "Só há 1 coleta"; sem coletas repetidas o app não conta a história do mercado.
**Aceite:**
- Gráfico do preço mediano por coleta, por modo e tipo.
- O mapa permite escolher a coleta ou comparar duas.
- Texto da seção explica quando há poucas coletas para concluir algo.

### 20. Publicar uma versão somente leitura — G (depende do item 10)
**Por quê:** hoje o app só roda em `localhost`; uma vitrine online mostra o projeto sem exigir que a pessoa suba o Docker.
**Aceite:**
- Instantâneo do banco (ou API estática) servido sem credenciais de escrita.
- Aviso visível de que os dados são uma amostra e a data da coleta.
- Nenhum segredo no repositório nem na imagem.

---

## Fase 4 — Engenharia e apresentação

### 11. Armazenamento de imagens — P
**Por quê:** o upload para o Google Drive depende de credenciais pessoais e é frágil.
**Aceite:**
- ✅ O Drive já é opcional: sem `CRED_PATH` e `FOLDER_ID`, o pipeline mantém as URLs originais.
- ⬜ Decisão registrada: manter URLs originais ou usar S3/MinIO.
- ⬜ Remover a dependência do Drive se não for usado.

### 12. Monitoramento da execução — M
**Por quê:** hoje só dá para ver o que aconteceu abrindo o Mongo.
**Aceite:**
- ✅ Métricas por execução (itens coletados, erros, duração) gravadas em `run_metrics`.
- ⬜ Painel simples no app ou no Grafana, incluindo lotes em quarentena depois do item 23.

### 13. Documentação para a vitrine — P (captura da DAG depende do item 4)
**Aceite:**
- ✅ README com diagrama atualizado, números de desempenho, cobertura de dados, decisões de arquitetura e seção de **coleta responsável**.
- ✅ GIF, MP4 e capturas do app.
- ⬜ Captura da DAG no Airflow.

### 14. Aposentar o `dev_pipeline` e scripts soltos — P
**Aceite:**
- Remover ou documentar `scripts/dev_pipeline/` e o bloco de demonstração de `scripts/utility/operator.py`.

---

## Ideias ainda não priorizadas

### 25. Atualizar preços pela listagem, sem reabrir cada anúncio — M (depende do item 23)
**Por quê:** a listagem já traz, em JSON-LD, os 30 itens de cada página com id, título, área, quartos e **preço** (conferido no HTML guardado). Recoletar só as 958 listagens da base inteira leva cerca de 1,3 h, contra 11 a 56 h pelos anúncios, e grava cerca de 128 MB por coleta em vez de 5,2 GB. A página do anúncio só precisaria ser aberta para anúncios novos. Detalhes em [ESCALA.md](ESCALA.md#como-reduzir).
**Aceite:**
- O snapshot de preço pode nascer da listagem (hoje nasce da página do anúncio).
- Anúncios conhecidos com preço inalterado não são reabertos.
- Medição do ganho de tempo e de requisições.

---

## Fora de escopo (por ora)

Kafka, Spark, Kubernetes e dbt. Para cerca de 29 mil anúncios (a base inteira de Uberlândia) seriam exagero; o critério é usar cada ferramenta só quando houver necessidade medida.

---

## Riscos e restrições

- **Termos de uso e bloqueios:** o site usa Cloudflare, pode mudar o HTML de novo e já bloqueou a coleta de venda. Não contornar proteções. Guardar o HTML bruto enquanto o lote não foi carregado (itens 1 e 22) e os testes de contrato (item 6) reduzem o custo de cada mudança. Coletar a base inteira é uma escala bem maior que a amostra: reler os termos do site antes.
- **Perda do bronze com a limpeza por lote (itens 22 e 23):** depois de um lote `ok`, reparsear exige recoletar. Mitigação: quarentena das falhas, amostra opcional (`HTML_SAMPLE_EVERY`) e fixtures em `tests/fixtures/`.
- **Disco:** a primeira coleta completa deve caber em 0,5 GB; depois, só os snapshots de preço crescem (cerca de 22 MB por coleta).
- **Paginação não verificada:** não se sabe se o site entrega todas as 378 páginas da busca de casas à venda (item 24).
- **Telefones das imobiliárias:** não são coletados. A versão anterior enviava contatos fictícios ao formulário do site, o que não deve voltar.
- **Amostra, não mercado inteiro:** o app e toda captura de tela devem dizer que os números descrevem uma amostra das primeiras páginas de cada busca.
