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
- ✅ Mapa de Uberlândia por bairro: contorno do IBGE (`scripts/geo/`), rota `/api/mapa` e seção no app. Spec em [spec/mapa-por-bairro.md](spec/mapa-por-bairro.md). Pendente só a leitura manual dos termos do IBGE (item 15).
- ✅ Índice de seções no topo do app, com links diretos (`#mapa`) e menu em telas menores.
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

### 3. ✅ Coleta paralela com fila e reserva atômica — M
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
- ✅ DAG `load` com caminhos corretos (agora `DockerOperator`).

---

## P1 — Qualidade e análise

### 5. ✅ Histórico de preço e ciclo de vida do anúncio — M
**Por quê:** o hash descarta mudanças; "variação de preço" e "tempo no mercado" são as análises mais valiosas.
**Aceite:**
- Tabela de snapshots por anúncio (preço, data da coleta).
- Datas de primeira e última aparição.
- Telas no app: variação de preço e tempo médio no mercado.

### 6. ✅ Qualidade dos dados e alerta de quebra do scraper — M
**Por quê:** o scraper ficou quebrado desde jan/2025 sem nenhum aviso.
**Aceite:**
- Validação dos documentos coletados (pydantic ou similar).
- Taxa de campos nulos por execução; a DAG falha acima de um limite.
- Teste de contrato com HTML de exemplo versionado em `tests/fixtures/`.
- Notificação em caso de falha (e-mail ou webhook).

### 7. ✅ Carga idempotente no Postgres — M
**Por quê:** hoje o staging é recriado (`if_exists="replace"`) e os `INSERT` não são reexecutáveis.
**Aceite:**
- Upsert (`ON CONFLICT`) para dimensões e fato.
- Reexecutar a DAG não duplica dados nem perde histórico.

### 8. Ampliar a cobertura da coleta — P (venda ✅; falta ampliar páginas e tipos)
**Por quê:** hoje é uma amostra (438 anúncios de aluguel e venda de casas e apartamentos, 3 páginas por busca; uma fração pequena dos milhares listados).
**Aceite:**
- `MAX_PAGES` e modos/tipos configuráveis por variável de ambiente ou parâmetro da DAG.
- Habilitar venda e demais tipos.
- Registrar no README a cobertura real e o viés de ordenação do site.

---

## P1 — Evolução do app e dos dados

### 15. ✅ Fechar o mapa por bairro — P
**Por quê:** o código está pronto, mas a documentação e a licença do contorno ficaram em aberto.
**Aceite:**
- ✅ Fonte (IBGE, Censo 2022) citada no app, no README e na arquitetura (D7).
- ⬜ Termos formais de redistribuição do IBGE lidos: o catálogo de metadados responde com desafio anti-bot, então a leitura de "Informações Técnicas e Legais" fica para uma checagem manual.
- ✅ `docs/ARCHITECTURE.md` e o README principal descrevem o mapa e a origem do contorno.
- ✅ Capturas de tela, GIF e MP4 do app refeitos com a seção do mapa e o índice do topo.

### 16. Ligar o mapa à lista e comparar por preço/m² — M
**Por quê:** o mapa e a lista de anúncios são seções separadas, e o preço bruto compara mal imóveis de tamanhos diferentes. O banco já guarda `custo_m2`.
**Aceite:**
- Clicar em um bairro filtra a lista da seção "Anúncios" (e a URL guarda o bairro).
- Nova métrica "Preço por m²" no mapa, com a mesma regra de 3 ou mais anúncios.
- Teste de integração da rota `/api/mapa` (hoje conferida só à mão).

### 17. Evolução no tempo — M (depende do item 4)
**Por quê:** a seção "Variação" mostra "Só há 1 coleta"; sem coletas repetidas o app não conta a história do mercado.
**Aceite:**
- Gráfico do preço mediano por coleta, por modo e tipo.
- O mapa permite escolher a coleta ou comparar duas.
- Texto da seção explica quando há poucas coletas para concluir algo.

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
- O workflow do CI roda `vite build` e esses testes.

### 20. Publicar uma versão somente leitura — G
**Por quê:** hoje o app só roda em `localhost`; uma vitrine online mostra o projeto sem exigir que a pessoa suba o Docker.
**Aceite:**
- Instantâneo do banco (ou API estática) servido sem credenciais de escrita.
- Aviso visível de que os dados são uma amostra e a data da coleta.
- Nenhum segredo no repositório nem na imagem (depende do item 10).

---

## P2 — Engenharia e apresentação

### 9. CI e subida em um comando — M (CI ✅; falta a subida em um comando)
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

## Ordem sugerida

1. Item 15 (terminar o que está aberto).
2. Itens 4 e 9 (coleta recorrente e subida em um comando): sem eles o app não acumula histórico.
3. Item 10 (segredos fora da imagem): antes de publicar qualquer coisa.
4. Item 8 (ampliar a cobertura): deixa o mapa e as médias por bairro mais preenchidos.
5. Itens 16, 18 e 19, depois 17 e 20, que dependem de mais dados e de mais coletas.

---

## Fora de escopo (por ora)

Kafka, Spark, Kubernetes e dbt. Para ~10 mil registros seriam exagero; o critério é usar cada ferramenta só quando houver necessidade medida.

---

## Riscos e pontos de atenção

- **Termos de uso e bloqueios:** o site usa Cloudflare e pode mudar o HTML de novo. Não contornar proteções; guardar o HTML bruto (item 1) e testes de contrato (item 6) reduzem o custo de cada mudança.
- **Telefones das imobiliárias:** não são coletados. A versão anterior enviava contatos fictícios ao formulário do site, o que não deve voltar.
- **Dados de demonstração:** o Postgres local ainda contém dados fictícios até a carga dos dados reais; identificar claramente em qualquer captura de tela.
