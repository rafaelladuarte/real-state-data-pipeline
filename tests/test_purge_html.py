"""Remoção segura do HTML e quarentena.

Integração (precisa de Mongo; a parte da carga também de Postgres): defina
MONGO_TEST_URI e POSTGRES_TEST_URI. Usa bancos descartáveis; nunca toca em
`real_state`. O storage é simulado em memória.
"""
from datetime import datetime, timedelta, UTC

from pymongo import MongoClient

import os

import psycopg2
import pytest

import scripts.etl.extraction.parse_property as parse_module
import scripts.etl.extraction.requeue as requeue_module
from scripts.etl import quarantine
from scripts.etl.load import purge_html
from scripts.etl.load.migrate import treat_data_to_postgres
from scripts.etl.load.model import build_model
from scripts.etl.quarantine import QuarantineLimitError
from scripts.infra.queue import LinkQueue
from scripts.infra.storage.mongo import MongoDB
from tests.test_incremental_load import postgres_db
from tests.test_model_load import AGENCY, imovel, snap

MONGO_URI = os.getenv("MONGO_TEST_URI")
PG_URI = os.getenv("POSTGRES_TEST_URI")
MONGO_DB = "real_state_test_purge"

pytestmark = pytest.mark.skipif(not MONGO_URI, reason="MONGO_TEST_URI não definido")
needs_postgres = pytest.mark.skipif(not PG_URI, reason="POSTGRES_TEST_URI não definido")


class FakeStore:
    """Storage em memória com a parte de remoção do ObjectStore."""

    def __init__(self, keys=()):
        self.objects = set(keys)
        self.deleted = []
        self.fail = False

    def delete_many(self, keys):
        if self.fail:
            raise RuntimeError("storage indisponível")
        self.objects -= set(keys)
        self.deleted.extend(keys)
        return len(keys)

    def get_html(self, key):
        raise AssertionError(f"não devia ler {key}")


@pytest.fixture
def mongo():
    client = MongoClient(MONGO_URI)
    client.drop_database(MONGO_DB)
    yield MongoDB(MONGO_URI, db=MONGO_DB)
    client.drop_database(MONGO_DB)
    client.close()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("PURGE_HTML", "PURGE_LEGACY_HTML", "BATCH_ID", "QUARANTINE_MAX_BATCHES",
                 "QUARANTINE_CONSECUTIVE", "HTML_QUARANTINE_DAYS"):
        monkeypatch.delenv(name, raising=False)


def key(n):
    return f"anuncio/2026-11-19/{n}.html.gz"


def add_ad(mongo, n, batch=None, treated=True, parsed=True, **extra):
    """Um anúncio coletado: documento da fila (links) e bruto (raw)."""
    link = {"link": f"https://x/imovel-id-{n}/", "html_key": key(n), "scraper": True}
    if parsed:
        link["parsed"] = True
    raw = {"anuncio_id": str(n), "html_key": key(n)}
    if treated:
        raw["treat"] = True
    if batch:
        raw["batch_id"] = batch
    mongo.insert_documents([{**link, **extra.get("link", {})}], "links_imoveis")
    mongo.insert_documents([{**raw, **extra.get("raw", {})}], "raw_imoveis")


def doc(mongo, collection, n):
    return mongo.get_documents({"html_key": key(n)}, collection)[0]


# ---------- Apagar só o que já foi carregado ----------

def test_purges_only_html_of_loaded_batches(mongo):
    add_ad(mongo, 1, batch="lote-1")
    add_ad(mongo, 2, batch="lote-2")            # lote ainda não carregado
    add_ad(mongo, 3, treated=False)             # ainda não tratado
    store = FakeStore([key(1), key(2), key(3)])

    purged = purge_html.purge_loaded(mongo, store, loaded=["lote-1"])

    assert purged == 1
    assert store.objects == {key(2), key(3)}
    assert doc(mongo, "raw_imoveis", 1)["html_purged"] is True
    assert doc(mongo, "links_imoveis", 1)["html_purged"] is True
    assert "html_purged" not in doc(mongo, "raw_imoveis", 2)
    assert "html_purged" not in doc(mongo, "raw_imoveis", 3)


def test_nothing_is_purged_when_no_batch_is_loaded(mongo):
    add_ad(mongo, 1, batch="lote-1")
    store = FakeStore([key(1)])

    assert purge_html.purge_loaded(mongo, store, loaded=[]) == 0
    assert store.objects == {key(1)}


def test_storage_failure_marks_nothing_and_retries_later(mongo):
    add_ad(mongo, 1, batch="lote-1")
    store = FakeStore([key(1)])
    store.fail = True

    with pytest.raises(RuntimeError):
        purge_html.purge_loaded(mongo, store, loaded=["lote-1"])
    assert "html_purged" not in doc(mongo, "raw_imoveis", 1)

    store.fail = False
    assert purge_html.purge_loaded(mongo, store, loaded=["lote-1"]) == 1
    assert store.objects == set()


