"""Quarentena do HTML: o que falhou no parse ou no tratamento fica guardado.

O HTML de um anúncio só é apagado depois que o lote dele foi carregado no
Postgres (purge_html.py). O que falhou antes disso (erro de parse ou anúncio em
quarentena no tratamento) fica no storage para ser examinado e reprocessado, e
é registrado aqui na coleção `quarentena_html`.

Limites (para não acumular disco nem insistir com um parser quebrado):
- `QUARANTINE_MAX_BATCHES` (padrão 20): quantos lotes distintos (execuções que
  registraram itens) podem ter HTML em quarentena ao mesmo tempo;
- `QUARANTINE_CONSECUTIVE` (padrão 3): quantas execuções seguidas podem
  acrescentar itens novos à quarentena;
- `HTML_QUARANTINE_DAYS` (padrão 7): idade a partir da qual o HTML em
  quarentena é apagado.
Ao atingir um dos dois primeiros limites a esteira para (QuarantineLimitError,
que falha a task e dispara o alerta), em vez de gastar horas coletando com um
parser quebrado.

"Lote" na quarentena é a execução do purge_html que registrou o item (cada uma
tem seu `batch_id`); com a coleta em lotes por página (item 23 do backlog)
passa a ser a página.

Como sair de um limite atingido (o `requeue` bloqueia a DAG `extraction`
inteira, inclusive o parse):
1. Examine `quarentena_html` (etapa e motivo de cada item) e corrija o parser.
2. Reconstrua a imagem e reprocesse o HTML retido:
   `REPROCESS=true python3 scripts/etl/extraction/parse_property.py`.
3. Dispare a DAG `treatment` (ela dispara a `load`). O `purge_html` no fim tira
   da quarentena o que deixou de falhar e registra uma execução sem itens novos,
   o que zera a contagem de execuções seguidas. Quarentena vazia nunca bloqueia.
Se o item não tem conserto, espere `HTML_QUARANTINE_DAYS` ou apague a entrada de
`quarentena_html` e dispare a `load`.
"""
from scripts.etl.quality import QualityError
from scripts.utility.log import get_logger

from datetime import datetime, timedelta, UTC

import os


logger = get_logger(__name__)

COLLECTION = "quarentena_html"
METRICS_COLLECTION = "run_metrics"
PURGE_STEP = "purge_html"


class QuarantineLimitError(QualityError):
    """Há HTML demais em quarentena: a coleta para até alguém olhar."""


def purge_enabled() -> bool:
    return os.getenv("PURGE_HTML", "true").lower() != "false"


def max_batches() -> int:
    return int(os.getenv("QUARANTINE_MAX_BATCHES", "20"))


def max_consecutive() -> int:
    return int(os.getenv("QUARANTINE_CONSECUTIVE", "3"))


def quarantine_days() -> int:
    return int(os.getenv("HTML_QUARANTINE_DAYS", "7"))


def failing_html(mongo) -> dict[str, tuple[str, str]]:
    """HTML retido por falha agora: {html_key: (etapa, motivo)}."""
    still_there = {"html_key": {"$exists": True}, "html_purged": {"$exists": False}}
    failing = {}
    for doc in mongo.get_documents(
        query={**still_there, "parse_error": {"$exists": True}},
        collection="links_imoveis",
    ):
        failing[doc["html_key"]] = ("parse", str(doc["parse_error"]))
    for doc in mongo.get_documents(
        query={**still_there, "treat_quarantine": True},
        collection="raw_imoveis",
    ):
        failing[doc["html_key"]] = ("tratamento", str(doc.get("treat_error", "")))
    return failing


def sync(mongo, batch_id: str) -> int:
    """Alinha o registro com o que está falhando. Devolve quantos itens são novos.

    Itens que deixaram de falhar (corrigidos e reprocessados, ou reenfileirados)
    saem do registro; o HTML deles segue o fluxo normal.
    """
    failing = failing_html(mongo)
    registered = {
        doc["html_key"]: doc
        for doc in mongo.get_documents(query={}, collection=COLLECTION)
    }

    resolved = [key for key in registered if key not in failing]
    if resolved:
        mongo.delete_documents(
            query={"html_key": {"$in": resolved}}, collection=COLLECTION
        )

    new = [
        {
            "html_key": key, "etapa": stage, "motivo": reason[:300],
            "batch_id": batch_id, "desde": datetime.now(UTC),
        }
        for key, (stage, reason) in failing.items()
        if key not in registered
    ]
    if new:
        mongo.insert_documents(documents=new, collection=COLLECTION)
    logger.info(
        f"Quarentena: {len(new)} novos, {len(resolved)} resolvidos, "
        f"{len(failing)} no total"
    )
    return len(new)


def expire(mongo, store, days: int | None = None, now: datetime | None = None) -> int:
    """Apaga o HTML em quarentena mais antigo que `days`. Devolve quantos."""
    days = quarantine_days() if days is None else days
    limit = (now or datetime.now(UTC)) - timedelta(days=days)
    expired = mongo.get_documents(query={"desde": {"$lt": limit}}, collection=COLLECTION)
    keys = [doc["html_key"] for doc in expired]
    if not keys:
        return 0

    # Primeiro o storage; só então o Mongo: se apagar falhar, nada é marcado
    store.delete_many(keys)
    marked = {"$set": {"html_purged": True, "html_quarantine_expired": True}}
    for collection in ("links_imoveis", "raw_imoveis"):
        mongo.update_documents(
            query={"html_key": {"$in": keys}}, set=marked, collection=collection
        )
    mongo.delete_documents(query={"html_key": {"$in": keys}}, collection=COLLECTION)
    logger.warning(
        f"{len(keys)} HTMLs em quarentena há mais de {days} dias foram apagados"
    )
    return len(keys)


def consecutive_runs_with_new(mongo) -> int:
    """Quantas execuções de purge_html, da mais recente para trás, trouxeram itens novos."""
    recent = mongo.get_documents_aggregate(
        pipeline=[
            {"$match": {"step": PURGE_STEP}},
            {"$sort": {"at": -1}},
            {"$limit": max_consecutive() + 1},
        ],
        collection=METRICS_COLLECTION,
    )
    count = 0
    for run in recent:
        if run.get("quarantined_new", 0) > 0:
            count += 1
        else:
            break
    return count


def check_limits(mongo) -> None:
    """Levanta QuarantineLimitError se algum limite da quarentena foi atingido."""
    keys = mongo.get_documents(query={}, collection=COLLECTION)
    if not keys:
        return  # nada em quarentena: nenhum limite se aplica

    batches = {doc.get("batch_id") for doc in keys}
    if len(batches) >= max_batches():
        raise QuarantineLimitError(
            f"{len(batches)} lotes com HTML em quarentena (limite "
            f"{max_batches()}); {len(keys)} itens. Examine a coleção "
            f"'{COLLECTION}', corrija o parser e reprocesse."
        )
    consecutive = consecutive_runs_with_new(mongo)
    if consecutive >= max_consecutive():
        raise QuarantineLimitError(
            f"{consecutive} execuções seguidas acrescentaram HTML à quarentena "
            f"(limite {max_consecutive()}); {len(keys)} itens. O parser pode ter "
            "quebrado: examine a coleção "
            f"'{COLLECTION}' antes de coletar mais."
        )
