"""Un solo ingresso per tutte le mesh: `load_mesh(percorso)`.

I quattro formati che si possono caricare — OBJ, STL, PLY, WRL — non sono
equivalenti, e la differenza conta per come il pezzo verrà letto:

| formato | topologia | nomi dei corpi | note |
|---|---|---|---|
| `.obj` | dichiarata | gruppi `o` / `g` | il formato in cui Tinkercad esporta |
| `.stl` | **assente** | solo ASCII, `solid` | i vertici si saldano al caricamento |
| `.ply` | dichiarata | nessuno | ASCII e binario, entrambi gli endian |
| `.wrl` | dichiarata | `DEF` | scena con Transform: si applicano |

Nessuno dei quattro porta un'unità di misura. Il progetto lavora in millimetri e
li assume tali: se un file è in metri o in pollici, l'analisi lo misurerà
coerentemente sbagliato, e non c'è modo di accorgersene dal file. È una cosa da
sapere prima di caricare, non un'ambiguità che il programma possa risolvere.

Un'altra differenza che conta e non si vede: **STL e PLY binario scrivono le
coordinate in precisione singola.** Lo stesso pezzo esportato in OBJ e in STL dà
quote che divergono nella quinta cifra decimale — misurato sulla mesh di
riferimento del progetto: scarto massimo 2·10⁻⁵ mm sulle quote, 4·10⁻⁶ mm sui
vertici. È due ordini di grandezza sotto la tolleranza con cui il registro
distingue due numeri, quindi non cambia nessuna decisione; ma se una quota
cambia di un capello fra due caricamenti dello stesso pezzo, la causa è questa e
non un errore di misura.
"""

from __future__ import annotations

from pathlib import Path

from core.mesh.mesh import Mesh, MeshNonLeggibile
from core.mesh.obj import load_obj
from core.mesh.ply import load_ply
from core.mesh.stl import load_stl
from core.mesh.wrl import load_wrl

#: Suffisso -> lettore. È anche l'elenco che l'API accetta in caricamento: uno
#: solo, così non può succedere che il backend prometta un formato che il
#: caricatore non legge.
LETTORI = {
    ".obj": load_obj,
    ".stl": load_stl,
    ".ply": load_ply,
    ".wrl": load_wrl,
}

SUFFISSI = frozenset(LETTORI)

#: Come si chiamano, per i messaggi all'utente.
ELENCO = ", ".join(sorted(SUFFISSI))


def load_mesh(path: str | Path) -> Mesh:
    """Carica una mesh scegliendo il lettore dal suffisso del file.

    Il suffisso è l'unico criterio: annusare il contenuto per indovinare il
    formato sembra generoso, ma trasforma un file rinominato per sbaglio in un
    errore che salta fuori tre passi più in là, sotto forma di quote assurde.
    """
    path = Path(path)
    lettore = LETTORI.get(path.suffix.lower())
    if lettore is None:
        raise MeshNonLeggibile(
            f"formato non supportato: {path.suffix or path.name!r}. "
            f"Formati letti: {ELENCO}.")
    return lettore(path)
