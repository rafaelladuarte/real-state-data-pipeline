import io
import json
from types import SimpleNamespace

from dags import alerting


def context(error="boom"):
    return {
        "task_instance": SimpleNamespace(
            dag_id="extraction", task_id="parse_property", try_number=2
        ),
        "exception": RuntimeError(error),
    }


def test_message_has_dag_task_and_error():
    message = alerting.format_message(context("parser quebrado"))
    assert "extraction" in message and "parse_property" in message
    assert "parser quebrado" in message and "tentativa: 2" in message


def test_notify_posts_json_to_webhook(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["body"] = json.loads(request.data)
        return io.BytesIO(b"ok")

    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example/abc")
    monkeypatch.setattr(alerting.urllib.request, "urlopen", fake_urlopen)
    alerting.notify_failure(context())

    assert sent["url"] == "https://hooks.example/abc"
    assert "parse_property" in sent["body"]["text"]


def test_notify_without_webhook_only_logs(monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)

    def explode(*args, **kwargs):
        raise AssertionError("não deveria chamar a rede")

    monkeypatch.setattr(alerting.urllib.request, "urlopen", explode)
    alerting.notify_failure(context())


def test_notify_never_raises_when_webhook_fails(monkeypatch):
    def broken(request, timeout):
        raise OSError("sem rede")

    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example/abc")
    monkeypatch.setattr(alerting.urllib.request, "urlopen", broken)
    alerting.notify_failure(context())  # não levanta
