# Arquitetura alvo

Documento de alinhamento. Descreve para onde a arquitetura vai e por quê; a ordem de implementação está em [BACKLOG.md](BACKLOG.md).

## Visão geral

```
                         Airflow (orquestração)
                                  │
  1. Descoberta ──▶ fila de links (Mongo: links_imoveis, com reserva atômica)
                                  │
  2. Coleta  ──▶ N workers em paralelo (dynamic task mapping)
       │            HTTP simples; Selenium só se o teste (D3) exigir
       ▼
  BRONZE  ── HTML comprimido em object storage S3-compatível (chave: tipo/data/id)
       │
  3. Parse ──▶ reprocessável a partir do HTML guardado
       ▼
  SILVER  ── Mongo: raw_* (parseado) → treat_* (limpo, com hash)
       │
  4. Carga idempotente (upsert)
       ▼
  GOLD    ── Postgres: dimensões + fato + snapshots de preço + views
       │
  5. API Express ──▶ app React   (+ contorno dos bairros do IBGE, estático, para o mapa; ver D7)

  Transversal: validação dos documentos, checagem de taxa de nulos por execução,
  testes de contrato com HTML de exemplo, alerta em falha, métricas por execução.
```

## Decisões

### D1. Camada bruta: HTML em object storage S3-compatível, mantendo o Mongo ✅
- **Problema:** o Mongo guardava documentos já parseados. Quando o site foi redesenhado, foi preciso reescrever os scrapers e coletar tudo de novo.
- **Decisão:** guardar o HTML comprimido (gzip) no object storage. O Mongo continua como camada parseada (silver).
- **Implementação:**
  - `property.py` só busca e grava o HTML (`anuncio/AAAA-MM-DD/<id>.html.gz`); `links.py` também grava as páginas de listagem.
  - `parse_property.py` lê do storage e gera `raw_imoveis`, com `anuncio_id`, `link` e `html_key` para rastreabilidade.
  - `REPROCESS=true python scripts/etl/extraction/parse_property.py` reparseia todos os HTMLs sem acessar o site e substitui os documentos brutos do anúncio (testado: 8 → 8, sem duplicar).
  - Na DAG: `get_links → get_property → parse_property → get_real_state → start_treatment`.
- **Storage usado:** RustFS (S3-compatível). O MinIO deixou de publicar imagens da edição comunitária (Docker Hub e Quay recusaram o pull), e o cliente Python `minio` fala o protocolo S3, então a troca não altera o código além das variáveis `S3_*`.
- **Atualização (D8):** o HTML deixa de ser permanente. Depois que o lote do anúncio é carregado no Postgres, `purge_html.py` o apaga (`PURGE_HTML=false` mantém tudo); só o HTML que falhou fica, em quarentena. Reparsear coletas antigas que deram certo passa a exigir recoletar.
- **Limitação conhecida:** o hash do tratamento não inclui o preço, então reprocessar atualiza o bruto, mas não altera documentos já tratados; isso é resolvido pelo histórico (D4).
- **Alternativas descartadas:** eliminar o Mongo (reescrita de tratamento e migração); manter só o Mongo (não permite reprocessar).

### D2. Paralelismo: Airflow dynamic task mapping + fila no Mongo ✅
- **Decisão:** a coleção `links_imoveis` funciona como fila. Cada worker reserva links com `find_one_and_update` (lease com expiração, `scripts/infra/queue.py`). Em falha, o link volta à fila com backoff exponencial (30 s, 60 s, 120 s…) e, após 3 tentativas, é marcado como erro.
- **Limite global:** um `RateLimiter` no Mongo reserva atomicamente o próximo "slot" de tempo, então a soma de todos os workers respeita um intervalo mínimo entre requisições (`MIN_INTERVAL_SECONDS`, padrão **1,25 s ≈ 0,8 anúncio/s ≈ 48 por minuto**). O relógio usado é o do servidor Mongo (`$$NOW`), independente dos clientes.
- **Na DAG:** `DockerOperator.partial(...).expand(environment=[...])` cria uma instância por worker (`SCRAPER_WORKERS`, padrão 3), todas consumindo a mesma fila.
- **Benchmark** (`docs/experiments/parallel_scaling.py`, 20 anúncios por rodada, requisições reais):

  | Workers | OK | Erros | Tempo (s) | Anúncios/s |
  |---|---|---|---|---|
  | 1 | 20 | 0 | 40,8 | 0,49 |
  | 2 | 20 | 0 | 26,3 | 0,76 |
  | 4 | 20 | 0 | 26,6 | 0,75 |

