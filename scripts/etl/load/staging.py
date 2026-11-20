"""Controle da carga incremental no Postgres.

O staging (`_treat_*`, `_snapshots_imoveis`) guarda só os lotes pendentes: o
`migrate.py` o preenche e o `model.py` o consome e o esvazia. A tabela
`lote_carga` registra os lotes já carregados (na mesma transação do model.py,
então "carregado" e "aplicado" nunca divergem) e é o que o `migrate.py` e a
limpeza do HTML consultam para saber o que falta.

Concorrência: migrate e model pegam o mesmo advisory lock de transação, então
nunca mexem no staging ao mesmo tempo; lotes diferentes entram em fila.
"""
from scripts.etl.batch import LEGACY_BATCH

# (tabela de staging, coleção do Mongo de origem)
STAGING_TABLES = (
    ("_treat_imoveis", "treat_imoveis"),
    ("_treat_imobiliarias", "treat_imobiliarias"),
    ("_snapshots_imoveis", "snapshots_imoveis"),
)

# Número arbitrário, igual para migrate e model
LOAD_LOCK_KEY = 726_041_120

CONTROL_DDL = """
CREATE TABLE IF NOT EXISTS public.lote_carga (
    batch_id TEXT PRIMARY KEY,
    carregado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    imoveis INTEGER NOT NULL DEFAULT 0,
    imobiliarias INTEGER NOT NULL DEFAULT 0,
    snapshots INTEGER NOT NULL DEFAULT 0
)
"""

_COUNT_COLUMN = {
    "_treat_imoveis": "imoveis",
    "_treat_imobiliarias": "imobiliarias",
    "_snapshots_imoveis": "snapshots",
}


def take_load_lock(cursor) -> None:
    cursor.execute("SELECT pg_advisory_xact_lock(%s)", (LOAD_LOCK_KEY,))


def ensure_control_table(cursor) -> None:
    cursor.execute(CONTROL_DDL)


def table_exists(cursor, table: str) -> bool:
    cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{table}",))
    return cursor.fetchone()[0]


def ensure_batch_column(cursor) -> None:
    """Staging criado antes da carga incremental não tem a coluna batch_id."""
    for table, _ in STAGING_TABLES:
        if table_exists(cursor, table):
            cursor.execute(
                f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS batch_id TEXT"
            )


def loaded_batches(cursor) -> list[str]:
    cursor.execute("SELECT batch_id FROM public.lote_carga")
    return [row[0] for row in cursor.fetchall()]


def staged_row_count(cursor, table: str) -> int:
    if not table_exists(cursor, table):
        return 0
    cursor.execute(f"SELECT count(*) FROM public.{table}")
    return cursor.fetchone()[0]


def record_loaded_and_clear(cursor) -> dict[str, dict[str, int]]:
    """Registra os lotes do staging em lote_carga e esvazia o staging.

    Roda dentro da transação do model.py: se algo falhar antes do commit,
    nada é registrado e o staging continua intacto para a próxima tentativa.
    """
    batches: dict[str, dict[str, int]] = {}
    for table, _ in STAGING_TABLES:
        if not table_exists(cursor, table):
            continue
        cursor.execute(
            f"SELECT COALESCE(batch_id, %s), count(*) FROM public.{table} GROUP BY 1",
            (LEGACY_BATCH,),
        )
        for batch_id, count in cursor.fetchall():
            batches.setdefault(batch_id, {})[_COUNT_COLUMN[table]] = count

    for batch_id, counts in batches.items():
        cursor.execute(
            """
            INSERT INTO public.lote_carga (batch_id, imoveis, imobiliarias, snapshots)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (batch_id) DO UPDATE SET
                carregado_em = now(),
                imoveis = EXCLUDED.imoveis,
                imobiliarias = EXCLUDED.imobiliarias,
                snapshots = EXCLUDED.snapshots
            """,
            (
                batch_id,
                counts.get("imoveis", 0),
                counts.get("imobiliarias", 0),
                counts.get("snapshots", 0),
            ),
        )

    for table, _ in STAGING_TABLES:
        if table_exists(cursor, table):
            cursor.execute(f"DELETE FROM public.{table}")
    return batches
