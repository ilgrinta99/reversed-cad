# -*- coding: utf-8 -*-
"""Riconoscimento di pattern di fori su una vista, per la quotatura.

Sta in `core/` perché è pura geometria: non sa niente del pezzo, riceve un elenco
di fori nel piano di una vista — ciascuno un centro e un raggio — e risponde a una
domanda sola: *questi fori formano un pattern che si quota una volta invece che
foro per foro?* Tre risposte possibili:

- **cerchio di fori** (bolt circle): N fori uguali, equidistanti su un cerchio dei
  centri. Si quota «N× Ød su Ø(pcd) PCD» invece di N richiami identici.
- **passo** (linear pitch): N fori uguali, allineati e a passo costante. Si quota
  «N× Ød passo p».
- **sparso**: nessun pattern; ogni foro va quotato da sé.

Questo modulo **non inventa quote**: non produce numeri per il *modello*. Il
diametro di un foro resta quello del registro (misurato o approvato); qui si
ricavano solo il diametro del cerchio dei centri (PCD) e il passo, che sono
conseguenze geometriche dei centri *già misurati*. Chi compone la tavola li
dichiara come ricavati, come già fa con gli ingombri d'assieme misurati sul
solido. È presentazione, non una fonte di quote.

Nessuna dipendenza: si esegue e si prova ovunque, come il resto di `core/drafting/`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Foro2D:
    """Un foro nel piano di una vista: centro `(x, y)` e raggio `r`.

    `ref` è un'etichetta opaca che il chiamante usa per risalire al foro d'origine
    (tipicamente l'indice del foro nel corpo). Questo modulo non la interpreta: la
    trasporta e basta, così il pattern riconosciuto sa a quali fori si riferisce.
    """

    x: float
    y: float
    r: float
    ref: object = None


@dataclass(frozen=True)
class Pattern:
    """Un gruppo di fori con lo stesso raggio e l'esito del riconoscimento.

    `kind` vale ``"bolt_circle"``, ``"passo"`` o ``"sparso"``. Gli altri campi
    hanno senso solo per il tipo che li produce: `centro`/`pcd` per il cerchio di
    fori, `passo` per il passo. `conteggio` è sempre il numero di fori del gruppo.
    """

    kind: str
    fori: tuple[Foro2D, ...]
    centro: tuple[float, float] | None = None
    pcd: float | None = None
    passo: float | None = None

    @property
    def conteggio(self) -> int:
        return len(self.fori)

    @property
    def raggio(self) -> float:
        """Raggio comune dei fori del gruppo (il primo: sono uguali per costruzione)."""
        return self.fori[0].r if self.fori else 0.0


# ---------------------------------------------------------------- pubblico


def raggruppa_fori(
    fori: list[Foro2D],
    *,
    tol_raggio: float = 1e-3,
    min_bolt: int = 4,
    min_passo: int = 3,
    tol_pcd_rel: float = 0.02,
    tol_ang_gradi: float = 2.0,
    tol_passo_rel: float = 0.03,
    tol_collineare: float | None = None,
) -> list[Pattern]:
    """Classifica i fori in pattern, uno per gruppo di raggio.

    Prima raggruppa per raggio (fori con raggio diverso non sono lo stesso foro,
    e non si quotano insieme). Dentro ogni gruppo prova, in ordine, il cerchio di
    fori e poi il passo; se nessuno regge, il gruppo è «sparso». Un gruppo troppo
    piccolo per essere un pattern è «sparso» anch'esso: così il chiamante può
    sempre iterare `pattern.fori` e disegnarli uno per uno.

    L'ordine dei fori dentro un gruppo «sparso» è quello d'ingresso: chi disegna
    conta su questo per non cambiare l'aspetto di una tavola che non ha pattern.
    """
    risultati: list[Pattern] = []
    for gruppo in _gruppi_per_raggio(fori, tol_raggio):
        pattern = _classifica_gruppo(
            gruppo,
            min_bolt=min_bolt,
            min_passo=min_passo,
            tol_pcd_rel=tol_pcd_rel,
            tol_ang_gradi=tol_ang_gradi,
            tol_passo_rel=tol_passo_rel,
            tol_collineare=tol_collineare,
        )
        risultati.append(pattern)
    return risultati


# ---------------------------------------------------------------- raggio


def _gruppi_per_raggio(fori: list[Foro2D], tol: float) -> list[list[Foro2D]]:
    """Fori con raggio uguale a meno di `tol`, in cluster crescenti di raggio.

    L'ordine d'ingresso è conservato *dentro* ogni cluster: si ordina solo per
    decidere i confini, poi ogni foro torna al suo posto originale.
    """
    if not fori:
        return []
    per_raggio = sorted(range(len(fori)), key=lambda i: fori[i].r)
    cluster_di: dict[int, int] = {}
    n_cluster = 0
    riferimento = fori[per_raggio[0]].r
    for pos, idx in enumerate(per_raggio):
        if pos > 0 and abs(fori[idx].r - riferimento) > tol:
            n_cluster += 1
            riferimento = fori[idx].r
        cluster_di[idx] = n_cluster
    gruppi: list[list[Foro2D]] = [[] for _ in range(n_cluster + 1)]
    for idx, foro in enumerate(fori):  # ordine originale
        gruppi[cluster_di[idx]].append(foro)
    return gruppi


def _classifica_gruppo(
    gruppo: list[Foro2D],
    *,
    min_bolt: int,
    min_passo: int,
    tol_pcd_rel: float,
    tol_ang_gradi: float,
    tol_passo_rel: float,
    tol_collineare: float | None,
) -> Pattern:
    if len(gruppo) >= min_bolt:
        bolt = _prova_cerchio(gruppo, tol_pcd_rel, tol_ang_gradi)
        if bolt is not None:
            return bolt
    if len(gruppo) >= min_passo:
        passo = _prova_passo(gruppo, tol_passo_rel, tol_collineare)
        if passo is not None:
            return passo
    return Pattern(kind="sparso", fori=tuple(gruppo))


# ---------------------------------------------------------------- cerchio


def _prova_cerchio(
    gruppo: list[Foro2D], tol_pcd_rel: float, tol_ang_gradi: float
) -> Pattern | None:
    """Cerchio di fori: centri equidistanti dal baricentro ed equispaziati in angolo.

    Il centro è il baricentro dei centri, non il centro dell'ingombro: un cerchio
    di fori decentrato rispetto al pezzo resta un cerchio di fori.
    """
    cx = sum(f.x for f in gruppo) / len(gruppo)
    cy = sum(f.y for f in gruppo) / len(gruppo)
    raggi = [math.hypot(f.x - cx, f.y - cy) for f in gruppo]
    medio = sum(raggi) / len(raggi)
    if medio <= 1e-6:
        return None
    tol_r = max(1e-3, medio * tol_pcd_rel)
    if max(abs(r - medio) for r in raggi) > tol_r:
        return None

    angoli = sorted(
        math.degrees(math.atan2(f.y - cy, f.x - cx)) % 360.0 for f in gruppo
    )
    n = len(angoli)
    passo_ang = 360.0 / n
    diffs = [(angoli[(i + 1) % n] - angoli[i]) % 360.0 for i in range(n)]
    if max(abs(d - passo_ang) for d in diffs) > tol_ang_gradi:
        return None

    return Pattern(
        kind="bolt_circle",
        fori=tuple(gruppo),
        centro=(cx, cy),
        pcd=2.0 * medio,
    )


# ---------------------------------------------------------------- passo


def _prova_passo(
    gruppo: list[Foro2D], tol_passo_rel: float, tol_collineare: float | None
) -> Pattern | None:
    """Passo lineare: fori allineati su una retta e a distanza costante.

    Più generale del solo allineamento agli assi: la direzione si ricava dai due
    fori più lontani, poi si controlla che tutti stiano sulla retta e che le
    distanze consecutive coincidano.
    """
    punti = [(f.x, f.y) for f in gruppo]
    a, b = _estremi(punti)
    dx, dy = punti[b][0] - punti[a][0], punti[b][1] - punti[a][1]
    lunghezza = math.hypot(dx, dy)
    if lunghezza <= 1e-9:
        return None
    ux, uy = dx / lunghezza, dy / lunghezza

    # Distanza di ciascun foro dalla retta (componente perpendicolare) e ascissa
    # lungo la retta (componente parallela).
    tol_perp = tol_collineare if tol_collineare is not None else max(1e-4, lunghezza * 1e-3)
    proiezioni: list[tuple[float, int]] = []
    for i, (px, py) in enumerate(punti):
        rx, ry = px - punti[a][0], py - punti[a][1]
        perp = abs(rx * (-uy) + ry * ux)
        if perp > tol_perp:
            return None
        proiezioni.append((rx * ux + ry * uy, i))

    proiezioni.sort()
    passi = [proiezioni[i + 1][0] - proiezioni[i][0] for i in range(len(proiezioni) - 1)]
    if not passi or min(passi) <= 1e-9:
        return None
    passo = sum(passi) / len(passi)
    if (max(passi) - min(passi)) > max(1e-4, passo * tol_passo_rel):
        return None

    ordinati = tuple(gruppo[i] for _, i in proiezioni)
    return Pattern(kind="passo", fori=ordinati, passo=passo)


def _estremi(punti: list[tuple[float, float]]) -> tuple[int, int]:
    """Indici della coppia di punti a distanza massima (direzione più stabile)."""
    a, b, best = 0, 0, -1.0
    for i in range(len(punti)):
        for j in range(i + 1, len(punti)):
            d = math.hypot(punti[i][0] - punti[j][0], punti[i][1] - punti[j][1])
            if d > best:
                a, b, best = i, j, d
    return a, b
