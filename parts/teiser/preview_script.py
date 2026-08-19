"""STL leggero per l'anteprima nel browser.

`cad/build_model.py` esporta STL a tassellazione fine: 23 MB per l'assieme, giusti
per la stampa e inutilizzabili per una pagina web. Questo script riapre il
documento appena costruito e ne esporta una versione grossolana, solo per la
visualizzazione. Gli STL di consegna non vengono toccati.
"""

import os
import sys

sys.path.insert(0, os.environ["TEISER_REPO_ROOT"])

import FreeCAD as App  # noqa: E402
import Mesh  # noqa: E402

from core.freecad.script import arg_path, args, done  # noqa: E402

out_dir = arg_path(0, "cartella del run")
deviazione = float(args()[1]) if len(args()) > 1 else 0.25

doc = App.openDocument(str(out_dir / "taiser.FCStd"))
pezzi = [doc.getObject("Scatola"), doc.getObject("Coperchio")]

mesh = Mesh.Mesh()
for oggetto in pezzi:
    # tessellate() restituisce (vertici, triangoli) con la deviazione richiesta:
    # più alta = meno triangoli. 0.25 mm è invisibile a schermo e divide per ~20.
    vertici, facce = oggetto.Shape.tessellate(deviazione)
    mesh.addMesh(Mesh.Mesh([[vertici[i] for i in f] for f in facce]))

destinazione = out_dir / "preview.stl"
mesh.write(str(destinazione))
print("preview.stl: %d triangoli, %.1f kB"
      % (mesh.CountFacets, os.path.getsize(destinazione) / 1024.0))

done()
