"""Simplificação de geometria (Douglas-Peucker) para o GeoJSON ficar leve."""


def _dist_ao_segmento(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


Ponto = tuple[float, float]


def simplificar_linha(pontos: list[Ponto], tolerancia: float) -> list[Ponto]:
    if len(pontos) < 3:
        return pontos
    manter = [False] * len(pontos)
    manter[0] = manter[-1] = True
    pilha = [(0, len(pontos) - 1)]
    while pilha:
        ini, fim = pilha.pop()
        maior, idx = 0.0, None
        for i in range(ini + 1, fim):
            d = _dist_ao_segmento(pontos[i], pontos[ini], pontos[fim])
            if d > maior:
                maior, idx = d, i
        if idx is not None and maior > tolerancia:
            manter[idx] = True
            pilha += [(ini, idx), (idx, fim)]
    return [p for p, m in zip(pontos, manter, strict=True) if m]


def simplificar_anel(anel: list[Ponto], tolerancia: float) -> list[Ponto] | None:
    """Anel fechado simplificado; None se degenerar (menos de 4 pontos)."""
    # O primeiro ponto é fixo e o anel é fechado: simplifica as duas metades separadamente
    meio = len(anel) // 2
    esq = simplificar_linha(anel[:meio + 1], tolerancia)
    dir_ = simplificar_linha(anel[meio:], tolerancia)
    resultado = esq[:-1] + dir_
    return resultado if len(resultado) >= 4 else None
