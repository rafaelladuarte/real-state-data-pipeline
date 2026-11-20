"""Reenfileira links antigos para uma nova observação (histórico de preço).

RECRAWL_AFTER_DAYS (padrão 7): links coletados há mais tempo voltam à fila.

Antes de reenfileirar, confere a quarentena do HTML: se há HTML demais retido por
falha (parser possivelmente quebrado), a coleta para aqui, em vez de gastar
horas coletando o que não vai ser aproveitado. Veja quarantine.py.
"""
from scripts.etl.quarantine import check_limits, expire, purge_enabled
from scripts.infra.queue import LinkQueue
from scripts.infra.security.secrets import get_secret_value
from scripts.infra.storage.mongo import MongoDB
from scripts.infra.storage.object_store import ObjectStore
from scripts.utility.log import get_logger

import os


logger = get_logger(__name__)


def requeue_links():
    if purge_enabled():
        mongo = MongoDB(uri=get_secret_value('MONGO_URI'))
        expire(mongo, ObjectStore())  # libera a quarentena vencida antes de checar
        check_limits(mongo)

    days = int(os.getenv("RECRAWL_AFTER_DAYS", "7"))
    queue = LinkQueue(
        get_secret_value('MONGO_URI'), os.getenv("LINKS_COLLECTION", "links_imoveis")
    )
    count = queue.requeue_stale(days)
    logger.info(f"{count} links reenfileirados (coletados há mais de {days} dias)")


if __name__ == '__main__':
    requeue_links()
