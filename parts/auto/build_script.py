"""Costruttore parametrico generico. Girato headless da core.freecad.runner.

Riceve una ricetta già verificata — ogni numero viene dal registro delle quote,
cioè è misurato dalla mesh o approvato dall'utente — e la esegue. Qui non si
decide e non si stima niente: se un parametro manca, la ricetta non lo conteneva,
e il pezzo esce senza quella feature invece che con una inventata.

Il repertorio è dichiarato e finito: prisma, raccordo verticale, cavità, fori
cilindrici. È il limite che l'analisi comunica all'utente sotto forma di feature
«non ricostruibili».
"""

import json
import os
import sys

# FreeCAD azzera PYTHONPATH: la radice del repo va rimessa a mano su sys.path.
sys.path.insert(0, os.environ["TEISER_REPO_ROOT"])

import FreeCAD  # noqa: E402,F401
import Part  # noqa: E402
from FreeCAD import Vector  # noqa: E402

from core.freecad.script import arg_path, done  # noqa: E402

recipe_path = arg_path(0, "recipe.json")
out_dir = arg_path(1, "cartella di uscita")
out_dir.mkdir(parents=True, exist_ok=True)

recipe = json.loads(recipe_path.read_text())
solids = []

for body in recipe["bodies"]:
    ox, oy, oz = (float(v) for v in body["origin"])
    length, width, height = (float(v) for v in body["size"])
    solid = Part.makeBox(length, width, height, Vector(ox, oy, oz))
    print(f"{body['name']}: prisma {length:.3f} x {width:.3f} x {height:.3f}")

    radius = body.get("fillet")
    if radius:
        # Solo gli spigoli verticali: sono quelli che l'analisi misura come
        # arretramento delle facce in pianta.
        vertical = [e for e in solid.Edges
                    if abs(e.Vertexes[0].Point.z - e.Vertexes[-1].Point.z) > 1e-6]
        try:
            solid = solid.makeFillet(float(radius), vertical)
            print(f"  raccordo verticale R{float(radius):.3f} su {len(vertical)} spigoli")
        except Exception as exc:  # il raggio può essere incompatibile con la faccia
            print(f"  raccordo R{float(radius):.3f} non applicabile ({exc}): "
                  f"il prisma resta a spigoli vivi")

    cavity = body.get("cavity")
    if cavity:
        walls = cavity["walls"]
        x0 = ox + float(walls.get("X-min", 0.0))
        y0 = oy + float(walls.get("Y-min", 0.0))
        x1 = ox + length - float(walls.get("X-max", 0.0))
        y1 = oy + width - float(walls.get("Y-max", 0.0))
        floor = float(cavity["floor"])
        depth = float(cavity["depth"])
        if x1 > x0 and y1 > y0 and depth > 0.0:
            pocket = Part.makeBox(x1 - x0, y1 - y0, depth + 1.0,
                                  Vector(x0, y0, oz + floor))
            solid = solid.cut(pocket)
            print(f"  cavità {x1 - x0:.3f} x {y1 - y0:.3f} x {depth:.3f}, "
                  f"fondo a {floor:.3f}")

    for bore in body.get("bores", []):
        diameter = float(bore["diameter"])
        depth = float(bore["depth"])
        cx, cy, cz = (float(v) for v in bore["center"])
        axis = {"X": Vector(1, 0, 0), "Y": Vector(0, 1, 0)}.get(bore["axis"],
                                                                Vector(0, 0, 1))
        start = Vector(cx, cy, cz) - axis.multiply((depth + 1.0) / 2.0)
        cylinder = Part.makeCylinder(diameter / 2.0, depth + 1.0, start,
                                     Vector(*{"X": (1, 0, 0), "Y": (0, 1, 0)}.get(
                                         bore["axis"], (0, 0, 1))))
        solid = solid.cut(cylinder)
        print(f"  foro Ø{diameter:.3f} asse {bore['axis']} in "
              f"({cx:.3f}, {cy:.3f}, {cz:.3f})")

    solids.append(solid)

assembly = solids[0] if len(solids) == 1 else Part.makeCompound(solids)
# BoundBox mente sulle BSpline: la misura di controllo si fa sempre con
# optimalBoundingBox(), anche dove non ce ne sono.
box = assembly.optimalBoundingBox()
print(f"ingombro verificato: {box.XLength:.3f} x {box.YLength:.3f} x {box.ZLength:.3f}")

assembly.exportStep(str(out_dir / "model.step"))
assembly.exportStl(str(out_dir / "model.stl"))
for solid, body in zip(solids, recipe["bodies"]):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in body["name"])
    solid.exportStep(str(out_dir / f"{safe}.step"))
print(f"scritti model.step, model.stl e {len(solids)} corpi singoli")

done()
