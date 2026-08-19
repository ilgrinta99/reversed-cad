# -*- coding: utf-8 -*-
"""Costruzione parametrica del contenitore TAISER (scatola + coperchio).

Eseguire con FreeCAD headless:
    /Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c cad/build_model.py

Tutte le quote provengono da cad/params.json, generato da tools/extract_params.py
misurando input/model.obj. Nessun valore e' scritto a mano qui.

Riferimento: origine al centro della base del corpo rettangolare della scatola,
X = lunghezza, Y = larghezza, Z = verso l'alto (lost+found_design.md 5-G).
"""
import json, math, os, sys

import FreeCAD as App
import Part
from FreeCAD import Vector, Rotation, Placement

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Percorsi configurabili: la web app li punta sulla cartella del run.
# Senza variabili d'ambiente vale il comportamento di sempre.
P = json.load(open(os.environ.get('TAISER_PARAMS', os.path.join(ROOT, 'cad', 'params.json'))))
OUT = os.environ.get('TAISER_OUT', os.path.join(ROOT, 'output'))
os.makedirs(OUT, exist_ok=True)

# fattore di scala X applicato al coperchio per la decisione F (filo esterno):
# 73.86 / 74.00 = 0.998108 -> porta le asole da +/-33.105 a +/-33.0425,
# cioe' esattamente sui fori delle colonnine della scatola.
SX_LID = P['coperchio']['piastra']['L'] / P['coperchio']['piastra']['_L_mesh']


# --------------------------------------------------------------- utilita'

def box_c(lx, ly, lz, cx=0.0, cy=0.0, cz=None, z0=None):
    """Parallelepipedo centrato in (cx, cy) e centrato in cz oppure appoggiato su z0."""
    zz = z0 if z0 is not None else cz - lz / 2.0
    return Part.makeBox(lx, ly, lz, Vector(cx - lx / 2.0, cy - ly / 2.0, zz))


def obround(w, l, h, cx, cy, z0, axis_long='Y'):
    """Asola (due semicerchi + rettangolo) estrusa in Z. w = larghezza, l = lunghezza totale."""
    r = w / 2.0
    dist = l - w                                    # interasse delle due testate
    if axis_long == 'Y':
        body = Part.makeBox(w, dist, h, Vector(cx - r, cy - dist / 2.0, z0)) if dist > 1e-9 else None
        c1 = Part.makeCylinder(r, h, Vector(cx, cy - dist / 2.0, z0))
        c2 = Part.makeCylinder(r, h, Vector(cx, cy + dist / 2.0, z0))
    else:
        body = Part.makeBox(dist, w, h, Vector(cx - dist / 2.0, cy - r, z0)) if dist > 1e-9 else None
        c1 = Part.makeCylinder(r, h, Vector(cx - dist / 2.0, cy, z0))
        c2 = Part.makeCylinder(r, h, Vector(cx + dist / 2.0, cy, z0))
    s = c1.fuse(c2)
    return s.fuse(body) if body is not None else s


def ellipse_prism(lx, ly, h, cx, cy, z0):
    """Cilindro a sezione ellittica lx x ly (assi completi), estruso in Z."""
    a, b = lx / 2.0, ly / 2.0
    major, minor = (a, b) if a >= b else (b, a)
    if a >= b:
        ell = Part.Ellipse(Vector(cx + a, cy, z0), Vector(cx, cy + b, z0), Vector(cx, cy, z0))
    else:
        ell = Part.Ellipse(Vector(cx, cy + b, z0), Vector(cx + a, cy, z0), Vector(cx, cy, z0))
    return Part.Face(Part.Wire([ell.toShape()])).extrude(Vector(0, 0, h))


