from scripts.utility.log import get_logger
from scripts.infra.storage.mongo import MongoDB
from scripts.infra.storage.postgres import PostgreDB
from scripts.infra.security.secrets import get_secret_value

logger = get_logger(__name__)


def treat_data_to_postgres():
    """Copia as coleções tratadas do Mongo para o staging do Postgres.

    O staging (_treat_*) é um snapshot completo da camada tratada, recriado a
    cada execução; a idempotência está no passo seguinte (model.py), que faz
    upsert no modelo. É seguro reexecutar e não perde dados se uma etapa falhar.
    Com volume muito maior, trocar por carga incremental com marca d'água.
    """
    logger.info("---------------- TREAT DATA TO POSTGRES----------------")
    mongo = MongoDB(
        uri=get_secret_value("MONGO_URI")
    )

    postgres = PostgreDB(
        uri=get_secret_value("POSTGRESQL_URI")
    )
    # postgres._create_database()

    list_collection_names = [
        "treat_imoveis",
        "treat_imobiliarias"
    ]
    for collection_name in list_collection_names:
        logger.info(f"Get documents in collection '{collection_name}'")
        documents = mongo.get_documents(
            query={},
            collection=collection_name
        )

        table_name = "_" + collection_name

        logger.info(f"Insert documents in table '{table_name}'")
        postgres.post_dataframe(
            collection_name=table_name,
            documents=documents,
            if_exists="replace"
        )


if __name__ == '__main__':
    treat_data_to_postgres()