def test_html_still_waiting_for_parse_is_kept(mongo):
    """Link recoletado na mesma chave e ainda sem parse: o HTML não pode sumir."""
    add_ad(mongo, 1, batch="lote-1")
    mongo.update_documents({"html_key": key(1)}, {"$unset": {"parsed": ""}}, "links_imoveis")
    store = FakeStore([key(1)])

    assert purge_html.purge_loaded(mongo, store, loaded=["lote-1"]) == 0
    assert store.objects == {key(1)}


def test_legacy_html_is_kept_unless_explicitly_enabled(mongo):
    add_ad(mongo, 1)  # tratado antes da carga incremental: sem batch_id
    store = FakeStore([key(1)])

    purge_html.purge_loaded(mongo, store, loaded=["legado"])
    assert store.objects == {key(1)}

    purge_html.purge_loaded(mongo, store, loaded=["legado"], include_legacy=True)
    assert store.objects == set()


def test_purge_html_false_keeps_everything(mongo, monkeypatch):
    monkeypatch.setenv("PURGE_HTML", "false")
    add_ad(mongo, 1, batch="lote-1", link={"parse_error": "x"})
    store = FakeStore([key(1)])

    result = purge_html.run(mongo=mongo, store=store, loaded=["lote-1"])

    assert result == {"skipped": True}
    assert store.objects == {key(1)}
    assert mongo.get_documents({}, "quarentena_html") == []


# ---------- Falha na carga mantém o HTML; sucesso o apaga ----------

@needs_postgres
def test_failed_load_keeps_html_and_successful_load_removes_it(mongo):
    store = FakeStore([key(1)])
    add_ad(mongo, 1, batch="lote-1")
    bad = imovel("h1", "preço inválido")
    MongoClient(MONGO_URI)[MONGO_DB]["treat_imoveis"].insert_one(
        {**bad, "batch_id": "lote-1"}
    )
    MongoClient(MONGO_URI)[MONGO_DB]["treat_imobiliarias"].insert_one(
        {**AGENCY, "batch_id": "lote-1"}
    )

    with postgres_db("real_state_test_purge_pg") as uri:
        treat_data_to_postgres(mongo=mongo, postgres_uri=uri)
        with pytest.raises(psycopg2.Error):
            build_model(uri)  # a carga falha

        purge_html.run(mongo=mongo, store=store, postgres_uri=uri)
        assert store.objects == {key(1)}, "HTML tem de ficar quando a carga falha"

        MongoClient(MONGO_URI)[MONGO_DB]["treat_imoveis"].update_one(
            {"hash": "h1"}, {"$set": {"preco": 1000}}
        )
        MongoClient(MONGO_URI)[MONGO_DB]["snapshots_imoveis"].insert_one(
            {**snap("h1", 1000, "01/11/2026"), "batch_id": "lote-1"}
        )
        treat_data_to_postgres(mongo=mongo, postgres_uri=uri)
        build_model(uri)  # agora dá certo

        report = purge_html.run(mongo=mongo, store=store, postgres_uri=uri)
        assert report["purged"] == 1
        assert store.objects == set(), "HTML sai depois da carga bem-sucedida"


# ---------- Quarentena ----------

def test_failures_go_to_quarantine_and_keep_their_html(mongo):
    add_ad(mongo, 1, batch="lote-1", treated=False, raw={}, link={"parse_error": "sem preço"})
    add_ad(mongo, 2, treated=False, raw={"treat_quarantine": True, "treat_error": "KeyError"})
    store = FakeStore([key(1), key(2)])

    report = purge_html.run(mongo=mongo, store=store, loaded=["lote-1"])

    assert report["quarantined_new"] == 2
    assert store.objects == {key(1), key(2)}
    entries = {d["html_key"]: d for d in mongo.get_documents({}, "quarentena_html")}
    assert entries[key(1)]["etapa"] == "parse" and entries[key(1)]["motivo"] == "sem preço"
    assert entries[key(2)]["etapa"] == "tratamento"

    # reexecutar não duplica
    again = purge_html.run(mongo=mongo, store=store, loaded=["lote-1"])
    assert again["quarantined_new"] == 0
    assert len(mongo.get_documents({}, "quarentena_html")) == 2


def test_quarantine_is_cleared_when_the_failure_is_fixed(mongo):
    add_ad(mongo, 1, treated=False, link={"parse_error": "x"})
    quarantine.sync(mongo, "lote-1")
    assert len(mongo.get_documents({}, "quarentena_html")) == 1

    mongo.update_documents({"html_key": key(1)}, {"$unset": {"parse_error": ""}}, "links_imoveis")
    quarantine.sync(mongo, "lote-2")
    assert mongo.get_documents({}, "quarentena_html") == []


