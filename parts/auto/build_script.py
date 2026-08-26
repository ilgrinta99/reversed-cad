"""Costruttore parametrico generico. Girato headless da core.freecad.runner.

Riceve una ricetta già verificata — ogni numero viene dal registro delle quote,
cioè è misurato dalla mesh o approvato dall'utente — e la esegue. Qui non si
decide e non si stima niente: se un parametro manca, la ricetta non lo conteneva,
e il pezzo esce senza quella feature invece che con una inventata.

Il repertorio è dichiarato e finito: prisma, raccordo verticale, cavità, cupole
(paraboloidi ellittici) e fori cilindrici, anche ad asse inclinato. È il limite
che l'analisi comunica all'utente sotto forma di feature «non ricostruibili».
"""

import json
import math
import os
import sys

# FreeCAD azzera PYTHONPATH: la radice del repo va rimessa a mano su sys.path.
sys.path.insert(0, os.environ["TEISER_REPO_ROOT"])

import FreeCAD  # noqa: E402,F401
import Part  # noqa: E402
from FreeCAD import Matrix, Rotation, Vector  # noqa: E402

from core.freecad.script import arg_path, done  # noqa: E402

ASSI = {"X": Vector(1, 0, 0), "Y": Vector(0, 1, 0), "Z": Vector(0, 0, 1)}


def paraboloide(altezza, semi_u, semi_v):
    """Cupola: paraboloide ellittico con il vertice nell'origine e l'asse +X.

    Il profilo è una parabola vera, non un arco di cerchio né una spline
    approssimata: Y² = 4·F·X con F = ¼ passa per (0,0) e (1,1), cioè descrive
    esattamente X = r² sul cerchio unitario. Si rivoluziona attorno a +X e poi si
    scalano i tre assi sulle quote misurate — altezza lungo l'asse, semiassi del
    bordo in trasversale. La scala anisotropa trasforma la superficie di
    rivoluzione in una B-spline: è la stessa forma, scritta in un'altra base.
    """
    parabola = Part.Parabola()
    parabola.Focal = 0.25
    profilo = parabola.toShape(0.0, 1.0)                 # (0,0,0) → (1,1,0)
    bordo = Part.makeLine(Vector(1, 1, 0), Vector(1, 0, 0))
    guscio = Part.Shell(profilo.revolve(Vector(0, 0, 0), Vector(1, 0, 0), 360).Faces
                        + bordo.revolve(Vector(0, 0, 0), Vector(1, 0, 0), 360).Faces)
    scala = Matrix()
    scala.scale(float(altezza), float(semi_u), float(semi_v))
    return Part.Solid(guscio).transformGeometry(scala)


def cupola_orientata(cap):
    """La cupola nella posizione misurata: bordo sul piano, vertice che sporge.

    `centro` è il centro del *bordo*, e il verso dice da che parte sta il vertice.
    Il solido nasce con il vertice nell'origine e il bordo a +X: si ruota +X sulla
    direzione vertice → bordo e si porta l'origine dove va il vertice.
    """
    asse = str(cap["axis"])
    verso = 1.0 if float(cap.get("verso", 1.0)) >= 0 else -1.0
    u_nome, v_nome = [k for k in "XYZ" if k != asse]
    altezza = float(cap["altezza"])
    solido = paraboloide(altezza, cap["semi"][u_nome], cap["semi"][v_nome])

    e = ASSI[asse]
    dal_vertice_al_bordo = Vector(e.x * verso, e.y * verso, e.z * verso)
    centro = Vector(*(float(v) for v in cap["centro"]))
    vertice = centro - Vector(dal_vertice_al_bordo.x * altezza,
                              dal_vertice_al_bordo.y * altezza,
                              dal_vertice_al_bordo.z * altezza)
    solido.Placement = FreeCAD.Placement(
        vertice, Rotation(Vector(1, 0, 0), dal_vertice_al_bordo))
    return solido

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

    # Le cupole si fondono *dopo* la cavità e *prima* dei fori: una cupola è
    # materiale che sporge dalla parete, e i fori che la attraversano devono
    # trovarcela.
    for cap in body.get("caps", []):
        cupola = cupola_orientata(cap)
        solid = solid.fuse(cupola).removeSplitter()
        semi = " x ".join(f"{float(v):.3f}" for v in cap["semi"].values())
        print(f"  cupola asse {cap['axis']} semiassi {semi} "
              f"altezza {float(cap['altezza']):.3f}")

    for bore in body.get("bores", []):
        diameter = float(bore["diameter"])
        depth = float(bore["depth"])
        centre = Vector(*(float(v) for v in bore["center"]))
        direction = bore.get("direction")
        if direction:
            axis = Vector(*(float(v) for v in direction))
        else:
            axis = ASSI.get(bore.get("axis"), Vector(0, 0, 1))
        axis = axis.normalize()
        lungo = depth + 1.0
        start = centre - Vector(axis.x * lungo / 2.0, axis.y * lungo / 2.0,
                                axis.z * lungo / 2.0)
        solid = solid.cut(Part.makeCylinder(diameter / 2.0, lungo, start, axis))
        etichetta = bore.get("axis") or (
            "inclinato %.1f°" % math.degrees(math.acos(min(1.0, max(
                abs(axis.x), abs(axis.y), abs(axis.z))))))
        print(f"  foro Ø{diameter:.3f} asse {etichetta} in "
              f"({centre.x:.3f}, {centre.y:.3f}, {centre.z:.3f})")

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
