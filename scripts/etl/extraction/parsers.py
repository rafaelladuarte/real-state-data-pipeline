"""Parsers puros (sem Selenium) para o HTML do ZAP Imóveis.

Recebem o HTML (page_source) e devolvem dicionários prontos para o Mongo.
Os anúncios da listagem vêm do JSON-LD; os detalhes, de atributos
`data-testid`/`data-cy`, mais estáveis que as classes CSS geradas.
"""
from bs4 import BeautifulSoup

import json
import re

BASE_URL = "https://www.zapimoveis.com.br"
IMOVEL_PREFIX = f"{BASE_URL}/imovel/"


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _json_ld(soup: BeautifulSoup) -> list[dict]:
    blocks = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (TypeError, ValueError):
            continue
        blocks.extend(data if isinstance(data, list) else [data])
    return blocks


def _text(soup: BeautifulSoup, selector: str) -> str | None:
    element = soup.select_one(selector)
    if not element:
        return None
    text = re.sub(r"\s+", " ", element.get_text(" ", strip=True)).strip()
    return text or None


def parse_total_results(html: str) -> int | None:
    """Total de anúncios do título (ex.: '2.318 Casas para alugar ...')."""
    title = _text(_soup(html), "h1")
    match = re.match(r"([\d.]+)\s", title or "")
    return int(match.group(1).replace(".", "")) if match else None


def parse_listing_links(html: str) -> list[str]:
    """Links dos anúncios de uma página de listagem (sem query string)."""
    links: list[str] = []
    for block in _json_ld(_soup(html)):
        if block.get("@type") != "ItemList":
            continue
        for entry in block.get("itemListElement", []):
            url = (entry.get("item") or {}).get("url", "")
            url = url.split("?")[0]
            if url.startswith(IMOVEL_PREFIX) and url not in links:
                links.append(url)
    return links


def _format_brl(value) -> str | None:
    if value is None:
        return None
    return "R$ " + f"{int(float(value)):,}".replace(",", ".")


def _classify_features(features: list[str]) -> dict:
    result = {
        "area": None, "quartos": None, "banheiro": None,
        "vagas": None, "suite": None, "outros": [],
    }
    for feature in features:
        lower = feature.lower()
        if "m²" in lower and result["area"] is None:
            result["area"] = feature
        elif "quarto" in lower and result["quartos"] is None:
            result["quartos"] = feature
        elif "banheiro" in lower and result["banheiro"] is None:
            result["banheiro"] = feature
        elif "vaga" in lower and result["vagas"] is None:
            result["vagas"] = feature
        elif "suíte" in lower and result["suite"] is None:
            result["suite"] = feature
        else:
            result["outros"].append(feature)
    return result


def parse_advertiser(soup: BeautifulSoup) -> dict:
    """Dados da imobiliária/anunciante exibidos na página do anúncio."""
    link = soup.select_one('[data-testid="official-store-redirect-link"]')
    url = link.get("href") if link else None
    if url and url.startswith("/"):
        url = BASE_URL + url

    content = _text(soup, '[data-testid="advertiser-info-content"]') or ""
    quantity = re.search(r"([\d.]+)\s+im[óo]veis", content)
    since = re.search(r"desde (\d{1,2} de \w+ de \d{4})", content)

    return {
        "imobiliaria_url": url,
        "imobiliaria_nome": _text(
            soup, '[data-testid="advertiser-info-header"]'
        ),
        "imobiliaria_qtd_imoveis": (
            f"{quantity.group(1)} imóveis" if quantity else None
        ),
        # Mantém o formato "criado em ..." esperado por extract_date
        "imobiliaria_desde": f"criado em {since.group(1)}" if since else None,
    }


def parse_property(html: str) -> dict:
    """Extrai os campos de um anúncio (formato da coleção raw_imoveis)."""
    soup = _soup(html)
    product = next(
        (b for b in _json_ld(soup) if b.get("@type") == "Product"), {}
    )

    features = [
        re.sub(r"\s+", " ", li.get_text(" ", strip=True))
        for li in soup.select('[data-testid="amenities-list"] li')
    ]
    features = [f for f in features if f]

    images = list(product.get("image", []))
    for img in soup.select('[data-testid="carousel-photos"] img'):
        srcset = img.get("srcset") or ""
        src = srcset.split(",")[-1].strip().split(" ")[0] or img.get("src")
        if src and src.startswith("http") and src not in images:
            images.append(src)

    price = (product.get("offers") or {}).get("price")

    return {
        "titulo_anuncio": (
            _text(soup, '[data-testid="ldp-title"], h1') or product.get("name")
        ),
        "descricao": _text(soup, '[data-testid="description-content"]')
        or product.get("description"),
        "preco": _format_brl(price),
        "condominio": _text(soup, '[data-testid="condoFee"]'),
        "iptu": _text(soup, '[data-testid="iptu"]'),
        **_classify_features(features),
        "endereco": _text(soup, '[data-testid="location-address"]'),
        "original_imagens": images,
        "data_anuncio": _text(soup, '[data-testid="info-date"]'),
        **parse_advertiser(soup),
    }
