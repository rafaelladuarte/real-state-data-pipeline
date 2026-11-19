from airflow.providers.docker.operators.docker import DockerOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow import DAG

from datetime import datetime

import os


default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'retries': 1,
}

# Segredos vindos das Variables do Airflow (secrets backend em /opt/secrets)
ETL_ENV = {
    "MONGO_URI": "{{ var.value.MONGO_URI }}",
    "POSTGRESQL_URI": "{{ var.value.POSTGRESQL_URI }}",
    "S3_ENDPOINT": "object_store:9000",
    "S3_ACCESS_KEY": "{{ var.value.S3_ACCESS_KEY }}",
    "S3_SECRET_KEY": "{{ var.value.S3_SECRET_KEY }}",
    # Intervalo mínimo GLOBAL entre requisições (somando todos os workers)
    "MIN_INTERVAL_SECONDS": os.getenv("MIN_INTERVAL_SECONDS", "1.25"),
}
# Quantidade de workers de coleta em paralelo
SCRAPER_WORKERS = int(os.getenv("SCRAPER_WORKERS", "3"))


with DAG(
    dag_id="extraction",
    default_args=default_args,
    start_date=datetime(2024, 12, 10),
    schedule_interval="0 0 * * *",
    catchup=False,
) as dag:
    links = DockerOperator(
        task_id="get_links_property",
        image="etl-scripts",
        api_version="auto",
        auto_remove=True,
        command="python3 scripts/etl/extraction/links.py",
        docker_url="unix://var/run/docker.sock",
        network_mode="real_state_airflow",
        environment=ETL_ENV,
        mount_tmp_dir=False
    )

    # Dynamic task mapping: uma instância por worker; todas consomem a mesma
    # fila (reserva atômica no Mongo) e dividem o limite global de requisições
    property = DockerOperator.partial(
        task_id="get_property",
        image="etl-scripts",
        api_version="auto",
        auto_remove=True,
        command="python3 scripts/etl/extraction/property.py",
        docker_url="unix://var/run/docker.sock",
        network_mode="real_state_airflow",
        mount_tmp_dir=False,
    ).expand(
        environment=[
            {**ETL_ENV, "WORKER_ID": f"worker-{i}"}
            for i in range(1, SCRAPER_WORKERS + 1)
        ]
    )

    parse_property = DockerOperator(
        task_id="parse_property",
        image="etl-scripts",
        api_version="auto",
        auto_remove=True,
        command="python3 scripts/etl/extraction/parse_property.py",
        docker_url="unix://var/run/docker.sock",
        network_mode="real_state_airflow",
        environment=ETL_ENV,
        mount_tmp_dir=False
    )

    real_state = DockerOperator(
        task_id="get_real_state",
        image="etl-scripts",
        api_version="auto",
        auto_remove=True,
        command="python3 scripts/etl/extraction/real_estate.py",
        docker_url="unix://var/run/docker.sock",
        network_mode="real_state_airflow",
        environment=ETL_ENV,
        mount_tmp_dir=False
    )

    start_treatment = TriggerDagRunOperator(
        task_id="start_treatment",
        trigger_dag_id="treatment",
        wait_for_completion=True,
        deferrable=True,
    )

    links >> property >> parse_property >> real_state >> start_treatment
