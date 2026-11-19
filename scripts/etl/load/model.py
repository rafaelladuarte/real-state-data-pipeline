"""Aplica a modelagem no Postgres a partir das tabelas de staging (_treat_*).

Executa, em UMA transação, todos os arquivos SQL de scripts/etl/modeling na
ordem correta. Todos são idempotentes (IF NOT EXISTS, OR REPLACE, upsert), então
reexecutar não duplica dados; se algo falhar, nada é aplicado.
"""
from scripts.infra.security.secrets import get_secret_value
from scripts.utility.log import get_logger

from pathlib import Path

from sqlalchemy import create_engine


logger = get_logger(__name__)

MODELING_DIR = Path(__file__).resolve().parents[1] / "modeling"
SQL_FILES = [
    "create_tables_oficial.sql",
    "create_function_analysis.sql",
    "create_triggers_analysis.sql",
    "insert_tables_oficial.sql",
    "create_views_dash.sql",
]


def build_model(uri: str | None = None) -> None:
    logger.info("---------------- MODEL DATA IN POSTGRES ----------------")
    engine = create_engine(uri or get_secret_value("POSTGRESQL_URI"))

    # Conexão crua: o script é enviado inteiro, sem interpretação de parâmetros
    connection = engine.raw_connection()
    try:
        cursor = connection.cursor()
        for name in SQL_FILES:
            logger.info(f"Executando {name}")
            cursor.execute((MODELING_DIR / name).read_text(encoding="utf-8"))
        connection.commit()
        logger.info("Modelagem aplicada")
    except Exception:
        connection.rollback()
        logger.error("Falha na modelagem; transação revertida")
        raise
    finally:
        connection.close()
        engine.dispose()


if __name__ == '__main__':
    build_model()
