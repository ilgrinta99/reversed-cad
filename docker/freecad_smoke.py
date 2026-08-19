"""Smoke test FreeCAD headless — gira nel build dell'immagine e in CI.

Verifica quel che serve davvero alla pipeline, non solo che l'import passi:
  * FreeCAD, Part e TechDraw importabili senza display;
  * costruzione di un solido e scrittura di STEP/STL;
  * `optimalBoundingBox()` disponibile e più stretto di `BoundBox` su una BSpline
    (la trappola documentata nel BUILD-LOG);
  * uscita pulita del processo.

Uso:  FreeCAD -c docker/freecad_smoke.py < /dev/null
"""

import sys
import tempfile
from pathlib import Path

import FreeCAD  # noqa: F401  (import obbligatorio prima di Part)
import Part

print(f"FreeCAD {FreeCAD.Version()[0]}.{FreeCAD.Version()[1]}.{FreeCAD.Version()[2]}")
print(f"python  {sys.version.split()[0]}")

failures: list[str] = []

try:
    import TechDraw  # noqa: F401

    print("TechDraw   ok")
except Exception as exc:  # pragma: no cover - dipende dal pacchetto
    failures.append(f"TechDraw non importabile: {exc}")

box = Part.makeBox(10, 20, 30)
if abs(box.Volume - 6000.0) > 1e-6:
    failures.append(f"volume del box errato: {box.Volume}")
else:
    print("solidi     ok")

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    box.exportStep(str(tmp / "smoke.step"))
    box.exportStl(str(tmp / "smoke.stl"))
    for name in ("smoke.step", "smoke.stl"):
        if not (tmp / name).is_file() or (tmp / name).stat().st_size == 0:
            failures.append(f"export {name} non prodotto")
    else:
        print("export     ok (STEP, STL)")

# BoundBox mente sulle BSpline: restituisce l'inviluppo dei punti di controllo.
# Qui serve solo accertare che optimalBoundingBox() esista e non sia più larga.
pts = [
    FreeCAD.Vector(0, 0, 0),
    FreeCAD.Vector(10, 30, 0),
    FreeCAD.Vector(20, -30, 0),
    FreeCAD.Vector(30, 0, 0),
]
spline = Part.BSplineCurve()
spline.interpolate(pts)
edge = spline.toShape()
try:
    naive = edge.BoundBox
    optimal = edge.optimalBoundingBox()
    print(f"BoundBox   naive YLen={naive.YLength:.3f}  optimal YLen={optimal.YLength:.3f}")
    if optimal.YLength > naive.YLength + 1e-9:
        failures.append("optimalBoundingBox() più larga di BoundBox: risultato inatteso")
except AttributeError as exc:
    failures.append(f"optimalBoundingBox() non disponibile: {exc}")

if failures:
    print("\nSMOKE TEST FALLITO:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print("\nSMOKE TEST OK")
