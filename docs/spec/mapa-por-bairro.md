# Especificação: mapa de Uberlândia colorido por bairro

Status: proposta (não implementada); fonte do contorno definida · Escopo: app de visualização (`app/`) e um script de preparo único (`scripts/geo/`).

## 1. Contexto e objetivo

O app responde "quanto custa alugar/comprar em Uberlândia?" com gráficos de barras por bairro. O ranking mostra a ordem, mas não a distribuição espacial. O objetivo é adicionar um **mapa de Uberlândia com cada bairro colorido por uma métrica** (preço médio, quantidade de anúncios ou idade do anúncio), respeitando os filtros que a página já tem (aluguel/venda e tipo de imóvel).

### Fora de escopo

- Um ponto por anúncio. Exigiria geocodificar endereços e guardar `lat`/`lon` no ETL e no modelo de dados. Fica registrado como evolução futura (seção 10).
- Mapa de ruas de fundo (tiles). O mapa desenha só os contornos dos bairros.
- Alterações em `dags/`, `docker-compose.yml`, tabelas e views do Postgres.

## 2. Restrições do dado atual

- O banco guarda apenas o **nome do bairro** (`endereco.bairro`) e o texto do endereço. Não há coordenadas.
- A coleta é uma amostra das primeiras páginas de cada busca, não o mercado inteiro. O mapa deve repetir esse aviso.
- As médias por bairro só consideram bairros com **3 ou mais anúncios** (regra já usada em `/api/preco-medio` e `/api/tempo-mercado`). Bairros abaixo disso aparecem sem valor.

## 3. Dado externo

Só o contorno dos bairros vem de fora. É um dado estático, obtido uma vez e versionado no repositório. Não entra no pipeline recorrente nem no Airflow.

| Dado | Origem | Frequência |
|---|---|---|
| Preço, quantidade e idade por bairro | Postgres (já existe) | A cada coleta |
| Contorno dos bairros (GeoJSON) | Fonte pública | Uma vez |

### Fonte escolhida: IBGE, Malha de Bairros do Censo 2022

Verificada em 2026-11-19 contra os dados reais do banco (438 anúncios, 77 bairros distintos, nenhum bairro nulo).

| Fonte | Resultado |
|---|---|
| **IBGE, Malha de Bairros (Censo 2022)** | **Escolhida.** `MG_bairros_CD2022.zip` (2,3 MB, shapefile SIRGAS 2000), 75 bairros em Uberlândia (`CD_MUN = 3170206`). |
| OpenStreetMap (Overpass) | 107 relações com polígono, 73 dos 75 nomes do IBGE em comum, mais 34 polígonos que o IBGE não tem (condomínios, loteamentos, chácaras). Licença ODbL, exige atribuição. Não acrescentou cobertura sobre os anúncios atuais. Reserva para bairros futuros. |
| Prefeitura de Uberlândia | Sem dado aberto de bairros: a página "Mapas e Bairros" só traz PDFs e os Dados Abertos tratam de receitas. O portal `planejaudi.com.br` oferece download de camadas, mas não foi confirmado se é oficial nem a licença. |

URL do arquivo: `https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/bairros/shp/UF/MG_bairros_CD2022.zip`

Ressalvas:

- O IBGE ajustou os limites aos setores censitários, então são aproximados.
- A licença formal de redistribuição do arquivo ainda precisa ser confirmada antes de versionar o GeoJSON; citar IBGE (Censo 2022) como fonte no README.
- O OSM exige a atribuição "© OpenStreetMap contributors" e o cabeçalho `User-Agent` nas consultas (sem ele o Overpass responde 406).

### Cobertura medida

| Contorno | Anúncios com polígono |
|---|---|
| IBGE | 411 de 438 (**93,8%**) |
| IBGE + OSM | 411 de 438 (93,8%), sem ganho |

Bairros do banco sem polígono no IBGE (27 anúncios): Bosque dos Buritis (5), Santa Maria (3), Jardim Célia (3), Copacabana (2), Jardim Finotti (2), Loteamento Monte Hebron (2) e 10 bairros com 1 anúncio cada.

Parte se resolve com `apelidos_bairros.json`, pois o nome é uma variação de um bairro existente: Conjunto Alvorada → Alvorada, Gávea Sul → Gávea, Mansour III → Mansour, Te-Vis - Jardim das Palmeiras → Jardim das Palmeiras. Isso leva a cobertura para cerca de 94,7%. Os demais (loteamentos e condomínios) ficam sem polígono e entram no relatório de cobertura.

