"""Baixa a Malha de Bairros do Censo 2022 (IBGE) de Minas Gerais.

Uso: python -m scripts.geo.baixar_bairros DESTINO
Fonte: IBGE, Malha de Bairros (Censo Demográfico) 2022. É um dado estático, baixado uma vez.
"""
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from scripts.utility.log import get_logger

logger = get_logger(__name__)

URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/bairros/shp/UF/"
    "MG_bairros_CD2022.zip"
)
NOME = "MG_bairros_CD2022"
EXTENSOES = (".shp", ".dbf", ".prj", ".cpg")


def baixar(destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    zip_path = destino / f"{NOME}.zip"
    logger.info("Baixando %s", URL)
    with urlopen(Request(URL, headers={"User-Agent": "real-state-pipeline/geo"}), timeout=120) as r:
        zip_path.write_bytes(r.read())
    with zipfile.ZipFile(zip_path) as z:
        # Extrai só os arquivos esperados, com nome fixo (nunca o caminho de dentro do zip)
        for ext in EXTENSOES:
            z.extract(f"{NOME}{ext}", destino)
    logger.info("Arquivos em %s", destino)
    return destino / f"{NOME}.shp"


if __name__ == "__main__":
    baixar(Path(sys.argv[1]))
