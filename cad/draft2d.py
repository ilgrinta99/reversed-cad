# -*- coding: utf-8 -*-
"""Guscio di compatibilita': il motore di disegno vive in `core/drafting/sheet.py`.

Il modulo era qui quando la tavola era una cosa sola con il pezzo. Ora il motore
e' generico (nessun numero del TAISER dentro) e per la regola di collocazione di
`docs/CONVENTIONS.md` sta in `core/`. Questo file resta perche' `cad/make_drawing.py`
e i comandi documentati continuino a funzionare senza modifiche.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.drafting.sheet import *          # noqa: F401,F403
from core.drafting.sheet import (          # noqa: F401  (non esportati da *)
    _arco_bezier, _clip_segmento, _dentro,
)
