# Especificação: coleta em lotes por página, com carga incremental e limpeza do HTML

Status: etapas 1 e 2 implementadas (carga incremental e remoção segura do HTML, decisão D8); lotes por página e validação em escala pendentes · Escopo: `scripts/etl/`, `scripts/infra/`, `dags/` · Data: 19/11/2026

Relacionada a: [docs/ESCALA.md](../ESCALA.md) (tempo e armazenamento medidos), `docs/ARCHITECTURE.md` (decisões D1, D2 e D5) e `docs/BACKLOG.md`.

## 1. Contexto e objetivo

Hoje a coleta roda em etapas, cada uma sobre **todos** os anúncios antes da seguinte:

```
descobrir links das 4 buscas → baixar todos os anúncios → parsear todos → tratar → carregar tudo
```

Para a amostra atual (438 anúncios) isso basta. Para a base inteira de Uberlândia no ZAP (28.722 anúncios, 958 páginas de listagem, segundo o `ESCALA.md`) há três problemas:

- **Dados só no fim:** a coleta dura de 11 a 56 horas, e parse, tratamento e carga só rodam depois.
- **Bloqueio no meio atrasa tudo:** o disjuntor falha a task de coleta e o parse, o tratamento e a carga do dia não rodam.
- **Disco:** o HTML bruto soma 5,2 GB por coleta completa e 268 GB por ano se recoletar toda semana. **A máquina onde o projeto roda não tem 10 GB para isso.**

**Objetivo:** processar a coleta em **lotes de uma página de listagem (cerca de 30 anúncios)**. Cada lote percorre o ciclo inteiro (coletar, parsear, tratar, carregar) e, **só se tudo deu certo, apaga o próprio HTML**. Os dados chegam ao Postgres durante a coleta e o armazenamento fica limitado.

### Requisito de disco

Coleta completa de Uberlândia com **no máximo 0,5 GB** de disco na primeira coleta, somando HTML, Mongo e Postgres. Depois disso só crescem os snapshots de preço, cerca de 22 MB por coleta (cerca de 1,1 GB em um ano de recoleta semanal); o HTML não cresce.

| Item | Orçamento |
|---|---|
| HTML em andamento (um lote por worker, 3 workers) | cerca de 15 MB |
| Quarentena (lotes que falharam) | no máximo 100 MB, com parada da coleta ao atingir |
| Mongo (silver) | cerca de 233 MB |
| Postgres (gold) | cerca de 173 MB, mais cerca de 22 MB por coleta (snapshots) |

### Fora de escopo

- Atualizar preços só pela listagem, sem abrir cada anúncio (maior economia de tempo, descrita no `ESCALA.md`). O desenho abaixo é compatível, mas é uma mudança separada.
- Contornar proteções anti-bot. O disjuntor e o ritmo limitado continuam valendo.
- Outras cidades ou outros portais.

## 2. Decisões

### 2.1 O lote é a página; a task do Airflow é um intervalo de páginas

- **Unidade de trabalho (lote):** uma página de listagem de uma busca, identificada por `(modo, tipo, página)`.
- **Task do Airflow:** um **intervalo de páginas** (`PAGES_PER_TASK`, padrão 10, cerca de 300 anúncios), mapeado com `.expand`, como já é feito com os workers. Uma task por página criaria mais de 958 containers por execução, cada um com início de Chrome e conexões.
- Dentro da task, os lotes rodam **no mesmo processo**, em sequência, sem disparar as DAGs `treatment` e `load` a cada lote. Essas DAGs seguem disponíveis para execução completa e reprocessamento.

### 2.2 Fila de lotes

Nova coleção Mongo `lotes_coleta`, no mesmo padrão da fila de links (`scripts/infra/queue.py`, reserva atômica com `find_one_and_update` e *lease*):

```
{ run_id, modo, tipo, pagina, estado, lease_owner, lease_until, tentativas,
  anuncios_total, anuncios_ok, html_keys[], erro, iniciado_em, concluido_em }
estado: pendente | em_andamento | ok | quarentena | bloqueado
```

