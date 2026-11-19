"""Testes de integração da carga no Postgres (precisam de um servidor Postgres).

Defina POSTGRES_TEST_URI apontando para um servidor (qualquer banco), por exemplo
postgresql+psycopg2://username:password@localhost:5434/postgres; sem ele, são
ignorados. Cada teste cria e remove o banco descartável `real_state_test`.
"""
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import os

import psycopg2
import pytest

from scripts.etl.load.model import build_model
from scripts.infra.storage.postgres import PostgreDB

BASE_URI = os.getenv("POSTGRES_TEST_URI")
TEST_DB = "real_state_test"

pytestmark = pytest.mark.skipif(
    not BASE_URI, reason="POSTGRES_TEST_URI não definido"
)


def imovel(hash_, preco, address="Rua A, 10 - Centro, Uberlândia - MG", **extra):
    return {
        "titulo_anuncio": f"Imóvel {hash_}", "tipo_imovel": "casas",
        "modo_imovel": "aluguel", "descricao": "desc", "preco": preco,
        "condominio": None, "iptu": None, "area": 80, "quartos": 2,
        "banheiro": 1, "vagas": 1, "suite": None, "outros": ["Varanda"],
        "endereco_completo": address, "rua": "Rua A", "bairro": "Centro",
        "numero": "10", "telefone": [], "id_imobiliaria": 1,
        "imagens": ["http://x/1.webp"], "data_cadastro": "01/10/2026",
        "data_atualizacao": None, "data_coleta_imovel": "19/11/2026",
        "hash": hash_, **extra,
    }


AGENCY = {
    "id_imobiliaria": 1, "nome_imobiliaria": "Imob", "credencial_imobiliaria": None,
    "quantidade_imovel": 10, "endereco_completo": "Não informado", "rua": None,
    "bairro": None, "numero": None, "data_cadastro": "16/09/2025",
    "telefone": None, "data_coleta": "19/11/2026",
}


@pytest.fixture
def uri():
    admin = create_engine(BASE_URI, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}"'))
        c.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    test_uri = make_url(BASE_URI).set(database=TEST_DB).render_as_string(
        hide_password=False
    )
    yield test_uri
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
    admin.dispose()


def snap(hash_, preco, data):
    return {"hash": hash_, "snapshot_key": f"{hash_}_{data}", "preco": preco,
            "condominio": None, "iptu": None, "data_coleta": data}


def stage(uri, imoveis, agencies=(AGENCY,), snapshots=()):
    db = PostgreDB(uri)
    db.post_dataframe("_treat_imoveis", imoveis, "replace")
    db.post_dataframe("_treat_imobiliarias", list(agencies), "replace")
    if snapshots:
        db.post_dataframe("_snapshots_imoveis", list(snapshots), "replace")


def scalar(uri, sql):
    engine = create_engine(uri)
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def test_rerun_does_not_duplicate_or_fail(uri):
    stage(uri, [imovel("h1", 1000), imovel("h2", 2000, "Rua B, 5 - Centro, Uberlândia - MG")])
    for _ in range(3):
        build_model(uri)

    assert scalar(uri, "SELECT count(*) FROM imovel") == 2
    assert scalar(uri, "SELECT count(*) FROM imobiliaria") == 1
    assert scalar(uri, "SELECT count(*) FROM tipo_imovel WHERE tipo = 'casas'") == 1


def test_shared_address_is_stored_once(uri):
    stage(uri, [imovel("h1", 1000), imovel("h2", 2000)])  # mesmo endereço
    build_model(uri)

    assert scalar(uri, "SELECT count(*) FROM imovel") == 2
    assert scalar(
        uri, "SELECT count(*) FROM endereco WHERE endereco LIKE 'Rua A%'"
    ) == 1


def test_price_comes_from_latest_snapshot_without_duplicating(uri):
    stage(uri, [imovel("h1", 1000)], snapshots=[snap("h1", 1000, "01/11/2026")])
    build_model(uri)
    # 2ª coleta: o hash do anúncio é o mesmo, só o preço mudou
    stage(uri, [imovel("h1", 1000)], snapshots=[
        snap("h1", 1000, "01/11/2026"), snap("h1", 1500, "08/11/2026"),
    ])
    build_model(uri)
    build_model(uri)  # reexecutar não altera nada

    assert scalar(uri, "SELECT count(*) FROM imovel") == 1
    assert scalar(uri, "SELECT count(*) FROM imovel_snapshot") == 2
    assert scalar(uri, "SELECT preco FROM imovel WHERE id_imovel = 'h1'") == 1500
    # triggers recalculam custo/faixa também no update
    assert scalar(uri, "SELECT faixa_area FROM imovel WHERE id_imovel = 'h1'") == "51-100m²"


def test_lifecycle_view_tracks_price_change_and_time_on_market(uri):
    stage(uri, [imovel("h1", 1000), imovel("h2", 2000, "Rua B, 5 - Centro, Uberlândia - MG")],
          snapshots=[
              snap("h1", 1000, "01/11/2026"), snap("h1", 1500, "08/11/2026"),
              snap("h2", 2000, "01/11/2026"),  # não apareceu na última coleta
          ])
    build_model(uri)

    row = create_engine(uri).connect().execute(text(
        "SELECT * FROM imovel_ciclo_vida WHERE id_imovel = 'h1'"
    )).mappings().one()
    assert row["coletas"] == 2 and row["mudancas_preco"] == 1
    assert row["preco_inicial"] == 1000 and row["preco_atual"] == 1500
    assert float(row["variacao_pct"]) == 50.0
    assert row["dias_no_mercado"] == 38  # 08/11/2026 - criado em 01/10/2026
    assert row["visto_na_ultima_coleta"] is True
    assert scalar(
        uri,
        "SELECT visto_na_ultima_coleta FROM imovel_ciclo_vida WHERE id_imovel = 'h2'",
    ) is False


def test_new_type_from_scraping_is_kept(uri):
    stage(uri, [imovel("h1", 1000, tipo_imovel="Sobrado")])
    build_model(uri)

    assert scalar(uri, "SELECT count(*) FROM imovel") == 1
    assert scalar(uri, "SELECT count(*) FROM tipo_imovel WHERE tipo = 'sobrado'") == 1


def test_failure_rolls_back_everything(uri):
    stage(uri, [imovel("h1", "preço inválido")])
    with pytest.raises(psycopg2.Error):
        build_model(uri)

    assert scalar(uri, "SELECT to_regclass('public.imovel') IS NULL") is True
