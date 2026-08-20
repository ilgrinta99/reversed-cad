"""Pezzi disponibili. Importare questo package li registra in `core.plugin.registry`.

`auto` sta in cima perché è il percorso predefinito: chi carica un OBJ non deve
scegliere niente, la mesh viene misurata così com'è. Gli altri sono pipeline
scritte su misura per un pezzo noto, raggiungibili indicandone l'id.
"""

from parts.auto import plugin as auto  # noqa: F401
from parts.demo_box import plugin as demo_box  # noqa: F401
from parts.teiser import plugin as teiser  # noqa: F401

__all__ = ["auto", "demo_box", "teiser"]