- **Leitura:** 1 worker fica limitado pela latência do navegador (~1,9 s por página); com 2 o teto global (0,80/s) já é atingido, e com 4 não há ganho, só mais Chrome em memória. Nenhum anúncio foi coletado duas vezes (20 chaves distintas em cada rodada). Comparado à coleta serial original (~5 s por anúncio, ≈ 0,2/s), a taxa é cerca de **3,8× maior**; 7.000 anúncios levariam ~2,6 h em vez de ~10 h.
- **Por que 3 workers por padrão:** 2 já saturam o teto; o terceiro dá folga quando uma página demora ou falha e é reenfileirada.
- **Limitações:** o limitador e a fila dependem do Mongo estar acessível a todos os workers. A lista de workers da DAG é fixa por configuração (`SCRAPER_WORKERS`), não calculada a partir do tamanho da fila; planejar isso dinamicamente exigiria `pymongo` na imagem do Airflow.
- **Alternativa descartada:** Redis + Celery (dois serviços a mais, sem necessidade para o volume atual).

### D3. Coleta: Selenium; HTTP simples não funciona (experimento concluído)
- **Experimento** (19/11/2026, `docs/experiments/http_vs_selenium.py`): 1 página de listagem e 5 anúncios, pausa de 2 s entre requisições, cada cliente na mesma amostra.

  | Cliente | Sucesso | Status | Latência média |
  |---|---|---|---|
  | `requests` | 0/6 | 403 | 0,11 s |
  | `httpx` | 0/6 | 403 | 0,09 s |
  | Selenium (Chrome headless) | 6/6 | 200 | 1,87 s |

- **Leitura:** a Cloudflare responde 403 a clientes HTTP simples, inclusive para o `robots.txt`. O Selenium recebe o conteúdo normalmente.
- **Decisão:** manter o Selenium na coleta. Não tentar imitar navegador por outras vias (fingerprint TLS, etc.): seria contornar a proteção do site, o que está fora do escopo.
- **Consequência para a escala:** o custo por anúncio (~1,9 s de busca + 3 s de pausa ≈ 5 s) vem do navegador e da pausa de cortesia, não de CPU. O ganho vem de paralelizar (D2) **respeitando um limite global de requisições**, não de trocar o cliente. Com N workers e pausa de 3 s cada, a taxa fica em torno de N/5 anúncios por segundo; o N máximo aceitável depende do limite de requisições por minuto definido abaixo.
- **Reaproveitamento:** reduzir o custo do navegador (reusar a sessão em lotes, hoje um Chrome novo por página) continua possível, mas na primeira tentativa a sessão reaproveitada expirou na página 2, então precisa ser medido.

### D4. Histórico: snapshots por coleta + ciclo de vida do anúncio ✅
- **Problema:** o hash do anúncio (tipo, modo, área, quartos, banheiros, vagas, bairro, data de criação) identifica o imóvel e ignora o preço; por isso um anúncio recoletado era descartado e mudanças de preço se perdiam.
- **Decisão e implementação:**
  - Cada observação gera um **snapshot** (`snapshots_imoveis` no Mongo, chave `hash + data de coleta`, índice único) mesmo quando o anúncio já está tratado; anúncios conhecidos não refazem imagens nem entram de novo em `treat_imoveis`.
  - No Postgres, `imovel_snapshot (id_imovel, data_coleta, preco, condominio, iptu)`; o **preço atual** de `imovel` vem do snapshot mais recente (fonte da verdade).
  - View `imovel_ciclo_vida`: primeira/última coleta, nº de coletas, preço inicial/atual, variação (%), mudanças de preço, **dias no mercado** (última coleta − data de criação do anúncio) e `visto_na_ultima_coleta`.
  - **Recoleta:** a task `requeue_stale_links` (primeira da DAG `extraction`) reenfileira links coletados há mais de `RECRAWL_AFTER_DAYS` (7) dias; links coletados antes do D4 contam como antigos.
  - `python scripts/etl/treatment/snapshots.py` cria o primeiro snapshot dos anúncios tratados antes do D4 (idempotente).
  - App: tempo mediano no mercado por bairro e variação de preço entre coletas.
