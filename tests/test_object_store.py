from datetime import date

import pytest

from scripts.infra.storage.object_store import (
    ObjectStore, ad_id_from_url, html_key,
)


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data

    def close(self):
        pass

    def release_conn(self):
        pass


class FakeMinio:
    def __init__(self):
        self.buckets, self.objects = set(), {}
        self.fail_on = set()

    def bucket_exists(self, bucket):
        return bucket in self.buckets

    def make_bucket(self, bucket):
        self.buckets.add(bucket)

    def put_object(self, bucket, key, data, length, content_type=None):
        self.objects[(bucket, key)] = data.read()

    def get_object(self, bucket, key):
        return FakeResponse(self.objects[(bucket, key)])

    def remove_object(self, bucket, key):
        self.objects.pop((bucket, key), None)  # como o S3: apagar o que não existe não falha

    def remove_objects(self, bucket, delete_list):
        # preguiçoso, como o cliente real: só apaga quando o resultado é consumido
        for item in delete_list:
            if (bucket, item.name) in self.fail_on:
                yield f"erro em {item.name}"
            else:
                self.objects.pop((bucket, item.name), None)


def test_ad_id_from_url():
    url = "https://www.zapimoveis.com.br/imovel/aluguel-casa-225m2-id-2915612050/"
    assert ad_id_from_url(url) == "2915612050"
    with pytest.raises(ValueError):
        ad_id_from_url("https://www.zapimoveis.com.br/aluguel/casas/")


def test_html_key():
    assert html_key("anuncio", "123", date(2026, 11, 19)) == "anuncio/2026-11-19/123.html.gz"


def test_roundtrip_compresses_and_creates_bucket():
    client = FakeMinio()
    store = ObjectStore(client=client, bucket="b")
    html = "<html>Uberlândia — açaí</html>" * 100
    store.put_html("anuncio/x.html.gz", html)

    assert "b" in client.buckets
    assert len(client.objects[("b", "anuncio/x.html.gz")]) < len(html.encode())
    assert store.get_html("anuncio/x.html.gz") == html


def _store_with(*names):
    client = FakeMinio()
    store = ObjectStore(client=client, bucket="b")
    for name in names:
        store.put_html(name, "<html/>")
    return store, client


def test_delete_removes_one_object_and_ignores_missing():
    store, client = _store_with("a", "b")
    store.delete("a")
    store.delete("nunca-existiu")
    assert set(k for _, k in client.objects) == {"b"}


def test_delete_many_removes_all_and_reports_the_count():
    store, client = _store_with("a", "b", "c")
    assert store.delete_many(["a", "c"]) == 2
    assert set(k for _, k in client.objects) == {"b"}
    assert store.delete_many([]) == 0


def test_delete_many_raises_when_an_object_fails():
    store, client = _store_with("a", "b")
    client.fail_on.add(("b", "b"))
    with pytest.raises(RuntimeError, match="1 de 2"):
        store.delete_many(["a", "b"])
