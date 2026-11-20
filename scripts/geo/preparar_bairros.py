"""Gera o GeoJSON de bairros de Uberlândia usado pelo mapa do app.

Uso: python -m scripts.geo.preparar_bairros PASTA_DO_SHAPEFILE [SAIDA.geojson]

Filtra Uberlândia, simplifica a geometria e grava em cada feature:
  bairro  nome oficial (IBGE)
  codigo  CD_BAIRRO do IBGE
  chaves  nome normalizado do bairro + apelidos (apelidos_bairros.json)
O app casa o bairro do anúncio com `chaves`; a API não precisa conhecer apelidos.
Os anéis seguem o sentido do shapefile (externo horário), que é o que o d3-geo espera.
"""
import json
import sys
from pathlib import Path

from scripts.geo.baixar_bairros import NOME
from scripts.geo.geometria import simplificar_anel
from scripts.geo.nomes import chaves_do_bairro
from scripts.geo.shapefile import ler_dbf, ler_shp
from scripts.utility.log import get_logger

logger = get_logger(__name__)

COD_MUNICIPIO = "3170206"  # Uberlândia
TOLERANCIA_GRAUS = 0.00004  # ~4 m
CASAS = 5  # ~1 m
APELIDOS = Path(__file__).with_name("apelidos_bairros.json")
SAIDA_PADRAO = Path("app/web/public/bairros-uberlandia.geojson")


def _arredondar(anel):
    return [[round(x, CASAS), round(y, CASAS)] for x, y in anel]


def construir(pasta: Path) -> dict:
    apelidos = json.loads(APELIDOS.read_text(encoding="utf-8"))
    atributos = ler_dbf(str(pasta / f"{NOME}.dbf"))
    geometrias = ler_shp(str(pasta / f"{NOME}.shp"))
    if len(atributos) != len(geometrias):
        raise ValueError("shapefile e dbf com número de registros diferente")

    features = []
    for attr, poligonos in zip(atributos, geometrias, strict=True):
        if attr["CD_MUN"] != COD_MUNICIPIO or not poligonos:
            continue
        saida = []
        for poligono in poligonos:
            aneis = [simplificar_anel(a, TOLERANCIA_GRAUS) for a in poligono]
            if aneis[0] is None:
                continue  # o anel externo sumiu: descarta o polígono
            saida.append([_arredondar(a) for a in aneis if a is not None])
        if not saida:
            continue
        features.append({
            "type": "Feature",
            "properties": {
                "bairro": attr["NM_BAIRRO"],
                "codigo": attr["CD_BAIRRO"],
                "chaves": chaves_do_bairro(attr["NM_BAIRRO"], apelidos),
            },
            "geometry": {"type": "MultiPolygon", "coordinates": saida},
        })
    features.sort(key=lambda f: f["properties"]["codigo"])
    return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
    pasta = Path(sys.argv[1])
    saida = Path(sys.argv[2]) if len(sys.argv) > 2 else SAIDA_PADRAO
    colecao = construir(pasta)
    saida.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(colecao, ensure_ascii=False, separators=(",", ":"))
    saida.write_text(texto, encoding="utf-8")
    kb = saida.stat().st_size / 1024
    logger.info("%d bairros, %.0f KB em %s", len(colecao["features"]), kb, saida)
