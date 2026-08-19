# -*- coding: utf-8 -*-
"""FASE 5 - confronto geometrico fra il modello parametrico e la mesh OBJ.

Per un campione di vertici della mesh calcola la distanza esatta alla superficie
del solido ricostruito (Part.Vertex.distToShape) e riporta la distribuzione,
evidenziando le zone con scostamento oltre soglia.

    /Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c tools/compare_model_mesh.py < /dev/null
"""
import os, sys, time, json, random

import FreeCAD as App
import Part
from FreeCAD import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = json.load(open(os.path.join(ROOT, 'cad', 'params.json')))
DX = P['_offset_mesh_modello']['dx']; DY = P['_offset_mesh_modello']['dy']
SX_LID = P['coperchio']['piastra']['L'] / P['coperchio']['piastra']['_L_mesh']
N = int(os.environ.get('TAISER_N', '900'))
SOGLIA_PIANA, SOGLIA_CURVA = 0.10, 0.50      # docs/CONVENTIONS.md

def load_obj(path):
    objs, cur = {}, None
    V = []
    for line in open(path):
        w = line.split()
        if not w: continue
        if w[0] == 'o': cur = w[1]; objs[cur] = []
        elif w[0] == 'v':
            V.append((float(w[1]), float(w[2]), float(w[3])))
        elif w[0] == 'f':
            for tk in w[1:]: objs[cur].append(int(tk.split('/')[0]) - 1)
    return V, {k: sorted(set(v)) for k, v in objs.items()}

V, objs = load_obj(os.path.join(ROOT, 'input', 'model.obj'))

def report(nome, solido, idx, tomodel, zone):
    random.seed(12345)
    pick = idx if len(idx) <= N else random.sample(idx, N)
    t0 = time.time()
    res = []
    for i in pick:
        p = tomodel(V[i])
        d = Part.Vertex(p[0], p[1], p[2]).distToShape(solido)[0]
        res.append((d, p))
    res.sort(key=lambda r: -r[0])
    d = [r[0] for r in res]
    n = len(d)
    q = lambda f: d[int((1 - f) * (n - 1))]
    print('\n=== %s ===  %d vertici campionati su %d  (%.1f s)'
          % (nome, n, len(idx), time.time() - t0))
    print('   media %.4f   mediana %.4f   p90 %.4f   p99 %.4f   max %.4f  (mm)'
          % (sum(d) / n, q(0.50), q(0.90), q(0.99), d[0]))
    for s, lab in ((SOGLIA_PIANA, 'oltre 0.10'), (SOGLIA_CURVA, 'oltre 0.50')):
        k = sum(1 for x in d if x > s)
        print('   %s mm: %d vertici (%.1f%%)' % (lab, k, 100.0 * k / n))
    print('   peggiori 8:')
    for dd, p in res[:8]:
        z = next((nm for nm, f in zone if f(p)), 'corpo/altro')
        print('      %.4f mm  in (%8.3f, %8.3f, %8.3f)   [%s]' % (dd, p[0], p[1], p[2], z))

doc = App.openDocument(os.path.join(ROOT, 'output', 'taiser.FCStd'))
scatola = doc.getObject('Scatola').Shape
coperchio = doc.getObject('Coperchio').Shape.copy()
coperchio.translate(Vector(0, 0, -P['scatola']['corpo']['H']))   # riporto a z=0

cu = P['scatola']['cupola']
zone_box = [
    ('raccordo base',    lambda p: p[2] < 1.6),
    ('cupola',           lambda p: p[0] > cu['x0'] - 0.01),
    ('colonnine',        lambda p: abs(p[0]) > 30.0 and abs(p[1]) > 12.0 and p[2] > 14.0),
    ('nervature',        lambda p: p[2] > 23.0 and p[1] < -14.0 and abs(p[0]) < 12.0),
    ('tasca X-',         lambda p: p[0] < -36.2),
    ('asola frontale',   lambda p: p[1] < -20.5 and 21.0 < p[2] < 26.5),
]
zone_lid = [
    ('raccordo base',    lambda p: p[2] < 1.85),
    ('asole',            lambda p: abs(p[0]) > 31.5 and abs(p[1]) > 14.5),
    ('tasche',           lambda p: p[2] > 0.9),
]
report('SCATOLA', scatola, objs['obj_0'], lambda v: (v[0] + DX, v[1] + DY, v[2]), zone_box)
report('COPERCHIO', coperchio, objs['obj_1'],
       lambda v: ((v[0] + 9.0) * SX_LID, v[1] - 56.833, v[2]), zone_lid)
print('\nSoglie da docs/CONVENTIONS.md: 0.10 mm su feature piane, 0.50 mm su curve.')
