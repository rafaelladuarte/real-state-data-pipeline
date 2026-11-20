"""Parsing dos anúncios a partir do HTML guardado no storage.

Gera a coleção raw_imoveis. Com REPROCESS=true reprocessa todos os HTMLs
(útil depois de mudar o parser), substituindo os documentos brutos do anúncio.
Só vale para o HTML que ainda está no storage: depois que o lote é carregado,
purge_html.py o apaga (PURGE_HTML=false mantém tudo).

Controle de qualidade: a taxa de campos vazios e de erros é avaliada ANTES de
gravar. Se o parser estiver quebrado (ex.: o site mudou), a execução falha e
nada é gravado nem marcado como processado; depois de corrigir o parser, basta
rodar de novo sobre o mesmo HTML.
"""
from scripts.etl.extraction.parsers import parse_property
from scripts.etl.quality import check_quality, raise_if_violated
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

    # HTML já apagado (lote carregado ou quarentena vencida) não pode ser relido
    query = {"html_key": {"$exists": True}, "html_purged": {"$exists": False}}
    if not reprocess:
        query["parsed"] = {"$exists": False}

    docs = mongo.get_documents(query=query, collection='links_imoveis')
    logger.info(f"{len(docs)} HTMLs para processar (reprocess={reprocess})")
    if not docs:
        return

    parsed_items = []  # (link_doc, registro bruto)
    list_id_error = defaultdict(list)

    for doc in docs:
        try:
            parsed = parse_property(store.get_html(doc["html_key"]))

            if not parsed["titulo_anuncio"] or not parsed["preco"]:
                raise ValueError("anúncio sem título ou preço")

            parsed_items.append((doc, {
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
            }))
        except Exception as e:
            logger.error(f"Erro ao processar {doc['html_key']}: {e}")
            list_id_error[str(e)].append(doc["_id"])

    # Qualidade antes de gravar: parser quebrado não contamina a camada bruta
    n_errors = sum(len(ids) for ids in list_id_error.values())
    report = check_quality([record for _, record in parsed_items], errors=n_errors)
    mongo.insert_documents(
        documents=[report.as_metrics("parse_property")], collection='run_metrics'
    )
    logger.info(
        f"Qualidade: {report.total} ok, {report.errors} erros, "
        f"nulos {({k: f'{v:.0%}' for k, v in report.null_rates.items() if v})}"
    )
    raise_if_violated(report, "parse_property")

    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    for start in range(0, len(parsed_items), BATCH_SIZE):
        batch = parsed_items[start:start + BATCH_SIZE]
        data = [record for _, record in batch]

        if reprocess:
            mongo.delete_documents(
                query={"anuncio_id": {"$in": [d["anuncio_id"] for d in data]}},
                collection='raw_imoveis'
            )

        logger.info("Insert documents in collection 'raw_imoveis'")
        mongo.insert_documents(documents=data, collection='raw_imoveis')
        mongo.update_documents(
            query={"_id": {"$in": [link_doc["_id"] for link_doc, _ in batch]}},
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
