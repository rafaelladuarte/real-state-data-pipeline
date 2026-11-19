from pathlib import Path

import pytest

from scripts.etl import quality
from scripts.etl.extraction import parse_property as parse_module
from scripts.etl.quality import (
    QualityError, check_error_rate, check_quality, raise_if_violated,
)

DETAIL_HTML = (Path(__file__).parent / "fixtures" / "detail.html").read_text(encoding="utf-8")


def good_doc():
    return {
        "titulo_anuncio": "t", "preco": "R$ 1", "endereco": "e", "area": "50 m²",
        "imobiliaria_url": "u", "data_anuncio": "d", "quartos": "2 quartos",
        "banheiro": "1 banheiro", "descricao": "x",
    }


def test_healthy_batch_passes():
    report = check_quality([good_doc() for _ in range(20)])
    assert report.ok and report.null_rates["preco"] == 0


def test_critical_field_empty_is_a_violation():
    docs = [good_doc() for _ in range(20)]
    for doc in docs[:3]:  # 15% > 5%
        doc["preco"] = None
    report = check_quality(docs)
    assert not report.ok
    assert "preco" in report.violations[0]
    with pytest.raises(QualityError):
        raise_if_violated(report, "x")


def test_important_field_tolerates_some_nulls_but_not_too_many():
    docs = [good_doc() for _ in range(20)]
    for doc in docs[:4]:  # 20% <= 30%
        doc["quartos"] = None
    assert check_quality(docs).ok
    for doc in docs[:8]:  # 40% > 30%
        doc["quartos"] = None
    assert not check_quality(docs).ok


def test_high_error_rate_is_a_violation():
    report = check_quality([good_doc() for _ in range(10)], errors=5)  # 33%
    assert any("erros" in v for v in report.violations)


def test_small_sample_is_not_judged():
    broken = [{"preco": None}] * 3
    assert check_quality(broken).ok
    assert check_error_rate(ok=0, errors=5).ok


def test_error_rate_only_check():
    assert not check_error_rate(ok=3, errors=17).ok
    assert check_error_rate(ok=18, errors=2).ok


# ---- parse_property: nada é gravado quando a qualidade falha ----

class FakeMongo:
    store: dict = {}

    def __init__(self, uri):
        pass

    def get_documents(self, query, collection):
        return list(self.store.get(collection, []))

    def insert_documents(self, documents, collection):
        self.store.setdefault(collection + "_inserted", []).extend(documents)

    def update_documents(self, query, set, collection):
        self.store.setdefault(collection + "_updated", []).append(set)

    def delete_documents(self, query, collection):
        return 0


class FakeObjectStore:
    html = DETAIL_HTML

    def get_html(self, key):
        return self.html


@pytest.fixture
def parse_env(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://fake")
    monkeypatch.setattr(parse_module, "MongoDB", FakeMongo)
    monkeypatch.setattr(parse_module, "ObjectStore", FakeObjectStore)
    FakeMongo.store = {"links_imoveis": [
        {"_id": i, "link": f"https://www.zapimoveis.com.br/imovel/x-id-{1000 + i}/",
         "html_key": f"anuncio/2026-11-19/{1000 + i}.html.gz", "tipo": "casas", "modo": "aluguel"}
        for i in range(12)
    ]}
    return FakeMongo.store


def test_parse_persists_when_quality_is_ok(parse_env):
    parse_module.parse_stored_property()

    assert len(parse_env["raw_imoveis_inserted"]) == 12
    assert parse_env["raw_imoveis_inserted"][0]["anuncio_id"] == "1000"
    assert parse_env["links_imoveis_updated"]
    assert parse_env["run_metrics_inserted"][0]["ok"] is True


def test_parse_with_broken_parser_writes_nothing_and_fails(parse_env, monkeypatch):
    # Simula mudança do site: o HTML não tem mais os campos esperados
    monkeypatch.setattr(FakeObjectStore, "html", "<html><body>layout novo</body></html>")

    with pytest.raises(QualityError):
        parse_module.parse_stored_property()

    assert "raw_imoveis_inserted" not in parse_env
    assert "links_imoveis_updated" not in parse_env
    metrics = parse_env["run_metrics_inserted"][0]
    assert metrics["ok"] is False and metrics["errors"] == 12
    assert quality.MAX_ERROR_RATE < metrics["error_rate"]