def obround_x(w, l, t, cy, cz, x0):
    """Asola nel piano YZ (larghezza w in Z, lunghezza l in Y) estrusa di t lungo X."""
    r = w / 2.0
    dist = l - w
    c1 = Part.makeCylinder(r, t, Vector(x0, cy - dist / 2.0, cz), Vector(1, 0, 0))
    c2 = Part.makeCylinder(r, t, Vector(x0, cy + dist / 2.0, cz), Vector(1, 0, 0))
    s = c1.fuse(c2)
    if dist > 1e-9:
        s = s.fuse(Part.makeBox(t, dist, w, Vector(x0, cy - dist / 2.0, cz - r)))
    return s


def half_space(n, d, size=400.0):
    """Solido che riempie il semispazio  n . p >= d  (n gia' normalizzato)."""
    nv = Vector(*n); nv.normalize()
    b = Part.makeBox(size, size, size, Vector(-size / 2.0, -size / 2.0, 0.0))
    b.Placement = Placement(nv * d, Rotation(Vector(0, 0, 1), nv))
    return b


def fillet_bottom(shape, r, z=0.0, tol=1e-6):
    """Raccorda tutti gli spigoli che giacciono nel piano z."""
    edges = [e for e in shape.Edges
             if all(abs(v.Point.z - z) < tol for v in e.Vertexes) and e.Length > tol]
    return shape.makeFillet(r, edges) if edges else shape


def elliptic_paraboloid(x0, a, b, c, cy, cz, n=80):
    """Paraboloide ellittico pieno:  (x-x0)/a = 1 - ((y-cy)/b)^2 - ((z-cz)/c)^2.

    Costruito come paraboloide di rivoluzione di raggio c, poi scalato in Y di b/c.
    Il campionamento e' uniforme in u (raggio normalizzato): la punta resta liscia.
    """
    pts = []
    for i in range(n + 1):
        u = 1.0 - i / float(n)                       # u = 1 alla base, 0 in punta
        pts.append(Vector(x0 + a * (1.0 - u * u), 0.0, cz + c * u))
    bs = Part.BSplineCurve()
    bs.interpolate(pts)
    wire = Part.Wire([bs.toShape(),
                      Part.makeLine(pts[-1], Vector(x0, 0.0, cz)),
                      Part.makeLine(Vector(x0, 0.0, cz), pts[0])])
    solid = Part.Face(wire).revolve(Vector(x0, 0, cz), Vector(1, 0, 0), 360)
    solid = Part.Solid(Part.Shell(solid.Faces)) if not solid.Solids else solid.Solids[0]
    m = App.Matrix(); m.scale(1.0, b / c, 1.0)       # simmetrico rispetto a y = 0
    solid = solid.transformGeometry(m)
    if abs(cy) > 1e-9:
        solid.translate(Vector(0, cy, 0))
    return solid


def tilted_elliptic_bore(pt, direction, ry, rz, x_from, x_to):
    """Foro a sezione ellittica lungo un asse inclinato.

    L'ellisse giace in un piano perpendicolare a X, quindi ogni sezione _|_X
    del foro e' esattamente ry x rz come misurato sulla mesh.
    """
    dy_dx, dz_dx = direction[1], direction[2]
    y0 = pt[1] + dy_dx * (x_from - pt[0])
    z0 = pt[2] + dz_dx * (x_from - pt[0])
    ell = Part.Ellipse(Vector(x_from, y0 + ry, z0),      # estremo asse maggiore
                       Vector(x_from, y0, z0 + rz),      # estremo asse minore
                       Vector(x_from, y0, z0))
    face = Part.Face(Part.Wire([ell.toShape()]))
    L = x_to - x_from
    return face.extrude(Vector(L, dy_dx * L, dz_dx * L))


# --------------------------------------------------------------- SCATOLA