def test_old_quarantine_is_deleted_by_age(mongo):
    add_ad(mongo, 1, treated=False, link={"parse_error": "x"})
    add_ad(mongo, 2, treated=False, link={"parse_error": "y"})
    quarantine.sync(mongo, "lote-1")
    # o primeiro entrou há 8 dias; o segundo, agora
    mongo.update_documents(
        {"html_key": key(1)},
        {"$set": {"desde": datetime.now(UTC) - timedelta(days=8)}},
        "quarentena_html",
    )
    store = FakeStore([key(1), key(2)])

    expired = quarantine.expire(mongo, store, days=7)

    assert expired == 1
    assert store.objects == {key(2)}
    assert doc(mongo, "links_imoveis", 1)["html_quarantine_expired"] is True
    assert [d["html_key"] for d in mongo.get_documents({}, "quarentena_html")] == [key(2)]


def test_quarantine_limit_by_distinct_batches(mongo, monkeypatch):
    monkeypatch.setenv("QUARANTINE_MAX_BATCHES", "3")
    for n in range(3):
        add_ad(mongo, n, treated=False, link={"parse_error": "x"})
        quarantine.sync(mongo, f"lote-{n}")
        if n < 2:
            quarantine.check_limits(mongo)  # abaixo do limite: segue

    with pytest.raises(QuarantineLimitError, match="3 lotes"):
        quarantine.check_limits(mongo)


def test_quarantine_limit_by_consecutive_runs(mongo, monkeypatch):
    monkeypatch.setenv("QUARANTINE_CONSECUTIVE", "3")
    add_ad(mongo, 1, treated=False, link={"parse_error": "x"})
    quarantine.sync(mongo, "lote-1")

    def run_metric(new, minutes):
        mongo.insert_documents([{
            "step": "purge_html", "quarantined_new": new,
            "at": datetime.now(UTC) - timedelta(minutes=minutes),
        }], "run_metrics")

    run_metric(1, 30)
    run_metric(1, 20)
    quarantine.check_limits(mongo)  # só 2 seguidas
    run_metric(1, 10)
    with pytest.raises(QuarantineLimitError, match="3 execuções seguidas"):
        quarantine.check_limits(mongo)

    # uma execução limpa (sem itens novos) quebra a sequência
    run_metric(0, 1)
    quarantine.check_limits(mongo)


def test_empty_quarantine_never_blocks(mongo, monkeypatch):
    monkeypatch.setenv("QUARANTINE_CONSECUTIVE", "1")
    mongo.insert_documents([{"step": "purge_html", "quarantined_new": 5,
                             "at": datetime.now(UTC)}], "run_metrics")
    quarantine.check_limits(mongo)  # histórico ruim, mas nada retido agora


def test_purge_run_stops_the_pipeline_at_the_limit(mongo, monkeypatch):
    monkeypatch.setenv("QUARANTINE_CONSECUTIVE", "1")
    add_ad(mongo, 1, treated=False, link={"parse_error": "x"})

    with pytest.raises(QuarantineLimitError):
        purge_html.run(mongo=mongo, store=FakeStore([key(1)]), loaded=[])


def test_extraction_does_not_start_while_quarantine_is_over_limit(mongo, monkeypatch):
    monkeypatch.setenv("QUARANTINE_MAX_BATCHES", "1")
    monkeypatch.setenv("MONGO_URI", "mongodb://fake")
    add_ad(mongo, 1, treated=False, link={"parse_error": "x"})
    quarantine.sync(mongo, "lote-1")

    monkeypatch.setattr(requeue_module, "MongoDB", lambda uri: mongo)
    monkeypatch.setattr(requeue_module, "ObjectStore", lambda: FakeStore([key(1)]))
    monkeypatch.setattr(
        requeue_module, "LinkQueue",
        lambda *a, **k: pytest.fail("não devia reenfileirar com a quarentena cheia"),
    )
    with pytest.raises(QuarantineLimitError):
        requeue_module.requeue_links()


# ---------- Integração com o parse e a fila ----------

def test_reprocess_skips_html_that_was_purged(mongo, monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://fake")
    add_ad(mongo, 1, batch="lote-1")
    store = FakeStore([key(1)])
    purge_html.purge_loaded(mongo, store, loaded=["lote-1"])

    monkeypatch.setattr(parse_module, "MongoDB", lambda uri: mongo)
    monkeypatch.setattr(parse_module, "ObjectStore", lambda: store)
    # FakeStore.get_html falha o teste se o HTML apagado for lido
    parse_module.parse_stored_property(reprocess=True)


def test_requeue_clears_the_purge_marks(mongo):
    add_ad(mongo, 1, batch="lote-1")
    old = datetime.now(UTC) - timedelta(days=30)
    mongo.update_documents(
        {"html_key": key(1)},
        {"$set": {"html_purged": True, "html_purged_at": old, "collected_at": old}},
        "links_imoveis",
    )

    queue = LinkQueue(MONGO_URI, "links_imoveis", db=MONGO_DB)
    assert queue.requeue_stale(7) == 1
    link = mongo.get_documents({}, "links_imoveis")[0]
    assert "html_purged" not in link and "html_key" not in link
