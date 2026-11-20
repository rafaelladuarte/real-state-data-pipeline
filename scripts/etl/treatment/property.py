from scripts.etl.batch import current_batch_id
from scripts.utility.log import get_logger
from scripts.infra.storage.mongo import MongoDB
from scripts.infra.security.secrets import get_secret_value
from scripts.utility.operator import (
    extract_date, extract_number,
    extract_address, tokenize_and_standardize,
    convert_format_data
)
from scripts.etl.quality import check_error_rate, raise_if_violated
from scripts.etl.treatment.images import treatment_images
from scripts.etl.treatment.snapshots import COLLECTION, build_snapshot

from collections import defaultdict
from datetime import datetime, UTC

import hashlib
import os


logger = get_logger(__name__)

BATCH_SIZE = 50
# Depois de N falhas o anúncio vai para quarentena (treat_quarantine) e deixa de
# entrar no quality gate; sem isso, uns poucos anúncios ruins reprovariam todas
# as execuções.
MAX_TREAT_ATTEMPTS = int(os.getenv("MAX_TREAT_ATTEMPTS", "3"))


def treat_property():
    logger.info("---------------- TREATMENT PROPERTY ----------------")
    batch_id = current_batch_id()
    logger.info(f"Lote deste tratamento: {batch_id}")

    mongo = MongoDB(
        uri=get_secret_value('MONGO_URI')
    )
    mongo.create_hash_index("treat_imoveis", "hash")
    mongo.create_hash_index(COLLECTION, "snapshot_key")
    known_hashes = set(mongo.distinct_values("hash", "treat_imoveis"))

    b = 0
    n_ok = 0
    n_errors = 0
    n_quarantined = 0
    failed_ids = []  # falhas desta execução: não voltam no loop
    while True:
        b += 1

        logger.info(f"=> Batch {b}")
        logger.info("Get documents in collection 'raw_imoveis'")
        docs = mongo.get_documents(
            query={
                'treat': {"$exists": False},
                '_id': {"$nin": failed_ids},
                '$or': [
                    {'treat_attempts': {"$exists": False}},
                    {'treat_attempts': {"$lt": MAX_TREAT_ATTEMPTS}},
                ],
            },
            collection='raw_imoveis',
            limit=BATCH_SIZE
        )

        if len(docs) == 0:
            break

        data = []
        snapshots = []
        list_id_error = defaultdict(list)
        list_id = []

        for doc in docs:
            try:
                data_cadastro, data_atualizacao = extract_date(
                    doc["data_anuncio"]
                )
                data_coleta = convert_format_data(doc["data_coleta_imovel"])

                street, number, district = extract_address(doc["endereco"])

                values = (
                    f"{doc["tipo_imovel"]} {doc["modo_imovel"]} "
                    f"{doc["area"]} {doc["quartos"]} "
                    f"{doc["banheiro"]} {doc["vagas"]} "
                    f"{district} {data_cadastro}"
                )

                token_byte = tokenize_and_standardize(values)

                unique_hash = hashlib.sha256(token_byte).hexdigest()

                price = extract_number(doc["preco"])
                condo = extract_number(doc["condominio"])
                iptu = extract_number(doc["iptu"])

                # Toda observação gera um snapshot de preço (histórico)
                snapshots.append(build_snapshot(
                    unique_hash, price, condo, iptu, data_coleta, batch_id
                ))

                if unique_hash in known_hashes:
                    # Anúncio já tratado: só o snapshot interessa
                    list_id.append(doc["_id"])
                    continue
                known_hashes.add(unique_hash)

                images = treatment_images(doc["original_imagens"], unique_hash)

                data.append(
                    {
                        "titulo_anuncio": doc["titulo_anuncio"],
                        "tipo_imovel": doc["tipo_imovel"],
                        "modo_imovel": doc["modo_imovel"],
                        "descricao": doc["descricao"],
                        "preco": price,
                        "condominio": condo,
                        "iptu": iptu,
                        "area": extract_number(doc["area"]),
                        "quartos": extract_number(doc["quartos"]),
                        "banheiro": extract_number(doc["banheiro"]),
                        "vagas": extract_number(doc["vagas"]),
                        "suite": extract_number(doc["suite"]),
                        "outros": doc["outros"],
                        "endereco_completo": doc["endereco"],
                        "rua": street,
                        "bairro": district,
                        "numero": number,
                        "telefone": doc["telefone"],
                        "id_imobiliaria": extract_number(
                            doc["imobiliaria_url"]
                        ),
                        "imagens": images,
                        "data_cadastro": data_cadastro,
                        "data_atualizacao": data_atualizacao,
                        "data_coleta_imovel": data_coleta,
                        "hash": unique_hash,
                        "batch_id": batch_id,
                    }
                )

                list_id.append(doc["_id"])
                logger.info(f"- {doc["titulo_anuncio"]}")
            except Exception as e:
                logger.error(f"Erro ao tratar {doc['_id']}: {e}")
                list_id_error[str(e)].append(doc['_id'])
                failed_ids.append(doc['_id'])
                if doc.get("treat_attempts", 0) + 1 >= MAX_TREAT_ATTEMPTS:
                    n_quarantined += 1

        logger.info(f"Insert {len(snapshots)} snapshots in '{COLLECTION}'")
        mongo.insert_hash_documents(
            documents=snapshots,
            collection=COLLECTION
        )

        logger.info("Insert documents in collection 'treat_imoveis'")
        mongo.insert_hash_documents(
            documents=data,
            collection='treat_imoveis'
        )

        if list_id:
            logger.info("Update documents in collection 'raw_imoveis'")
            mongo.update_documents(
                query={
                    "_id": {
                        "$in": list_id
                    }
                },
                set={
                    "$set": {
                        "treat": True,
                        # Liga o HTML ao lote: só é apagado depois que o lote
                        # estiver carregado no Postgres (purge_html.py)
                        "batch_id": batch_id,
                        "updated_dt": datetime.now().strftime(
                            "%d-%m-%Y %H:%M:%S"
                        )
                    }
                },
                collection='raw_imoveis'
            )

        n_ok += len(list_id)
        failed_ids_batch = [i for ids in list_id_error.values() for i in ids]
        n_errors += len(failed_ids_batch)

        for error_type, ids_error in list_id_error.items():
            # Não é "treat": o anúncio continua pendente e conta uma tentativa
            mongo.update_documents(
                query={"_id": {"$in": ids_error}},
                set={
                    "$set": {
                        "treat_error": error_type,
                        "updated_dt": datetime.now().strftime(
                            "%d-%m-%Y %H:%M:%S"
                        )
                    },
                    "$inc": {"treat_attempts": 1},
                },
                collection='raw_imoveis'
            )
        if failed_ids_batch:
            mongo.update_documents(
                query={
                    "_id": {"$in": failed_ids_batch},
                    "treat_attempts": {"$gte": MAX_TREAT_ATTEMPTS},
                },
                set={"$set": {"treat_quarantine": True}},
                collection='raw_imoveis'
            )

    # Quality gate: só depois de gravar o que deu certo
    report = check_error_rate(n_ok, n_errors)
    if n_ok + n_errors:
        mongo.insert_documents(
            documents=[{
                **report.as_metrics("treat_property"),
                "quarantined": n_quarantined,
                "at": datetime.now(UTC),
            }],
            collection='run_metrics'
        )
    logger.info(
        f"Tratamento: {n_ok} ok, {n_errors} erros, "
        f"{n_quarantined} em quarentena"
    )
    raise_if_violated(report, "treat_property")


if __name__ == '__main__':
    treat_property()
