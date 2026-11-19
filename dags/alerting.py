"""Alerta de falha das DAGs (on_failure_callback).

Envia uma mensagem JSON {"text": "..."} para ALERT_WEBHOOK_URL (formato aceito por
Slack, Discord com /slack, Mattermost etc.). Sem a variável, só registra em log.
Nunca levanta exceção: um alerta que falha não pode derrubar a DAG.
"""
import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)


def format_message(context: dict) -> str:
    task = context.get("task_instance")
    dag_id = getattr(task, "dag_id", None) or context.get("dag").dag_id
    task_id = getattr(task, "task_id", "?")
    try_number = getattr(task, "try_number", "?")
    error = str(context.get("exception") or "sem detalhe")
    return (
        f":rotating_light: Falha no pipeline imobiliário\n"
        f"DAG: {dag_id} | task: {task_id} | tentativa: {try_number}\n"
        f"Erro: {error[:500]}"
    )


def notify_failure(context: dict) -> None:
    message = format_message(context)
    logger.error(message)

    url = os.getenv("ALERT_WEBHOOK_URL")
    if not url:
        return
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps({"text": message}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(request, timeout=10).close()
    except Exception as error:  # noqa: BLE001 - o alerta nunca deve quebrar a DAG
        logger.error(f"Falha ao enviar alerta: {error}")
