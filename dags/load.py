from airflow.providers.docker.operators.docker import DockerOperator
from airflow import DAG
from alerting import notify_failure

from datetime import datetime


# Segredos vindos das Variables do Airflow (secrets backend em /opt/secrets)
ETL_ENV = {
    "MONGO_URI": "{{ var.value.MONGO_URI }}",
    "POSTGRESQL_URI": "{{ var.value.POSTGRESQL_URI }}",
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

    migrate >> model