- **O que já aparece com 1 coleta:** tempo no mercado (vem da data de criação do anúncio no site; na amostra, mediana de 14 dias para aluguel e 46 para venda). **Variação de preço** só aparece a partir da 2ª coleta em outro dia; até lá o app informa isso em vez de mostrar uma tela vazia.
- **Cuidado de interpretação:** `visto_na_ultima_coleta = falso` não significa que o anúncio saiu do ar, porque a coleta cobre só parte das páginas. Detectar remoção de verdade exigiria varrer toda a busca.
- **Bugs corrigidos no caminho:** `insert_hash_documents` quebrava com lista vazia (exatamente o caso de uma recoleta sem anúncios novos) e logava `ERROR` com 0 erros.
- **Não validado com dados reais ainda:** a mudança de preço foi testada com dados sintéticos (testes de integração); a recoleta real em outro dia ainda não aconteceu.

### D5. Carga no Postgres: staging completo + upsert idempotente ✅
- **Problema:** os `INSERT` não eram reexecutáveis (falhavam em tipos/modos já existentes e duplicavam endereços), os joins por texto de endereço eram ambíguos, imóveis com tipo novo eram descartados em silêncio pelo `INNER JOIN`, e `update.py` estava quebrado.
- **Decisão:**
  - `migrate.py` copia a camada tratada do Mongo para o staging `_treat_*` (snapshot completo, recriado a cada execução).
  - `model.py` aplica todos os arquivos SQL de `scripts/etl/modeling` em **uma transação**; todos são idempotentes (`IF NOT EXISTS`, `OR REPLACE`, `ON CONFLICT`).
  - `endereco` ganhou índice único: imóveis do mesmo endereço compartilham uma linha.
  - Tipos e modos novos da coleta são criados a partir do staging.
  - Imóveis e imobiliárias usam upsert: preço, descrição, imagens e datas são atualizados só quando mudam (os triggers recalculam custo/m² e faixa de área).
- **Resultado:** reexecutar 3 vezes mantém 169 imóveis, 26 imobiliárias e 168 endereços (antes 195, com duplicados); se algo falha, nada é aplicado. Coberto por testes de integração (`tests/test_model_load.py`).
- **Escolha consciente (substituída pela D8):** o staging era completo, recriado a cada execução, o que era barato com ~10 mil linhas. A D8 trocou isso por carga incremental por lote.
- **Limitação:** o hash do tratamento ignora o preço, então um anúncio recoletado com preço novo ainda é descartado na camada Mongo antes de chegar aqui; isso é resolvido pelo histórico (D4).
- **Na DAG `load`:** `migrate_to_postgres → model_data`, ambos em `DockerOperator` (os caminhos antigos para `/opt/airflow/scr/...` não existiam). A DAG `treatment` já a dispara no fim.

