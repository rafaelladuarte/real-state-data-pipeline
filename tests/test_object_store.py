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

    def bucket_exists(self, bucket):
        return bucket in self.buckets

    def make_bucket(self, bucket):
        self.buckets.add(bucket)

    def put_object(self, bucket, key, data, length, content_type=None):
        self.objects[(bucket, key)] = data.read()

    def get_object(self, bucket, key):
        return FakeResponse(self.objects[(bucket, key)])


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
