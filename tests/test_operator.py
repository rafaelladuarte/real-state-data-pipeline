from datetime import datetime, timedelta

import pytest

from scripts.utility.operator import (
    convert_format_data,
    extract_address,
    extract_date,
    extract_number,
    tokenize_and_standardize,
)


def test_convert_format_data():
    assert convert_format_data("25-07-2024 10:30:00") == "25/07/2024"


@pytest.mark.parametrize("text, expected", [
    ("3 banheiro", 3),
    ("R$ 280.000", 280000),
    ("R$ 1.800.000,00", 1800000.0),
    ("45,67", 45.67),
    ("1.234,56", 1234.56),
    ("sem numero", None),
    ("", None),
    (None, None),
])
def test_extract_number(text, expected):
    assert extract_number(text) == expected


def test_extract_number_returns_list_for_multiple_values():
    assert extract_number("de 2 a 3 quartos") == [2, 3]


def test_extract_date_created_only():
    created, updated = extract_date("Anúncio criado em 18 de outubro de 2024.")
    assert created == "18/10/2024"
    assert updated is None


def test_extract_date_weeks_and_days():
    today = datetime.now()
    _, updated = extract_date("criado em 25 de julho de 2024, atualizado há 3 semanas.")
    assert updated == (today - timedelta(weeks=3)).strftime("%d/%m/%Y")

    _, updated = extract_date("criado em 6 de setembro de 2024, atualizado há 3 days.")
    assert updated == (today - timedelta(days=3)).strftime("%d/%m/%Y")


def test_extract_date_months_crosses_year():
    today = datetime.now()
    _, updated = extract_date("criado em 14 de maio de 2024, atualizado há 14 mês.")
    month, year = today.month - 14, today.year
    while month <= 0:
        month += 12
        year -= 1
    assert updated == datetime(year, month, min(today.day, 28)).strftime("%d/%m/%Y")


def test_extract_date_hours_and_empty():
    assert extract_date("criado em 17 de agosto de 2024, atualizado há 10 horas.")[1] is None
    assert extract_date("") == (None, None)
    assert extract_date(None) == (None, None)


def test_tokenize_and_standardize():
    assert tokenize_and_standardize("Rua José  Elias, nº 10!") == b"rua_jose_elias_no_10"
    assert tokenize_and_standardize("") == ""
    assert tokenize_and_standardize(None) == ""


@pytest.mark.parametrize("text, expected", [
    ("Rua Argemiro Costa, 1770 - Jardim Versailles, Uberlândia - MG",
     ("Rua Argemiro Costa", "1770", "Jardim Versailles")),
    ("Rua José Elias - Jardim Karaíba, Uberlândia - MG",
     ("Rua José Elias", None, "Jardim Karaíba")),
    ("Jaraguá, Uberlândia - MG", (None, None, "Jaraguá")),
    ("endereço sem padrão", (None, None, None)),
])
def test_extract_address(text, expected):
    assert extract_address(text) == expected
