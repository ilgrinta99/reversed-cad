"""Pezzi disponibili. Importare questo package li registra in `core.plugin.registry`.

Aggiungere un pezzo = aggiungere una cartella qui e una riga sotto. Il backend web
non cambia.
"""

from parts.demo_box import plugin as demo_box  # noqa: F401
from parts.teiser import plugin as teiser  # noqa: F401

__all__ = ["demo_box", "teiser"]
