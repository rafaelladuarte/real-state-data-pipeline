"""Aplica a modelagem no Postgres a partir das tabelas de staging (_treat_*).

Executa, em UMA transação, todos os arquivos SQL de scripts/etl/modeling na
ordem correta. Todos são idempotentes (IF NOT EXISTS, OR REPLACE, upsert), então
reexecutar não duplica dados; se algo falhar, nada é aplicado.

Carga incremental: o staging contém só os lotes pendentes (veja staging.py). Na
mesma transação, ao final, os lotes aplicados são registrados em `lote_carga` e
o staging é esvaziado; se algo falhar, o staging e o registro ficam como estavam.
"""
from scripts.etl.load.staging import (
    ensure_batch_column, ensure_control_table, record_loaded_and_clear,
    take_load_lock,
)
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


ORPHANS_SQL = """
SELECT COUNT(*) FROM public._treat_imoveis A
LEFT JOIN public.imobiliaria B ON A.id_imobiliaria = B.id_imobiliaria
WHERE B.id_imobiliaria IS NULL
"""


def _warn_orphans(cursor) -> None:
    """Imóveis de imobiliárias não coletadas ficam fora da tabela fato (INNER JOIN)."""
    cursor.execute(ORPHANS_SQL)
    orphans = cursor.fetchone()[0]
    if orphans:
        logger.warning(
            f"{orphans} imóveis ficaram fora da tabela fato: "
            "imobiliária ainda não coletada"
        )


def build_model(uri: str | None = None) -> None:
    logger.info("---------------- MODEL DATA IN POSTGRES ----------------")
    engine = create_engine(uri or get_secret_value("POSTGRESQL_URI"))

    # Conexão crua: o script é enviado inteiro, sem interpretação de parâmetros
    connection = engine.raw_connection()
    try:
        cursor = connection.cursor()
        take_load_lock(cursor)
        ensure_control_table(cursor)
        ensure_batch_column(cursor)
        for name in SQL_FILES:
            logger.info(f"Executando {name}")
            cursor.execute((MODELING_DIR / name).read_text(encoding="utf-8"))
            if name == "insert_tables_oficial.sql":
                _warn_orphans(cursor)
        ensure_batch_column(cursor)  # staging criado pelos próprios SQL acima
        batches = record_loaded_and_clear(cursor)
        connection.commit()
        logger.info(
            f"Modelagem aplicada; lotes carregados: {sorted(batches) or 'nenhum'}"
        )
    except Exception:
        connection.rollback()
        logger.error("Falha na modelagem; transação revertida")
        raise
    finally:
        connection.close()
        engine.dispose()


if __name__ == '__main__':
    build_model()
