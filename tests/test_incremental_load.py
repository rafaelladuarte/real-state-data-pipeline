"""Carga incremental: o staging leva só os lotes pendentes e o model os registra.

Integração (precisa de Mongo e Postgres): defina MONGO_TEST_URI e
POSTGRES_TEST_URI. Usa bancos descartáveis (`real_state_test_*`); nunca toca em
`real_state`.
"""
from contextlib import contextmanager

from pymongo import MongoClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import os

import psycopg2
import pytest

from scripts.etl.batch import LEGACY_BATCH, current_batch_id, new_batch_id
from scripts.etl.load.migrate import treat_data_to_postgres
from scripts.etl.load.model import build_model
from scripts.infra.storage.mongo import MongoDB
from tests.test_model_load import AGENCY, imovel, snap

MONGO_URI = os.getenv("MONGO_TEST_URI")
PG_URI = os.getenv("POSTGRES_TEST_URI")
MONGO_DB = "real_state_test_incremental"

pytestmark = pytest.mark.skipif(
    not (MONGO_URI and PG_URI),
    reason="MONGO_TEST_URI e POSTGRES_TEST_URI não definidos",
)


@contextmanager
def postgres_db(name):
    admin = create_engine(PG_URI, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(PG_URI).set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def uri():
    with postgres_db("real_state_test_inc_a") as value:
        yield value


@pytest.fixture
def mongo():
    client = MongoClient(MONGO_URI)
    client.drop_database(MONGO_DB)
    yield MongoDB(MONGO_URI, db=MONGO_DB)
    client.drop_database(MONGO_DB)
    client.close()


def put(mongo, batch_id, imoveis=(), snapshots=(), agencies=()):
    """Grava documentos tratados no Mongo com o lote informado (None = legado)."""
    def tag(docs):
        return [{**d, **({"batch_id": batch_id} if batch_id else {})} for d in docs]

    client = MongoClient(MONGO_URI)[MONGO_DB]
    for collection, docs in (
        ("treat_imoveis", imoveis), ("snapshots_imoveis", snapshots),
        ("treat_imobiliarias", agencies),
    ):
        if docs:
            client[collection].insert_many(tag(docs))


def load(mongo, uri, **kwargs):
    staged = treat_data_to_postgres(mongo=mongo, postgres_uri=uri, **kwargs)
    build_model(uri)
    return staged


def rows(uri, sql):
    with create_engine(uri).connect() as c:
        return [tuple(r) for r in c.execute(text(sql))]


def scalar(uri, sql):
    return rows(uri, sql)[0][0]


# Estado observável sem depender de ids sequenciais (endereco.id_endereco)
STATE_SQL = {
    "imovel": """
        SELECT I.id_imovel, I.preco, E.endereco, T.tipo, M.modo
        FROM imovel I JOIN endereco E ON E.id_endereco = I.id_endereco_imovel
        JOIN tipo_imovel T ON T.id_tipo = I.id_tipo_imovel
        JOIN modo_imovel M ON M.id_modo = I.id_modo_imovel ORDER BY 1""",
    "imobiliaria": "SELECT id_imobiliaria, nome_imobiliaria FROM imobiliaria ORDER BY 1",
    "snapshot": """SELECT id_imovel, data_coleta, preco FROM imovel_snapshot
                   ORDER BY 1, 2""",
}


def state(uri):
    return {name: rows(uri, sql) for name, sql in STATE_SQL.items()}


def three_batches():
    """Os mesmos dados divididos em 3 lotes (um deles muda o preço de h1)."""
    return [
        ("lote-1", [imovel("h1", 1000)], [snap("h1", 1000, "01/11/2026")], [AGENCY]),
        ("lote-2", [imovel("h2", 2000, "Rua B, 5 - Centro, Uberlândia - MG")],
         [snap("h2", 2000, "01/11/2026")], []),
        ("lote-3", [imovel("h3", 3000, "Rua C, 7 - Centro, Uberlândia - MG")],
         [snap("h1", 1500, "08/11/2026"), snap("h3", 3000, "08/11/2026")], []),
    ]


def test_batch_ids_are_unique_and_overridable(monkeypatch):
    monkeypatch.delenv("BATCH_ID", raising=False)
    assert new_batch_id() != new_batch_id()
    assert current_batch_id() != current_batch_id()
    monkeypatch.setenv("BATCH_ID", "forcado")
    assert current_batch_id() == "forcado"


def test_batches_load_to_the_same_state_as_one_full_load(mongo):
    """Critério de aceite: N lotes = carga única."""
    batches = three_batches()

    with postgres_db("real_state_test_inc_full") as full_uri:
        for batch, imoveis, snaps, agencies in batches:
            put(mongo, batch, imoveis, snaps, agencies)
        load(mongo, full_uri)
        expected = state(full_uri)

    MongoClient(MONGO_URI).drop_database(MONGO_DB)
    with postgres_db("real_state_test_inc_split") as split_uri:
        for batch, imoveis, snaps, agencies in batches:
            put(mongo, batch, imoveis, snaps, agencies)
            load(mongo, split_uri)  # um ciclo migrate + model por lote
        assert state(split_uri) == expected
        assert scalar(split_uri, "SELECT count(*) FROM lote_carga") == 3

    assert len(expected["imovel"]) == 3
    # o preço de h1 vem do snapshot mais recente
    assert dict((r[0], r[1]) for r in expected["imovel"])["h1"] == 1500


def test_only_pending_batches_are_staged(mongo, uri):
    put(mongo, "lote-1", [imovel("h1", 1000)], [snap("h1", 1000, "01/11/2026")], [AGENCY])
    first = load(mongo, uri)
    assert first["_treat_imoveis"] == 1

    put(mongo, "lote-2", [imovel("h2", 2000, "Rua B, 5 - Centro, Uberlândia - MG")])
    second = load(mongo, uri)
    # só o lote novo foi copiado; o lote-1 não voltou ao staging
    assert second == {"_treat_imoveis": 1}
    assert scalar(uri, "SELECT count(*) FROM imovel") == 2


def test_nothing_pending_stages_nothing(mongo, uri):
    put(mongo, "lote-1", [imovel("h1", 1000)], agencies=[AGENCY])
    load(mongo, uri)
    assert load(mongo, uri) == {}
    assert scalar(uri, "SELECT count(*) FROM imovel") == 1


def test_staging_is_empty_after_model(mongo, uri):
    put(mongo, "lote-1", [imovel("h1", 1000)], [snap("h1", 1000, "01/11/2026")], [AGENCY])
    load(mongo, uri)
    for table in ("_treat_imoveis", "_treat_imobiliarias", "_snapshots_imoveis"):
        assert scalar(uri, f"SELECT count(*) FROM {table}") == 0
    assert rows(uri, "SELECT batch_id, imoveis, snapshots FROM lote_carga") == [
        ("lote-1", 1, 1)
    ]


def test_forced_reload_of_a_batch_does_not_duplicate(mongo, uri, monkeypatch):
    put(mongo, "lote-1", [imovel("h1", 1000)], [snap("h1", 1000, "01/11/2026")], [AGENCY])
    load(mongo, uri)
    before = state(uri)

    monkeypatch.setenv("BATCH_ID", "lote-1")
    forced = load(mongo, uri)
    assert forced["_treat_imoveis"] == 1  # recarregou mesmo já carregado
    assert state(uri) == before
    assert scalar(uri, "SELECT count(*) FROM lote_carga") == 1


def test_failed_load_keeps_batch_pending_and_does_not_duplicate_staging(mongo, uri):
    put(mongo, "lote-1", [imovel("h1", "preço inválido")], agencies=[AGENCY])
    treat_data_to_postgres(mongo=mongo, postgres_uri=uri)
    with pytest.raises(psycopg2.Error):
        build_model(uri)

    # nada foi registrado nem aplicado, e o staging continua com o lote
    assert scalar(uri, "SELECT count(*) FROM lote_carga") == 0
    assert scalar(uri, "SELECT to_regclass('public.imovel') IS NULL") is True
    assert scalar(uri, "SELECT count(*) FROM _treat_imoveis") == 1

    # nova tentativa: o lote ainda é pendente e não duplica no staging
    treat_data_to_postgres(mongo=mongo, postgres_uri=uri)
    assert scalar(uri, "SELECT count(*) FROM _treat_imoveis") == 1

    # corrigido o dado, a carga completa
    MongoClient(MONGO_URI)[MONGO_DB]["treat_imoveis"].update_one(
        {"hash": "h1"}, {"$set": {"preco": 1000}}
    )
    load(mongo, uri)
    assert scalar(uri, "SELECT count(*) FROM imovel") == 1
    assert scalar(uri, "SELECT count(*) FROM lote_carga") == 1


def test_documents_without_batch_id_load_once_as_legacy(mongo, uri):
    put(mongo, None, [imovel("h1", 1000)], [snap("h1", 1000, "01/11/2026")], [AGENCY])
    first = load(mongo, uri)
    assert first["_treat_imoveis"] == 1
    assert rows(uri, "SELECT batch_id FROM lote_carga") == [(LEGACY_BATCH,)]

    assert load(mongo, uri) == {}  # o legado não volta ao staging
    assert scalar(uri, "SELECT count(*) FROM imovel") == 1


def test_old_staging_without_batch_column_still_loads(uri):
    """Staging de antes da carga incremental (sem batch_id) continua aplicável."""
    from tests.test_model_load import stage

    stage(uri, [imovel("h1", 1000)], snapshots=[snap("h1", 1000, "01/11/2026")])
    build_model(uri)
    assert scalar(uri, "SELECT count(*) FROM imovel") == 1
    assert rows(uri, "SELECT batch_id FROM lote_carga") == [(LEGACY_BATCH,)]


# ---------- Regressões da revisão de código ----------

def test_batch_with_unapplied_rows_stays_pending_until_resolved(mongo, uri):
    """Imóvel de imobiliária ainda não coletada não pode sumir para sempre."""
    orphan = {**imovel("h1", 1000), "id_imobiliaria": 99}
    put(mongo, "lote-1", [orphan], [snap("h1", 1000, "01/11/2026")], [AGENCY])
    load(mongo, uri)

    # nada do imóvel chegou e o lote não foi registrado
    assert scalar(uri, "SELECT count(*) FROM imovel") == 0
    assert scalar(uri, "SELECT count(*) FROM lote_carga") == 0
    # continua pendente: a próxima carga o envia de novo
    assert treat_data_to_postgres(mongo=mongo, postgres_uri=uri)["_treat_imoveis"] == 1

    # a imobiliária chega em outro lote: agora tudo se aplica
    put(mongo, "lote-2", agencies=[{**AGENCY, "id_imobiliaria": 99}])
    load(mongo, uri)
    assert scalar(uri, "SELECT count(*) FROM imovel") == 1
    assert scalar(uri, "SELECT count(*) FROM imovel_snapshot") == 1
    assert sorted(r[0] for r in rows(uri, "SELECT batch_id FROM lote_carga")) == [
        "lote-1", "lote-2"
    ]


def test_batch_loaded_halfway_is_completed_later(mongo, uri):
    """A carga pegou o lote enquanto o tratamento ainda gravava."""
    put(mongo, "lote-1", [imovel("h1", 1000)], agencies=[AGENCY])
    load(mongo, uri)
    assert rows(uri, "SELECT imoveis FROM lote_carga") == [(1,)]

    # o tratamento termina de gravar o mesmo lote depois da carga
    put(mongo, "lote-1", [imovel("h2", 2000, "Rua B, 5 - Centro, Uberlândia - MG")])
    staged = load(mongo, uri)

    assert staged["_treat_imoveis"] == 2  # o lote volta inteiro
    assert scalar(uri, "SELECT count(*) FROM imovel") == 2
    assert rows(uri, "SELECT imoveis FROM lote_carga") == [(2,)]
    assert load(mongo, uri) == {}


def test_new_field_after_a_failed_load_does_not_break_staging(mongo, uri):
    """Sobra de staging + documento com campo novo não pode travar a carga."""
    put(mongo, "lote-1", [imovel("h1", "preço inválido")], agencies=[AGENCY])
    treat_data_to_postgres(mongo=mongo, postgres_uri=uri)
    with pytest.raises(psycopg2.Error):
        build_model(uri)

    put(mongo, "lote-2", [imovel("h2", 2000, "Rua B, 5 - Centro, Uberlândia - MG",
                                 campo_novo="x")])
    staged = treat_data_to_postgres(mongo=mongo, postgres_uri=uri)
    assert staged["_treat_imoveis"] == 2  # os dois lotes pendentes, sem erro
