"""Apaga o HTML bruto cujo lote já está carregado no Postgres.

Roda depois da carga (DAG `load`). Regra: o HTML de um anúncio só é apagado
quando tudo já deu certo para ele: foi parseado, tratado e o lote dele foi
aplicado por inteiro no Postgres (consta em `lote_carga` e o Mongo não tem
documentos dele a mais; regra em staging.py). Qualquer falha antes disso deixa
o HTML no storage:

- parse com erro ou anúncio em quarentena no tratamento: fica registrado em
  `quarentena_html` (veja quarantine.py), com limites que param a esteira;
- lote ainda não carregado, carregado pela metade ou com linhas não aplicadas:
  o HTML espera a próxima execução;
- outro documento que usa a mesma chave ainda não foi carregado: o HTML fica.

`PURGE_HTML=false` desliga tudo (o HTML fica para sempre, como antes).
O HTML de anúncios tratados antes da carga incremental (sem batch_id) só é
apagado com `PURGE_LEGACY_HTML=true`, para não surpreender quem ainda quer
reprocessar a coleta antiga.
"""
from scripts.etl.batch import LEGACY_BATCH, current_batch_id
from scripts.etl.load.staging import (
    fully_loaded_batches, mongo_batch_counts, recorded_counts,
)
from scripts.etl.quarantine import (
    PURGE_STEP, check_limits, expire, purge_enabled, sync,
)
from scripts.infra.security.secrets import get_secret_value
from scripts.infra.storage.mongo import MongoDB
from scripts.infra.storage.object_store import ObjectStore
from scripts.utility.log import get_logger

from datetime import datetime, UTC

import os

from sqlalchemy import create_engine


logger = get_logger(__name__)

CHUNK = 500


def recorded_counts_from_postgres(postgres_uri: str) -> dict[str, dict[str, int]]:
    engine = create_engine(postgres_uri)
    connection = engine.raw_connection()
    try:
        return recorded_counts(connection.cursor())
    finally:
        connection.close()
        engine.dispose()


def _purgeable_query(loaded: list[str], include_legacy: bool) -> dict:
    base = {
        "treat": True,
        "html_key": {"$exists": True},
        "html_purged": {"$exists": False},
    }
    clauses = [{"batch_id": {"$in": loaded}}]
    if include_legacy and LEGACY_BATCH in loaded:
        clauses.append({"batch_id": {"$exists": False}})
    return {**base, "$or": clauses}


def purge_loaded(mongo, store, loaded: list[str], include_legacy: bool = False) -> int:
    """Apaga o HTML dos anúncios de lotes carregados. Devolve quantos objetos."""
    if not loaded:
        logger.info("Nenhum lote carregado: nada a apagar")
        return 0

    docs = mongo.get_documents(
        query=_purgeable_query(loaded, include_legacy), collection="raw_imoveis"
    )
    purged = 0
    for start in range(0, len(docs), CHUNK):
        chunk = docs[start:start + CHUNK]
        ids = [doc["_id"] for doc in chunk]
        keys = sorted({doc["html_key"] for doc in chunk})

        # A mesma chave pode ser usada por outro documento que ainda precisa
        # dela: um link recoletado esperando o parse, ou um bruto que não é
        # deste lote carregado (em quarentena, por exemplo). Esse HTML fica.
        in_use = {
            doc["html_key"] for doc in mongo.get_documents(
                query={"html_key": {"$in": keys}, "parsed": {"$exists": False}},
                collection="links_imoveis",
            )
        } | {
            doc["html_key"] for doc in mongo.get_documents(
                query={
                    "html_key": {"$in": keys},
                    "_id": {"$nin": ids},
                    "html_purged": {"$exists": False},
                },
                collection="raw_imoveis",
            )
        }
        keys = [key for key in keys if key not in in_use]
        if not keys:
            continue

        # Primeiro o storage; só então o Mongo. Se apagar falhar, nada é
        # marcado e a próxima execução tenta de novo.
        store.delete_many(keys)
        marked = {"$set": {"html_purged": True, "html_purged_at": datetime.now(UTC)}}
        mongo.update_documents(
            query={"_id": {"$in": ids}, "html_key": {"$in": keys}},
            set=marked, collection="raw_imoveis",
        )
        mongo.update_documents(
            query={"html_key": {"$in": keys}}, set=marked, collection="links_imoveis",
        )
        purged += len(keys)
    logger.info(f"{purged} HTMLs de lotes carregados foram apagados")
    return purged


def run(mongo=None, store=None, postgres_uri=None, loaded=None) -> dict:
    logger.info("---------------- PURGE HTML ----------------")
    if not purge_enabled():
        logger.info("PURGE_HTML=false: o HTML bruto fica guardado")
        return {"skipped": True}

    mongo = mongo or MongoDB(uri=get_secret_value("MONGO_URI"))
    store = store or ObjectStore()
    if loaded is None:
        recorded = recorded_counts_from_postgres(
            postgres_uri or get_secret_value("POSTGRESQL_URI")
        )
        loaded = fully_loaded_batches(mongo_batch_counts(mongo), recorded)
    include_legacy = os.getenv("PURGE_LEGACY_HTML", "false").lower() == "true"

    purged = purge_loaded(mongo, store, loaded, include_legacy)
    new = sync(mongo, current_batch_id())
    expired = expire(mongo, store)

    report = {
        "step": PURGE_STEP, "at": datetime.now(UTC), "purged": purged,
        "quarantined_new": new, "quarantine_expired": expired,
        "quarantined_total": len(mongo.get_documents({}, "quarentena_html")),
    }
    mongo.insert_documents(documents=[report], collection="run_metrics")
    logger.info(
        f"Purge: {purged} apagados, {new} novos em quarentena "
        f"({report['quarantined_total']} no total), {expired} expirados"
    )
    # Depois de registrar a execução: os limites olham o histórico
    check_limits(mongo)
    return report


if __name__ == '__main__':
    run()