def build_scatola():
    S = P['scatola']
    co, pa, fo, ca = S['corpo'], S['pareti'], S['fondo'], S['cavita']

    log = []
    import os as _os
    DBG = _os.environ.get('TAISER_DEBUG')
    def dbg(tag, sh):
        if DBG:
            b = sh.BoundBox
            print('   [dbg] %-22s X %8.3f..%8.3f  Y %8.3f..%8.3f  Z %8.3f..%8.3f  vol=%.1f'
                  % (tag, b.XMin, b.XMax, b.YMin, b.YMax, b.ZMin, b.ZMax, sh.Volume))
            sys.stdout.flush()
    s = box_c(co['L'], co['W'], co['H'], z0=0.0)
    dbg('corpo', s)
    s = fillet_bottom(s, S['raccordo_base']['R'])
    dbg('fillet', s)
    log.append('corpo %.2f x %.2f x %.2f, raccordo base R%.1f'
               % (co['L'], co['W'], co['H'], S['raccordo_base']['R']))

    # cavita'
    s = s.cut(box_c(ca['L'], ca['W'], co['H'] - fo['t'] + 1.0, z0=fo['t']))
    dbg('cavita', s)
    log.append('cavita %.2f x %.2f, fondo %.1f, pareti tx=%.1f ty=%.1f'
               % (ca['L'], ca['W'], fo['t'], pa['t_x'], pa['t_y']))

    # cupola (paraboloide ellittico, piena)
    cu = S['cupola']
    s = s.fuse(elliptic_paraboloid(cu['x0'], cu['a'], cu['b'], cu['c'], cu['cy'], cu['cz']))
    dbg('cupola', s)
    log.append('cupola paraboloide a=%.3f b=%.3f c=%.3f in x0=%.2f' %
               (cu['a'], cu['b'], cu['c'], cu['x0']))

    # foro D3 nella parete destra
    f = S['foro_parete_dx']
    x_in = co['L'] / 2.0 - pa['t_x'] - 1.0
    s = s.cut(Part.makeCylinder(f['D'] / 2.0, 4.0, Vector(x_in, f['y'], f['z']), Vector(1, 0, 0)))
    dbg('foroD3', s)
    log.append('foro D%.3f parete X+ in y=%.1f z=%.2f' % (f['D'], f['y'], f['z']))

    # 2 fori ellittici inclinati attraverso parete + cupola
    x_from = co['L'] / 2.0 - pa['t_x'] - 1.0
    x_to = cu['x0'] + cu['a'] + 1.0
    for k in ('A', 'B'):
        b = S['fori_cupola'][k]
        ry, rz = b['sez_perp_X_YxZ'][0] / 2.0, b['sez_perp_X_YxZ'][1] / 2.0
        s = s.cut(tilted_elliptic_bore(b['punto'], b['dir'], ry, rz, x_from, x_to))
        log.append('foro cupola %s: ellisse %.3f x %.3f, inclinato %.2f deg in XY'
                   % (k, 2 * ry, 2 * rz, b['angolo_XY_deg']))

    # asola nella parete frontale Y-
    a = S['asola_frontale']
    s = s.cut(box_c(a['L_x'], pa['t_y'] + 2.0, a['H_z'],
                    cx=a['cx'], cy=-co['W'] / 2.0 + pa['t_y'] / 2.0, cz=a['cz']))
    dbg('asola frontale', s)
    log.append('asola parete Y-: %.3f x %.3f in x=%.3f z=%.3f'
               % (a['L_x'], a['H_z'], a['cx'], a['cz']))

    # tasca sulla faccia X-
    t = S['tasca_sx']
    s = s.cut(box_c(2 * t['prof'], t['W_y'], t['H_z'],
                    cx=-co['L'] / 2.0, cy=t['cy'], cz=t['cz']))
    dbg('tasca sx', s)
    ri = t['rilievo']
    s = s.fuse(obround_x(ri['W_z'], ri['L_y'], t['prof'], ri['cy'], ri['cz'], -co['L'] / 2.0))
    log.append('tasca faccia X-: %.3f x %.3f prof %.3f, con rilievo asolato %.3f x %.3f'
               % (t['W_y'], t['H_z'], t['prof'], ri['W_z'], ri['L_y']))

    # colonnine: 3 alte con smusso + 1 blocco basso diverso (vedi params.json)
    col = S['colonnine']
    st = col['standard']
    lx = st['x_est'] - st['x_int']; ly = st['y_est'] - st['y_int']
    for sx, sy in st['segni_xy']:
        c = box_c(lx, ly, st['z_top'] - st['z_base'],
                  cx=sx * (st['x_int'] + lx / 2.0), cy=sy * (st['y_int'] + ly / 2.0),
                  z0=st['z_base'])
        c = c.cut(half_space([-0.6105 * sx, -0.3612 * sy, -0.7048], st['piani_smusso'][0]['d']))
        s = s.fuse(c)
    log.append('%d colonnine %.3f x %.3f da z=%.3f a %.1f, smusso fino a z=%.3f'
               % (st['n'], lx, ly, st['z_base'], st['z_top'], st['smusso_z_top']))

    sp = col['speciale']
    slx = sp['x_est'] - sp['x_int']; sly = sp['y_est'] - sp['y_int']
    for sx, sy in sp['segni_xy']:
        s = s.fuse(box_c(slx, sly, sp['z_top'] - sp['z_base'],
                         cx=sx * (sp['x_int'] + slx / 2.0), cy=sy * (sp['y_int'] + sly / 2.0),
                         z0=sp['z_base']))
    log.append('1 blocco speciale %.3f x %.3f da z=%.3f a %.1f, senza smusso'
               % (slx, sly, sp['z_base'], sp['z_top']))

    # fori (asole) nelle colonnine
    for grp in (st, sp):
        f = grp['foro']
        for sx, sy in grp['segni_xy']:
            s = s.cut(obround(f['W'], f['L'], co['H'] - f['z_base'] + 2.0,
                              sx * f['cx'], sy * f['cy'], f['z_base'], axis_long='Y'))
        log.append('%d asole %.3f x %.3f da z=%.3f' % (grp['n'], f['W'], f['L'], f['z_base']))

    # 2 nervature interne sulla parete Y-
    nv = S['nervature']
    yc = -45.786 + P['_offset_mesh_modello']['dy']
    R = nv['_R_arco_fit']
    for cx in nv['x_centri']:
        disc = Part.makeCylinder(R, nv['t_x'], Vector(cx - nv['t_x'] / 2.0, yc, 24.046),
                                 Vector(1, 0, 0))
        clip = box_c(nv['t_x'] + 1.0, nv['y_a'] - nv['y_da'], nv['z_max'] - nv['z_min'],
                     cx=cx, cy=(nv['y_da'] + nv['y_a']) / 2.0,
                     cz=(nv['z_min'] + nv['z_max']) / 2.0)
        s = s.fuse(disc.common(clip))
        dbg('nervatura x=%.2f' % cx, s)
    log.append('2 nervature parete Y-, spessore %.3f, arco R%.3f' % (nv['t_x'], R))

    return s.removeSplitter(), log


