from scripts.utility.log import get_logger

from scripts.etl.extraction.scraper import WebScraper
from scripts.infra.storage.mongo import MongoDB

from scripts.infra.security.secrets import get_secret_value
from scripts.etl.extraction.parsers import parse_property

from collections import defaultdict
from datetime import datetime
from time import sleep


logger = get_logger(__name__)

DETAIL_READY_CSS = '[data-testid="location-address"]'
PAUSE_SECONDS = 3


def get_property():
    logger.info("---------------- SCRAPER LINKS ----------------")

    mongo = MongoDB(
        uri=get_secret_value('MONGO_URI')
    )

    b = 0
    while True:

        b += 1
        # if b == 3:
        #     break

        logger.info(f"=> Batch {b}")
        logger.info("Get documents in collection 'links_imoveis'")
        docs = mongo.get_documents(
            query={
                'scraper': {
                    "$exists": False
                }
            },
            collection='links_imoveis'
        )

        if len(docs) == 0:
            break

        data = []
        list_id_error = defaultdict(list)
        list_id = []

        logger.info("Start Scraper")
        for doc in docs[:50]:
            try:
                html = WebScraper.fetch_html_once(doc['link'], DETAIL_READY_CSS)
                parsed = parse_property(html)

                if not parsed["titulo_anuncio"] or not parsed["preco"]:
                    raise ValueError("anúncio sem título ou preço")

                data.append({
                    **parsed,
                    "tipo_imovel": doc['tipo'],
                    "modo_imovel": doc['modo'],
                    # Telefone não é coletado (exigiria enviar contatos
                    # fictícios ao formulário do site)
                    "telefone": [],
                    "data_coleta_imovel": datetime.now().strftime(
                        "%d-%m-%Y %H:%M:%S"
                    )
                })

                list_id.append(doc['_id'])

                logger.info(f"- {parsed['titulo_anuncio']}")

            except Exception as e:
                logger.error(f"Erro em {doc['link']}: {e}")
                list_id_error[str(e).strip().split("\n")[0]].append(doc['_id'])

            sleep(PAUSE_SECONDS)

        logger.info("Insert documents in collection 'imoveis'")
        mongo.insert_documents(
            documents=data,
            collection='raw_imoveis'
        )

        logger.info("Update documents in collection 'links_imoveis'")
        mongo.update_documents(
            query={
                "_id": {
                    "$in": list_id
                }
            },
            set={
                "$set": {
                    "scraper": True,
                    "updated_dt": datetime.now().strftime(
                        "%d-%m-%Y %H:%M:%S"
                    )
                }
            },
            collection='links_imoveis'
        )

        if len(list_id_error) > 0:
            for error_type, ids_error in list_id_error.items():

                mongo.update_documents(
                    query={
                        "_id": {
                            "$in": ids_error
                        }
                    },
                    set={
                        "$set": {
                            "scraper": True,
                            "error": error_type,
                            "updated_dt": datetime.now().strftime(
                                "%d-%m-%Y %H:%M:%S"
                            )
                        }
                    },
                    collection='links_imoveis'
                )


if __name__ == '__main__':
    get_property()
