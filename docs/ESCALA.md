# Escala: coletar todos os anúncios de Uberlândia no ZAP Imóveis

Quanto tempo leva e quanto espaço ocupa coletar **todos** os anúncios de Uberlândia (aluguel e venda de casas e apartamentos), em vez da amostra de 3 páginas por busca.

Data das medidas: 19/11/2026. Tudo que está marcado como **medido** vem de dados reais do projeto; o que está como **estimado** é conta em cima dessas medidas, com a premissa dita ao lado.

## Resumo

| | Amostra atual | Base inteira de Uberlândia |
|---|---|---|
| Anúncios | 438 | **28.722** (7.047 de aluguel, 21.675 de venda) |
| Páginas de listagem | 12 | 958 |
| Tempo de coleta completa | não medido | **11 a 12 h no melhor caso; cerca de 56 h (2,3 dias) no ritmo observado em coleta real** |
| HTML bruto (object store) | 54 MB | **cerca de 5,2 GB por coleta completa** |
| Mongo (silver) | 3,6 MB | cerca de 233 MB |
| Postgres (gold) | 2,6 MB de tabelas do projeto | cerca de 173 MB, mais 15 MB por coleta (snapshots) |
| Crescimento do HTML se recoletar toda semana | – | **cerca de 21 GB por mês e 268 GB por ano**, se nada for descartado |

