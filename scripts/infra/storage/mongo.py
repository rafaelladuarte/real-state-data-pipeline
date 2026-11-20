from scripts.utility.log import get_logger
from bson.objectid import ObjectId
from pymongo import MongoClient, InsertOne, errors


logger = get_logger(__name__)


DEFAULT_DB = "real_state"


class MongoDB:
    def __init__(self, uri: str, db: str = DEFAULT_DB):
        self._uri = uri
        # Um cliente por instância (pool de conexões interno do pymongo)
        self._client = MongoClient(uri)
        self._db = self._client[db]

    def insert_documents(
        self,
        documents: list,
        collection: str
    ) -> None:
        coll = self._db[collection]

        documents = [{**doc, '_id': ObjectId()} for doc in documents]

        if len(documents) > 1:
            coll.insert_many(documents)
        elif len(documents) == 1:
            coll.insert_one(documents[0])

    def insert_hash_documents(
        self,
        documents: list,
        collection: str
    ) -> None:
        if not documents:
            return

        coll = self._db[collection]

        documents = [{**doc, '_id': ObjectId()} for doc in documents]

        operations = [InsertOne(doc) for doc in documents]

        try:
            result = coll.bulk_write(operations, ordered=False)
            logger.info(f"Documentos inseridos com sucesso: {result.inserted_count}")
        except errors.BulkWriteError as e:
            duplicates = [
                1
                for err in e.details['writeErrors']
                if err['code'] == 11000
            ]
            logger.info(f"- Documents ignored due to duplication: {len(duplicates)}")
            other_errors = [
                err
                for err in e.details['writeErrors']
                if err['code'] != 11000
            ]
            if other_errors:
                logger.error(
                    f"- Documents ignored for other errors: {len(other_errors)}"
                )

    def get_documents(
        self,
        query: dict,
        collection: str,
        limit: int = 0
    ) -> list[dict]:
        coll = self._db[collection]

        cursor = coll.find(query)
        if limit:
            cursor = cursor.limit(limit)
        data = []
        for c in cursor:
            data.append(c)

        return data

    def update_documents(
        self,
        query: dict,
        set: dict,
        collection: str
    ) -> None:
        coll = self._db[collection]

        coll.update_many(query, set)

    def delete_documents(
        self,
        query: dict,
        collection: str
    ) -> int:
        coll = self._db[collection]

        return coll.delete_many(query).deleted_count

    def update_document(
        self,
        query: dict,
        set: dict,
        collection: str
    ) -> None:
        coll = self._db[collection]

        coll.update_one(query, set)

    def get_documents_aggregate(
        self,
        pipeline: list,
        collection: str
    ) -> list[dict]:
        coll = self._db[collection]

        cursor = coll.aggregate(pipeline)

        data = []
        for c in cursor:
            data.append(c)

        return data

    def find_missing_mobi_url(
        self,
        list_url: list,
    ) -> list[str]:
        coll = self._db['imobiliarias']

        existing_mobi_url = coll.distinct(
            "id_imobiliaria",
            {
                "imobiliaria": {
                    "$in": list_url
                }
            }
        )

        missing_mobi_url = [
            mobi_id
            for mobi_id in list_url
            if mobi_id not in existing_mobi_url
        ]

        return missing_mobi_url

    def get_ids_uniques(
            self,
            flag: str,
            collection: str
    ) -> list[dict]:
        coll = self._db[collection]

        cursor = coll.distinct(key=flag)
        data = cursor[:50]

        return data

    def distinct_values(self, field: str, collection: str) -> list:
        return self._db[collection].distinct(field)

    def close(self) -> None:
        self._client.close()

    def list_collection_names(self) -> list[str]:
        database = self._db

        data = database.list_collection_names()

        return data

    def create_plain_index(self, collection: str, field: str) -> None:
        """Índice comum (não único) para consultas por campo, como batch_id."""
        self._db[collection].create_index([(field, 1)])

    def create_hash_index(
        self,
        collection: str,
        hash: str
    ) -> None:
        coll = self._db[collection]

        indexs_exists = coll.index_information()

        index_name = f"{hash}_1"
        if index_name not in indexs_exists:
            coll.create_index([(hash, 1)], unique=True)
            logger.info(f"Index {hash} created in collection {collection}")
        else:
            logger.info(f"Index {hash} already exists in collection {collection}")
