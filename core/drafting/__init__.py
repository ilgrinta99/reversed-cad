"""Motore di disegno: dalla geometria proiettata ai file di tavola.

Tre pezzi, e il confine fra loro conta:

- `sheet.py` — le primitive e i tre backend (SVG, PDF, DXF). Nessuna dipendenza.
- `layout.py` — cornice, cartiglio, scale normalizzate, disposizione delle viste.
- `tavola.py` — il compositore: una specifica dichiarativa diventa fogli.
- `hlr.py` + `project_script.py` — l'unico punto che tocca FreeCAD, per la
  proiezione con rimozione delle linee nascoste. Girano dentro FreeCAD e passano
  il risultato come JSON, così tutto il resto resta eseguibile ovunque.

`hlr` non si importa da qui: importarlo fuori da FreeCAD fallirebbe, e questo
package deve restare importabile dal backend web.
"""

from core.drafting import layout, sheet, tavola  # noqa: F401
