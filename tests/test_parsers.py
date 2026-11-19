from pathlib import Path

from scripts.etl.extraction.parsers import (
    parse_listing_links, parse_property, parse_total_results,
)
from scripts.utility.operator import extract_address, extract_date, extract_number

FIXTURES = Path(__file__).parent / "fixtures"


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_total_results():
    assert parse_total_results(read("listing.html")) == 2318


def test_listing_links_are_clean_unique_and_filtered():
    links = parse_listing_links(read("listing.html"))
    assert len(links) == 2
    assert all(
        link.startswith("https://www.zapimoveis.com.br/imovel/") for link in links
    )
    assert all("?" not in link for link in links)


def test_parse_property_fields():
    data = parse_property(read("detail.html"))
    assert data["titulo_anuncio"] == "Casa para alugar com 3 quartos"
    assert data["preco"] == "R$ 4.200"
    assert data["area"] == "225 m²"
    assert data["quartos"] == "3 quartos"
    assert data["banheiro"] == "3 banheiros"
    assert data["vagas"] == "2 vagas"
    assert data["suite"] == "2 suítes"
    assert data["outros"] == ["Varanda", "Closet"]
    assert data["original_imagens"] == [
        "https://img.example/1.webp", "https://img.example/a-large.webp",
    ]
    assert data["imobiliaria_url"].endswith("/imobiliaria/875370/")
    assert data["imobiliaria_nome"] == "Delta Imoveis Locação"


def test_parsed_property_is_compatible_with_treatment():
    data = parse_property(read("detail.html"))
    assert extract_number(data["preco"]) == 4200
    assert extract_number(data["condominio"]) is None
    assert extract_number(data["iptu"]) == 150
    assert extract_number(data["area"]) == 225
    assert extract_number(data["imobiliaria_url"]) == 875370
    assert extract_date(data["data_anuncio"])[0] == "03/10/2026"
    assert extract_address(data["endereco"]) == (
        "Rua das Ipoméias", "255", "Cidade Jardim",
    )


def test_parsed_advertiser_is_compatible_with_treatment():
    data = parse_property(read("detail.html"))
    assert extract_number(data["imobiliaria_qtd_imoveis"]) == 1815
    assert extract_date(data["imobiliaria_desde"])[0] == "16/09/2025"


def test_parse_property_handles_empty_page():
    data = parse_property("<html></html>")
    assert data["preco"] is None and data["outros"] == []