### D6. Qualidade, alertas e CI ✅
- **Gate de qualidade** (`scripts/etl/quality.py`): o parsing avalia campos vazios e erros **antes de gravar**. Com o parser quebrado, nada entra em `raw_imoveis` e os links não são marcados como processados; corrigido o parser, a execução seguinte reprocessa o mesmo HTML (benefício direto da camada bruta, D1). Testado com um parser simulado como quebrado.
- **Limites** (calibrados com os dados reais, em que os campos essenciais têm 0% de nulos): críticos ≤ 5%, importantes ≤ 30%, erros ≤ 20%, e só com amostra de pelo menos 10 itens.
- **Bloqueio do site:** o worker de coleta também falha quando a taxa de links que desistiram passa do limite.
- **Disjuntor anti-bloqueio:** ao detectar o desafio da Cloudflare (título "Just a moment..."), o worker lança `BlockedError`, não repete a requisição, devolve o link à fila com pausa de 15 min sem gastar tentativa e, após 3 bloqueios seguidos, interrompe a coleta e falha a task. Motivação real: na coleta de venda, com 3 workers e 1,25 s de intervalo, cerca de um quarto das requisições passou a receber o desafio; os workers foram parados, o site voltou ao normal e a coleta foi retomada com 2 workers e 3 s de intervalo. O benchmark do D2 (20 anúncios por rodada) não revelou esse limite: ele só aparece em coletas mais longas, então o intervalo seguro precisa ser validado em volume.
- **Observabilidade:** coleção `run_metrics` com total, erros, taxas e violações por etapa.
- **Alertas:** `on_failure_callback` das três DAGs envia a falha ao webhook de `ALERT_WEBHOOK_URL`; o envio nunca derruba a DAG.
- **CI:** lint (ruff), pytest com Mongo e Postgres como serviços, build do frontend e build da imagem de ETL com teste rápido. Validado localmente a partir de um clone novo; o workflow em si ainda não rodou no GitHub.
- **Achados no caminho:** `index.html` do app e os HTMLs de exemplo dos testes não estavam versionados (a regra `*.html` do `.gitignore` os escondia), o que quebraria o build e os testes de quem clonasse; o healthcheck do Mongo no compose usava o comando `mongo`, que não existe nas imagens atuais; e o limitador agora desconta metade da latência de ida e volta para acordar perto do slot reservado.

### D7. Mapa por bairro: contorno estático do IBGE, casado por nome ✅
- **Problema:** o banco guarda só o nome do bairro (sem latitude/longitude), então um mapa por anúncio exigiria geocodificar endereços. O mapa por bairro precisa apenas de um contorno por bairro.
- **Decisão:** usar a **Malha de Bairros do Censo 2022 (IBGE)**, baixada uma vez e versionada como `app/web/public/bairros-uberlandia.geojson` (75 bairros, ~70 KB, geometria simplificada). Não entra no Airflow: é um dado estático, gerado por `scripts/geo/` (`baixar_bairros.py`, `preparar_bairros.py`). OpenStreetMap e a Prefeitura foram avaliados; o IBGE ganhou por ser um arquivo único, oficial e com código de bairro (comparação em [spec/mapa-por-bairro.md](spec/mapa-por-bairro.md)).
- **Casamento por nome:** o bairro do anúncio e o do IBGE são reduzidos a uma chave (sem acento, minúsculas, abreviações como "Sta." e "Jd." expandidas). Variações conhecidas ("Gávea Sul" → "Gávea") ficam em `scripts/geo/apelidos_bairros.json` e vão para o campo `chaves` de cada feature. A API (`/api/mapa`) lê o GeoJSON, agrega por polígono e aplica a mesma regra de 3 ou mais anúncios dos gráficos.
- **Cobertura medida:** 415 de 438 anúncios (94,7%) caem em um bairro com polígono. Os demais são loteamentos e condomínios sem contorno oficial; `python -m scripts.geo.relatorio_cobertura` lista os que ficaram de fora e sai com erro abaixo de 90%.
- **Mapa sem fundo:** SVG com `d3-geo`, sem tiles, então o app continua funcionando sem rede.
- **Limitações:** os limites do IBGE são aproximados (ajustados aos setores censitários). A normalização existe em Python (`scripts/geo/nomes.py`) e em JavaScript (`app/api/bairros.js`) e precisa ser mantida igual; gravar a chave no ETL está no backlog (item 18).
- **Licença:** dado público do IBGE; a fonte é citada no app e no README. Os termos formais de redistribuição não puderam ser lidos automaticamente (o catálogo de metadados do IBGE responde com desafio anti-bot, que não é contornado); confira o documento "Informações Técnicas e Legais" do IBGE antes de redistribuir o arquivo fora deste projeto.

