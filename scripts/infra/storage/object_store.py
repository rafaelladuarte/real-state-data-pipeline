"""Camada bruta (bronze): HTML guardado comprimido em object storage S3-compatível
(RustFS no docker-compose; o cliente é o `minio`, que fala o protocolo S3).

Chave: <tipo>/<AAAA-MM-DD>/<id>.html.gz  (tipo: "anuncio" ou "listagem").
Permite reprocessar o parsing sem acessar o site de novo.
"""
from datetime import date

import gzip
import io
import os
import re

DEFAULT_BUCKET = "real-state-html"


def ad_id_from_url(url: str) -> str:
    """Id do anúncio no final da URL (…-id-2915612050/)."""
    match = re.search(r"id-(\d+)", url)
    if not match:
        raise ValueError(f"id do anúncio não encontrado em {url}")
    return match.group(1)


def html_key(kind: str, name: str, when: date | None = None) -> str:
    when = when or date.today()
    return f"{kind}/{when.isoformat()}/{name}.html.gz"


class ObjectStore:
    def __init__(self, client=None, bucket: str | None = None):
        self._client = client or self._default_client()
        self._bucket = bucket or os.getenv("S3_BUCKET", DEFAULT_BUCKET)
        self._ensured = False

    @staticmethod
    def _default_client():
        from minio import Minio

        return Minio(
            os.getenv("S3_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("S3_ACCESS_KEY", "username"),
            secret_key=os.getenv("S3_SECRET_KEY", "password"),
            secure=os.getenv("S3_SECURE", "false").lower() == "true",
        )

    def _ensure_bucket(self) -> None:
        if not self._ensured:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
            self._ensured = True

    def put_html(self, key: str, html: str) -> None:
        self._ensure_bucket()
        data = gzip.compress(html.encode("utf-8"))
        self._client.put_object(
            self._bucket, key, io.BytesIO(data), len(data),
            content_type="application/gzip",
        )

    def get_html(self, key: str) -> str:
        response = self._client.get_object(self._bucket, key)
        try:
            return gzip.decompress(response.read()).decode("utf-8")
        finally:
            response.close()
            response.release_conn()
