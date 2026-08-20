"""Lettura di mesh PLY: ASCII e binario, little e big endian.

Il PLY dichiara la propria struttura in testa al file — quali elementi ci sono,
quante istanze, e di che proprietà è fatta ognuna. Il lettore quindi non indovina
il tracciato dei dati: lo legge. È anche il motivo per cui bisogna saper saltare
le proprietà che non servono (colori, normali, confidenze): stanno in mezzo a
quelle che servono, e senza contarne i byte si legge la cosa sbagliata.

Le facce sono liste di lunghezza variabile (`property list uchar int vertex_index`)
e possono essere quadrilateri: si triangolano a ventaglio.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from core.mesh.mesh import Mesh, MeshNonLeggibile, costruisci, ventaglio

#: Tipi scalari PLY -> (codice struct, byte). I sinonimi sono quelli che gli
#: esportatori usano davvero: `float` e `float32` sono la stessa cosa.
TIPI = {
    "char": ("b", 1), "int8": ("b", 1),
    "uchar": ("B", 1), "uint8": ("B", 1),
    "short": ("h", 2), "int16": ("h", 2),
    "ushort": ("H", 2), "uint16": ("H", 2),
    "int": ("i", 4), "int32": ("i", 4),
    "uint": ("I", 4), "uint32": ("I", 4),
    "float": ("f", 4), "float32": ("f", 4),
    "double": ("d", 8), "float64": ("d", 8),
}

#: Nomi con cui gli esportatori chiamano la lista di indici di una faccia.
NOMI_INDICI = ("vertex_index", "vertex_indices")


def load_ply(path: str | Path) -> Mesh:
    path = Path(path)
    dati = path.read_bytes()
    formato, elementi, inizio = _intestazione(dati, path)

    if formato == "ascii":
        vertices, faces = _corpo_ascii(dati[inizio:], elementi, path)
    else:
        vertices, faces = _corpo_binario(dati, inizio, elementi,
                                         "<" if "little" in formato else ">", path)
    # Il PLY non ha un concetto di corpo: i nomi dei corpi, se servono, li
    # ritrova la segmentazione. Dichiararne di finti sarebbe peggio di non averne.
    return costruisci(vertices, faces, source=path, format="ply")


# ---------------------------------------------------------------- intestazione


def _intestazione(dati: bytes, path: Path):
    """Legge l'intestazione e restituisce (formato, elementi, offset del corpo)."""
    fine = dati.find(b"end_header")
    if not dati[:3].lower().startswith(b"ply") or fine < 0:
        raise MeshNonLeggibile(f"{path}: manca l'intestazione PLY (`ply` … `end_header`)")
    testa = dati[:fine].decode("ascii", errors="replace")
    resto = dati[fine:]
    inizio = fine + resto.find(b"\n") + 1

    formato = ""
    elementi: list[dict] = []
    for riga in testa.splitlines():
        parti = riga.split()
        if not parti:
            continue
        if parti[0] == "format" and len(parti) >= 2:
            formato = parti[1]
        elif parti[0] == "element" and len(parti) >= 3:
            elementi.append({"nome": parti[1], "n": int(parti[2]), "proprieta": []})
        elif parti[0] == "property" and elementi:
            elementi[-1]["proprieta"].append(_proprieta(parti, path))
    if formato not in ("ascii", "binary_little_endian", "binary_big_endian"):
        raise MeshNonLeggibile(f"{path}: formato PLY non riconosciuto ({formato!r})")
    if not any(e["nome"] == "vertex" for e in elementi):
        raise MeshNonLeggibile(f"{path}: l'intestazione PLY non dichiara vertici")
    return formato, elementi, inizio


def _proprieta(parti: list[str], path: Path) -> dict:
    if parti[1] == "list":
        if len(parti) < 5:
            raise MeshNonLeggibile(f"{path}: `property list` incompleta: {' '.join(parti)}")
        return {"lista": True, "tipo_n": parti[2], "tipo": parti[3], "nome": parti[4]}
    if len(parti) < 3:
        raise MeshNonLeggibile(f"{path}: `property` incompleta: {' '.join(parti)}")
    return {"lista": False, "tipo": parti[1], "nome": parti[2]}


