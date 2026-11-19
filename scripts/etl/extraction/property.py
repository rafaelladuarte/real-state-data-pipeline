"""Worker de coleta: busca o HTML dos anúncios e guarda na camada bruta.

Vários workers podem rodar em paralelo (tarefas mapeadas do Airflow ou
processos): cada link é reservado de forma atômica (LinkQueue) e todos
compartilham um limite global de requisições (RateLimiter).

Somente busca e armazena; o parsing é feito por parse_property.py.
"""
from scripts.etl.extraction.scraper import WebScraper
from scripts.etl.quality import check_error_rate, raise_if_violated
from scripts.infra.queue import LinkQueue, RateLimiter
from scripts.infra.security.secrets import get_secret_value
from scripts.infra.storage.mongo import MongoDB
from scripts.infra.storage.object_store import (
    ObjectStore, ad_id_from_url, html_key
)
from scripts.utility.log import get_logger

from datetime import datetime, UTC
from time import monotonic

import os
import socket


logger = get_logger(__name__)

DETAIL_READY_CSS = '[data-testid="location-address"]'
# Intervalo mínimo GLOBAL entre requisições (0,8 req/s ≈ 48 por minuto)
MIN_INTERVAL_SECONDS = float(os.getenv("MIN_INTERVAL_SECONDS", "1.25"))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))


def run_worker(worker_id: str, collection: str = "links_imoveis") -> dict:
    uri = get_secret_value('MONGO_URI')
    queue = LinkQueue(uri, collection)
    limiter = RateLimiter(uri, MIN_INTERVAL_SECONDS)
    store = ObjectStore()

    stats = {"worker": worker_id, "ok": 0, "errors": 0}
    started = monotonic()
    logger.info(f"Worker {worker_id} iniciado")

    while True:
        doc = queue.claim(worker_id)
        if doc is None:
            break

        limiter.wait()
        try:
            html = WebScraper.fetch_html_once(doc['link'], DETAIL_READY_CSS)
            key = html_key("anuncio", ad_id_from_url(doc['link']))
            store.put_html(key, html)
            queue.complete(doc["_id"], key)
            stats["ok"] += 1
            logger.info(f"[{worker_id}] {key}")
        except Exception as e:
            stats["errors"] += 1
            final = queue.fail(
                doc, str(e).strip().split("\n")[0], MAX_ATTEMPTS
            )
            logger.error(
                f"[{worker_id}] erro em {doc['link']}: {e} "
                f"({'desistiu' if final else 'nova tentativa depois'})"
            )

    stats["duration_s"] = round(monotonic() - started, 1)
    logger.info(f"Worker {worker_id} finalizado: {stats}")

    report = check_error_rate(stats["ok"], stats["errors"])
    if stats["ok"] + stats["errors"]:
        MongoDB(uri).insert_documents(
            documents=[{**report.as_metrics("fetch"), **stats, "at": datetime.now(UTC)}],
            collection='run_metrics',
        )
    # Muitos erros seguidos indicam bloqueio do site: falha a task para alertar
    raise_if_violated(report, f"fetch {worker_id}")
    return stats


def get_property():
    logger.info("---------------- SCRAPER LINKS ----------------")
    worker_id = os.getenv("WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
    run_worker(worker_id, os.getenv("LINKS_COLLECTION", "links_imoveis"))


if __name__ == '__main__':
    get_property()
