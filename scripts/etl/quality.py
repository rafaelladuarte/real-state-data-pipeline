"""Controle de qualidade da coleta: taxa de campos nulos e de erros por execução.

Detecta quando o site muda (parser passa a devolver campos vazios) ou bloqueia
a coleta (muitos erros). Quem chama decide o que fazer com o relatório; os
scripts de ETL levantam QualityError, o que faz a task da DAG falhar e alertar.
"""
from dataclasses import dataclass, field
from datetime import datetime, UTC

# Campos cujo vazio indica parser quebrado ou página inesperada
CRITICAL_FIELDS = (
    "titulo_anuncio", "preco", "endereco", "area", "imobiliaria_url", "data_anuncio",
)
# Campos importantes, mas que alguns anúncios realmente não têm
IMPORTANT_FIELDS = ("quartos", "banheiro", "descricao")

MAX_NULL_RATE_CRITICAL = 0.05
MAX_NULL_RATE_IMPORTANT = 0.30
MAX_ERROR_RATE = 0.20
# Abaixo disso a amostra é pequena demais para concluir algo
MIN_SAMPLE = 10


class QualityError(RuntimeError):
    """A coleta violou os limites de qualidade."""


@dataclass
class QualityReport:
    total: int
    errors: int = 0
    null_rates: dict = field(default_factory=dict)
    violations: list = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        attempted = self.total + self.errors
        return self.errors / attempted if attempted else 0.0

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_metrics(self, step: str) -> dict:
        return {
            "step": step,
            "at": datetime.now(UTC),
            "total": self.total,
            "errors": self.errors,
            "error_rate": round(self.error_rate, 4),
            "null_rates": {k: round(v, 4) for k, v in self.null_rates.items()},
            "violations": self.violations,
            "ok": self.ok,
        }


def _is_empty(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def check_quality(docs: list[dict], errors: int = 0) -> QualityReport:
    """Avalia documentos parseados (`docs`) e a quantidade de falhas (`errors`)."""
    report = QualityReport(total=len(docs), errors=errors)

    if report.total:
        for name in CRITICAL_FIELDS + IMPORTANT_FIELDS:
            nulls = sum(_is_empty(doc.get(name)) for doc in docs)
            report.null_rates[name] = nulls / report.total

    attempted = report.total + errors
    if attempted < MIN_SAMPLE:
        return report

    for name in CRITICAL_FIELDS:
        rate = report.null_rates.get(name, 1.0)
        if rate > MAX_NULL_RATE_CRITICAL:
            report.violations.append(
                f"campo crítico '{name}' vazio em {rate:.0%} dos anúncios "
                f"(limite {MAX_NULL_RATE_CRITICAL:.0%})"
            )
    for name in IMPORTANT_FIELDS:
        rate = report.null_rates.get(name, 1.0)
        if rate > MAX_NULL_RATE_IMPORTANT:
            report.violations.append(
                f"campo '{name}' vazio em {rate:.0%} dos anúncios "
                f"(limite {MAX_NULL_RATE_IMPORTANT:.0%})"
            )
    if report.error_rate > MAX_ERROR_RATE:
        report.violations.append(
            f"{report.error_rate:.0%} de erros ({errors} de {attempted}; "
            f"limite {MAX_ERROR_RATE:.0%})"
        )
    return report


def check_error_rate(ok: int, errors: int) -> QualityReport:
    """Avalia só a taxa de erros (ex.: coleta bloqueada pelo site)."""
    report = QualityReport(total=ok, errors=errors)
    if ok + errors >= MIN_SAMPLE and report.error_rate > MAX_ERROR_RATE:
        report.violations.append(
            f"{report.error_rate:.0%} de erros ({errors} de {ok + errors}; "
            f"limite {MAX_ERROR_RATE:.0%})"
        )
    return report


def raise_if_violated(report: QualityReport, step: str) -> None:
    if not report.ok:
        raise QualityError(f"[{step}] " + "; ".join(report.violations))
