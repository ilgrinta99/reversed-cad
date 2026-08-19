"""Script FreeCAD del pezzo demo. Girato headless da core.freecad.runner.

Gli argomenti arrivano dall'ambiente, non da sys.argv: FreeCAD tratterebbe gli
argomenti posizionali come file da aprire. Vedi core/freecad/runner.py.

Riceve i valori già verificati dal registro delle quote: qui non si decide nulla e
non si stima nulla, si costruisce.
"""

import json
import os
import sys

# FreeCAD azzera PYTHONPATH: la radice del repo va rimessa a mano su sys.path,
# altrimenti `core.*` non è importabile. Vedi core/freecad/runner.py, trappola 4.
sys.path.insert(0, os.environ["TEISER_REPO_ROOT"])

import FreeCAD  # noqa: E402,F401
import Part  # noqa: E402

from core.freecad.script import arg_path, done  # noqa: E402

params_path = arg_path(0, "params.json")
out_dir = arg_path(1, "cartella di uscita")

p = json.loads(params_path.read_text())
out_dir.mkdir(parents=True, exist_ok=True)

length, width, height = p["length"], p["width"], p["height"]
print(f"box {length:.3f} x {width:.3f} x {height:.3f} mm")

solid = Part.makeBox(length, width, height)

# BoundBox mente sulle BSpline; qui non ce ne sono, ma la misura di controllo si
# fa comunque con optimalBoundingBox() — è l'abitudine che evita l'errore altrove.
bb = solid.optimalBoundingBox()
print(f"ingombro verificato: {bb.XLength:.3f} x {bb.YLength:.3f} x {bb.ZLength:.3f}")

solid.exportStep(str(out_dir / "model.step"))
solid.exportStl(str(out_dir / "model.stl"))
print(f"volume: {solid.Volume:.3f} mm3")
print("scritti model.step, model.stl")

done()