### D8. Carga incremental por lote e limpeza segura do HTML ✅
- **Problema:** o staging era recriado com a camada tratada inteira a cada carga. Com um lote por página isso copiaria ~13,8 milhões de linhas para 28.722 anúncios (spec em `docs/spec/coleta-em-lotes.md`). E o HTML bruto cresce 268 GB por ano se recoletar toda semana, mais do que o disco comporta.
- **Decisão (carga incremental):**
  - Cada execução do tratamento gera um `batch_id` único (`AAAAMMDDTHHMMSS-xxxx`; só a data seria um bug: o que fosse tratado depois da primeira carga do dia nunca subiria). Documentos tratados, snapshots de preço e imobiliárias o carregam.
  - `migrate.py` compara os lotes do Mongo com `lote_carga` e recria o staging com os lotes pendentes. `model.py` aplica o staging, **registra os lotes em `lote_carga` e o esvazia na mesma transação**: "aplicado" e "registrado" nunca divergem, e uma carga que falha deixa o lote pendente, sem duplicar nada ao tentar de novo.
  - Um lote é pendente se não está em `lote_carga`, se o Mongo tem hoje mais documentos dele do que os registrados (a carga o pegou pela metade) ou se alguma linha dele não chegou às tabelas finais. Este último caso cobre os `INNER JOIN` do `insert_tables_oficial.sql`: um imóvel de imobiliária ainda não coletada deixa o lote pendente em vez de ser perdido, e ele volta na próxima carga. O staging é recriado a cada carga (o Mongo é a origem), o que também acompanha campos novos nos documentos.
  - `migrate` e `model` tomam o mesmo advisory lock de transação, então lotes diferentes entram em fila em vez de disputar o staging. Foi a alternativa às tabelas `TEMP` da spec, porque migrate e model são tasks (processos) separadas.
  - `BATCH_ID=<id>` força a recarga de um lote; documentos tratados antes disso (sem `batch_id`) entram uma única vez como o lote `legado`.
- **Decisão (limpeza do HTML):**
  - `purge_html.py`, último passo da DAG `load`, apaga o HTML só de anúncios tratados cujo lote foi aplicado por inteiro (mesma regra de pendência acima), e só se nenhum outro documento que usa a mesma chave ainda depender dela. Primeiro o storage, depois a marca no Mongo (`html_purged`): se apagar falhar, nada é marcado e a próxima execução tenta de novo.
  - O que falhou no parse ou no tratamento fica no storage e é registrado em `quarentena_html`. Limites: `QUARANTINE_MAX_BATCHES` (lotes distintos com HTML retido) e `QUARANTINE_CONSECUTIVE` (execuções seguidas que acrescentaram itens). Ao atingir um deles, o `purge_html` falha e o `requeue` (primeira task da `extraction`) recusa iniciar a coleta, em vez de gastar horas com um parser quebrado. Após `HTML_QUARANTINE_DAYS` o HTML em quarentena é apagado.
  - `PURGE_HTML=false` mantém o HTML para sempre. O HTML de anúncios tratados antes da carga incremental só é apagado com `PURGE_LEGACY_HTML=true`.
