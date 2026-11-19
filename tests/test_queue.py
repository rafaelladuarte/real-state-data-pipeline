"""Testes de integração da fila e do limitador (precisam de um Mongo).

Defina MONGO_TEST_URI (ex.: mongodb://username:password@localhost:27018/?authSource=admin);
sem ele, os testes são ignorados. Usam o banco descartável `real_state_test`.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from time import monotonic

import os

import pytest

from scripts.infra.queue import LinkQueue, RateLimiter, backoff_seconds

URI = os.getenv("MONGO_TEST_URI")
TEST_DB = "real_state_test"


def test_backoff_grows_and_is_capped():
    assert [backoff_seconds(n) for n in (1, 2, 3)] == [30, 60, 120]
    assert backoff_seconds(20) == 600


pytestmark_mongo = pytest.mark.skipif(not URI, reason="MONGO_TEST_URI não definido")


@pytest.fixture
def db():
    from pymongo import MongoClient

    client = MongoClient(URI)
    client.drop_database(TEST_DB)
    yield client[TEST_DB]
    client.drop_database(TEST_DB)


@pytestmark_mongo
def test_claim_never_hands_same_link_twice(db):
    db.links.insert_many([{"link": f"l{i}"} for i in range(60)])

    def worker(name):
        queue, got = LinkQueue(URI, "links", TEST_DB), []
        while (doc := queue.claim(name)) is not None:
            got.append(doc["link"])
        return got

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(worker, [f"w{i}" for i in range(6)]))

    claimed = [link for r in results for link in r]
    assert len(claimed) == 60 and len(set(claimed)) == 60


@pytestmark_mongo
def test_expired_lease_is_reclaimed_and_valid_lease_is_not(db):
    past = datetime.now(timezone.utc) - timedelta(seconds=5)
    future = datetime.now(timezone.utc) + timedelta(seconds=300)
    db.links.insert_many([
        {"link": "expired", "lease_until": past},
        {"link": "busy", "lease_until": future},
    ])
    queue = LinkQueue(URI, "links", TEST_DB)
    assert queue.claim("w")["link"] == "expired"
    assert queue.claim("w") is None


@pytestmark_mongo
def test_fail_retries_with_backoff_then_gives_up(db):
    db.links.insert_one({"link": "x"})
    queue = LinkQueue(URI, "links", TEST_DB)

    doc = queue.claim("w")
    assert queue.fail(doc, "boom", max_attempts=2) is False
    assert queue.claim("w") is None  # em backoff

    doc = db.links.find_one({"link": "x"})
    assert queue.fail(doc, "boom", max_attempts=2) is True
    stored = db.links.find_one({"link": "x"})
    assert stored["scraper"] is True and stored["error"] == "boom"


@pytestmark_mongo
def test_complete_marks_link_done(db):
    db.links.insert_one({"link": "x"})
    queue = LinkQueue(URI, "links", TEST_DB)
    doc = queue.claim("w")
    queue.complete(doc["_id"], "anuncio/k.html.gz")
    stored = db.links.find_one({"link": "x"})
    assert stored["scraper"] is True and stored["html_key"] == "anuncio/k.html.gz"
    assert "lease_until" not in stored
    assert queue.claim("w") is None


@pytestmark_mongo
def test_rate_limiter_spaces_requests_across_threads(db):
    interval, calls = 0.3, 6
    limiter = RateLimiter(URI, interval, collection="rate", db=TEST_DB)

    def call(_):
        limiter.wait()
        return monotonic()

    with ThreadPoolExecutor(max_workers=3) as pool:
        times = sorted(pool.map(call, range(calls)))

    gaps = [b - a for a, b in zip(times, times[1:])]
    # Intervalo global respeitado (tolerância para a latência das chamadas)
    assert min(gaps) >= interval * 0.7
    assert times[-1] - times[0] >= interval * (calls - 1) * 0.8


@pytestmark_mongo
def test_requeue_stale_resets_only_old_or_unmarked_links(db):
    old = datetime.now(timezone.utc) - timedelta(days=10)
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    base = {"scraper": True, "html_key": "k", "parsed": True}
    db.links.insert_many([
        {"link": "old", "collected_at": old, **base},
        {"link": "recent", "collected_at": recent, **base},
        {"link": "legacy", **base},                 # coletado antes do D4
        {"link": "pending"},                        # nunca coletado
    ])
    queue = LinkQueue(URI, "links", TEST_DB)

    assert queue.requeue_stale(7) == 2
    assert db.links.find_one({"link": "old"}).get("scraper") is None
    assert db.links.find_one({"link": "legacy"}).get("html_key") is None
    assert db.links.find_one({"link": "recent"})["scraper"] is True
    claimed = {queue.claim("w")["link"] for _ in range(3)}
    assert claimed == {"old", "legacy", "pending"}
    assert queue.claim("w") is None  # "recent" continua coletado
