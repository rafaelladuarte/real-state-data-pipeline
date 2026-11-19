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
  4. Carga incremental e idempotente (upsert)
       ▼
  GOLD    ── Postgres: dimensões + fato + snapshots de preço + views
       │
  5. API Express ──▶ app React

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
- **Limitação conhecida:** o hash do tratamento não inclui o preço, então reprocessar atualiza o bruto, mas não altera documentos já tratados; isso é resolvido pelo histórico (D4).
- **Alternativas descartadas:** eliminar o Mongo (reescrita de tratamento e migração); manter só o Mongo (não permite reprocessar).

### D2. Paralelismo: Airflow dynamic task mapping + fila no Mongo
- **Decisão:** a coleção `links_imoveis` funciona como fila. Cada worker reserva links com `find_one_and_update` (com expiração da reserva) e processa em lotes mapeados com `.expand`.
- **Regras de coleta:** pausa por domínio, retentativa com backoff, limite de workers configurável.
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

### D4. Histórico: snapshots por coleta + primeira/última aparição
- **Problema:** o hash descarta anúncios já vistos, então mudanças de preço se perdem.
- **Decisão:** tabela de snapshots (anúncio, preço, data da coleta) e colunas de primeira/última aparição; anúncios que somem são marcados como inativos.
- **Habilita:** variação de preço e tempo médio no mercado.

## Princípios

- **Reprocessável:** qualquer camada pode ser reconstruída a partir da anterior.
- **Idempotente:** reexecutar uma etapa não duplica nem perde dados.
- **Observável:** cada execução registra itens coletados, erros e duração; quebra de parser gera alerta.
- **Coleta responsável:** ritmo limitado, sem contornar proteções, sem envio de dados fictícios a formulários, uso educacional.
- **Proporcional:** sem Kafka, Spark, Kubernetes ou dbt; cada ferramenta só entra com necessidade medida.

## Ordem sugerida de implementação

1. ~~**D3** — experimento HTTP vs Selenium~~ ✅ concluído: Selenium fica (ver D3).
2. ~~**D1** — armazenar HTML bruto e separar o parsing~~ ✅ concluído.
3. **D2** — fila com reserva atômica e workers em paralelo; benchmark com 1, 2 e 4 workers.
4. **Carga incremental** — upsert nas dimensões e no fato.
5. **D4** — snapshots de preço e telas no app.
6. **Qualidade e alertas**, depois **CI e subida em um comando**.
7. Só então **ampliar a cobertura** (mais páginas, venda e demais tipos).

## Pontos em aberto

- Onde hospedar o MinIO no `docker-compose` e política de retenção do HTML (tamanho × tempo).
- Frequência de recoleta para detectar mudanças de preço e anúncios removidos.
- Limite global de requisições por minuto que define o número máximo de workers (o experimento do D3 mostrou que o gargalo é o ritmo de cortesia, não o cliente).
