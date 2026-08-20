"""Lettura di mesh STL, binarie e ASCII.

Lo STL è il formato che non porta topologia: ogni triangolo dichiara i suoi tre
vertici per conto proprio, e due triangoli adiacenti scrivono due volte gli stessi
due punti. Caricato così com'è, la segmentazione in corpi troverebbe un corpo per
triangolo. I vertici si saldano quindi al caricamento — senza spostarli: vedi
`core/mesh/mesh.py`.

Le normali dichiarate nel file si ignorano di proposito. Sono ridondanti, spesso
sbagliate, e quella che conta la ricalcola `core/mesh/patches.py` dall'ordine dei
vertici. Un STL con normali coerenti e vertici in ordine inverso è un file rotto,
e prendere per buone le sue normali significherebbe nasconderlo.

Distinguere binario da ASCII per l'intestazione `solid` non funziona: molti
esportatori scrivono `solid` anche nei primi cinque byte di un file binario. Si
guarda invece la dimensione, che in un STL binario è esattamente
84 + 50 × numero di triangoli.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from core.mesh.mesh import Mesh, MeshNonLeggibile, costruisci

#: Intestazione (80) + conteggio triangoli (4).
TESTATA = 84
#: Normale (12) + tre vertici (36) + attributo (2).
PER_TRIANGOLO = 50


def load_stl(path: str | Path) -> Mesh:
    path = Path(path)
    dati = path.read_bytes()
    if _e_binario(dati):
        vertices, faces, nomi, gruppi = _leggi_binario(dati, path)
    else:
        vertices, faces, nomi, gruppi = _leggi_ascii(dati, path)
    return costruisci(vertices, faces, source=path, group_names=nomi,
                      face_group=gruppi, format="stl", salda_vertici=True)


def _e_binario(dati: bytes) -> bool:
    if len(dati) < TESTATA:
        return False
    (n,) = struct.unpack_from("<I", dati, 80)
    return len(dati) == TESTATA + n * PER_TRIANGOLO


def _leggi_binario(dati: bytes, path: Path):
    """Un STL binario è un array a passo fisso: si legge in un colpo solo.

    Un ciclo Python su un file da mezzo milione di triangoli costa minuti; il
    dtype strutturato lo fa in una frazione di secondo.
    """
    (n,) = struct.unpack_from("<I", dati, 80)
    record = np.dtype([("normale", "<f4", 3), ("punti", "<f4", (3, 3)),
                       ("attributo", "<u2")])
    if len(dati) < TESTATA + n * record.itemsize:
        raise MeshNonLeggibile(
            f"{path}: l'intestazione dichiara {n} triangoli ma il file ne contiene meno")
    blocco = np.frombuffer(dati, dtype=record, count=n, offset=TESTATA)
    vertices = blocco["punti"].reshape(-1, 3).astype(float)
    faces = np.arange(3 * n, dtype=int).reshape(-1, 3)
    # Nel binario non c'è posto per i nomi: l'intestazione è un commento di 80 byte
    # e non c'è modo di dire dove finisce un corpo e comincia l'altro.
    return vertices, faces, (), None


def _leggi_ascii(dati: bytes, path: Path):
    """L'ASCII ha `solid <nome>`, ed è l'unico posto in cui uno STL nomina i corpi."""
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    nomi: list[str] = []
    gruppi: list[int] = []
    corrente = -1
    in_facet: list[tuple[float, float, float]] = []

    for riga in dati.decode("utf-8", errors="replace").splitlines():
        parti = riga.split()
        if not parti:
            continue
        parola = parti[0].lower()
        if parola == "solid":
            nome = " ".join(parti[1:]).strip()
            nomi.append(nome or f"solido_{len(nomi)}")
            corrente = len(nomi) - 1
        elif parola == "vertex" and len(parti) >= 4:
            in_facet.append((float(parti[1]), float(parti[2]), float(parti[3])))
        elif parola == "endloop":
            if len(in_facet) >= 3:
                base = len(vertices)
                vertices.extend(in_facet)
                # Un loop con più di tre vertici non è STL, ma esiste in natura:
                # si triangola a ventaglio invece di rifiutare il file.
                for i in range(1, len(in_facet) - 1):
                    faces.append((base, base + i, base + i + 1))
                    gruppi.append(corrente)
            in_facet = []
    if not vertices:
        raise MeshNonLeggibile(
            f"{path}: nessun triangolo. Non è uno STL binario valido (dimensione "
            f"incompatibile con l'intestazione) né uno STL ASCII leggibile.")
    return vertices, faces, tuple(nomi), gruppi
