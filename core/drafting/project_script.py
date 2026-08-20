# -*- coding: utf-8 -*-
"""Proietta i solidi di un modello e scrive gli spigoli 2D in JSON. Gira sotto FreeCAD.

Riceve due percorsi: la specifica delle viste e il file da scrivere. Non sa che
tavola verra' fuori — non impagina, non quota, non conosce il pezzo. Serve solo a
portare fuori dal processo FreeCAD il risultato dell'HLR, che e' l'unica cosa per
cui FreeCAD e' insostituibile.

Specifica (JSON):
    {"shapes": {"nome": "/percorso/corpo.step", ...},
     "views":  [{"id": "...", "shape": "nome", "u": [..], "w": [..],
                 "hidden": true, "section": {"point": [..], "normal": [..]}}, ...]}

Uscita (JSON):
    {"shapes": {"nome": {"bbox": [x0,y0,z0,x1,y1,z1], "volume": v}},
     "views":  {"id": {"visibili": [...], "nascosti": [...], "sezione": [[...]],
                       "bbox": [x0,y0,x1,y1]}}}
"""
import json
import os
import sys

# FreeCAD azzera PYTHONPATH: la radice del repo va rimessa a mano su sys.path.
sys.path.insert(0, os.environ["TEISER_REPO_ROOT"])

import Part  # noqa: E402

from core.drafting import hlr  # noqa: E402
from core.freecad.script import arg_path, done  # noqa: E402

spec = json.loads(arg_path(0, "specifica delle viste").read_text())
out_path = arg_path(1, "file JSON di uscita")

shapes = {}
info = {}
for nome, percorso in spec["shapes"].items():
    shape = Part.Shape()
    shape.read(str(percorso))
    shapes[nome] = shape
    # BoundBox mente sulle BSpline: la misura di controllo si fa sempre con
    # optimalBoundingBox(), anche dove non ce ne sono.
    box = shape.optimalBoundingBox()
    info[nome] = {
        "bbox": [box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax],
        "volume": shape.Volume,
    }
    print("%s: ingombro %.3f x %.3f x %.3f" % (nome, box.XLength, box.YLength, box.ZLength))

viste = {}
for vista in spec["views"]:
    shape = shapes[vista["shape"]]
    sez = vista.get("section")
    viste[vista["id"]] = hlr.proietta_json(
        shape, vista["u"], vista["w"],
        sez=(sez["point"], sez["normal"]) if sez else None,
        nascosti=vista.get("hidden", True),
    )
    n_vis = len(viste[vista["id"]]["visibili"])
    n_nas = len(viste[vista["id"]]["nascosti"])
    print("vista %s: %d spigoli visibili, %d nascosti%s"
          % (vista["id"], n_vis, n_nas, ", sezionata" if sez else ""))

out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps({"shapes": info, "views": viste}))
print("scritte %d viste in %s" % (len(viste), out_path.name))

done()
