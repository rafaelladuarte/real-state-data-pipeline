"""Reenfileira links antigos para uma nova observação (histórico de preço).

RECRAWL_AFTER_DAYS (padrão 7): links coletados há mais tempo voltam à fila.
"""
from scripts.infra.queue import LinkQueue
from scripts.infra.security.secrets import get_secret_value
from scripts.utility.log import get_logger

import os


logger = get_logger(__name__)


def requeue_links():
    days = int(os.getenv("RECRAWL_AFTER_DAYS", "7"))
    queue = LinkQueue(
        get_secret_value('MONGO_URI'), os.getenv("LINKS_COLLECTION", "links_imoveis")
    )
    count = queue.requeue_stale(days)
    logger.info(f"{count} links reenfileirados (coletados há mais de {days} dias)")


if __name__ == '__main__':
    requeue_links()