- **Resultado:** carregar os mesmos dados em 3 lotes ou de uma vez deixa o Postgres no mesmo estado (teste de equivalência); reexecutar não duplica; falha na carga mantém o HTML e sucesso o remove. Nos dados reais de 19/11, a primeira carga levou os 438 imóveis como `legado` e a seguinte não tinha nada pendente. Testes em `tests/test_incremental_load.py` e `tests/test_purge_html.py`.
- **Consequência (perda do bronze):** depois do lote carregado, reparsear exige recoletar; `REPROCESS=true` só vale para o HTML retido. Mitigação: a quarentena e as fixtures de `tests/fixtures/`.
- **Recuperação da quarentena:** o `requeue` bloqueia a DAG `extraction` inteira, inclusive o parse. O caminho para retomar (corrigir o parser, `REPROCESS=true` no parse e disparar a `treatment`, que encadeia a `load` e o `purge_html`) está em `scripts/etl/quarantine.py` e no README.
- **Revisão de código:** a primeira versão perdia para sempre imóveis descartados pelos `INNER JOIN`, registrava lotes carregados pela metade e podia travar o staging com um campo novo. Os três casos viraram testes de regressão (falham no código anterior).
- **Limitações:** `treat_property` e `treat_real_state` são tasks separadas e geram `batch_id` diferentes; como a pendência é calculada por lote e por coleção, isso não afeta a carga. Fixar um `BATCH_ID` pela DAG seria pior: refazer o run com Clear reutilizaria um lote já registrado. Na quarentena, "lote" é a execução do `purge_html` que registrou o item. O "lote" do tratamento é a execução; com a coleta em lotes por página (item 23 do backlog) passa a ser a página. O HTML das **listagens** (`listagem/...`) ainda não é apagado. Falta medir o disco na primeira coleta completa (item 24).

## Princípios

- **Reprocessável:** qualquer camada pode ser reconstruída a partir da anterior.
- **Idempotente:** reexecutar uma etapa não duplica nem perde dados.
- **Observável:** cada execução registra itens coletados, erros e duração; quebra de parser gera alerta.
- **Coleta responsável:** ritmo limitado, sem contornar proteções, sem envio de dados fictícios a formulários, uso educacional.
- **Proporcional:** sem Kafka, Spark, Kubernetes ou dbt; cada ferramenta só entra com necessidade medida.

## Ordem sugerida de implementação

1. ~~**D3** — experimento HTTP vs Selenium~~ ✅ concluído: Selenium fica (ver D3).
2. ~~**D1** — armazenar HTML bruto e separar o parsing~~ ✅ concluído.
3. ~~**D2** — fila com reserva atômica e workers em paralelo~~ ✅ concluído (benchmark em D2).
4. ~~**Carga idempotente** — upsert nas dimensões e no fato~~ ✅ concluído (ver D5).
5. ~~**D4** — snapshots de preço e telas no app~~ ✅ concluído (ver D4; a variação real depende de uma 2ª coleta em outro dia).
6. ~~**Qualidade e alertas**, depois **CI**~~ ✅ concluído (ver D6). Falta a **subida em um comando**.
7. Só então **ampliar a cobertura** (mais páginas, venda e demais tipos).

## Pontos em aberto

- Onde hospedar o MinIO no `docker-compose` e política de retenção do HTML (tamanho × tempo).
- Frequência de recoleta para detectar mudanças de preço e anúncios removidos.
- ~~Limite global de requisições~~ definido: 1,25 s entre requisições (≈ 48/min), configurável. Revisar se o site começar a responder com bloqueios.

### D-hash. Identidade do imóvel e quarentena no tratamento

- **Decisão:** o hash do imóvel (tipo, modo, área, quartos, banheiros, vagas, bairro, data de criação) **não** inclui o `anuncio_id` nem a imobiliária. A intenção é juntar o mesmo imóvel anunciado por várias imobiliárias.
- **Limitação:** unidades idênticas no mesmo bairro e cadastradas no mesmo dia (ex.: lançamentos) viram um só. Incluir o `anuncio_id` evitaria isso, mas mudaria todos os hashes já gravados e duplicaria o histórico.
- **Erros no tratamento:** um anúncio que falha **não** é marcado como tratado; recebe `treat_error` e `treat_attempts`. Após `MAX_TREAT_ATTEMPTS` (3) vai para quarentena (`treat_quarantine`) e sai da fila e do quality gate. A taxa de erros da execução é avaliada depois de gravar o que deu certo e registrada em `run_metrics`.
- **Carga:** a tabela fato usa `INNER JOIN` com `imobiliaria` (`id_imobiliaria` é `NOT NULL`); imóveis de imobiliárias ainda não coletadas ficam de fora, e `model.py` registra um aviso com a quantidade.
