# Real Estate Data Pipeline

<p align="center">
<img alt="GitHub code size in bytes"  src="https://img.shields.io/github/languages/code-size/rafaelladuarte/real_state_data_pipeline?style=plastic">
<img alt="GitHub repo file count"  src="https://img.shields.io/github/directory-file-count/rafaelladuarte/real_state_data_pipeline?style=plastic">
<img alt="GitHub last commit"  src="https://img.shields.io/github/last-commit/rafaelladuarte/real_state_data_pipeline?style=plastic">
</p>

<img src="docs/images/imoveis.jpeg">

<p align="center">
<img src="https://img.shields.io/static/v1?label=Status&message=Concluido&color=green&style=for-the-badge"/>
</p>

## Descrição do Projeto

O **Real Estate Data Pipeline** é um projeto de portfólio voltado para a criação de um pipeline de ETL (Extração, Transformação e Carga) para coletar dados de imóveis à venda em sites de imobiliárias de Uberlândia-MG. O objetivo é organizar, transformar e carregar os dados em um banco de dados, permitindo sua visualização em um app web interativo (React + API Express).

## Objetivo

Este projeto visa automatizar o processo de coleta e análise de dados de imóveis, gerando insights sobre o mercado imobiliário de forma prática e eficiente. O pipeline automatizado irá:

- **Extrair** dados como preço, localização e características dos imóveis a partir de sites de imobiliárias.
- **Transformar** os dados brutos por meio de limpeza e cálculos de insights (ex. preço médio por bairro, variação de preços por características).
- **Carregar** os dados limpos e processados em bancos de dados: MongoDB (dados brutos) e PostgreSQL (dados tratados e modelados).
- **Visualizar** os dados por meio de um app web interativo, facilitando a análise de tendências no mercado imobiliário.

## Tecnologias Utilizadas

- **Docker**: Containerização dos scripts de ETL (imagem `etl-scripts` com Chrome e dependências), executados pelo Airflow via `DockerOperator`.
- **Python**: Linguagem principal para desenvolver os scripts de scraping e transformação de dados.
- **Apache Airflow**: Orquestração e gerenciamento do pipeline de ETL.
- **MongoDB**: Armazenamento dos dados brutos coletados pelo scraping.
- **PostgreSQL**: Dados tratados, modelagem relacional, triggers, funções e views de análise.
- **React + Recharts / Express**: App web para visualização interativa dos dados (pasta `app/`).
- **Selenium**: Ferramentas para scraping de dados dos sites de imobiliárias.

## App de visualização

A pasta [`app/`](app/README.md) traz uma API Express e um frontend React que consomem as views do Postgres (preço médio por bairro, distribuição por tipo, dispersão preço × área e listagem filtrável).

## Estrutura do Pipeline

1. **Extração de Dados**
   - Coleta de dados de sites de imobiliárias usando scripts de scraping em Python.
   - Paginação automática para garantir a coleta de todos os imóveis disponíveis.
   
2. **Transformação de Dados**
   - Limpeza dos dados brutos: tratamento de valores nulos, formatação de preços e localização.
   - Cálculo de métricas como preço médio por bairro e análise de variações.

3. **Carga de Dados**
   - Dados brutos no MongoDB; dados limpos e modelados migrados para o PostgreSQL.
   
4. **Visualização**
   - API Express sobre as views do PostgreSQL e frontend React com gráficos e listagem filtrável.
   - Visualização de insights, como tendências de preços por localização.

## Cronograma de Execução

### Parte 1
- ✅ Planejamento e definição de escopo
- ✅ Escolha dos sites de imobiliárias e região alvo
- ✅ Desenho do pipeline de ETL

### Parte 2
- ✅ Configuração do banco de dados MongoDB
- ✅ Desenvolvimento de scripts de scraping para coleta de dados
- ✅ Testes de scraping em massa

Lembrete:
- Implementar coleta de numero de telefone das imobiliarias

### Parte 3
- ✅ Configuração do banco de dados PostgreSQL
- ✅ Migração dados brutos para o PostgreSQL
- ✅ Modelagem de Dados
- ✅ Limpeza e tratamento dos dados brutos
- ✅ Inserção dos dados modelados no banco de dados

### Parte 4
- ✅ Design e Implementação do Pipeline de ETL no Apache Airflow
- ✅ Encadeamento extração → tratamento e agendamento diário
- 🔁 Monitoramento e Controle do Pipeline por meio de Logs

### Parte 5
- ✅ Funções, triggers e views para cálculo de insights
- ✅ App web interativo (API Express + React)

### Parte 6
- Testes automatizados dos parsers de tratamento
- Revisão do pipeline e otimização

### Parte 7
- ✅ Documentação do projeto

## Contribuições

Este é um projeto de portfólio pessoal, mas contribuições e sugestões são sempre bem-vindas. Sinta-se à vontade para abrir issues ou enviar pull requests!

## Autor

Desenvolvido por Rafaella Duarte.