def _codice(tipo: str, path: Path) -> tuple[str, int]:
    try:
        return TIPI[tipo]
    except KeyError:
        raise MeshNonLeggibile(f"{path}: tipo PLY sconosciuto: {tipo!r}") from None


# ---------------------------------------------------------------- corpo


def _corpo_ascii(dati: bytes, elementi: list[dict], path: Path):
    campi = re.split(rb"\s+", dati.strip())
    pos = 0
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []

    for elemento in elementi:
        nomi = [p["nome"] for p in elemento["proprieta"]]
        for _ in range(elemento["n"]):
            valori: dict[str, list[float]] = {}
            for prop in elemento["proprieta"]:
                if prop["lista"]:
                    n = int(float(campi[pos])); pos += 1
                    valori[prop["nome"]] = [float(c) for c in campi[pos:pos + n]]
                    pos += n
                else:
                    valori[prop["nome"]] = [float(campi[pos])]; pos += 1
            _accumula(elemento["nome"], nomi, valori, vertices, faces, path)
    return vertices, faces


def _corpo_binario(dati: bytes, inizio: int, elementi: list[dict], ordine: str, path: Path):
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    pos = inizio

    for elemento in elementi:
        nomi = [p["nome"] for p in elemento["proprieta"]]
        fisso = all(not p["lista"] for p in elemento["proprieta"])
        if fisso and elemento["nome"] == "vertex":
            # Il caso normale: i vertici hanno proprietà di dimensione fissa, e si
            # leggono in blocco. Colori e normali restano nel dtype e si scartano
            # dopo, che è più veloce e più semplice che saltarli a mano.
            dtype = np.dtype([(p["nome"], ordine + _codice(p["tipo"], path)[0])
                              for p in elemento["proprieta"]])
            blocco = np.frombuffer(dati, dtype=dtype, count=elemento["n"], offset=pos)
            pos += elemento["n"] * dtype.itemsize
            for asse in "xyz":
                if asse not in dtype.names:
                    raise MeshNonLeggibile(f"{path}: i vertici PLY non hanno la coordinata {asse}")
            vertices.extend(zip(blocco["x"].astype(float),
                                blocco["y"].astype(float),
                                blocco["z"].astype(float)))
            continue
        for _ in range(elemento["n"]):
            valori, pos = _leggi_record(dati, pos, elemento["proprieta"], ordine, path)
            _accumula(elemento["nome"], nomi, valori, vertices, faces, path)
    return vertices, faces


def _leggi_record(dati: bytes, pos: int, proprieta: list[dict], ordine: str, path: Path):
    valori: dict[str, list[float]] = {}
    for prop in proprieta:
        if prop["lista"]:
            codice, larghezza = _codice(prop["tipo_n"], path)
            n = int(np.frombuffer(dati, dtype=ordine + codice, count=1, offset=pos)[0])
            pos += larghezza
            codice, larghezza = _codice(prop["tipo"], path)
            valori[prop["nome"]] = np.frombuffer(
                dati, dtype=ordine + codice, count=n, offset=pos).astype(float).tolist()
            pos += n * larghezza
        else:
            codice, larghezza = _codice(prop["tipo"], path)
            valori[prop["nome"]] = [
                float(np.frombuffer(dati, dtype=ordine + codice, count=1, offset=pos)[0])]
            pos += larghezza
    return valori, pos


def _accumula(elemento: str, nomi: list[str], valori: dict[str, list[float]],
              vertices: list, faces: list, path: Path) -> None:
    """Un record letto diventa un vertice o una faccia; gli altri elementi si saltano."""
    if elemento == "vertex":
        try:
            vertices.append((valori["x"][0], valori["y"][0], valori["z"][0]))
        except KeyError:
            raise MeshNonLeggibile(f"{path}: i vertici PLY non hanno x, y, z") from None
    elif elemento == "face":
        for nome in NOMI_INDICI:
            if nome in valori and len(valori[nome]) >= 3:
                faces.extend(ventaglio([int(v) for v in valori[nome]]))
                return
        if not any(n in nomi for n in NOMI_INDICI):
            raise MeshNonLeggibile(
                f"{path}: le facce PLY non dichiarano {' né '.join(NOMI_INDICI)}")
