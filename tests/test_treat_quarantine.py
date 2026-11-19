"""Tratamento: erros não viram 'treat', contam tentativas e vão para quarentena."""
import pytest

import scripts.etl.treatment.property as treat_module
from scripts.etl.quality import QualityError


class FakeMongo:
    def __init__(self, uri):
        self.docs = FakeMongo.docs
        self.updates = []
        self.inserted = []

    def create_hash_index(self, *a):
        pass

    def distinct_values(self, field, collection):
        return []

    def get_documents(self, query, collection, limit=0):
        out = [
            d for d in self.docs
            if "treat" not in d
            and d["_id"] not in query["_id"]["$nin"]
            and d.get("treat_attempts", 0) < treat_module.MAX_TREAT_ATTEMPTS
        ]
        return out[:limit] if limit else out

    def insert_hash_documents(self, documents, collection):
        self.inserted.append((collection, documents))

    def insert_documents(self, documents, collection):
        self.inserted.append((collection, documents))

    def update_documents(self, query, set, collection):
        self.updates.append((query, set))


def _bad(i, attempts=0):
    doc = {"_id": i, "data_anuncio": "x"}  # faltam campos -> KeyError
    if attempts:
        doc["treat_attempts"] = attempts
    return doc


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://fake")
    monkeypatch.setattr(treat_module, "MongoDB", FakeMongo)
    created = []
    monkeypatch.setattr(
        treat_module, "MongoDB", lambda uri: created.append(FakeMongo(uri)) or created[-1]
    )
    return created


def test_errors_are_counted_not_marked_treated(env):
    FakeMongo.docs = [_bad(i) for i in range(3)]
    treat_module.treat_property()  # amostra < MIN_SAMPLE: gate não falha

    updates = env[0].updates
    sets = [s for _, s in updates]
    assert all("treat" not in s.get("$set", {}) for s in sets)
    assert any(s.get("$inc") == {"treat_attempts": 1} for s in sets)
    assert not any(s.get("$set", {}).get("scraper") for s in sets)


def test_failures_reach_quality_gate(env):
    FakeMongo.docs = [_bad(i) for i in range(12)]
    with pytest.raises(QualityError):
        treat_module.treat_property()


def test_quarantine_on_last_attempt(env):
    FakeMongo.docs = [_bad(1, attempts=treat_module.MAX_TREAT_ATTEMPTS - 1)]
    treat_module.treat_property()

    assert any(
        s.get("$set", {}).get("treat_quarantine") for _, s in env[0].updates
    )
