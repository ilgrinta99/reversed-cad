"""Sezioni piane di una mesh: il contorno vero del pezzo a una data quota.

La segmentazione in patch dice di quali superfici è fatto un corpo; la sezione
dice che forma ha. Serve dove l'ingombro non basta — in pianta, per far vedere di
quanto un prisma ricostruito si scosta dal profilo reale, senza dover aspettare la
build e il confronto.

Nessun numero del pezzo: qui c'è una sola tolleranza di lettura, dichiarata.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

#: Due punti più vicini di così sono lo stesso punto nel concatenare i segmenti.
JOIN_TOL = 1e-4


def cross_section(vertices: np.ndarray, faces: np.ndarray, axis: int,
                  value: float) -> list[np.ndarray]:
    """Interseca la mesh con un piano e restituisce i contorni chiusi, in 2D.

    Gli assi residui restano nell'ordine naturale (sezione su Z ⇒ coordinate X, Y).
    """
    if len(faces) == 0:
        return []
    tri = vertices[faces]                     # (F, 3, 3)
    d = tri[:, :, axis] - value
    crosses = ~((d > 0).all(axis=1) | (d < 0).all(axis=1))
    tri, d = tri[crosses], d[crosses]
    if len(tri) == 0:
        return []

    segments: list[tuple[np.ndarray, np.ndarray]] = []
    for p, dd in zip(tri, d):
        hits = []
        for i in range(3):
            j = (i + 1) % 3
            if dd[i] == 0.0:
                hits.append(p[i])
            elif dd[i] * dd[j] < 0.0:
                hits.append(p[i] + (p[j] - p[i]) * (dd[i] / (dd[i] - dd[j])))
        if len(hits) >= 2:
            segments.append((hits[0], hits[1]))

    keep = [k for k in range(3) if k != axis]
    return [chain[:, keep] for chain in _chains(segments)]


def _chains(segments: list[tuple[np.ndarray, np.ndarray]]) -> list[np.ndarray]:
    """Concatena i segmenti in polilinee, seguendo i punti coincidenti.

    Due triangoli adiacenti calcolano lo stesso punto di intersezione partendo
    dallo stesso spigolo, ma percorso nei due versi: il risultato coincide a meno
    dell'ultima cifra. I punti si saldano quindi su una griglia, controllando anche
    le celle vicine — altrimenti due punti a distanza nulla ma a cavallo di un
    bordo di cella resterebbero separati e il contorno si spezzerebbe lì.
    """
    lookup: dict[tuple[int, int, int], tuple] = {}
    position: dict[tuple, np.ndarray] = {}
    adjacency: dict[tuple, list[tuple]] = defaultdict(list)

    def node(p: np.ndarray) -> tuple:
        cell = tuple(np.floor(p / JOIN_TOL).astype(np.int64))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    hit = lookup.get((cell[0] + dx, cell[1] + dy, cell[2] + dz))
                    if hit is not None and np.linalg.norm(position[hit] - p) <= JOIN_TOL:
                        return hit
        lookup[cell] = cell
        position[cell] = p
        return cell

    for a, b in segments:
        ka, kb = node(a), node(b)
        if ka == kb:
            continue
        adjacency[ka].append(kb)
        adjacency[kb].append(ka)

    # Si parte dalle estremità (grado 1): iniziare a metà di una polilinea aperta
    # produrrebbe due tronconi al posto di un contorno.
    order = sorted(adjacency, key=lambda k: len(adjacency[k]))
    seen: set[tuple] = set()
    out: list[np.ndarray] = []
    for start in order:
        if start in seen:
            continue
        seen.add(start)
        chain = [start]
        for direction in (0, 1):
            current = start
            while True:
                nxt = [k for k in adjacency[current] if k not in seen]
                if not nxt:
                    break
                current = nxt[0]
                seen.add(current)
                if direction == 0:
                    chain.append(current)
                else:
                    chain.insert(0, current)
        if len(chain) > 2:
            out.append(np.asarray([position[k] for k in chain]))
    out.sort(key=len, reverse=True)
    return out


def polygon_area(points: np.ndarray) -> float:
    """Area racchiusa da un contorno chiuso (formula di Gauss), sempre positiva."""
    if len(points) < 3:
        return 0.0
    x, y = points[:, 0], points[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)