## 4. Arquitetura

```
[Fonte pública] --(uma vez)--> scripts/geo --> bairros-uberlandia.geojson (versionado)
                                                        |
Postgres --> API Express --> GET /api/mapa --> React <Mapa/> (d3-geo, SVG)
                                                        ^
                                       GeoJSON servido como estático pelo Vite
```

O casamento entre bairro do banco e polígono é feito por **nome normalizado** (minúsculas, sem acento, sem prefixos como "Bairro" ou "Jardim" abreviado). O script de preparo grava em cada feature `bairro` (nome oficial), `codigo` (IBGE) e `chaves` (chave do nome oficial mais as dos apelidos de `apelidos_bairros.json`). A API lê o GeoJSON, mapeia cada bairro do anúncio para a chave do polígono e agrega por ela, então bairros como "Gávea" e "Gávea Sul" caem no mesmo polígono.

## 5. Estrutura de arquivos

```
scripts/geo/                          NOVO (preparo único, fora de scripts/etl/)
  __init__.py
  baixar_bairros.py                   baixa o contorno da fonte escolhida
  preparar_bairros.py                 simplifica a geometria, normaliza nomes, gera o GeoJSON
  apelidos_bairros.json               equivalência "nome no anúncio -> bairro oficial"
  relatorio_cobertura.py              lista bairros do banco sem par no mapa e vice-versa
app/api/server.js                     + rota GET /api/mapa
app/web/public/bairros-uberlandia.geojson   NOVO, estático
app/web/package.json                  + d3-geo
app/web/src/Mapa.jsx                  NOVO (componente do mapa)
app/web/src/App.jsx                   + seção do mapa
app/web/src/style.css                 + estilos do mapa
tests/test_geo_bairros.py             NOVO
docs/ARCHITECTURE.md                  + trecho sobre o mapa e a origem do contorno
```

`scripts/geo/` fica fora de `scripts/etl/` de propósito: o ETL roda a cada coleta, e o contorno é baixado uma vez. Misturar os dois sugeriria que o Airflow precisa atualizá-lo.

## 6. Preparo do contorno (`scripts/geo/`)

1. `baixar_bairros.py` obtém o dado bruto da fonte escolhida.
2. `preparar_bairros.py`:
   - mantém só os polígonos dentro do município de Uberlândia;
   - simplifica a geometria (alvo: arquivo final na casa de centenas de KB);
   - normaliza nomes e grava em cada feature `properties.bairro` (nome oficial) e `properties.chave` (nome normalizado);
   - aplica `apelidos_bairros.json` para unir variações de grafia.
3. `relatorio_cobertura.py` consulta os bairros distintos do Postgres e imprime:
   - bairros do banco **sem polígono**;
   - polígonos **sem nenhum anúncio**;
   - a porcentagem de anúncios cobertos pelo mapa.

O relatório é o instrumento de aceite do casamento de nomes (seção 9).

## 7. API: `GET /api/mapa`

Parâmetros opcionais: `modo` (`aluguel|venda`) e `tipo`, com o mesmo significado dos demais endpoints.

Resposta, uma linha por bairro com pelo menos um anúncio, **sem `LIMIT`**:

```json
[
  {
    "bairro": "Santa Mônica",
    "chave": "santa monica",
    "quantidade": 12,
    "media_preco": 2350,
    "dias_mediana": 18
  }
]
```

Regras:

- `quantidade` conta todos os anúncios do bairro com os filtros aplicados.
- `media_preco` e `dias_mediana` vêm como `null` quando o bairro tem menos de 3 anúncios, para a regra ser a mesma dos gráficos de barras.
- A consulta reaproveita os `JOIN`s de `/api/preco-medio` (`imovel`, `endereco`, `tipo_imovel`, `modo_imovel`) e de `/api/tempo-mercado` (`imovel_ciclo_vida`). Valores em parâmetros posicionais, como no restante de `server.js`.
- Somente leitura, sem alterar tabelas nem views.

## 8. Interface

Nova seção do app, no padrão editorial das existentes (kicker, título que muda com o dado, lede):

