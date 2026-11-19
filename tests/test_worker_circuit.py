"""O worker não insiste quando o site responde com desafio anti-bot."""
import pytest

from scripts.etl.extraction import property as worker
from scripts.etl.extraction.scraper import BlockedError
from scripts.etl.quality import QualityError


class FakeQueue:
    def __init__(self, links):
        self.pending = [
            {"_id": i, "link": f"https://x/imovel/a-id-{100 + i}/"} for i in range(links)
        ]
        self.released, self.failed, self.completed = [], [], []

    def claim(self, worker_id):
        return self.pending.pop(0) if self.pending else None

    def release(self, doc, cooldown):
        self.released.append((doc["_id"], cooldown))

    def fail(self, doc, error, max_attempts):
        self.failed.append(doc["_id"])
        return True

    def complete(self, doc_id, key):
        self.completed.append(doc_id)


class FakeLimiter:
    def __init__(self, *args, **kwargs):
        pass

    def wait(self):
        return 0


class FakeStore:
    def put_html(self, key, html):
        pass


class FakeMongo:
    metrics: list = []

    def __init__(self, uri):
        pass

    def insert_documents(self, documents, collection):
        FakeMongo.metrics.extend(documents)


@pytest.fixture
def setup(monkeypatch):
    queue = FakeQueue(10)
    monkeypatch.setenv("MONGO_URI", "mongodb://fake")
    monkeypatch.setattr(worker, "LinkQueue", lambda uri, collection: queue)
    monkeypatch.setattr(worker, "RateLimiter", FakeLimiter)
    monkeypatch.setattr(worker, "ObjectStore", FakeStore)
    monkeypatch.setattr(worker, "MongoDB", FakeMongo)
    FakeMongo.metrics = []
    return queue


def test_stops_after_consecutive_blocks_without_burning_attempts(setup, monkeypatch):
    calls = []

    def blocked(url, css):
        calls.append(url)
        raise BlockedError("desafio anti-bot: 'Just a moment...'")

    monkeypatch.setattr(worker.WebScraper, "fetch_html_once", staticmethod(blocked))

    with pytest.raises(QualityError, match="anti-bot"):
        worker.run_worker("w1")

    assert len(calls) == worker.MAX_CONSECUTIVE_BLOCKS  # parou, não varreu a fila
    assert len(setup.released) == worker.MAX_CONSECUTIVE_BLOCKS
    assert setup.failed == []  # bloqueio não conta como tentativa do link
    assert len(setup.pending) == 10 - worker.MAX_CONSECUTIVE_BLOCKS


def test_a_success_resets_the_block_counter(setup, monkeypatch):
    outcomes = iter([BlockedError("b"), BlockedError("b"), "<html/>"] * 2 + ["<html/>"] * 4)

    def fetch(url, css):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(worker.WebScraper, "fetch_html_once", staticmethod(fetch))
    monkeypatch.setattr(worker, "ad_id_from_url", lambda url: "1")

    stats = worker.run_worker("w1")

    assert stats["ok"] == 6 and stats["blocked"] == 4  # nunca 3 seguidos
    assert setup.pending == []