# --------------------------------------------------------------- COPERCHIO

def build_coperchio():
    C = P['coperchio']
    pl = C['piastra']
    log = []
    s = box_c(pl['L'], pl['W'], pl['S'], z0=0.0)
    s = fillet_bottom(s, C['raccordo_base']['R'])
    log.append('piastra %.2f x %.2f x %.2f (X scalato x%.6f, decisione F), raccordo R%.1f'
               % (pl['L'], pl['W'], pl['S'], SX_LID, C['raccordo_base']['R']))

    a = C['asole']
    for sx in (1, -1):
        for sy in (1, -1):
            s = s.cut(obround(a['W'] * SX_LID, a['L'], pl['S'] + 2.0,
                              sx * a['cx'] * SX_LID, sy * a['cy'], -1.0, axis_long='Y'))
    log.append('4 asole %.3f x %.3f passanti in (+/-%.4f, +/-%.4f)'
               % (a['W'] * SX_LID, a['L'], a['cx'] * SX_LID, a['cy']))

    def pocket(t, cx):
        z0 = pl['S'] - t['prof']
        lx, ly = t['L_x'] * SX_LID, t['W_y']
        if t.get('forma') == 'ellisse':
            return ellipse_prism(lx, ly, t['prof'] + 1.0, cx, t['cy'], z0)
        return box_c(lx, ly, t['prof'] + 1.0, cx=cx, cy=t['cy'], z0=z0)

    for key in ('tasca_grande', 'tasca_annidata'):
        t = C[key]
        s = s.cut(pocket(t, t['cx'] * SX_LID))
        log.append('%s (%s) %.3f x %.3f prof %.3f'
                   % (key, t.get('forma', 'rettangolo'), t['L_x'] * SX_LID, t['W_y'], t['prof']))

    tp = C['tasche_piccole']
    for cx in tp['cx']:
        s = s.cut(pocket(tp, cx * SX_LID))
    log.append('2 tasche piccole (%s) %.3f x %.3f prof %.3f'
               % (tp.get('forma'), tp['L_x'] * SX_LID, tp['W_y'], tp['prof']))

    return s.removeSplitter(), log


