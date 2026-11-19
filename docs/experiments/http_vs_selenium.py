"""Experimento D3: HTTP simples vs Selenium (ver docs/ARCHITECTURE.md).

Uso: PYTHONPATH=. MONGO_URI=... python docs/experiments/http_vs_selenium.py
Requer a coleção links_imoveis populada e `pip install httpx requests`.
"""
import os
import statistics
import time

import httpx
import requests
from pymongo import MongoClient

from scripts.etl.extraction.parsers import parse_listing_links, parse_property
from scripts.etl.extraction.scraper import WebScraper

LISTING = "https://www.zapimoveis.com.br/aluguel/casas/mg+uberlandia/"
PAUSE = 2

client = MongoClient(os.environ["MONGO_URI"])
links = [d["link"] for d in client["real_state"]["links_imoveis"].find({}, {"link": 1}).limit(5)]
URLS = [("listagem", LISTING)] + [("anuncio", u) for u in links]


def is_valid(kind: str, html: str) -> bool:
    try:
        if kind == "listagem":
            return len(parse_listing_links(html)) > 0
        return bool(parse_property(html)["preco"])
    except Exception:
        return False


def run(name: str, fetch) -> None:
    results = []
    for kind, url in URLS:
        start = time.time()
        try:
            status, html = fetch(url)
        except Exception as error:
            status, html = f"ERR {type(error).__name__}", ""
        results.append((status, is_valid(kind, html), time.time() - start))
        time.sleep(PAUSE)

    ok = sum(r[1] for r in results)
    statuses = sorted({str(r[0]) for r in results})
    latency = statistics.mean(r[2] for r in results)
    print(
        f"{name}: sucesso {ok}/{len(results)} | status {statuses} | "
        f"latência média {latency:.2f}s"
    )


def fetch_requests(url: str):
    response = requests.get(url, timeout=20)
    return response.status_code, response.text


def fetch_httpx(url: str):
    with httpx.Client(http2=False, timeout=20, follow_redirects=True) as http:
        response = http.get(url)
        return response.status_code, response.text


def fetch_selenium(url: str):
    ready = '[data-testid="location-address"]' if "/imovel/" in url else (
        'script[type="application/ld+json"]'
    )
    return 200, WebScraper.fetch_html_once(url, ready)


if __name__ == "__main__":
    run("requests", fetch_requests)
    run("httpx   ", fetch_httpx)
    run("selenium", fetch_selenium)
