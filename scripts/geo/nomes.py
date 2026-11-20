"""Normalização de nomes de bairro e casamento com os polígonos do mapa.

O anúncio e o IBGE escrevem o mesmo bairro de formas diferentes ("Sta. Mônica",
"Bairro Santa Mônica"). Os dois lados são reduzidos a uma chave comparável.
"""
import re
import unicodedata

# Abreviações comuns nos anúncios (já sem acento e em minúsculas)
ABREVIACOES = {
    "sta": "santa", "sto": "santo", "jd": "jardim", "res": "residencial",
    "cond": "condominio", "pq": "parque", "vl": "vila",
}
PREFIXOS_IGNORADOS = ("bairro ",)


def normalizar(nome: str | None) -> str:
    """'Sta. Mônica' -> 'santa monica'. Vazio ou None -> ''."""
    if not nome:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", nome.lower()) if unicodedata.category(c) != "Mn"
    )
    limpo = re.sub(r"[^a-z0-9]+", " ", sem_acento).strip()
    for prefixo in PREFIXOS_IGNORADOS:
        if limpo.startswith(prefixo):
            limpo = limpo[len(prefixo):]
    return " ".join(ABREVIACOES.get(p, p) for p in limpo.split())


def chaves_do_bairro(oficial: str, apelidos: dict[str, str]) -> list[str]:
    """Chave do nome oficial mais a de cada apelido que aponta para ele."""
    chave = normalizar(oficial)
    extras = sorted(
        normalizar(apelido) for apelido, destino in apelidos.items()
        if normalizar(destino) == chave
    )
    return [chave, *[c for c in extras if c != chave]]


def resolver(nome: str | None, chaves_por_bairro: dict[str, str]) -> str | None:
    """Devolve a chave do polígono para um nome de anúncio, ou None se não houver par."""
    chave = normalizar(nome)
    return chaves_por_bairro.get(chave)