- A descoberta passa a ser só **4 requisições** (uma por busca, para ler o total de anúncios e calcular o número de páginas). Ela cria os documentos de lote; os workers é que baixam as páginas.
- Reexecutar retoma: lotes `ok` não voltam, `em_andamento` com *lease* vencido voltam a `pendente`.

### 2.3 Ciclo de um lote

1. **Reservar** o lote (*lease*).
2. **Baixar a listagem** e extrair os links. Todas as requisições passam pelo `RateLimiter` global (1,25 s); a pausa fixa de 3 s da descoberta atual é removida.
3. **Baixar os anúncios** do lote que ainda precisam de coleta (novos ou vencidos por `RECRAWL_AFTER_DAYS`). Cada HTML grava em `anuncio/<data>/<id>` e a chave entra em `html_keys`.
4. **Parsear** só os links do lote (`parse_stored_property` com filtro por `batch_id`).
5. **Checagem de qualidade** do lote (seção 2.5).
6. **Tratar** só os documentos do lote (`batch_id`), gerando também o snapshot de preço da coleta.
7. **Carregar** no Postgres só os ids do lote (seção 2.4).
8. **Apagar** os HTMLs de `html_keys` e marcar o lote `ok`. Qualquer falha antes desse passo mantém o HTML.

### 2.4 Carga incremental (pré-requisito)

Hoje `migrate.py` recria o staging `_treat_*` com a coleção inteira (`query={}`, `if_exists="replace"`), como a D5 registra. Com um lote por página isso copiaria cerca de **13,8 milhões de linhas** no total (958 lotes × a base já tratada), em vez de 28.722.

- Os documentos tratados e os snapshots passam a carregar o `batch_id` do lote.
- O staging contém **só o lote**. A idempotência continua no `model.py` (`ON CONFLICT`), que já é reexecutável.
- **Concorrência:** workers carregando ao mesmo tempo disputariam o mesmo staging. Opção recomendada: staging em **tabelas `TEMP` dentro da mesma transação** do `model.py`, que são privadas da sessão e não conflitam. Precisa ser validada com os arquivos SQL de `scripts/etl/modeling` (que referenciam `_treat_*`). Alternativa: um *advisory lock* do Postgres que serializa a carga.
- Resultado esperado: carregar os mesmos dados em lotes dá **o mesmo estado final** no Postgres que a carga completa atual (critério de aceite 3).

### 2.5 Apagar só depois do sucesso, com quarentena

| Resultado do lote | HTML | Estado | Efeito na coleta |
|---|---|---|---|
| Parse, qualidade, tratamento e carga passaram | apagado | `ok` | segue |
| Bloqueio anti-bot (`BlockedError`) | mantido até o lote ser refeito | `bloqueado`, volta à fila após `BLOCK_COOLDOWN_SECONDS` | disjuntor como hoje (3 seguidos interrompem o worker) |
| Falha de parse, qualidade ou tratamento | **mantido (quarentena)** | `quarentena` | conta contra o limite abaixo |

**Limite da quarentena:** a coleta **para** quando houver `QUARANTINE_MAX_BATCHES` lotes em quarentena (padrão 20, cerca de 100 MB) ou quando `QUARANTINE_CONSECUTIVE` lotes seguidos falharem (padrão 3). Um parser quebrado falha logo no primeiro lote, em vez de gastar horas.

**Limpeza da quarentena:** lotes em quarentena são apagados após `HTML_QUARANTINE_DAYS` (padrão 7), ou quando forem reprocessados com sucesso ou descartados à mão.

**Amostra opcional:** `HTML_SAMPLE_EVERY=N` guarda 1 HTML a cada N lotes `ok` (padrão 0, desligado), para alimentar `tests/fixtures/` sem ocupar disco.

### 2.6 Checagem de qualidade por lote

`scripts/etl/quality.py` exige no mínimo `MIN_SAMPLE = 10` documentos e usa limites de 5% de nulos em campos críticos e 20% de erros. Em um lote de cerca de 30 anúncios, 2 nulos já dão 6,7% e disparariam a quarentena por ruído.

