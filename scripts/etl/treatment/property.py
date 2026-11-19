from scripts.utility.log import get_logger
from scripts.infra.storage.mongo import MongoDB
from scripts.infra.security.secrets import get_secret_value
from scripts.utility.operator import (
    extract_date, extract_number,
    extract_address, tokenize_and_standardize,
    convert_format_data
)
from scripts.etl.treatment.images import treatment_images
from scripts.etl.treatment.snapshots import COLLECTION, build_snapshot

from collections import defaultdict
from datetime import datetime

import hashlib


logger = get_logger(__name__)


def treat_property():
    logger.info("---------------- TREATMENT PROPERTY ----------------")

    mongo = MongoDB(
        uri=get_secret_value('MONGO_URI')
    )
    mongo.create_hash_index("treat_imoveis", "hash")
    mongo.create_hash_index(COLLECTION, "snapshot_key")
    known_hashes = set(mongo.distinct_values("hash", "treat_imoveis"))

    b = 0
    while True:
        b += 1

        logger.info(f"=> Batch {b}")
        logger.info("Get documents in collection 'raw_imoveis'")
        docs = mongo.get_documents(
            query={
                'treat': {
                    "$exists": False
                },
            },
            collection='raw_imoveis'
        )

        if len(docs) == 0:
            break

        data = []
        snapshots = []
        list_id_error = defaultdict(list)
        list_id = []

        for doc in docs[:50]:
            try:
                list_id.append(doc["_id"])
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
                    unique_hash, price, condo, iptu, data_coleta
                ))

                if unique_hash in known_hashes:
                    # Anúncio já tratado: só o snapshot interessa
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
                        "hash": unique_hash
                    }
                )

                logger.info(f"- {doc["titulo_anuncio"]}")
            except Exception as e:
                list_id_error[str(e)].append(doc['_id'])

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
                    "updated_dt": datetime.now().strftime(
                        "%d-%m-%Y %H:%M:%S"
                    )
                }
            },
            collection='raw_imoveis'
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
                    collection='raw_imoveis'
                )


if __name__ == '__main__':
    treat_property()
