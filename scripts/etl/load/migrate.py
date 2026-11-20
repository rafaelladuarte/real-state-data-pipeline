"""Copia a camada tratada (Mongo) para o staging do Postgres, só o que falta.

Carga incremental: consulta `lote_carga` (lotes já carregados) e leva ao staging
apenas os documentos de lotes ainda pendentes. O model.py aplica esse staging e
o esvazia, então o staging nunca guarda mais que os lotes pendentes.

- Se uma carga falhar no meio, o lote continua pendente e entra de novo na
  próxima execução (o upsert do model.py é idempotente).
- `BATCH_ID=<id>` carrega só aquele lote, mesmo que já conste como carregado
  (recarga forçada). `BATCH_ID=legado` carrega os documentos sem batch_id.
"""
from scripts.etl.batch import LEGACY_BATCH, pending_query
from scripts.etl.load.staging import (
    STAGING_TABLES, ensure_batch_column, ensure_control_table, loaded_batches,
    staged_row_count, take_load_lock,
)
from scripts.infra.security.secrets import get_secret_value
from scripts.infra.storage.mongo import MongoDB
from scripts.utility.log import get_logger

import os

import pandas as pd
from sqlalchemy import create_engine


logger = get_logger(__name__)


def _with_batch(documents: list[dict]) -> list[dict]:
    """Sem _id e com batch_id (documentos antigos entram como o lote `legado`)."""
    return [
        {
            **{k: v for k, v in doc.items() if k != "_id"},
            "batch_id": doc.get("batch_id") or LEGACY_BATCH,
        }
        for doc in documents
    ]


def treat_data_to_postgres(
    mongo: MongoDB | None = None,
    postgres_uri: str | None = None,
    batch_id: str | None = None,
) -> dict[str, int]:
    """Leva os lotes pendentes ao staging. Devolve quantos documentos por tabela."""
    logger.info("---------------- TREAT DATA TO POSTGRES----------------")
    mongo = mongo or MongoDB(uri=get_secret_value("MONGO_URI"))
    batch_id = batch_id or os.getenv("BATCH_ID") or None
    engine = create_engine(postgres_uri or get_secret_value("POSTGRESQL_URI"))

    try:
        with engine.begin() as connection:
            # Mesmo lock do model.py: não mexer no staging enquanto ele aplica
            cursor = connection.connection.cursor()
            take_load_lock(cursor)
            ensure_control_table(cursor)
            ensure_batch_column(cursor)
            loaded = loaded_batches(cursor)
            logger.info(f"Lotes já carregados: {len(loaded)}")

            query = pending_query(loaded, batch_id)
            staged: dict[str, int] = {}
            for table, collection in STAGING_TABLES:
                mongo.create_plain_index(collection, "batch_id")
                documents = mongo.get_documents(query=query, collection=collection)
                if not documents:
                    logger.info(f"Coleção '{collection}': nada pendente")
                    continue

                rows = _with_batch(documents)
                batches = sorted({row["batch_id"] for row in rows})
                logger.info(
                    f"Coleção '{collection}': {len(rows)} documentos, "
                    f"lotes {batches}"
                )

                already_staged = staged_row_count(cursor, table)
                if already_staged:
                    # Lotes de execuções anteriores ainda não aplicados: cada
                    # lote é reenviado inteiro, sem duplicar o que já está lá
                    cursor.execute(
                        f"DELETE FROM public.{table} WHERE COALESCE(batch_id, %s) "
                        "= ANY(%s)",
                        (LEGACY_BATCH, batches),
                    )
                # Staging vazio: recria a tabela (tipos inferidos de novo)
                pd.DataFrame(rows).to_sql(
                    table, connection,
                    if_exists="append" if already_staged else "replace",
                    index=False,
                )
                staged[table] = len(rows)
    finally:
        engine.dispose()

    if not staged:
        logger.info("Nada pendente para carregar")
    return staged


if __name__ == '__main__':
    treat_data_to_postgres()
