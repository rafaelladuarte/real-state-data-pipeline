"""Identificador de lote: o que o tratamento grava e a carga incremental consome.

Cada execução do tratamento gera um lote. Os documentos tratados e os snapshots
de preço carregam o `batch_id`; a carga leva ao Postgres só os lotes que ainda
não foram carregados. O id é único por execução (data, hora e sufixo aleatório):
com só a data, o que fosse tratado depois da primeira carga do dia seria
considerado "já carregado" e nunca subiria.

`BATCH_ID` no ambiente força um id (útil para recarregar um lote específico).
"""
from datetime import datetime, UTC

import os
import secrets

# Documentos tratados antes da carga incremental não têm batch_id
LEGACY_BATCH = "legado"


def new_batch_id() -> str:
    """AAAAMMDDTHHMMSS-xxxx, em UTC: ordena por tempo e não repete."""
    return f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{secrets.token_hex(2)}"


def current_batch_id() -> str:
    return os.getenv("BATCH_ID") or new_batch_id()


def pending_query(pending: list[str]) -> dict | None:
    """Filtro do Mongo para os documentos dos lotes `pending`.

    `legado` seleciona os documentos sem batch_id. Lista vazia: None (nada a buscar).
    """
    clauses = []
    named = [batch for batch in pending if batch != LEGACY_BATCH]
    if named:
        clauses.append({"batch_id": {"$in": named}})
    if LEGACY_BATCH in pending:
        clauses.append({"batch_id": {"$exists": False}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$or": clauses}
