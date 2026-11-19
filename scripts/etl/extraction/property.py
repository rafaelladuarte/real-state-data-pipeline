"""Coleta o HTML dos anúncios e guarda na camada bruta (MinIO).

Somente busca e armazena; o parsing é feito por parse_property.py, que pode
ser reexecutado sem acessar o site.
"""
from scripts.etl.extraction.scraper import WebScraper
from scripts.infra.security.secrets import get_secret_value
from scripts.infra.storage.mongo import MongoDB
from scripts.infra.storage.object_store import (
    ObjectStore, ad_id_from_url, html_key
)
from scripts.utility.log import get_logger

from collections import defaultdict
from datetime import datetime
from time import sleep


logger = get_logger(__name__)

DETAIL_READY_CSS = '[data-testid="location-address"]'
PAUSE_SECONDS = 3
BATCH_SIZE = 50


def get_property():
    logger.info("---------------- SCRAPER LINKS ----------------")

    mongo = MongoDB(
        uri=get_secret_value('MONGO_URI')
    )
    store = ObjectStore()

    b = 0
    while True:
        b += 1

        logger.info(f"=> Batch {b}")
        logger.info("Get documents in collection 'links_imoveis'")
        docs = mongo.get_documents(
            query={'scraper': {"$exists": False}},
            collection='links_imoveis'
        )

        if len(docs) == 0:
            break

        list_id_error = defaultdict(list)

        logger.info("Start Scraper")
        for doc in docs[:BATCH_SIZE]:
            try:
                html = WebScraper.fetch_html_once(
                    doc['link'], DETAIL_READY_CSS
                )
                key = html_key("anuncio", ad_id_from_url(doc['link']))
                store.put_html(key, html)

                mongo.update_documents(
                    query={"_id": doc["_id"]},
                    set={
                        "$set": {
                            "scraper": True,
                            "html_key": key,
                            "updated_dt": datetime.now().strftime(
                                "%d-%m-%Y %H:%M:%S"
                            ),
                        }
                    },
                    collection='links_imoveis'
                )
                logger.info(f"- {key}")

            except Exception as e:
                logger.error(f"Erro em {doc['link']}: {e}")
                list_id_error[
                    str(e).strip().split("\n")[0]
                ].append(doc['_id'])

            sleep(PAUSE_SECONDS)

        for error_type, ids_error in list_id_error.items():
            mongo.update_documents(
                query={"_id": {"$in": ids_error}},
                set={
                    "$set": {
                        "scraper": True,
                        "error": error_type,
                        "updated_dt": datetime.now().strftime(
                            "%d-%m-%Y %H:%M:%S"
                        ),
                    }
                },
                collection='links_imoveis'
            )


if __name__ == '__main__':
    get_property()
