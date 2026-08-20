"""Lettura di mesh VRML (.wrl), versioni 1.0 e 2.0/97.

Il VRML è un formato di *scena*, non di mesh: la geometria sta dentro un albero di
nodi, e un `Transform` sposta, ruota e scala tutto quello che ha sotto. Ignorare i
Transform darebbe una mesh con i pezzi tutti nell'origine — plausibile a vedersi,
sbagliata da misurare. Qui si applicano.

Quello che si legge:

* `IndexedFaceSet` con `coord Coordinate { point [...] }` e `coordIndex [...]`
  (VRML 2.0), e `Coordinate3 { point [...] }` + `IndexedFaceSet { coordIndex }`
  con la geometria corrente (VRML 1.0);
* `Transform` con `translation`, `rotation` (asse + angolo, radianti) e `scale`;
* `DEF <nome>`, che diventa il nome del corpo, e `USE <nome>` per i nodi ripetuti.

Quello che **non** si legge, e viene detto invece di essere approssimato: le
primitive parametriche (`Box`, `Sphere`, `Cylinder`, `Cone`), `Extrusion` ed
`ElevationGrid`. Un file fatto solo di quelle solleva un errore che le nomina: è
una mesh che non c'è, non una mesh vuota.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from core.mesh.mesh import Mesh, MeshNonLeggibile, costruisci, ventaglio

#: Nodi con geometria che questo lettore non sa trasformare in triangoli.
NON_SUPPORTATI = ("Box", "Sphere", "Cylinder", "Cone", "Extrusion", "ElevationGrid",
                  "Text", "PointSet", "IndexedLineSet")

_TOKEN = re.compile(rb"[\{\}\[\]]|[^\s\{\}\[\],]+")


def load_wrl(path: str | Path) -> Mesh:
    path = Path(path)
    testo = path.read_bytes()
    if not testo.lstrip()[:6].upper().startswith(b"#VRML"):
        raise MeshNonLeggibile(f"{path}: manca l'intestazione `#VRML`")
    token = [t.decode("utf-8", errors="replace")
             for t in _TOKEN.findall(_senza_commenti(testo))]

    lettore = _Lettore(path)
    lettore.nodo(token, 0, np.eye(4), None)
    if not lettore.faces:
        trovati = sorted(lettore.saltati)
        if trovati:
            raise MeshNonLeggibile(
                f"{path}: nessun IndexedFaceSet. Il file contiene {', '.join(trovati)}, "
                f"che questo lettore non converte in triangoli: riesportare la scena "
                f"come mesh (IndexedFaceSet), oppure caricare un OBJ, STL o PLY.")
        raise MeshNonLeggibile(f"{path}: nessuna geometria leggibile nella scena VRML")
    return costruisci(lettore.vertices, lettore.faces, source=path,
                      group_names=tuple(lettore.nomi), face_group=lettore.face_group,
                      format="wrl")


def _senza_commenti(dati: bytes) -> bytes:
    """`#` commenta fino a fine riga — tranne nella prima, che è l'intestazione."""
    righe = dati.split(b"\n")
    return b"\n".join([righe[0]] + [r.split(b"#")[0] for r in righe[1:]])


