"""Experimento D2: escala da coleta com 1, 2 e 4 workers (ver docs/ARCHITECTURE.md).

Copia links de `links_imoveis` para `bench_links` e coleta o HTML de cada grupo
com N workers (processos) compartilhando fila e limite global de requisições.

Uso: PYTHONPATH=. MONGO_URI=... python docs/experiments/parallel_scaling.py [itens_por_rodada]
Requer o storage S3 e o Mongo no ar. Faz requisições reais ao site.
"""
from pymongo import MongoClient

import os
import subprocess
import sys
import time

ITEMS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
INTERVAL = os.getenv("MIN_INTERVAL_SECONDS", "1.25")
db = MongoClient(os.environ["MONGO_URI"])["real_state"]

source = list(db.links_imoveis.find({"error": {"$exists": False}}, {"link": 1, "tipo": 1, "modo": 1}))
needed = ITEMS * 3
assert len(source) >= needed, f"precisa de {needed} links, há {len(source)}"
rows = []

for round_no, workers in enumerate((1, 2, 4)):
    chunk = source[round_no * ITEMS:(round_no + 1) * ITEMS]
    db.bench_links.drop()
    db.rate_limit.drop()
    db.bench_links.insert_many([{k: v for k, v in d.items() if k != "_id"} for d in chunk])

    env = {**os.environ, "LINKS_COLLECTION": "bench_links"}
    start = time.monotonic()
    procs = [
        subprocess.Popen(
            [sys.executable, "scripts/etl/extraction/property.py"],
            env={**env, "WORKER_ID": f"w{i}"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for i in range(workers)
    ]
    for p in procs:
        p.wait()
    elapsed = time.monotonic() - start

    ok = db.bench_links.count_documents({"html_key": {"$exists": True}})
    failed = db.bench_links.count_documents({"error": {"$exists": True}})
    distinct_keys = len(db.bench_links.distinct("html_key"))
    rows.append((workers, ok, failed, distinct_keys, elapsed, ok / elapsed))
    print(f"{workers} worker(s): {ok} ok, {failed} erro, {distinct_keys} chaves distintas, "
          f"{elapsed:.1f}s, {ok / elapsed:.2f} anúncios/s", flush=True)

db.bench_links.drop()
db.rate_limit.drop()
print(f"\nintervalo mínimo global: {INTERVAL}s (teto ≈ {1 / float(INTERVAL):.2f} anúncios/s)")
print("| workers | ok | erros | tempo (s) | anúncios/s |\n|---|---|---|---|---|")
for w, ok, failed, _, el, rate in rows:
    print(f"| {w} | {ok} | {failed} | {el:.1f} | {rate:.2f} |")