- **Por lote:** só detecta **quebra evidente** (por exemplo, mais de 50% de nulos em algum campo crítico, ou erro de parse em mais de 50% dos anúncios), que indica HTML novo.
- **Por execução:** os limites atuais continuam valendo sobre o acumulado (janela de todos os lotes da execução), que é estatisticamente mais estável.
- Os limites ficam em constantes, no mesmo arquivo.

### 2.7 O que muda em relação às decisões anteriores

- **D1 (bronze em object storage):** o HTML bruto deixa de ser permanente. Ele existe só enquanto o lote não foi carregado, ou em quarentena. **Perde-se** a capacidade de reparsear coletas antigas que deram certo (por exemplo, para extrair um campo novo); isso passa a exigir recoletar. A amostra opcional e os HTMLs de `tests/fixtures/` atenuam, e `REPROCESS=true` só vale para o HTML retido.
- **D2 (fila e reserva atômica):** estendida para lotes, com o mesmo padrão de *lease*.
- **D5 (staging completo):** substituída por staging do lote, como a própria D5 já previa para volume maior.

## 3. Mudanças por arquivo

```
scripts/infra/storage/object_store.py   + delete(key), delete_many(keys)
scripts/infra/queue.py                  + LoteQueue (claim, complete, quarantine, release)
scripts/etl/extraction/links.py         descoberta reduzida a 4 requisições; cria lotes
scripts/etl/extraction/pipeline_lotes.py  NOVO: ciclo do lote (seção 2.3) e laço do worker
scripts/etl/extraction/parse_property.py  filtro por batch_id
scripts/etl/treatment/property.py       filtro por batch_id; snapshot do lote
scripts/etl/load/migrate.py             staging só do lote (TEMP ou por batch_id)
scripts/etl/load/model.py               aceita staging do lote; mesma transação
scripts/etl/quality.py                  limites por lote e por execução
dags/extraction.py                      .expand sobre intervalos de páginas; sem TriggerDagRun por lote
tests/                                  ver seção 5
docs/ARCHITECTURE.md                    nova decisão (D8) e notas em D1, D2 e D5
docs/ESCALA.md                          atualizar orçamento e tempos
```

## 4. Configuração

| Variável | Padrão | Função |
|---|---|---|
| `MAX_PAGES` | `3` | Páginas por busca; `0` = todas (coleta completa) |
| `PAGES_PER_TASK` | `10` | Páginas por task do Airflow |
| `SCRAPER_WORKERS` | `3` | Workers em paralelo (já existe) |
| `PURGE_HTML` | `true` | Apaga o HTML do lote depois da carga |
| `QUARANTINE_MAX_BATCHES` | `20` | Para a coleta ao atingir |
| `QUARANTINE_CONSECUTIVE` | `3` | Para a coleta após N lotes seguidos em quarentena |
| `HTML_QUARANTINE_DAYS` | `7` | Idade para limpar a quarentena |
| `HTML_SAMPLE_EVERY` | `0` | Guarda 1 HTML a cada N lotes ok (0 = nunca) |

`PURGE_HTML=false` mantém o comportamento atual, útil para depurar e para quem tem disco de sobra.

## 5. Critérios de aceite

1. **Disco:** a primeira coleta de Uberlândia com `MAX_PAGES=0` não passa de 0,5 GB no total e, ao fim, o bucket só contém lotes em quarentena (nenhum HTML de lote `ok`). Em recoletas, o crescimento fica restrito aos snapshots de preço.
2. **Apagar só depois do sucesso:** teste que força falha na carga e verifica que o HTML do lote **continua** no storage; e teste de que, com sucesso, ele é removido.
3. **Carga incremental equivalente:** carregar os mesmos anúncios em N lotes e de uma vez deixa o Postgres no mesmo estado (mesmas linhas em `imovel`, `endereco`, `imobiliaria` e `imovel_snapshot`). Reexecutar um lote não duplica nada.
4. **Quarentena:** com um parser que devolve campos nulos, o primeiro lote vai para quarentena, o HTML fica guardado, a coleta para e o alerta de falha dispara.
5. **Limite da quarentena:** teste cobre `QUARANTINE_MAX_BATCHES` e `QUARANTINE_CONSECUTIVE`.
6. **Concorrência:** com 3 workers, nenhum lote é processado duas vezes e as cargas simultâneas não se corrompem.
7. **Retomada:** matar o processo no meio e reexecutar termina a coleta sem refazer lotes `ok`.
8. **Bloqueio:** um lote bloqueado volta à fila com a pausa e não conta como quarentena; o disjuntor continua interrompendo o worker após 3 bloqueios seguidos.
9. **Dados durante a coleta:** depois do primeiro lote, o Postgres já tem os anúncios dele e o app os mostra.
10. **Compatibilidade:** `PURGE_HTML=false` e as DAGs `treatment` e `load` completas continuam funcionando.
11. Documentação atualizada: `ARCHITECTURE.md` (D8), `ESCALA.md`, README e `app/README.md`, se houver impacto.

