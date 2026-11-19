# Backlog

Objetivo: evoluir o projeto de uma esteira funcional para uma vitrine de **coleta em escala e pipeline completo**, com resultados mensuráveis.

Legenda de esforço: **P** (horas) · **M** (1–2 dias) · **G** (vários dias).
Legenda de status: ✅ feito · 🔁 em andamento · ⬜ a fazer.

---

## Já entregue

- ✅ DAG `extraction` com nome de script corrigido, agendamento diário e encadeamento com `treatment`.
- ✅ Remoção de arquivos de terceiros versionados e da DAG de exemplo.
- ✅ `logging` no lugar de `print` nos scripts de ETL.
- ✅ Testes (`pytest`) dos utilitários de tratamento e dos parsers de HTML.
- ✅ Correções de SQL: função `calcular_faixa_area`, triggers reexecutáveis, views e insert com sintaxe válida.
- ✅ App de visualização (API Express + React) sobre as views do Postgres.
- ✅ Scrapers reescritos para o novo HTML do ZAP Imóveis (parsers puros, sem o formulário de telefone).
- 🔁 Primeira coleta real (amostra de ~170 anúncios de aluguel).

---

## P0 — Base para demonstrar escala

### 1. ✅ Guardar o HTML bruto e separar extração de parsing — M
**Por quê:** quando o site mudou, foi preciso reescrever os scrapers e coletar tudo de novo. Com o HTML guardado, basta reprocessar.
**Aceite:**
- O scraper grava o HTML comprimido (object storage S3-compatível) com chave `data/tipo/id`.
- Um passo separado lê o HTML guardado e produz `raw_imoveis`.
- Existe um comando para reprocessar sem acessar o site.

### 2. ✅ Medir se HTTP simples serve para os anúncios — P
**Por quê:** os dados estão no HTML estático; se `httpx` funcionar, a coleta fica dezenas de vezes mais rápida e o Selenium fica só onde for indispensável.
**Aceite:**
- Experimento documentado: taxa de sucesso, latência e bloqueios de HTTP vs. Selenium.
- Decisão registrada no README (não contornar desafios de bot como a Cloudflare).

**Resultado:** HTTP simples recebe 403 da Cloudflare (0/6); Selenium 6/6. Mantém-se o Selenium; o ganho de escala vem de paralelizar (item 3). Detalhes em [ARCHITECTURE.md](ARCHITECTURE.md#d3).

### 3. Coleta paralela com fila e reserva atômica — M
**Por quê:** hoje a coleta é serial (um Chrome novo por página, ~5 s por anúncio).
**Aceite:**
- Links na fila do Mongo reservados com `find_one_and_update` (com expiração da reserva).
- N workers em paralelo, sem processar o mesmo link duas vezes.
- Pausa por domínio e retentativa com backoff.
- Benchmark publicado: anúncios por hora com 1, 2, 4 workers.

### 4. Airflow executando de ponta a ponta — M
**Por quê:** as DAGs não foram exercitadas; a coleta foi rodada por scripts diretos.
**Aceite:**
- Variáveis do compose documentadas (`.env.example`).
- Nome da imagem alinhado (`etl-scripts` nas DAGs vs. `etl_scripts` no compose).
- Rede entre containers: `MONGO_URI` e `POSTGRESQL_URI` usam o nome dos serviços.
- Lotes paralelos com dynamic task mapping (`.expand`).
- DAG `load` com caminhos corretos (hoje aponta para `/opt/airflow/scr/...`).

---

## P1 — Qualidade e análise

### 5. Histórico de preço e ciclo de vida do anúncio — M
**Por quê:** o hash descarta mudanças; "variação de preço" e "tempo no mercado" são as análises mais valiosas.
**Aceite:**
- Tabela de snapshots por anúncio (preço, data da coleta).
- Datas de primeira e última aparição.
- Telas no app: variação de preço e tempo médio no mercado.

### 6. Qualidade dos dados e alerta de quebra do scraper — M
**Por quê:** o scraper ficou quebrado desde jan/2025 sem nenhum aviso.
**Aceite:**
- Validação dos documentos coletados (pydantic ou similar).
- Taxa de campos nulos por execução; a DAG falha acima de um limite.
- Teste de contrato com HTML de exemplo versionado em `tests/fixtures/`.
- Notificação em caso de falha (e-mail ou webhook).

### 7. Carga incremental e idempotente no Postgres — M
**Por quê:** hoje o staging é recriado (`if_exists="replace"`) e os `INSERT` não são reexecutáveis.
**Aceite:**
- Upsert (`ON CONFLICT`) para dimensões e fato.
- Reexecutar a DAG não duplica dados nem perde histórico.

### 8. Ampliar a cobertura da coleta — P
**Por quê:** hoje é uma amostra (~2,5% de ~7.000 anúncios de aluguel; só casas e apartamentos).
**Aceite:**
- `MAX_PAGES` e modos/tipos configuráveis por variável de ambiente ou parâmetro da DAG.
- Habilitar venda e demais tipos.
- Registrar no README a cobertura real e o viés de ordenação do site.

---

## P2 — Engenharia e apresentação

### 9. CI e subida em um comando — M
**Aceite:**
- GitHub Actions com lint (ruff), `pytest` e `docker build`.
- `make up` (ou equivalente) sobe Postgres, Mongo, Airflow e o app.
- `.env.example` completo.

### 10. Segredos fora da imagem Docker — P
**Por quê:** `scripts/Dockerfile` copia `.env` e `client_secrets.json` para dentro da imagem.
**Aceite:**
- Segredos injetados em tempo de execução (variáveis de ambiente / volume).
- `requirements.txt` das imagens versionado (hoje está no `.gitignore`) e com `beautifulsoup4` e `lxml`.

### 11. Armazenamento de imagens — P
**Por quê:** o upload para o Google Drive depende de credenciais pessoais e é frágil.
**Aceite:**
- Decisão registrada: manter URLs originais ou usar S3/MinIO.
- Remover a dependência do Drive se não for usado.

### 12. Monitoramento da execução — M
**Aceite:**
- Tabela ou métricas por execução: itens coletados, erros, duração.
- Painel simples no app ou no Grafana.

### 13. Documentação para a vitrine — P
**Aceite:**
- README com diagrama atualizado, números de desempenho (antes/depois) e cobertura de dados.
- Seção de decisões de arquitetura (por que Mongo no bruto, por que parsing separado).
- Seção de **coleta responsável**: ritmo limitado, sem contornar proteções do site, sem envio de contatos fictícios, uso restrito a fins educacionais.
- GIF ou screenshots do app e da DAG no Airflow.

### 14. Aposentar o `dev_pipeline` e scripts soltos — P
**Aceite:**
- Remover ou documentar `scripts/dev_pipeline/` e o bloco de demonstração de `operator.py`.

---

## Fora de escopo (por ora)

Kafka, Spark, Kubernetes e dbt. Para ~10 mil registros seriam exagero; o critério é usar cada ferramenta só quando houver necessidade medida.

---

## Riscos e pontos de atenção

- **Termos de uso e bloqueios:** o site usa Cloudflare e pode mudar o HTML de novo. Não contornar proteções; guardar o HTML bruto (item 1) e testes de contrato (item 6) reduzem o custo de cada mudança.
- **Telefones das imobiliárias:** não são coletados. A versão anterior enviava contatos fictícios ao formulário do site, o que não deve voltar.
- **Dados de demonstração:** o Postgres local ainda contém dados fictícios até a carga dos dados reais; identificar claramente em qualquer captura de tela.
