"""Parsing dos anúncios a partir do HTML guardado no MinIO.

Gera a coleção raw_imoveis. Com REPROCESS=true reprocessa todos os HTMLs
(útil depois de mudar o parser), substituindo os documentos brutos do anúncio.
"""
from scripts.etl.extraction.parsers import parse_property
from scripts.infra.security.secrets import get_secret_value
from scripts.infra.storage.mongo import MongoDB
from scripts.infra.storage.object_store import ObjectStore, ad_id_from_url
from scripts.utility.log import get_logger

from collections import defaultdict
from datetime import datetime

import os


logger = get_logger(__name__)

BATCH_SIZE = 100


def parse_stored_property(reprocess: bool | None = None):
    logger.info("---------------- PARSE PROPERTY ----------------")
    if reprocess is None:
        reprocess = os.getenv("REPROCESS", "false").lower() == "true"

    mongo = MongoDB(
        uri=get_secret_value('MONGO_URI')
    )
    store = ObjectStore()

    query = {"html_key": {"$exists": True}}
    if not reprocess:
        query["parsed"] = {"$exists": False}

    docs = mongo.get_documents(query=query, collection='links_imoveis')
    logger.info(f"{len(docs)} HTMLs para processar (reprocess={reprocess})")

    for start in range(0, len(docs), BATCH_SIZE):
        data, list_id = [], []
        list_id_error = defaultdict(list)

        for doc in docs[start:start + BATCH_SIZE]:
            try:
                html = store.get_html(doc["html_key"])
                parsed = parse_property(html)

                if not parsed["titulo_anuncio"] or not parsed["preco"]:
                    raise ValueError("anúncio sem título ou preço")

                data.append({
                    **parsed,
                    "anuncio_id": ad_id_from_url(doc["link"]),
                    "link": doc["link"],
                    "html_key": doc["html_key"],
                    "tipo_imovel": doc['tipo'],
                    "modo_imovel": doc['modo'],
                    # Telefone não é coletado (exigiria enviar contatos
                    # fictícios ao formulário do site)
                    "telefone": [],
                    # Data em que o HTML foi coletado (pela chave)
                    "data_coleta_imovel": _collected_at(doc),
                })
                list_id.append(doc["_id"])
            except Exception as e:
                logger.error(f"Erro ao processar {doc['html_key']}: {e}")
                list_id_error[str(e)].append(doc["_id"])

        now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

        if reprocess and data:
            mongo.delete_documents(
                query={"anuncio_id": {"$in": [d["anuncio_id"] for d in data]}},
                collection='raw_imoveis'
            )

        if data:
            logger.info("Insert documents in collection 'raw_imoveis'")
            mongo.insert_documents(documents=data, collection='raw_imoveis')
            mongo.update_documents(
                query={"_id": {"$in": list_id}},
                set={"$set": {"parsed": True, "updated_dt": now}},
                collection='links_imoveis'
            )

        for error_type, ids in list_id_error.items():
            mongo.update_documents(
                query={"_id": {"$in": ids}},
                set={"$set": {"parsed": True, "parse_error": error_type,
                              "updated_dt": now}},
                collection='links_imoveis'
            )


def _collected_at(doc: dict) -> str:
    """dd-mm-aaaa HH:MM:SS a partir da data presente na chave do HTML."""
    year, month, day = doc["html_key"].split("/")[1].split("-")
    return f"{day}-{month}-{year} 00:00:00"


if __name__ == '__main__':
    parse_stored_property()