- **Mapa SVG** desenhado com `d3-geo` (projeção ajustada ao GeoJSON com `fitSize`), sem mapa de fundo.
- **Seletor de métrica:** preço médio, anúncios, idade do anúncio.
- **Escala de cor sequencial** a partir da cor de identidade (`--accent`), válida nos dois temas, com legenda de faixa de valores. Bairros sem valor em cinza neutro (`--line`/`--wash`), com legenda explicando que têm menos de 3 anúncios ou nenhum.
- **Tooltip** no estilo `.tip` existente: nome do bairro, valor da métrica e quantidade de anúncios.
- **Filtros:** segue o seletor de modo do topo; o filtro de tipo segue o padrão de `PrecoPorBairro`.
- **"Ver como tabela"** com os mesmos dados, como em `ChartBlock`, para o mapa não ser a única forma de ler o dado.
- **Acessibilidade:** cada polígono com `<title>`, foco por teclado e contraste de texto conforme a validação de paleta já feita no app. Cor nunca é o único canal: a tabela cobre isso.
- **Mobile:** o SVG usa `viewBox` e escala com a largura da coluna.
- Estados de carregamento, erro e vazio iguais aos demais blocos ("Carregando…", "Não foi possível carregar.", "Sem dados para mostrar.").
- A nota de rodapé do mapa repete que os dados são uma amostra das primeiras páginas de cada busca.

## 9. Critérios de aceite

1. `scripts/geo/` gera `bairros-uberlandia.geojson` a partir da fonte escolhida e é reexecutável.
2. `relatorio_cobertura.py` roda contra o Postgres e mostra a cobertura. **Meta: pelo menos 90% dos anúncios caem em um bairro com polígono.** Se a meta não for atingida, os bairros restantes entram em `apelidos_bairros.json` ou ficam documentados como não cobertos.
3. `GET /api/mapa` responde com os filtros `modo` e `tipo`, aplica a regra de 3 anúncios e não usa `LIMIT`.
4. O mapa renderiza nos temas claro e escuro, muda ao trocar aluguel/venda e abre como tabela.
5. O app funciona **sem rede** (sem tiles e sem CDN de mapa).
6. O GeoJSON versionado tem tamanho razoável (referência: menos de 1 MB).
7. Testes em `tests/test_geo_bairros.py` cobrem a normalização de nomes (acentos, caixa, prefixos, abreviações) e o casamento com o GeoJSON.
8. `docs/ARCHITECTURE.md`, `app/README.md` (lista de endpoints) e o README principal citam a funcionalidade, a fonte e a licença do contorno.

## 10. Riscos e decisões em aberto

| Risco / decisão | Mitigação |
|---|---|
| Nomes de bairro do anúncio não batem com o GeoJSON ("Sta. Mônica", "Bairro Santa Mônica") | Normalização + `apelidos_bairros.json` + relatório de cobertura |
| Fonte sem todos os bairros ou com geometria desatualizada | Cobertura medida em 93,8% com o IBGE; OSM como reserva para bairros novos |
| Licença do IBGE para redistribuir o arquivo não confirmada | Confirmar antes de versionar o GeoJSON; registrar a atribuição |
| Bairros com poucos anúncios ficam cinza e o mapa parece vazio | Legenda explícita; tabela com a contagem; texto do lede que explica a regra |
| Anúncios com bairro nulo ou endereço genérico (há `id_endereco_imovel != '1'` nas views) | Fora do mapa; contados no relatório de cobertura |
| Decisão em aberto: `Mapa.jsx` separado ou dentro de `App.jsx` | Preferência por arquivo separado, já que `App.jsx` tem ~550 linhas |

**Evolução futura:** um ponto por anúncio exigiria geocodificação (por exemplo Nominatim), colunas `lat`/`lon` em `endereco`, ajustes em `scripts/etl/treatment/` e nas views. Só vale a pena se os anúncios trouxerem endereço com rua e número, o que precisa ser medido antes.

## 11. Plano de entrega sugerido

1. ~~Comparar as fontes de contorno e escolher uma~~ (feito, seção 3).
2. ~~`scripts/geo/` + GeoJSON + relatório de cobertura + testes~~ (feito: 75 bairros, 70 KB, 94,7% de cobertura, 15 testes).
3. Rota `/api/mapa`.
4. Componente `Mapa` e a seção no app, com tabela e temas.
5. Documentação e novas capturas de tela para o README.
