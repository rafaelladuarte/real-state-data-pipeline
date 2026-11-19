from scripts.utility.log import get_logger
from scripts.infra.storage.mongo import MongoDB
from scripts.infra.storage.postgres import PostgreDB
from scripts.infra.security.secrets import get_secret_value


logger = get_logger(__name__)


def update_data_to_postgres():
    logger.info("---------------- UPDATE DATA TO POSTGRES----------------")
    mongo = MongoDB(
        uri=get_secret_value("MONGO_URI")
    )

    postgres = PostgreDB(
        uri=get_secret_value("POSTGRESQL_URI")
    )

    list_collection_names = [
        "treat_imoveis",
        "treat_imobiliarias"
    ]
    for collection_name in list_collection_names:
        logger.info(f"=> Collection {collection_name}")

        logger.info("Get documents in collection")
        documents = mongo.get_documents(
            query={"data_migradação": {"$exists": False}},
            collection=collection_name
        )

        documents = mongo.get_documents(
            query={""},
            collection=collection_name
        )

        table_name = "_" + collection_name

        logger.info(f"Insert documents in table '{table_name}'")
        postgres.post_dataframe(
            collection_name=table_name,
            documents=documents,
            if_exists='append'
        )


if __name__ == '__main__':
    update_data_to_postgres()