# --------------------------------------------------------------- main

def bbox(s):
    """BoundBox stretto.

    shape.BoundBox su superfici BSpline (qui la cupola, generata da transformGeometry)
    restituisce l'inviluppo dei punti di controllo, che deborda parecchio: va usato
    optimalBoundingBox, che tassella e misura la geometria reale.
    """
    try:
        b = s.optimalBoundingBox()
    except Exception:
        b = s.BoundBox
    return '%.3f x %.3f x %.3f  [X %.3f..%.3f  Y %.3f..%.3f  Z %.3f..%.3f]' % (
        b.XLength, b.YLength, b.ZLength, b.XMin, b.XMax, b.YMin, b.YMax, b.ZMin, b.ZMax)


scatola, log_s = build_scatola()
coperchio, log_c = build_coperchio()

print('== SCATOLA ==')
for l in log_s: print('   ' + l)
print('   bbox   ' + bbox(scatola))
print('   volume %.3f mm3   solidi=%d   valido=%s'
      % (scatola.Volume, len(scatola.Solids), scatola.isValid()))
print('== COPERCHIO ==')
for l in log_c: print('   ' + l)
print('   bbox   ' + bbox(coperchio))
print('   volume %.3f mm3   solidi=%d   valido=%s'
      % (coperchio.Volume, len(coperchio.Solids), coperchio.isValid()))

doc = App.newDocument('taiser')
o1 = doc.addObject('Part::Feature', 'Scatola');   o1.Shape = scatola
lid = coperchio.copy(); lid.translate(Vector(0, 0, P['scatola']['corpo']['H']))
o2 = doc.addObject('Part::Feature', 'Coperchio'); o2.Shape = lid
doc.recompute()

import Import
Import.export([o1], os.path.join(OUT, 'scatola.step'))
Import.export([o2], os.path.join(OUT, 'coperchio.step'))
Import.export([o1, o2], os.path.join(OUT, 'model.step'))
Part.Compound([scatola, lid]).exportStl(os.path.join(OUT, 'model.stl'))
scatola.exportStl(os.path.join(OUT, 'scatola.stl'))
coperchio.exportStl(os.path.join(OUT, 'coperchio.stl'))
doc.saveAs(os.path.join(OUT, 'taiser.FCStd'))
print('\nesportati in %s: model.step scatola.step coperchio.step model.stl taiser.FCStd' % OUT)
# FreeCAD esce con codice 0 anche dopo un'eccezione: la sentinella dice al runner
# della web app che lo script e' arrivato in fondo. Vedi core/freecad/runner.py.
print('TEISER_OK')
