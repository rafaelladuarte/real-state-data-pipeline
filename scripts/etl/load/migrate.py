"""Copia a camada tratada (Mongo) para o staging do Postgres, só o que falta.

Carga incremental: compara os lotes do Mongo com `lote_carga` (lotes já
aplicados por inteiro) e leva ao staging apenas os lotes pendentes (regra em
staging.py). O model.py aplica esse staging e o esvazia.

- O staging é recriado a cada carga com todos os lotes pendentes: o Mongo é a
  origem, então um lote que ficou pela metade, que falhou ou que tinha linhas
  não aplicadas é simplesmente enviado de novo, inteiro (o upsert do model.py é
  idempotente). Recriar também acompanha campos novos nos documentos.
- `BATCH_ID=<id>` carrega só aquele lote, mesmo que já conste como carregado
  (recarga forçada). `BATCH_ID=legado` carrega os documentos sem batch_id.
"""
from scripts.etl.batch import LEGACY_BATCH, pending_query
from scripts.etl.load.staging import (
    STAGING_TABLES, ensure_batch_column, ensure_control_table, mongo_batch_counts,
    pending_batches, recorded_counts, table_exists, take_load_lock,
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

            if batch_id:
                pending = [batch_id]
            else:
                recorded = recorded_counts(cursor)
                pending = pending_batches(mongo_batch_counts(mongo), recorded)
                logger.info(f"Lotes já carregados: {len(recorded)}")
            logger.info(f"Lotes pendentes: {pending or 'nenhum'}")
            query = pending_query(pending)

            staged: dict[str, int] = {}
            for table, collection, _ in STAGING_TABLES:
                mongo.create_plain_index(collection, "batch_id")
                documents = (
                    mongo.get_documents(query=query, collection=collection)
                    if query else []
                )
                if not documents:
                    # Nada pendente desta coleção: o staging não pode guardar
                    # sobras de uma carga anterior
                    if table_exists(cursor, table):
                        cursor.execute(f"DELETE FROM public.{table}")
                    logger.info(f"Coleção '{collection}': nada pendente")
                    continue

                rows = _with_batch(documents)
                logger.info(f"Coleção '{collection}': {len(rows)} documentos")
                pd.DataFrame(rows).to_sql(
                    table, connection, if_exists="replace", index=False
                )
                staged[table] = len(rows)
    finally:
        engine.dispose()

    if not staged:
        logger.info("Nada pendente para carregar")
    return staged


if __name__ == '__main__':
    treat_data_to_postgres()