class _Lettore:
    """Percorre l'albero dei nodi accumulando triangoli in coordinate di scena."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.vertices: list[tuple[float, float, float]] = []
        self.faces: list[tuple[int, int, int]] = []
        self.face_group: list[int] = []
        self.nomi: list[str] = []
        self.saltati: set[str] = set()
        #: Nodi con un `DEF`, per risolvere `USE`: nome -> (indice del token, matrice).
        self.definiti: dict[str, int] = {}

    # -- percorso dell'albero ---------------------------------------------

    def nodo(self, tk: list[str], i: int, M: np.ndarray, nome: str | None) -> int:
        """Legge i token da `i` fino alla fine del blocco corrente. Ritorna la posizione."""
        while i < len(tk):
            t = tk[i]
            if t == "}" or t == "]":
                return i + 1
            if t == "DEF" and i + 1 < len(tk):
                self.definiti[tk[i + 1]] = i + 2
                nome, i = tk[i + 1], i + 2
                continue
            if t == "USE" and i + 1 < len(tk):
                salto = self.definiti.get(tk[i + 1])
                if salto is not None:
                    self.nodo(tk, salto, M, tk[i + 1])
                i += 2
                continue
            if t == "Transform" or t == "Separator":       # Separator = VRML 1.0
                i = self._transform(tk, i + 1, M, nome)
                nome = None
                continue
            if t == "IndexedFaceSet":
                i = self._face_set(tk, i + 1, M, nome)
                nome = None
                continue
            if t in NON_SUPPORTATI:
                self.saltati.add(t)
            if t == "{" or t == "[":
                i = self.nodo(tk, i + 1, M, nome)
                continue
            i += 1
        return i

    def _transform(self, tk: list[str], i: int, M: np.ndarray, nome: str | None) -> int:
        """Un Transform: si leggono i campi, si compone la matrice, si scende."""
        if i < len(tk) and tk[i] == "{":
            i += 1
        traslazione = np.zeros(3)
        scala = np.ones(3)
        rotazione = None
        while i < len(tk) and tk[i] != "}":
            campo = tk[i]
            if campo == "translation":
                traslazione, i = _numeri(tk, i + 1, 3)
            elif campo == "scaleFactor" or campo == "scale":
                scala, i = _numeri(tk, i + 1, 3)
            elif campo == "rotation":
                r, i = _numeri(tk, i + 1, 4)
                rotazione = r
            elif campo == "children" or campo == "child":
                i = self.nodo(tk, i + 1, _componi(M, traslazione, rotazione, scala), nome)
            else:
                # In VRML 1.0 i figli di un Separator sono nodi fratelli, non un
                # campo `children`: si scende con la matrice composta finora.
                i = self._figlio(tk, i, _componi(M, traslazione, rotazione, scala), nome)
        return i + 1

    def _figlio(self, tk: list[str], i: int, M: np.ndarray, nome: str | None) -> int:
        t = tk[i]
        if t in ("Transform", "Separator"):
            return self._transform(tk, i + 1, M, nome)
        if t == "IndexedFaceSet":
            return self._face_set(tk, i + 1, M, nome)
        if t == "DEF" and i + 1 < len(tk):
            self.definiti[tk[i + 1]] = i + 2
            return self._figlio(tk, i + 2, M, tk[i + 1])
        if t in NON_SUPPORTATI:
            self.saltati.add(t)
        if t == "{" or t == "[":
            return self.nodo(tk, i + 1, M, nome)
        if t == "Coordinate3":
            return self._coordinate3(tk, i + 1, M)
        return i + 1

    # -- geometria ---------------------------------------------------------

    def _coordinate3(self, tk: list[str], i: int, M: np.ndarray) -> int:
        """VRML 1.0: le coordinate stanno in un nodo a sé, valido per i fratelli."""
        if i < len(tk) and tk[i] == "{":
            i += 1
        while i < len(tk) and tk[i] != "}":
            if tk[i] == "point":
                self._punti_correnti, i = _lista_numeri(tk, i + 1)
            else:
                i += 1
        return i + 1

    _punti_correnti: list[float] = []

    def _face_set(self, tk: list[str], i: int, M: np.ndarray, nome: str | None) -> int:
        if i < len(tk) and tk[i] == "{":
            i += 1
        punti: list[float] | None = None
        indici: list[float] | None = None
        while i < len(tk) and tk[i] != "}":
            campo = tk[i]
            if campo == "coord":
                punti, i = self._coord(tk, i + 1)
            elif campo == "point":                       # Coordinate inline
                punti, i = _lista_numeri(tk, i + 1)
            elif campo == "coordIndex":
                indici, i = _lista_numeri(tk, i + 1)
            else:
                i += 1
        if punti is None:
            punti = list(self._punti_correnti)           # VRML 1.0: Coordinate3 fratello
        if punti and indici:
            self._aggiungi(punti, indici, M, nome)
        return i + 1

    def _coord(self, tk: list[str], i: int) -> tuple[list[float], int]:
        """`coord Coordinate { point [...] }`, oppure `coord USE <nome>`."""
        while i < len(tk) and tk[i] in ("Coordinate", "DEF", "{"):
            if tk[i] == "DEF" and i + 1 < len(tk):
                self.definiti[tk[i + 1]] = i + 2
                i += 2
                continue
            i += 1
        if i < len(tk) and tk[i] == "USE" and i + 1 < len(tk):
            salto = self.definiti.get(tk[i + 1])
            if salto is not None:
                punti, _ = self._coord(tk, salto)
                return punti, i + 2
            return [], i + 2
        punti: list[float] = []
        while i < len(tk) and tk[i] != "}":
            if tk[i] == "point":
                punti, i = _lista_numeri(tk, i + 1)
            else:
                i += 1
        return punti, i + 1

    def _aggiungi(self, punti: list[float], indici: list[float],
                  M: np.ndarray, nome: str | None) -> None:
        p = np.asarray(punti, dtype=float)
        if p.size % 3:
            raise MeshNonLeggibile(
                f"{self.path}: un `point` ha {p.size} numeri, non multiplo di 3")
        p = p.reshape(-1, 3)
        p = (M[:3, :3] @ p.T).T + M[:3, 3]

        base = len(self.vertices)
        self.vertices.extend(map(tuple, p))
        gruppo = -1
        if nome:
            self.nomi.append(nome)
            gruppo = len(self.nomi) - 1

        faccia: list[int] = []
        for v in indici:
            k = int(v)
            if k < 0:                                    # -1 chiude la faccia
                if len(faccia) >= 3:
                    for tri in ventaglio([base + j for j in faccia]):
                        self.faces.append(tri)
                        self.face_group.append(gruppo)
                faccia = []
            else:
                faccia.append(k)
        if len(faccia) >= 3:                             # ultima faccia senza -1
            for tri in ventaglio([base + j for j in faccia]):
                self.faces.append(tri)
                self.face_group.append(gruppo)


# ---------------------------------------------------------------- numeri


def _componi(M: np.ndarray, traslazione, rotazione, scala) -> np.ndarray:
    """Matrice 4x4 del figlio: prima la scala, poi la rotazione, poi la traslazione."""
    R = np.eye(3)
    if rotazione is not None and len(rotazione) == 4:
        asse = np.asarray(rotazione[:3], dtype=float)
        norma = np.linalg.norm(asse)
        if norma > 1e-12:
            R = _rodrigues(asse / norma, float(rotazione[3]))
    L = np.eye(4)
    L[:3, :3] = R @ np.diag(np.asarray(scala, dtype=float))
    L[:3, 3] = np.asarray(traslazione, dtype=float)
    return M @ L


def _rodrigues(u: np.ndarray, angolo: float) -> np.ndarray:
    """Rotazione attorno a un asse unitario, angolo in radianti (convenzione VRML)."""
    K = np.array([[0.0, -u[2], u[1]], [u[2], 0.0, -u[0]], [-u[1], u[0], 0.0]])
    return np.eye(3) + math.sin(angolo) * K + (1.0 - math.cos(angolo)) * (K @ K)


def _numeri(tk: list[str], i: int, quanti: int) -> tuple[np.ndarray, int]:
    fuori: list[float] = []
    while i < len(tk) and len(fuori) < quanti:
        try:
            fuori.append(float(tk[i]))
        except ValueError:
            break
        i += 1
    while len(fuori) < quanti:
        fuori.append(0.0)
    return np.asarray(fuori), i


def _lista_numeri(tk: list[str], i: int) -> tuple[list[float], int]:
    """Il contenuto numerico di un `[ ... ]`, o un solo numero se le parentesi mancano."""
    fuori: list[float] = []
    if i < len(tk) and tk[i] == "[":
        i += 1
        while i < len(tk) and tk[i] != "]":
            try:
                fuori.append(float(tk[i]))
            except ValueError:
                pass
            i += 1
        return fuori, i + 1
    while i < len(tk):
        try:
            fuori.append(float(tk[i]))
        except ValueError:
            break
        i += 1
    return fuori, i
