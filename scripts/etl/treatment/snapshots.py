"""Snapshots de preço: uma observação do anúncio por data de coleta (D4).

O hash do anúncio ignora o preço (identifica o imóvel), então mudanças de
preço só são preservadas por estes snapshots.
"""
from scripts.infra.security.secrets import get_secret_value
from scripts.infra.storage.mongo import MongoDB
from scripts.utility.log import get_logger


logger = get_logger(__name__)

COLLECTION = "snapshots_imoveis"


def build_snapshot(
    hash_: str, preco, condominio, iptu, data_coleta: str,
    batch_id: str | None = None,
) -> dict:
    """data_coleta no formato dd/mm/aaaa. A chave evita duplicar no mesmo dia.

    `batch_id` é o lote do tratamento, usado pela carga incremental.
    """
    snapshot = {
        "hash": hash_,
        "snapshot_key": f"{hash_}_{data_coleta}",
        "preco": preco,
        "condominio": condominio,
        "iptu": iptu,
        "data_coleta": data_coleta,
    }
    if batch_id:
        snapshot["batch_id"] = batch_id
    return snapshot


def backfill_snapshots() -> None:
    """Cria o primeiro snapshot de anúncios tratados antes do D4 (idempotente)."""
    mongo = MongoDB(uri=get_secret_value('MONGO_URI'))
    mongo.create_hash_index(COLLECTION, "snapshot_key")

    docs = mongo.get_documents(query={}, collection="treat_imoveis")
    snapshots = [
        build_snapshot(
            d["hash"], d.get("preco"), d.get("condominio"), d.get("iptu"),
            d["data_coleta_imovel"],
        )
        for d in docs
        if d.get("preco") is not None
    ]
    logger.info(f"Backfill: {len(snapshots)} snapshots")
    mongo.insert_hash_documents(documents=snapshots, collection=COLLECTION)


if __name__ == '__main__':
    backfill_snapshots()
