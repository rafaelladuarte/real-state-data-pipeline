"""Experimento D3: HTTP simples vs Selenium (ver docs/ARCHITECTURE.md).

Uso: PYTHONPATH=. MONGO_URI=... python docs/experiments/http_vs_selenium.py
Requer a coleção links_imoveis populada e `pip install httpx requests`.
"""
import time, statistics, httpx, requests
from pymongo import MongoClient
from scripts.etl.extraction.parsers import parse_property, parse_listing_links
from scripts.etl.extraction.scraper import WebScraper
import os

links = [d["link"] for d in MongoClient(os.environ["MONGO_URI"])["real_state"]["links_imoveis"].find({}, {"link": 1}).limit(5)]
listing = "https://www.zapimoveis.com.br/aluguel/casas/mg+uberlandia/"
urls = [("listagem", listing)] + [("anuncio", u) for u in links]

def ok_detail(html): 
    try: return bool(parse_property(html)["preco"])
    except Exception: return False
def ok_listing(html): return len(parse_listing_links(html)) > 0

def run(name, fetch):
    res = []
    for kind, u in urls:
        t = time.time()
        try: status, html = fetch(u)
        except Exception as e: status, html = f"ERR {type(e).__name__}", ""
        dt = time.time() - t
        good = ok_listing(html) if kind == "listagem" else ok_detail(html)
        res.append((kind, status, good, dt)); time.sleep(2)
    n = len(res); print(f"{name}: sucesso {sum(r[2] for r in res)}/{n} | status {sorted(set(str(r[1]) for r in res))} | latência média {statistics.mean(r[3] for r in res):.2f}s")

def f_requests(u):
    r = requests.get(u, timeout=20); return r.status_code, r.text
def f_httpx(u):
    with httpx.Client(http2=False, timeout=20, follow_redirects=True) as c:
        r = c.get(u); return r.status_code, r.text
def f_selenium(u):
    css = 'script[type="application/ld+json"]' if "imovel" not in u else '[data-testid="location-address"]'
    return 200, WebScraper.fetch_html_once(u, css)

run("requests", f_requests)
run("httpx   ", f_httpx)
run("selenium", f_selenium)
