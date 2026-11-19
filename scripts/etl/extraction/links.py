from scripts.etl.extraction.parsers import (
    parse_listing_links, parse_total_results
)
from scripts.etl.extraction.scraper import WebScraper
from scripts.infra.security.secrets import get_secret_value
from scripts.infra.storage.mongo import MongoDB
from scripts.utility.log import get_logger

from datetime import datetime
from time import sleep

import os


logger = get_logger(__name__)

PAGE_SIZE = 30
LISTING_READY_CSS = 'script[type="application/ld+json"]'
# Limite de páginas por busca (cada página traz ~30 anúncios)
MAX_PAGES = int(os.getenv("MAX_PAGES", "3"))
PAUSE_SECONDS = 3


def get_links_property():
    mongo = MongoDB(
        uri=get_secret_value('MONGO_URI')
    )

    tipos = [
        "casas",
        "apartamentos",
        # "studio",
        # "quitinetes",
        # "casas-de-condominio",
        # "cobertura", "flat", "float",
    ]
    modos = [
        # "venda",
        "aluguel"
    ]

    blends = [
        (modo, tipo)
        for tipo in tipos
        for modo in modos
    ]

    known_links = {
        doc["link"]
        for doc in mongo.get_documents(
            query={}, collection='links_imoveis'
        )
    }

    for modo, tipo in blends:
        url = f"https://www.zapimoveis.com.br/{modo}/{tipo}/mg+uberlandia/"

        logger.info(f"----------- {tipo.upper()} {modo.upper()} -----------")

        html = WebScraper.fetch_html_once(url, LISTING_READY_CSS)
        total = parse_total_results(html) or 0
        pages = min(MAX_PAGES, -(-total // PAGE_SIZE))
        logger.info(f"{total} anúncios encontrados; coletando {pages} páginas")

        for page in range(1, pages + 1):
            logger.info(f"- PÁGINA {page}")
            if page > 1:
                sleep(PAUSE_SECONDS)
                html = WebScraper.fetch_html_once(
                    f"{url}?pagina={page}", LISTING_READY_CSS
                )

            links = [
                link for link in parse_listing_links(html)
                if link not in known_links
            ]
            logger.info(f"{len(links)} links novos")
            if not links:
                continue

            known_links.update(links)
            logger.info("Insert documents in collection 'links_imoveis'")
            mongo.insert_documents(
                documents=[
                    {
                        "link": link,
                        "tipo": tipo,
                        "modo": modo,
                        "created_dt": datetime.now().strftime(
                            "%d-%m-%Y %H:%M:%S"
                        )
                    }
                    for link in links
                ],
                collection='links_imoveis'
            )

        sleep(PAUSE_SECONDS)


if __name__ == '__main__':
    get_links_property()
