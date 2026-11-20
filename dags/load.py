from airflow.providers.docker.operators.docker import DockerOperator
from airflow import DAG
from alerting import notify_failure

from datetime import datetime

import os


# Segredos vindos das Variables do Airflow (secrets backend em /opt/secrets)
ETL_ENV = {
    "MONGO_URI": "{{ var.value.MONGO_URI }}",
    "POSTGRESQL_URI": "{{ var.value.POSTGRESQL_URI }}",
}

# O purge_html também fala com o storage S3 e usa os limites da quarentena
PURGE_ENV = {
    **ETL_ENV,
    "S3_ENDPOINT": "object_store:9000",
    "S3_ACCESS_KEY": "{{ var.value.S3_ACCESS_KEY }}",
    "S3_SECRET_KEY": "{{ var.value.S3_SECRET_KEY }}",
    "PURGE_HTML": os.getenv("PURGE_HTML", "true"),
    "PURGE_LEGACY_HTML": os.getenv("PURGE_LEGACY_HTML", "false"),
    "QUARANTINE_MAX_BATCHES": os.getenv("QUARANTINE_MAX_BATCHES", "20"),
    "QUARANTINE_CONSECUTIVE": os.getenv("QUARANTINE_CONSECUTIVE", "3"),
    "HTML_QUARANTINE_DAYS": os.getenv("HTML_QUARANTINE_DAYS", "7"),
}


with DAG(
    'load',
    default_args={
        'start_date': datetime(2024, 12, 1),
        'retries': 1,
        'on_failure_callback': notify_failure,
    },
    schedule_interval=None,
    catchup=False,
) as dag:

    migrate = DockerOperator(
        task_id="migrate_to_postgres",
        image="etl-scripts",
        api_version="auto",
        auto_remove=True,
        command="python3 scripts/etl/load/migrate.py",
        docker_url="unix://var/run/docker.sock",
        network_mode="real_state_airflow",
        environment=ETL_ENV,
        mount_tmp_dir=False
    )

    model = DockerOperator(
        task_id="model_data",
        image="etl-scripts",
        api_version="auto",
        auto_remove=True,
        command="python3 scripts/etl/load/model.py",
        docker_url="unix://var/run/docker.sock",
        network_mode="real_state_airflow",
        environment=ETL_ENV,
        mount_tmp_dir=False
    )

    # Só apaga o HTML depois que o model.py registrou o lote como carregado.
    # Sem retry: a falha aqui é o limite da quarentena, que repetir não resolve.
    purge_html = DockerOperator(
        task_id="purge_html",
        image="etl-scripts",
        api_version="auto",
        auto_remove=True,
        command="python3 scripts/etl/load/purge_html.py",
        docker_url="unix://var/run/docker.sock",
        network_mode="real_state_airflow",
        environment=PURGE_ENV,
        mount_tmp_dir=False,
        retries=0,
    )

    migrate >> model >> purge_html
