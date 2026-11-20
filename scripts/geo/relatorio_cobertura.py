"""Relatório de cobertura: quantos anúncios caem em um bairro com polígono no mapa.

Uso:
  POSTGRESQL_URI=postgresql://user:senha@localhost:5434/real_state \
    python -m scripts.geo.relatorio_cobertura [GEOJSON]
  python -m scripts.geo.relatorio_cobertura [GEOJSON] --arquivo bairros.txt   # linhas "bairro|qtd"

Meta (docs/spec/mapa-por-bairro.md): pelo menos 90% dos anúncios com polígono.
"""
import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from scripts.geo.nomes import normalizar

GEOJSON_PADRAO = Path("app/web/public/bairros-uberlandia.geojson")
META = 0.90

CONSULTA = """
    SELECT e.bairro, COUNT(*)::int FROM imovel i
    JOIN endereco e ON e.id_endereco = i.id_endereco_imovel
    GROUP BY e.bairro ORDER BY 2 DESC
"""


@dataclass
class Cobertura:
    total: int
    cobertos: int
    sem_poligono: list[tuple[str, int]] = field(default_factory=list)
    poligonos_sem_anuncio: list[str] = field(default_factory=list)

    @property
    def taxa(self) -> float:
        return self.cobertos / self.total if self.total else 0.0


def calcular(bairros: list[tuple[str | None, int]], geojson: dict) -> Cobertura:
    """`bairros`: (nome no anúncio, nº de anúncios). Casa pelas chaves do GeoJSON."""
    por_chave = {}
    for f in geojson["features"]:
        for chave in f["properties"]["chaves"]:
            por_chave[chave] = f["properties"]["bairro"]
    usados, sem, cobertos = set(), [], 0
    for nome, qtd in bairros:
        oficial = por_chave.get(normalizar(nome))
        if oficial:
            cobertos += qtd
            usados.add(oficial)
        else:
            sem.append((nome or "(sem bairro)", qtd))
    oficiais = {f["properties"]["bairro"] for f in geojson["features"]}
    return Cobertura(
        total=sum(q for _, q in bairros),
        cobertos=cobertos,
        sem_poligono=sorted(sem, key=lambda x: -x[1]),
        poligonos_sem_anuncio=sorted(oficiais - usados),
    )


def carregar_do_banco(uri: str) -> list[tuple[str | None, int]]:
    import psycopg2  # dependência do projeto; só é necessária ao consultar o banco

    with psycopg2.connect(uri.replace("postgresql+psycopg2://", "postgresql://")) as con:
        with con.cursor() as cur:
            cur.execute(CONSULTA)
            return [(b, q) for b, q in cur.fetchall()]


def carregar_do_arquivo(caminho: str) -> list[tuple[str | None, int]]:
    linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
    return [(b.strip(), int(q)) for b, q in (x.rsplit("|", 1) for x in linhas if "|" in x)]


def imprimir(c: Cobertura) -> None:
    pct, meta = 100 * c.taxa, 100 * META
    print(f"Anúncios: {c.total} | com polígono: {c.cobertos} ({pct:.1f}%) | meta {meta:.0f}%")
    print(f"\nBairros do banco sem polígono ({len(c.sem_poligono)}):")
    for nome, qtd in c.sem_poligono:
        print(f"  {qtd:4}  {nome}")
    print(f"\nPolígonos sem nenhum anúncio ({len(c.poligonos_sem_anuncio)}):")
    print("  " + ", ".join(c.poligonos_sem_anuncio))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("geojson", nargs="?", default=str(GEOJSON_PADRAO))
    ap.add_argument("--arquivo")
    args = ap.parse_args()
    geo = json.loads(Path(args.geojson).read_text(encoding="utf-8"))
    if args.arquivo:
        dados = carregar_do_arquivo(args.arquivo)
    else:
        uri = os.getenv("POSTGRESQL_URI")
        if not uri:
            sys.exit("Defina POSTGRESQL_URI ou use --arquivo")
        dados = carregar_do_banco(uri)
    cob = calcular(dados, geo)
    imprimir(cob)
    sys.exit(0 if cob.taxa >= META else 1)