## 6. Plano de entrega

Quatro etapas, cada uma útil sozinha:

1. **Carga incremental** (seção 2.4): `batch_id` nos documentos tratados e staging só do lote, com o teste de equivalência (critério 3). Já reduz o custo da carga hoje, mesmo sem os lotes.
2. **Remoção segura do HTML** (seções 2.5 e a parte do `ObjectStore`): `delete`, apagar depois da carga e quarentena com limites. Pode rodar no fluxo atual, apagando ao fim.
3. **Lotes** (seções 2.1 a 2.3): `lotes_coleta`, `pipeline_lotes.py`, descoberta de 4 requisições e a DAG com `.expand` sobre intervalos de páginas.
4. **Validação em escala:** rodar com `MAX_PAGES` pequeno, depois uma busca inteira (por exemplo, aluguel de casas, 77 páginas) medindo disco, tempo e quarentena, e só então a base inteira. Atualizar `ESCALA.md` com os números reais.

## 7. Riscos e pontos em aberto

| Risco / decisão | Mitigação |
|---|---|
| **Perda do bronze:** depois do lote `ok`, reparsear exige recoletar | Quarentena das falhas, amostra opcional (`HTML_SAMPLE_EVERY`), fixtures e testes de contrato |
| **Erro silencioso do parser** (valor errado que passa na checagem de nulos): o HTML já foi apagado | Invariantes simples na checagem (preço e área positivos, bairro preenchido) e a amostra opcional; a checagem de nulos sozinha não pega valores errados |
| **Checagem de qualidade ruidosa em lotes de 30** | Limites por lote só para quebra evidente; limites finos no acumulado da execução (seção 2.6) |
| **Carga concorrente no staging** | Tabelas `TEMP` na mesma transação (a validar com os SQL atuais) ou *advisory lock* |
| **Anúncios mudam de página durante a coleta** (repetidos e perdidos) | Já existe hoje; o hash do imóvel e a chave única de snapshot (hash + data) evitam duplicatas, mas não os perdidos |
| **Páginas além da profundidade que o site entrega** | A descoberta lê o total e confere se a última página responde; se o site limitar, segmentar as buscas (por bairro, faixa de preço). **Não foi medido** se as 378 páginas de venda de casas existem |
| **Imobiliárias:** `get_real_state` e `treat_real_state` hoje rodam no fim | Decidir se rodam por lote (upsert por imobiliária do lote) ou uma vez ao fim da execução. Em aberto |
| **Overhead por lote** (conexões, checagem, carga) | Lote lógico de uma página, mas task do Airflow de 10 páginas; medir na etapa 4 |
| **Termos de uso:** coletar a base inteira é escala bem maior que a amostra | Reler os termos do site antes; ritmo limitado e sem contornar proteções |

**Decisões em aberto para quem implementar:**

- `TEMP` ou *advisory lock* na carga (validar com os SQL).
- Valores finais de `QUARANTINE_*`, `PAGES_PER_TASK` e dos limites por lote, a calibrar com dados reais.
- Se a listagem (cerca de 118 MB por coleta) também é apagada ou fica como a última coleta. Proposta: apagar, para respeitar o orçamento.
- Se esta mudança inclui a atualização de preço pela listagem ou fica para depois.
