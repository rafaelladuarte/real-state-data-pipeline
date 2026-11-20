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


def pending_query(loaded: list[str], batch_id: str | None = None) -> dict:
    """Filtro do Mongo para o que ainda precisa ir ao Postgres.

    Com `batch_id`, só aquele lote (mesmo já carregado: recarga forçada).
    Sem ele, tudo que não está em `loaded`, inclusive os documentos sem
    batch_id (que contam como o lote `legado`).
    """
    if batch_id == LEGACY_BATCH:
        return {"batch_id": {"$exists": False}}
    if batch_id:
        return {"batch_id": batch_id}

    clauses = [{"batch_id": {"$exists": True, "$nin": loaded}}]
    if LEGACY_BATCH not in loaded:
        clauses.append({"batch_id": {"$exists": False}})
    return {"$or": clauses}
