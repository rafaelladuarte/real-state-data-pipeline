"""Fila de links com reserva atômica e limitador global de requisições.

Ambos usam o Mongo como estado compartilhado, então funcionam entre
processos/containers diferentes (workers do Airflow):

- LinkQueue.claim: reserva um link com `find_one_and_update` (lease com
  expiração); dois workers nunca recebem o mesmo link.
- RateLimiter.wait: reserva atomicamente o próximo "slot" de tempo, de modo
  que a soma de todos os workers respeite um intervalo mínimo entre requisições.
"""
from pymongo import MongoClient, ReturnDocument

from datetime import datetime, timedelta, UTC
from time import monotonic, sleep

DB = "real_state"
BASE_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 600


def backoff_seconds(attempts: int) -> int:
    """Espera antes de nova tentativa: 30 s, 60 s, 120 s … até 10 min."""
    return min(BASE_BACKOFF_SECONDS * 2 ** (attempts - 1), MAX_BACKOFF_SECONDS)


def _now() -> datetime:
    return datetime.now(UTC)


class LinkQueue:
    def __init__(
        self, uri: str, collection: str = "links_imoveis", db: str = DB
    ):
        self._coll = MongoClient(uri)[db][collection]

    def claim(self, worker_id: str, lease_seconds: int = 300) -> dict | None:
        """Reserva o próximo link pendente (ou cujo lease/backoff expirou)."""
        now = _now()
        return self._coll.find_one_and_update(
            {
                "scraper": {"$exists": False},
                "$or": [
                    {"lease_until": {"$exists": False}},
                    {"lease_until": {"$lt": now}},
                ],
            },
            {"$set": {
                "lease_owner": worker_id,
                "lease_until": now + timedelta(seconds=lease_seconds),
            }},
            return_document=ReturnDocument.AFTER,
        )

    def complete(self, doc_id, html_key: str) -> None:
        self._coll.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "scraper": True,
                    "html_key": html_key,
                    "collected_at": _now(),
                    "updated_dt": _now().strftime("%d-%m-%Y %H:%M:%S"),
                },
                "$unset": {"lease_until": "", "lease_owner": "", "error": ""},
            },
        )

    def requeue_stale(self, older_than_days: int) -> int:
        """Reenfileira links coletados há mais de N dias (nova observação).

        Links sem `collected_at` (coletados antes do D4) contam como antigos.
        Limpa o estado da coleta anterior para que o worker busque de novo.
        """
        limit = _now() - timedelta(days=older_than_days)
        result = self._coll.update_many(
            {
                "scraper": True,
                "html_key": {"$exists": True},
                "$or": [
                    {"collected_at": {"$lt": limit}},
                    {"collected_at": {"$exists": False}},
                ],
            },
            {"$unset": {
                "scraper": "", "html_key": "", "parsed": "", "attempts": "",
                "error": "", "parse_error": "", "lease_until": "",
                "lease_owner": "", "html_purged": "", "html_purged_at": "",
                "html_quarantine_expired": "",
            }},
        )
        return result.modified_count

    def release(self, doc: dict, cooldown_seconds: int) -> None:
        """Devolve o link à fila após uma pausa, sem contar como tentativa."""
        self._coll.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {"lease_until": _now() + timedelta(seconds=cooldown_seconds)},
                "$unset": {"lease_owner": ""},
            },
        )

    def fail(self, doc: dict, error: str, max_attempts: int = 3) -> bool:
        """Registra a falha. Devolve True se esgotou as tentativas."""
        attempts = doc.get("attempts", 0) + 1
        final = attempts >= max_attempts
        update = {"attempts": attempts, "error": error}
        if final:
            update["scraper"] = True
            update["updated_dt"] = _now().strftime("%d-%m-%Y %H:%M:%S")
        else:
            update["lease_until"] = _now() + timedelta(
                seconds=backoff_seconds(attempts)
            )
        self._coll.update_one({"_id": doc["_id"]}, {"$set": update})
        return final


class RateLimiter:
    """Intervalo mínimo global entre requisições, somando todos os workers."""

    def __init__(
        self, uri: str, min_interval: float, key: str = "zapimoveis",
        collection: str = "rate_limit", db: str = DB
    ):
        self._coll = MongoClient(uri)[db][collection]
        self._key = key
        self._interval_ms = int(min_interval * 1000)

    def wait(self) -> float:
        """Reserva o próximo slot e dorme até ele. Devolve a espera (s)."""
        started = monotonic()
        doc = self._coll.find_one_and_update(
            {"_id": self._key},
            [{"$set": {
                "now": "$$NOW",
                "slot": {"$max": [
                    "$$NOW",
                    {"$add": [
                        {"$ifNull": ["$slot", datetime(1970, 1, 1)]},
                        self._interval_ms,
                    ]},
                ]},
            }}],
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        # slot e now vêm do relógio do servidor, então a diferença independe do
        # cliente. O servidor carimbou "now" no meio da chamada: desconta metade
        # da ida e volta para acordar perto do slot reservado.
        round_trip = monotonic() - started
        delay = max((doc["slot"] - doc["now"]).total_seconds() - round_trip / 2, 0)
        if delay:
            sleep(delay)
        return delay
