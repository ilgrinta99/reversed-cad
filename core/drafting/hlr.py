# -*- coding: utf-8 -*-
"""Proiezione con rimozione delle linee nascoste. Gira **dentro** FreeCAD.

E' l'unico modulo di `core/drafting/` che importa FreeCAD, ed e' voluto: la
geometria proiettata la calcola l'algoritmo di TechDraw (esatto sui B-rep,
silhouette comprese), mentre l'impaginazione della tavola e' Python puro e sta in
`tavola.py`. Fra i due passa un JSON di spigoli 2D, quindi il compositore non ha
bisogno di FreeCAD e resta testabile ovunque.

Perche' non TechDraw fino in fondo: in modalita' headless TechDraw non disegna le
quote, la loro grafica sta nel lato GUI. Le viste sono TechDraw, la quotatura e
l'impaginazione sono nostre.
"""
import math

import FreeCAD as App
import Part
import TechDraw
from FreeCAD import Placement, Rotation, Vector

#: Deflessione di discretizzazione delle curve non elementari, in mm di corda.
DEFLESSIONE = 0.03


def mat_vista(u, w):
    """Matrice mondo -> vista. u = destra nel disegno, w = alto; n = u x w = verso l'osservatore."""
    u = Vector(*u); w = Vector(*w)
    u.normalize(); w.normalize()
    n = u.cross(w)
    return App.Matrix(u.x, u.y, u.z, 0,
                      w.x, w.y, w.z, 0,
                      n.x, n.y, n.z, 0,
                      0, 0, 0, 1)


def ruota_per_vista(shape, u, w):
    """Copia del solido ruotata perche' la direzione di vista diventi +Z."""
    s = shape.copy()
    s.transformShape(mat_vista(u, w))
    return s


#: `TechDraw.project` restituisce quattro gruppi, in quest'ordine:
#: 0 = spigoli vivi in vista, 1 = spigoli di tangenza in vista,
#: 2 = spigoli vivi nascosti, 3 = spigoli di tangenza nascosti.
#: Verificato su un cubo e un cilindro: i gruppi 1 e 3 restano vuoti quando il
#: solido non ha raccordi, ed e' il modo di distinguerli senza fidarsi dei nomi.
GRUPPI_VISIBILI = (0, 1)
GRUPPI_NASCOSTI = (2, 3)


def proietta(shape, u, w):
    """Restituisce (visibili, nascosti) come liste di Edge 2D nel piano XY."""
    s = ruota_per_vista(shape, u, w)
    g = TechDraw.project(s, Vector(0, 0, 1))
    vis = [e for i in GRUPPI_VISIBILI if i < len(g) for e in g[i].Edges]
    nas = [e for i in GRUPPI_NASCOSTI if i < len(g) for e in g[i].Edges]
    return vis, nas


def sezione(shape, punto, normale):
    """Taglia il solido col semispazio n.p >= d e restituisce (resto, poligoni di taglio).

    I poligoni sono in coordinate del modello: chi disegna li porta in vista con
    la stessa matrice della proiezione, cosi' campitura e spigoli coincidono.
    """
    n = Vector(*normale); n.normalize()
    d = n.dot(Vector(*punto))
    big = Part.makeBox(2000, 2000, 2000, Vector(-1000, -1000, 0))
    big.Placement = Placement(n * d, Rotation(Vector(0, 0, 1), n))
    resto = shape.cut(big)
    polys = []
    for fa in resto.Faces:
        try:
            nn = fa.normalAt(*fa.Surface.parameter(fa.CenterOfMass))
        except Exception:
            continue
        if abs(abs(nn.dot(n)) - 1.0) < 1e-4 and abs(n.dot(fa.CenterOfMass) - d) < 1e-4:
            for wi in fa.Wires:
                polys.append(wi.discretize(Deflection=0.05))
    return resto, polys


# ---------------------------------------------------------------- serializzazione


def edge_to_dict(e, defl=DEFLESSIONE):
    """Un Edge 2D di TechDraw diventa una primitiva JSON: linea, cerchio, arco o polilinea.

    Cerchi e archi restano tali invece di essere discretizzati: il PDF li scrive
    come Bezier e il DXF come CIRCLE/ARC, quindi la tavola resta vettoriale vera.
    """
    nome = type(e.Curve).__name__
    if nome in ('Line', 'LineSegment') and len(e.Vertexes) == 2:
        a, b = e.Vertexes[0].Point, e.Vertexes[-1].Point
        return {'t': 'l', 'a': [a.x, a.y], 'b': [b.x, b.y]}
    if nome == 'Circle':
        c = e.Curve
        giro = abs(e.LastParameter - e.FirstParameter) > 2 * math.pi - 1e-6
        if e.isClosed() or giro:
            return {'t': 'c', 'c': [c.Center.x, c.Center.y], 'r': c.Radius}
        return {'t': 'a', 'c': [c.Center.x, c.Center.y], 'r': c.Radius,
                'a1': math.degrees(e.FirstParameter), 'a2': math.degrees(e.LastParameter)}
    try:
        pts = e.discretize(Deflection=defl)
    except Exception:
        pts = e.discretize(Number=48)
    return {'t': 'p', 'pts': [[p.x, p.y] for p in pts]}


def proietta_json(shape, u, w, sez=None, nascosti=True):
    """Proiezione completa di una vista, pronta per il JSON.

    `sez` = (punto, normale): il solido viene tagliato e i poligoni di taglio
    tornano gia' in coordinate di vista, cosi' il compositore li campisce senza
    sapere nulla di FreeCAD.
    """
    corpo = shape
    polys2d = []
    if sez is not None:
        corpo, polys = sezione(shape, sez[0], sez[1])
        m = mat_vista(u, w)
        polys2d = [[[float(q.x), float(q.y)] for q in (m.multiply(p) for p in poly)]
                   for poly in polys]
    vis, nas = proietta(corpo, u, w)
    fuori = {
        'visibili': [edge_to_dict(e) for e in vis],
        'nascosti': [edge_to_dict(e) for e in nas] if nascosti else [],
        'sezione': polys2d,
    }
    fuori['bbox'] = _bbox(fuori)
    return fuori


def _bbox(vista):
    """Ingombro 2D della vista, in coordinate di vista. Serve a scegliere la scala."""
    xs, ys = [], []

    def add(x, y):
        xs.append(x); ys.append(y)

    for gruppo in ('visibili', 'nascosti'):
        for e in vista[gruppo]:
            if e['t'] == 'l':
                add(*e['a']); add(*e['b'])
            elif e['t'] in ('c', 'a'):
                add(e['c'][0] - e['r'], e['c'][1] - e['r'])
                add(e['c'][0] + e['r'], e['c'][1] + e['r'])
            else:
                for p in e['pts']:
                    add(*p)
    for poly in vista['sezione']:
        for p in poly:
            add(*p)
    if not xs:
        return [0.0, 0.0, 0.0, 0.0]
    return [min(xs), min(ys), max(xs), max(ys)]