Conclusão: o **armazenamento de dados é barato**. O que pesa é o **HTML bruto acumulado** (que cresce a cada recoleta) e o **tempo e o risco de bloqueio** da coleta. Há uma alavanca grande para as recoletas, descrita em [Como reduzir](#como-reduzir).

## 1. Tamanho do universo

O ZAP informa o total de anúncios no título de cada busca. Os valores abaixo foram lidos das páginas de listagem que o pipeline já guardou em 19/11/2026 (`<meta name="description">`, "N anúncios de ... em Uberlândia, MG"):

| Busca | Anúncios | Páginas de 30 |
|---|---|---|
| Aluguel de apartamentos | 4.739 | 158 |
| Aluguel de casas | 2.308 | 77 |
| Venda de apartamentos | 10.340 | 345 |
| Venda de casas | 11.335 | 378 |
| **Total** | **28.722** | **958** |

Esses totais mudam todo dia. Medido: o número é o que o site declarou; não foi verificado se a paginação do site alcança todas essas páginas (ver [Riscos](#riscos-e-o-que-não-foi-medido)).

## 2. Tempo de coleta

**Requisições:** 28.722 páginas de anúncio + 958 de listagem = **29.680 requisições**.

**Taxas medidas no projeto** (README, seção "Resultados medidos", e `run_metrics` no Mongo):

| Origem | Taxa |
|---|---|
| Teto do limitador global (`MIN_INTERVAL_SECONDS=1,25`) | 0,8 requisição/s |
| Benchmark com 2 ou 4 workers (20 anúncios, requisições reais) | 0,76 anúncio/s |
| Coleta real de venda, com ritmo reduzido após bloqueios (1 worker, 65 anúncios em 440,5 s) | 0,147 anúncio/s (6,8 s por anúncio) |

**Cenários para 28.722 anúncios** (estimado: taxa × anúncios, mais 958 listagens a 4,9 s cada, ou 1,3 h; ver a nota abaixo):

| Cenário | Taxa | Tempo |
|---|---|---|
| Teto teórico do limitador | 0,8/s | 11,3 h |
| Benchmark | 0,76/s | 11,8 h |
| Ritmo observado em coleta real | 0,147/s | **55,5 h (2,3 dias)** |

- **Descoberta de links:** `links.py` percorre as buscas em sequência, fora do limitador global: espera 3 s entre páginas e abre um Chrome por página (cerca de 1,9 s de latência medida). São 958 páginas × 4,9 s, ou **1,3 h**, e nenhum anúncio é coletado antes de a descoberta terminar.
- A partir de 2 workers o teto global já é atingido (benchmark do README), então **mais workers não aceleram**; só gastariam mais memória. O gargalo é o intervalo entre requisições, que existe de propósito (coleta responsável).
- A diferença entre 11 h e 56 h vem do que aconteceu na coleta de venda: o site começou a devolver desafios anti-bot, o disjuntor do worker pausou os links (15 min por bloqueio) e o ritmo foi reduzido. Numa coleta de 29 mil requisições, esperar bloqueios é razoável. O tempo real fica entre os dois cenários.
- **Não medido:** o tempo do parsing (`parse_property`), do tratamento e da carga no Postgres. As métricas guardadas não têm duração para esses passos. São etapas locais (sem o site), então tendem a ser bem menores que a coleta, mas isso é uma expectativa, não um número.
- Recoletar toda semana (`RECRAWL_AFTER_DAYS=7`) repete essa conta: no cenário observado seriam 56 h de coleta por semana, cerca de um terço do tempo de uma máquina ligada.

## 3. Armazenamento

### Tamanho por anúncio (medido na amostra de 438 anúncios)

| Camada | Medida | Por anúncio |
|---|---|---|
| Object store (HTML bruto, gzip) | 331 páginas de anúncio, 53,3 MB (média de **161 KB**); 12 páginas de listagem, 1,47 MB (média de 123 KB) | 161 KB mais cerca de 4 KB de listagem |
| Mongo, em disco | 3,04 MB de dados e 0,51 MB de índices para 438 anúncios | **8,1 KB** |
| Postgres | `imovel`, `endereco`, `imovel_snapshot` e as tabelas de staging: cerca de 2,6 MB | **6,0 KB** |

Notas sobre as medidas:

- O bucket tem 331 páginas de anúncio, não 438: parte da amostra foi coletada antes de o HTML bruto passar a ser guardado (backlog, item 1). Por isso a média usa as 331.
- O HTML de um anúncio tem em média 710 KB sem compressão e 160 KB com gzip (4,4 vezes). O gzip é o que o pipeline já usa.
- O `du` do bucket dá 58,1 MB para 54,8 MB de dados, ou seja, 8,7% de sobrecarga (metadados e blocos). Em objetos maiores essa proporção tende a cair, mas usei a medida.
- O Postgres do app tem 12 MB no total por causa do próprio banco vazio; contei só as tabelas do projeto.

### Projeção para 28.722 anúncios (estimado, uma coleta completa)

| Camada | Cálculo | Total |
|---|---|---|
| HTML dos anúncios | 28.722 × 161 KB | 4,62 GB |
| HTML das listagens | 958 × 123 KB | 118 MB |
| **Object store** (com 8,7% de sobrecarga) | | **5,15 GB** |
| Mongo | 28.722 × 8,1 KB | 233 MB |
| Postgres | 28.722 × 6,0 KB | 173 MB |
| Snapshot de preço por coleta (Postgres) | 28.722 × 0,52 KB | 15 MB |
| Snapshot de preço por coleta (Mongo) | 28.722 × 0,25 KB | 7 MB |

Banco de dados (Mongo e Postgres) ficam abaixo de 0,5 GB. Não são o problema.

### Crescimento do HTML com recoletas

Cada recoleta grava HTML novo sob a data do dia. Sem política de retenção, acumula (estimado, 5,15 GB por coleta completa):

| Coletas completas guardadas | Object store |
|---|---|
| 1 | 5,2 GB |
| 4 (1 mês, semanal) | 20,6 GB |
| 13 (1 trimestre) | 67 GB |
| 52 (1 ano) | 268 GB |

A política de retenção do HTML já era um ponto em aberto em `ARCHITECTURE.md`; com a base inteira ela deixa de ser opcional.

### Custo em dinheiro

Depende de onde rodar, e o projeto roda hoje em Docker local, sem custo de hospedagem. A fórmula é: **GB guardados × preço do GB por mês do provedor**. Como exemplo, com **US$ 0,023 por GB-mês** (preço de tabela de referência de um armazenamento S3 padrão; **não verifiquei o preço atual**, confira no provedor):

| Object store | Custo mensal de exemplo |
|---|---|
| 5,2 GB | cerca de US$ 0,12 |
| 20,6 GB | cerca de US$ 0,47 |
| 67 GB | cerca de US$ 1,54 |
| 268 GB | cerca de US$ 6,16 |

O armazenamento custa centavos a poucos dólares por mês. O custo real seria a máquina que roda o coletor por horas, com um Chrome por worker. **Não medi o consumo de memória e CPU por worker**, então não dá para dimensionar a máquina sem um teste.

## Como reduzir

1. **Atualizar preços pela listagem, sem reabrir cada anúncio (maior ganho).** A listagem já traz, em JSON-LD, os 30 itens de cada página com id, título, área, quartos e **preço** (conferido no HTML guardado: todos os 30 itens da página têm `offers.price`). Recoletar só as 958 páginas de listagem leva cerca de 1,3 h (no ritmo atual da descoberta de links), contra 11 a 56 horas, e grava cerca de 128 MB por coleta em vez de 5,2 GB. A página do anúncio só precisaria ser aberta para anúncios **novos**. Isso exige mudar o pipeline: hoje o snapshot de preço nasce da página do anúncio.
2. **Política de retenção do HTML:** manter só as últimas N coletas por anúncio, ou descartar o HTML de anúncios cujo conteúdo não mudou.
3. **Compressão melhor:** num teste com 10 páginas de anúncio, `xz` ficou em 123 KB contra 160 KB do gzip (cerca de 23% menor). `zstd` não foi testado.
4. **Alertar quando a coleta atingir o teto de bloqueios**, para não gastar horas com o disjuntor aberto.

## Riscos e o que não foi medido

- **Profundidade da paginação:** coletei só 3 páginas por busca. Não sei se o site entrega as 378 páginas da busca de casas à venda. Se limitar a profundidade, será preciso segmentar as buscas (por bairro, faixa de preço, número de quartos), o que muda o número de requisições.
- **Duplicidade:** o mesmo imóvel pode estar anunciado por várias imobiliárias. O hash do pipeline junta esses casos (decisão D-hash), então o número de imóveis **distintos** tende a ser menor que 28.722.
- **Bloqueio anti-bot:** o site usa Cloudflare e bloqueou a coleta de venda mesmo no ritmo definido. O projeto não contorna a proteção. Uma coleta de quase 30 mil requisições pode ser interrompida e retomada várias vezes.
- **Termos de uso:** o projeto é educacional. Coletar a base inteira é uma escala bem diferente da amostra; vale reler os termos do site antes.
- **Não medidos:** tempo de parsing, tratamento e carga; memória e CPU por worker; consumo de banda; compressão com `zstd`.
- **Outras cidades:** os valores por anúncio (161 KB de HTML, 8,1 KB no Mongo, 6,0 KB no Postgres, 7 s por anúncio no pior caso) servem para multiplicar pelo total de qualquer outra busca. Só medi o total de Uberlândia.

## Como reproduzir as medidas

```bash
# Mongo: tamanho por coleção
docker exec real_state_mongo mongosh -u username -p password --authenticationDatabase admin \
  --quiet real_state --eval 'db.getCollectionNames().forEach(c => printjson([c, db[c].stats().size]))'

# Postgres: tamanho por tabela
docker exec real_state_postgres psql -U username -d real_state \
  -c "SELECT relname, n_live_tup, pg_total_relation_size(relid) FROM pg_stat_user_tables ORDER BY 3 DESC"

# Object store: tamanho do bucket
docker exec real_state_minio du -sk /data/real-state-html

# Métricas de coleta (duração por worker)
docker exec real_state_mongo mongosh -u username -p password --authenticationDatabase admin \
  --quiet real_state --eval 'db.run_metrics.find({step:"fetch"}).forEach(printjson)'
```

Os totais por busca estão no `<meta name="description">` das páginas de listagem guardadas em `listagem/<data>/`.
