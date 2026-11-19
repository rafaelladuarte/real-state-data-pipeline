from scripts.infra.security.secrets import get_secret_value
from scripts.infra.storage.mongo import MongoDB
from scripts.utility.log import get_logger

from datetime import datetime


logger = get_logger(__name__)

NOT_INFORMED = "Não informado"


def get_real_state():
    """Monta a coleção raw_imobiliarias a partir dos anúncios já coletados.

    A página pública da imobiliária fica atrás de um desafio da Cloudflare,
    então os dados vêm do bloco "anunciante" da própria página do anúncio
    (nome, quantidade de imóveis e data de cadastro). Credencial, endereço
    e telefone não estão disponíveis nessa origem.
    """
    logger.info("---------------- REAL STATE ----------------")

    mongo = MongoDB(
        uri=get_secret_value('MONGO_URI')
    )

    known = {
        doc["imobiliaria"]
        for doc in mongo.get_documents(
            query={}, collection='raw_imobiliarias'
        )
    }

    docs = mongo.get_documents(
        query={
            "get_mobi": {"$exists": False},
            "imobiliaria_url": {"$ne": None},
        },
        collection='raw_imoveis'
    )

    agencies = {}
    for doc in docs:
        agencies.setdefault(doc["imobiliaria_url"], doc)

    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    data = [
        {
            "imobiliaria": url,
            "nome_imobiliaria": doc.get("imobiliaria_nome"),
            "credencial_imobiliaria": None,
            "endereco_imobiliaria": NOT_INFORMED,
            "quantidade_imovel": doc.get("imobiliaria_qtd_imoveis"),
            "data_cadastro_imobiliaria": doc.get("imobiliaria_desde"),
            "telefone_imobiliaria": None,
            "data_coleta_imobiliaria": now,
        }
        for url, doc in agencies.items()
        if url not in known
    ]

    if data:
        logger.info(
            f"Insert {len(data)} documents in collection 'raw_imobiliarias'"
        )
        mongo.insert_documents(
            documents=data,
            collection='raw_imobiliarias'
        )

    if docs:
        logger.info("Update documents in collection 'raw_imoveis'")
        mongo.update_documents(
            query={"_id": {"$in": [doc["_id"] for doc in docs]}},
            set={"$set": {"get_mobi": True, "updated_dt": now}},
            collection="raw_imoveis"
        )


if __name__ == '__main__':
    get_real_state()
