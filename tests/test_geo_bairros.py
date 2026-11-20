"""Testes do preparo do mapa de bairros: nomes, geometria, shapefile e cobertura."""
import json
from pathlib import Path

import pytest

from scripts.geo.geometria import simplificar_anel, simplificar_linha
from scripts.geo.nomes import chaves_do_bairro, normalizar, resolver
from scripts.geo.relatorio_cobertura import calcular
from scripts.geo.shapefile import area_assinada

GEOJSON = Path("app/web/public/bairros-uberlandia.geojson")


@pytest.mark.parametrize("entrada,esperado", [
    ("Santa Mônica", "santa monica"),
    ("Sta. Mônica", "santa monica"),
    ("Bairro Santa Mônica", "santa monica"),
    ("  JARDIM   das Palmeiras ", "jardim das palmeiras"),
    ("Jd. Karaíba", "jardim karaiba"),
    ("Te-Vis - Jardim das Palmeiras", "te vis jardim das palmeiras"),
    ("", ""),
    (None, ""),
])
def test_normalizar(entrada, esperado):
    assert normalizar(entrada) == esperado


def test_chaves_incluem_apelidos_do_bairro():
    apelidos = {"Gávea Sul": "Gávea", "Mansour III": "Mansour"}
    assert chaves_do_bairro("Gávea", apelidos) == ["gavea", "gavea sul"]
    assert chaves_do_bairro("Centro", apelidos) == ["centro"]


def test_resolver_devolve_none_sem_par():
    assert resolver("Sta Mônica", {"santa monica": "santa monica"}) == "santa monica"
    assert resolver("Lugar Inexistente", {"santa monica": "santa monica"}) is None


def test_area_assinada_distingue_sentido():
    horario = [(0, 0), (0, 1), (1, 1), (1, 0)]
    assert area_assinada(horario) < 0
    assert area_assinada(horario[::-1]) > 0


def test_simplificar_linha_remove_ponto_colinear_e_mantem_desvio():
    assert simplificar_linha([(0, 0), (1, 0.0001), (2, 0)], 0.001) == [(0, 0), (2, 0)]
    assert len(simplificar_linha([(0, 0), (1, 1), (2, 0)], 0.001)) == 3


def test_simplificar_anel_mantem_fechado_e_descarta_degenerado():
    quadrado = [(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]
    anel = simplificar_anel(quadrado, 0.0001)
    assert anel[0] == anel[-1] and len(anel) >= 4
    assert simplificar_anel([(0, 0), (1, 0), (0, 0), (0, 0)], 5) is None


def _geo(*bairros):
    return {"features": [
        {"properties": {"bairro": nome, "chaves": chaves}} for nome, chaves in bairros
    ]}


def test_calcular_cobertura():
    geo = _geo(("Gávea", ["gavea", "gavea sul"]), ("Centro", ["centro"]), ("Tibery", ["tibery"]))
    c = calcular([("Gávea Sul", 3), ("Centro", 5), ("Loteamento X", 2), (None, 1)], geo)
    assert (c.total, c.cobertos) == (11, 8)
    assert c.taxa == pytest.approx(8 / 11)
    assert c.sem_poligono == [("Loteamento X", 2), ("(sem bairro)", 1)]
    assert c.poligonos_sem_anuncio == ["Tibery"]


@pytest.mark.skipif(not GEOJSON.exists(), reason="GeoJSON de bairros não gerado")
def test_geojson_versionado_e_valido():
    geo = json.loads(GEOJSON.read_text(encoding="utf-8"))
    feats = geo["features"]
    assert len(feats) >= 70
    assert GEOJSON.stat().st_size < 1_000_000
    chaves = [c for f in feats for c in f["properties"]["chaves"]]
    assert len(chaves) == len(set(chaves)), "chave repetida entre bairros"
    for f in feats:
        for poligono in f["geometry"]["coordinates"]:
            for anel in poligono:
                assert anel[0] == anel[-1] and len(anel) >= 4
                for lon, lat in anel:
                    assert -49 < lon < -48 and -19.5 < lat < -18.5  # Uberlândia
