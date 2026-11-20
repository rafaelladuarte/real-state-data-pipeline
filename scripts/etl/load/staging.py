"""Controle da carga incremental no Postgres.

O staging (`_treat_*`, `_snapshots_imoveis`) é recriado a cada carga com os
lotes pendentes: o `migrate.py` o preenche e o `model.py` o aplica e o esvazia.
A tabela `lote_carga` registra os lotes **inteiramente** aplicados, com quantos
documentos de cada coleção foram levados (na mesma transação do model.py, então
"registrado" e "aplicado" nunca divergem).

Um lote é pendente quando:
- ainda não está em `lote_carga`; ou
- o Mongo tem hoje mais documentos dele do que os registrados (a carga pegou o
  lote pela metade, por exemplo enquanto o tratamento ainda gravava); ou
- alguma linha dele não chegou às tabelas finais (por exemplo, imóvel de uma
  imobiliária ainda não coletada, descartado pelo INNER JOIN). Nesse caso ele
  não é registrado e volta na próxima carga.

O `migrate.py` e o `purge_html.py` usam a mesma regra: o HTML de um lote
pendente nunca é apagado.

Concorrência: migrate e model pegam o mesmo advisory lock de transação, então
nunca mexem no staging ao mesmo tempo.
"""
from scripts.etl.batch import LEGACY_BATCH

# (tabela de staging, coleção do Mongo de origem, coluna em lote_carga)
STAGING_TABLES = (
    ("_treat_imoveis", "treat_imoveis", "imoveis"),
    ("_treat_imobiliarias", "treat_imobiliarias", "imobiliarias"),
    ("_snapshots_imoveis", "snapshots_imoveis", "snapshots"),
)
COUNT_KEYS = tuple(key for _, _, key in STAGING_TABLES)

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

# Linhas do staging que o insert_tables_oficial.sql não levou às tabelas finais
UNAPPLIED_SQL = {
    "_treat_imoveis": """
        SELECT COALESCE(A.batch_id, %s), count(*) FROM public._treat_imoveis A
        LEFT JOIN public.imovel I ON I.id_imovel = A.hash
        WHERE I.id_imovel IS NULL GROUP BY 1""",
    "_treat_imobiliarias": """
        SELECT COALESCE(A.batch_id, %s), count(*) FROM public._treat_imobiliarias A
        LEFT JOIN public.imobiliaria B ON B.id_imobiliaria = A.id_imobiliaria
        WHERE B.id_imobiliaria IS NULL GROUP BY 1""",
    # Snapshot sem preço é descartado de propósito: não conta como pendência
    "_snapshots_imoveis": """
        SELECT COALESCE(S.batch_id, %s), count(*) FROM public._snapshots_imoveis S
        LEFT JOIN public.imovel_snapshot P
            ON P.id_imovel = S.hash
           AND P.data_coleta = TO_DATE(S.data_coleta, 'DD/MM/YYYY')
        WHERE S.preco IS NOT NULL AND P.id_imovel IS NULL GROUP BY 1""",
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
    for table, _, _ in STAGING_TABLES:
        if table_exists(cursor, table):
            cursor.execute(
                f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS batch_id TEXT"
            )


def recorded_counts(cursor) -> dict[str, dict[str, int]]:
    """Lotes registrados em lote_carga, com os documentos levados de cada coleção."""
    if not table_exists(cursor, "lote_carga"):
        return {}
    cursor.execute(f"SELECT batch_id, {', '.join(COUNT_KEYS)} FROM public.lote_carga")
    return {
        row[0]: dict(zip(COUNT_KEYS, row[1:], strict=True))
        for row in cursor.fetchall()
    }


def mongo_batch_counts(mongo) -> dict[str, dict[str, int]]:
    """Documentos por lote hoje no Mongo (sem batch_id contam como `legado`)."""
    counts: dict[str, dict[str, int]] = {}
    for _, collection, key in STAGING_TABLES:
        for row in mongo.get_documents_aggregate(
            pipeline=[{"$group": {"_id": "$batch_id", "n": {"$sum": 1}}}],
            collection=collection,
        ):
            batch = row["_id"] or LEGACY_BATCH
            counts.setdefault(batch, {})[key] = row["n"]
    return counts


def pending_batches(
    current: dict[str, dict[str, int]], recorded: dict[str, dict[str, int]]
) -> list[str]:
    """Lotes que ainda precisam ir ao Postgres (novos ou com documentos a mais)."""
    return sorted(
        batch for batch, counts in current.items()
        if batch not in recorded
        or any(counts.get(k, 0) > recorded[batch].get(k, 0) for k in COUNT_KEYS)
    )


def fully_loaded_batches(
    current: dict[str, dict[str, int]], recorded: dict[str, dict[str, int]]
) -> list[str]:
    """Lotes registrados que não têm nada pendente: só o HTML deles pode sair."""
    pending = set(pending_batches(current, recorded))
    return sorted(batch for batch in recorded if batch not in pending)


def record_loaded_and_clear(cursor) -> tuple[dict, dict]:
    """Registra os lotes inteiramente aplicados e esvazia o staging.

    Devolve (carregados, pendentes): {batch_id: {coluna: linhas}}. Lotes com
    alguma linha não aplicada ficam fora de lote_carga e voltam na próxima
    carga (o Mongo é a origem; o upsert do model.py é idempotente).

    Roda dentro da transação do model.py: se algo falhar antes do commit,
    nada é registrado e o staging continua intacto para a próxima tentativa.
    """
    staged: dict[str, dict[str, int]] = {}
    unapplied: dict[str, dict[str, int]] = {}
    for table, _, key in STAGING_TABLES:
        if not table_exists(cursor, table):
            continue
        cursor.execute(
            f"SELECT COALESCE(batch_id, %s), count(*) FROM public.{table} GROUP BY 1",
            (LEGACY_BATCH,),
        )
        for batch_id, count in cursor.fetchall():
            staged.setdefault(batch_id, {})[key] = count
        cursor.execute(UNAPPLIED_SQL[table], (LEGACY_BATCH,))
        for batch_id, count in cursor.fetchall():
            unapplied.setdefault(batch_id, {})[key] = count

    loaded = {b: c for b, c in staged.items() if b not in unapplied}
    for batch_id, counts in loaded.items():
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
            (batch_id, *(counts.get(k, 0) for k in COUNT_KEYS)),
        )

    for table, _, _ in STAGING_TABLES:
        if table_exists(cursor, table):
            cursor.execute(f"DELETE FROM public.{table}")
    return loaded, unapplied
