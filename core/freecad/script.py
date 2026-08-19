"""Utilità per gli script che girano *dentro* FreeCAD.

FreeCAD azzera PYTHONPATH, quindi `core.*` non è importabile da solo. Ogni script
eseguito da `core.freecad.runner.run_script` inizia con questo prologo:

    import os, sys
    sys.path.insert(0, os.environ["TEISER_REPO_ROOT"])
    from core.freecad.script import arg_path, done

Questo modulo non importa FreeCAD: resta testabile con un interprete qualsiasi.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

#: Devono restare allineate a core/freecad/runner.py.
ARGS_ENV = "TEISER_ARGS"
ROOT_ENV = "TEISER_REPO_ROOT"
SUCCESS_SENTINEL = "TEISER_OK"


def args() -> list[str]:
    """Argomenti passati dal runner.

    Non si legge `sys.argv`: FreeCAD ci mette dentro il proprio binario e `-c`, e
    per giunta tenta di aprire gli argomenti posizionali come documenti.
    """
    raw = os.environ.get(ARGS_ENV)
    if not raw:
        return []
    return list(json.loads(raw))


def arg_path(index: int, what: str = "argomento") -> Path:
    values = args()
    try:
        return Path(values[index])
    except IndexError:
        raise SystemExit(
            f"{what} mancante in posizione {index}: ricevuti {values!r}. "
            f"Lo script va eseguito tramite core.freecad.runner.run_script()."
        ) from None


def done() -> None:
    """Ultima riga di ogni script: dichiara il successo.

    Serve perché FreeCAD esce con codice 0 anche dopo un'eccezione non catturata:
    senza questa riga il runner considera lo script fallito, ed è giusto così.
    """
    print(SUCCESS_SENTINEL)
