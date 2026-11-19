from scripts.utility.log import get_logger
import requests
import os


logger = get_logger(__name__)


def download_image(url: str, filename: str) -> tuple[str | None, str | None]:
    response = requests.get(url)
    if response.status_code == 200:
        with open(filename, 'wb') as f:
            f.write(response.content)
        return os.path.abspath(filename), filename
    else:
        return None, None


def delete_image(filepath: str):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
        #     print(f"Imagem {filepath} apagada com sucesso.")
        # else:
        #     print(f"O arquivo {filepath} não foi encontrado.")
    except Exception as e:
        logger.error(f"Ocorreu um erro ao tentar apagar a imagem: {e}")
