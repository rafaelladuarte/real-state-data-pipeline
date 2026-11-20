"""Leitor mínimo de shapefile de polígonos (.shp + .dbf), só com a biblioteca padrão.

Cobre o que a Malha de Bairros do IBGE usa: tipo Polygon (5), anéis externos em sentido
horário e furos em anti-horário. Evita depender de geopandas/GDAL para um preparo único.
"""
import struct

POLYGON = 5


def ler_dbf(caminho: str) -> list[dict[str, str]]:
    dados = open(caminho, "rb").read()
    n_registros, tam_cabecalho, tam_registro = struct.unpack("<xxxxIHH", dados[:12])
    campos, pos = [], 32
    while dados[pos] != 0x0D:
        campos.append((dados[pos:pos + 11].split(b"\0")[0].decode(), dados[pos + 16]))
        pos += 32
    linhas = []
    for i in range(n_registros):
        reg = dados[tam_cabecalho + i * tam_registro: tam_cabecalho + (i + 1) * tam_registro]
        off, linha = 1, {}
        for nome, tam in campos:
            linha[nome] = reg[off:off + tam].decode("utf-8", "replace").strip()
            off += tam
        linhas.append(linha)
    return linhas


def area_assinada(anel: list[tuple[float, float]]) -> float:
    """Fórmula do cadarço: negativa no sentido horário."""
    pares = zip(anel, anel[1:] + anel[:1], strict=True)
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in pares) / 2


def ler_shp(caminho: str) -> list[list[list[list[tuple[float, float]]]]]:
    """Uma entrada por registro; cada uma é uma lista de polígonos [anel_externo, *furos]."""
    dados = open(caminho, "rb").read()
    registros, pos = [], 100
    while pos < len(dados):
        tam = struct.unpack(">I", dados[pos + 4:pos + 8])[0] * 2
        corpo = dados[pos + 8:pos + 8 + tam]
        pos += 8 + tam
        tipo = struct.unpack("<i", corpo[:4])[0]
        if tipo == 0:
            registros.append([])
            continue
        if tipo != POLYGON:
            raise ValueError(f"tipo de geometria {tipo} não suportado (esperado polígono)")
        n_partes, n_pontos = struct.unpack("<ii", corpo[36:44])
        inicios = list(struct.unpack(f"<{n_partes}i", corpo[44:44 + 4 * n_partes]))
        off = 44 + 4 * n_partes
        pontos = [
            struct.unpack("<dd", corpo[off + 16 * i: off + 16 * (i + 1)]) for i in range(n_pontos)
        ]
        fins = inicios[1:] + [n_pontos]
        aneis = [pontos[a:b] for a, b in zip(inicios, fins, strict=True)]
        poligonos: list[list[list[tuple[float, float]]]] = []
        for anel in aneis:
            if area_assinada(anel) <= 0 or not poligonos:  # horário = externo
                poligonos.append([anel])
            else:
                poligonos[-1].append(anel)  # furo do último externo
        registros.append(poligonos)
    return registros
