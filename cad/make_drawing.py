# -*- coding: utf-8 -*-
"""FASE 4 - genera la tavola tecnica quotata dal modello parametrico.

    /Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c cad/make_drawing.py < /dev/null

La geometria proiettata viene da TechDraw.project (algoritmo di TechDraw, esatto).
Il disegno del foglio - cornice, cartiglio, quote, campiture - e' composto da
cad/draft2d.py, perche' in modalita' headless TechDraw non puo' disegnare le quote
(la loro grafica sta nel lato GUI). Le viste sono quindi TechDraw a tutti gli effetti,
mentre l'impaginazione e la quotatura sono nostre.

Uscite: output/drawing.pdf (4 fogli A3), output/drawing.dxf, output/drawing_p*.svg
Il quarto foglio e' l'assonometria isometrica: assieme, scatola e coperchio.
"""
import os, sys, math, json

import FreeCAD as App
import Part
from FreeCAD import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'cad'))
import draft2d as D
# La proiezione con rimozione delle linee nascoste e' generica e vive in core/:
# la usa anche la tavola del percorso automatico. Qui restano l'impaginazione e
# le quote, che del TAISER sanno tutto.
from core.drafting import hlr
from core.drafting.layout import ISOMETRICA, testo_scala

# Percorsi configurabili: vedi cad/build_model.py e docs/CONVENTIONS.md.
P = json.load(open(os.environ.get('TAISER_PARAMS', os.path.join(ROOT, 'cad', 'params.json'))))
OUT = os.environ.get('TAISER_OUT', os.path.join(ROOT, 'output'))
SCALA = 2.0
SCALA_ISO = 2.0
A3 = (420.0, 297.0)

proietta = hlr.proietta
sezione = hlr.sezione


# ------------------------------------------------------------ proiezione
def disegna_edges(f, edges, T, stile, defl=0.03, scala=None):
    """Riversa gli Edge 2D nel foglio applicando la trasformazione carta T."""
    scala = SCALA if scala is None else scala
    for e in edges:
        nome = type(e.Curve).__name__
        if nome in ('Line', 'LineSegment') and len(e.Vertexes) == 2:
            a = T(e.Vertexes[0].Point); b = T(e.Vertexes[1].Point)
            f.linea(a[0], a[1], b[0], b[1], stile)
        elif nome == 'Circle':
            c = e.Curve
            ctr = T(c.Center); r = c.Radius * scala
            if e.isClosed() or abs(e.LastParameter - e.FirstParameter) > 2 * math.pi - 1e-6:
                f.cerchio(ctr[0], ctr[1], r, stile)
            else:
                a1 = math.degrees(e.FirstParameter); a2 = math.degrees(e.LastParameter)
                f.arco(ctr[0], ctr[1], r, a1, a2, stile)
        else:
            try:
                pts = e.discretize(Deflection=defl)
            except Exception:
                pts = e.discretize(Number=48)
            f.polilinea([T(p) for p in pts], stile)


def trasf(cx_carta, cy_carta, cx_mod=0.0, cy_mod=0.0, scala=None):
    """Model (mm) -> carta (mm), con la scala di tavola."""
    s = SCALA if scala is None else scala

    def T(p):
        x = p[0] if not hasattr(p, 'x') else p.x
        y = p[1] if not hasattr(p, 'x') else p.y
        return (cx_carta + (x - cx_mod) * s, cy_carta + (y - cy_mod) * s)
    return T


# ------------------------------------------------------------ cartiglio
def cornice_e_cartiglio(f, titolo, sottotitolo, foglio_n, foglio_tot, note=()):
    m = 10.0
    f.polilinea([(m, m), (f.w - m, m), (f.w - m, f.h - m), (m, f.h - m)], 'cornice', chiusa=True)
    x0, y0, cw = m + 5.0, m + 5.0, 170.0
    y_note, y_dati, y_tit = 14.0, 33.0, 12.0          # altezze delle tre fasce
    ch = y_note + y_dati + y_tit
    f.polilinea([(x0, y0), (x0 + cw, y0), (x0 + cw, y0 + ch), (x0, y0 + ch)], 'cornice', chiusa=True)
    f.linea(x0, y0 + y_note, x0 + cw, y0 + y_note, 'sottile')
    f.linea(x0, y0 + y_note + y_dati, x0 + cw, y0 + y_note + y_dati, 'sottile')
    for i in (1, 2):
        f.linea(x0, y0 + y_note + 11.0 * i, x0 + cw, y0 + y_note + 11.0 * i, 'sottile')
    f.linea(x0 + 100.0, y0 + y_note, x0 + 100.0, y0 + y_note + y_dati, 'sottile')

    f.testo(x0 + 3, y0 + ch - 8.0, titolo, 4.5, st='contorno', grassetto=True)
    sx = [('OGGETTO', sottotitolo), ('SCALA', '%g:1     UNITA: mm' % SCALA),
          ('PROIEZIONE', 'europea (1o diedro)')]
    dx = [('FOGLIO', '%d di %d' % (foglio_n, foglio_tot)),
          ('FORMATO', 'A3   420 x 297'), ('ORIGINE', 'modello parametrico FreeCAD')]
    for col, xx, ww in ((sx, x0 + 3, 97.0), (dx, x0 + 103, 65.0)):
        for i, (k, v) in enumerate(col):
            yy = y0 + y_note + y_dati - 11.0 * i
            f.testo(xx, yy - 4.0, k, 2.0, st='contorno')
            f.testo(xx, yy - 8.5, v, 2.8, st='contorno')
    for i, t in enumerate(note[:4]):
        f.testo(x0 + 3, y0 + y_note - 4.0 - 3.3 * i, t, 2.2, st='contorno')

    sxs, sys_ = f.w - m - 34.0, m + 8.0                # simbolo 1o diedro
    f.cerchio(sxs, sys_, 4.0, 'sottile'); f.cerchio(sxs, sys_, 2.4, 'sottile')
    f.polilinea([(sxs + 9, sys_ - 4), (sxs + 22, sys_ - 2.4),
                 (sxs + 22, sys_ + 2.4), (sxs + 9, sys_ + 4)], 'sottile', chiusa=True)


def etichetta(f, x, y, testo):
    f.testo(x, y, testo, 3.4, anc='middle', st='contorno', grassetto=True)


def linea_di_sezione(f, x1, y1, x2, y2, lettera, verso=1):
    """Traccia la traccia del piano di sezione con frecce e lettere."""
    f.linea(x1, y1, x2, y2, 'asse')
    for (px, py) in ((x1, y1), (x2, y2)):
        if abs(x2 - x1) < 1e-6:          # traccia verticale
            f._freccia((px + 4.0 * verso, py), (-verso, 0))
            f.testo(px + 4.0 * verso, py + (7 if py == max(y1, y2) else -10), lettera,
                    3.4, anc='middle', st='asse', grassetto=True)
        else:
            f._freccia((px, py + 4.0 * verso), (0, -verso))
            f.testo(px + (5 if px == max(x1, x2) else -5), py + 4.5 * verso, lettera,
                    3.4, anc='middle', st='asse', grassetto=True)


# ============================================================== FOGLI

doc = App.openDocument(os.path.join(OUT, 'taiser.FCStd'))
SCATOLA = doc.getObject('Scatola').Shape
# Nel documento il coperchio sta gia' in posizione di montaggio: l'assieme lo usa
# com'e', i fogli del pezzo singolo lo riportano a terra.
ASSIEME = Part.makeCompound([SCATOLA, doc.getObject('Coperchio').Shape])
COPERCHIO = doc.getObject('Coperchio').Shape.copy()
COPERCHIO.translate(Vector(0, 0, -P['scatola']['corpo']['H']))

CO = P['scatola']['corpo']
CA = P['scatola']['cavita']
PA = P['scatola']['pareti']
CU = P['scatola']['cupola']
PL = P['coperchio']['piastra']
X_MIN, X_MAX = -CO['L'] / 2.0, CU['x0'] + CU['a']          # -36.93 .. 43.07
X_MID = (X_MIN + X_MAX) / 2.0

VISTE = {                                    # nome -> (u, w)
    'pianta':    ((1, 0, 0), (0, 1, 0)),     # osservatore in +Z
    'prospetto': ((1, 0, 0), (0, 0, 1)),     # osservatore in -Y
    'laterale':  ((0, 1, 0), (0, 0, 1)),     # osservatore in +X
    'iso':       ISOMETRICA,                 # osservatore in (1, -1, 1)
}


def vista(f, shape, nome_vista, T, sez=None, nascosti=True, cupola=False, scala=None):
    """Proietta shape nella vista indicata e la disegna sul foglio."""
    u, w = VISTE[nome_vista]
    corpo = shape
    polys2d = []
    if sez is not None:
        punto, normale = sez
        corpo, polys = sezione(shape, punto, normale)
        m = hlr.mat_vista(u, w)
        polys2d = [[T(m.multiply(q)) for q in poly] for poly in polys]
    vis, nas = proietta(corpo, u, w)
    if polys2d:
        f.tratteggio(polys2d, passo=1.6, ang=45.0)
    if nascosti:
        disegna_edges(f, nas, T, 'nascosto', scala=scala)
    disegna_edges(f, vis, T, 'contorno', scala=scala)
    if cupola:
        silhouette_cupola(f, nome_vista, T)
    return polys2d


def assonometria(f, shape, cx, cy, etichetta_testo, scala=SCALA_ISO, nascosti=False,
                 cupola=False):
    """Assonometria isometrica centrata sul proprio ingombro proiettato.

    Non e' una vista di misura — non si quota — ma e' quella che fa capire in un
    colpo d'occhio che pezzo si sta guardando, e per questo sta in tavola.
    """
    u, w = VISTE['iso']
    vis, nas = proietta(shape, u, w)
    xs, ys = [], []
    for e in vis:
        for v in e.Vertexes:
            xs.append(v.Point.x); ys.append(v.Point.y)
    cx_mod = (min(xs) + max(xs)) / 2.0 if xs else 0.0
    cy_mod = (min(ys) + max(ys)) / 2.0 if ys else 0.0
    T = trasf(cx, cy, cx_mod, cy_mod, scala=scala)
    if nascosti:
        disegna_edges(f, nas, T, 'nascosto', scala=scala)
    disegna_edges(f, vis, T, 'contorno', scala=scala)
    if cupola:
        silhouette_cupola_obliqua(f, u, w, T)
    basso = cy - ((max(ys) - min(ys)) / 2.0 if ys else 0.0) * scala
    etichetta(f, cx, basso - 10.0, '%s  %s' % (etichetta_testo, testo_scala(scala)))
    return (max(xs) - min(xs) if xs else 0.0, max(ys) - min(ys) if ys else 0.0)


def silhouette_cupola_obliqua(f, u, w, T, n=120, stile='contorno'):
    """Silhouette della cupola per una direzione di vista qualunque.

    In assonometria le tre curve chiuse di `silhouette_cupola` non servono: la
    direzione non e' un asse. La silhouette e' pero' ancora analitica. Scritto il
    paraboloide come

        P(v, s) = (x0 + a(1 - v^2 - s^2),  cy + b v,  cz + c s)

    la normale e' proporzionale a (1/a, 2v/b, 2s/c), e il contorno apparente e'
    dove la normale e' ortogonale alla direzione di vista d: una *retta* nel piano
    (v, s), che va poi intersecata col disco unitario — fuori dal disco la cupola
    non c'e' piu', c'e' il bordo ellittico, che TechDraw disegna gia'.
    """
    d = App.Vector(*u).cross(App.Vector(*w))
    d.normalize()
    x0, a, b, c = CU['x0'], CU['a'], CU['b'], CU['c']
    cy, cz = CU['cy'], CU['cz']
    A, B, C = 2.0 * a * d.y / b, 2.0 * a * d.z / c, -d.x
    norma2 = A * A + B * B
    if norma2 < 1e-12:
        return                                   # vista lungo l'asse: solo il bordo
    dist2 = C * C / norma2
    if dist2 >= 1.0:
        return                                   # la retta non taglia il disco
    semi = math.sqrt(1.0 - dist2)
    vx, sx = A * C / norma2, B * C / norma2      # piede della perpendicolare
    dv, ds = -B / math.sqrt(norma2), A / math.sqrt(norma2)
    pts = []
    for i in range(n + 1):
        k = -semi + 2.0 * semi * i / n
        v, s = vx + dv * k, sx + ds * k
        p = App.Vector(x0 + a * (1.0 - v * v - s * s), cy + b * v, cz + c * s)
        pts.append(T((p.dot(App.Vector(*u).normalize()), p.dot(App.Vector(*w).normalize()))))
    f.polilinea(pts, stile)


def silhouette_cupola(f, nome_vista, T, n=140, stile='contorno'):
    """Contorno esatto della cupola, calcolato dall'equazione del paraboloide.

    L'HLR di TechDraw e' accuratissimo quando produce la silhouette di questa
    superficie BSpline (errore 0.017 mm), ma in alcune viste non la genera affatto.
    La curva analitica la fornisce sempre; dove l'HLR c'e' gia', le due coincidono.
    """
    x0, a, b, c = CU['x0'], CU['a'], CU['b'], CU['c']
    cy, cz = CU['cy'], CU['cz']
    pts = []
    for i in range(n + 1):
        t = -1.0 + 2.0 * i / n
        if nome_vista == 'pianta':
            pts.append(T((x0 + a * (1 - t * t), cy + b * t)))
        elif nome_vista == 'prospetto':
            pts.append(T((x0 + a * (1 - t * t), cz + c * t)))
        else:                                   # laterale: ellisse di base in x = x0
            th = math.pi * t
            pts.append(T((cy + b * math.cos(th), cz + c * math.sin(th))))
    f.polilinea(pts, stile, chiusa=(nome_vista == 'laterale'))


def confronto_tavola():
    """FASE 4: confronta le quote generate con le 6 quote della tavola TinkerCAD."""
    bb_s = SCATOLA.optimalBoundingBox(); bb_c = COPERCHIO.optimalBoundingBox()
    return [
        ('T1', 'Scatola  lunghezza', 80.00, bb_s.XLength),
        ('T2', 'Scatola  larghezza', 46.00, bb_s.YLength),
        ('T3', 'Scatola  altezza',   27.00, bb_s.ZLength),
        ('T4', 'Coperchio lunghezza', 74.00, bb_c.XLength),
        ('T5', 'Coperchio larghezza', 46.00, bb_c.YLength),
        ('T6', 'Coperchio spessore',   2.50, bb_c.ZLength),
    ]


# -------------------------------------------------------------- foglio 1
f1 = D.Foglio(*A3)
cornice_e_cartiglio(
    f1, 'CONTENITORE TAISER', 'Scatola - viste ortogonali', 1, 4,
    note=('Modello parametrico ricostruito dalla mesh OBJ Tinkercad; la tavola TinkerCAD',
          'di partenza riportava solo i 3 ingombri esterni (80 x 46 x 27).',
          'Tratteggio fine = spigoli nascosti.  Linea mista rossa = assi e piani di sezione.'))

T_lat = trasf(105.0, 212.0, 0.0, CO['H'] / 2.0)
etichetta(f1, 105.0, 158.0, 'VISTA LATERALE DESTRA')
vista(f1, SCATOLA, 'laterale', T_lat, cupola=True)
f1.quota_lineare(T_lat((-CO['W'] / 2.0, 0)), T_lat((CO['W'] / 2.0, 0)), -18.0, '%.2f' % CO['W'])
f1.quota_lineare(T_lat((-CO['W'] / 2.0, 0)), T_lat((-CO['W'] / 2.0, CO['H'])), -14.0,
                 '%.2f' % CO['H'], orizzontale=False)
f1.quota_lineare(T_lat((CU['cy'] - CU['b'], CU['cz'] + CU['c'])),
                 T_lat((CU['cy'] + CU['b'], CU['cz'] + CU['c'])), 24.2,
                 '%.2f  (cupola)' % (2 * CU['b']))

T_pro = trasf(272.0, 212.0, X_MID, CO['H'] / 2.0)
etichetta(f1, 272.0, 158.0, 'PROSPETTO FRONTALE')
vista(f1, SCATOLA, 'prospetto', T_pro, cupola=True)
f1.quota_lineare(T_pro((X_MIN, CO['H'])), T_pro((X_MAX, CO['H'])), 8.0, '%.2f' % (X_MAX - X_MIN))
f1.quota_lineare(T_pro((X_MIN, CO['H'])), T_pro((CU['x0'], CO['H'])), 18.0, '%.2f' % CO['L'])
f1.quota_lineare(T_pro((X_MAX, 0)), T_pro((X_MAX, CO['H'])), 14.0, '%.2f' % CO['H'],
                 orizzontale=False)

T_pia = trasf(272.0, 100.0, X_MID, 0.0)
etichetta(f1, 272.0, 22.0, 'PIANTA')
vista(f1, SCATOLA, 'pianta', T_pia, cupola=True)
f1.quota_lineare(T_pia((X_MIN, -CO['W'] / 2.0)), T_pia((X_MAX, -CO['W'] / 2.0)), -24.0,
                 '%.2f' % (X_MAX - X_MIN))
f1.quota_lineare(T_pia((X_MAX, -CO['W'] / 2.0)), T_pia((X_MAX, CO['W'] / 2.0)), 26.0,
                 '%.2f' % CO['W'], orizzontale=False)
p1 = T_pia((X_MIN - 4.0, 0.0)); p2 = T_pia((X_MAX + 4.0, 0.0))
linea_di_sezione(f1, p1[0], p1[1], p2[0], p2[1], 'A')
p1 = T_pia((0.0, -CO['W'] / 2.0 - 2.0)); p2 = T_pia((0.0, CO['W'] / 2.0 + 2.0))
linea_di_sezione(f1, p1[0], p1[1], p2[0], p2[1], 'B')

# -------------------------------------------------------------- foglio 2
ZC = P['scatola']['fori_cupola']['A']['punto'][2]
f2 = D.Foglio(*A3)
cornice_e_cartiglio(
    f2, 'CONTENITORE TAISER', 'Scatola - sezioni', 2, 4,
    note=('A-A: piano verticale longitudinale Y=0.   B-B: piano verticale trasversale X=0.',
          'C-C: piano orizzontale Z=%.3f, sull\'asse dei due fori della cupola.' % ZC,
          'Il contorno della cupola e\' la curva analitica del paraboloide (vedi riquadro).'))

T_aa = trasf(272.0, 210.0, X_MID, CO['H'] / 2.0)
etichetta(f2, 272.0, 256.0, 'SEZIONE A-A')
vista(f2, SCATOLA, 'prospetto', T_aa, sez=((0, 0, 0), (0, -1, 0)), nascosti=False, cupola=True)
f2.quota_lineare(T_aa((X_MIN + PA['t_x'], CO['H'])), T_aa((CU['x0'] - PA['t_x'], CO['H'])),
                 9.0, '%.2f' % CA['L'])
f2.quota_lineare(T_aa((X_MIN, 0)), T_aa((X_MIN + PA['t_x'], 0)), -12.0, '%.2f' % PA['t_x'],
                 fuori=True)
f2.quota_lineare(T_aa((CU['x0'], 0)), T_aa((X_MAX, 0)), -24.0, 'a=%.3f' % CU['a'])
f2.quota_lineare(T_aa((X_MIN, 0)), T_aa((X_MIN, P['scatola']['fondo']['t'])), -14.0,
                 '%.2f' % P['scatola']['fondo']['t'], orizzontale=False, fuori=True)
f2.quota_lineare(T_aa((X_MAX, CU['cz'] - CU['c'])), T_aa((X_MAX, CU['cz'] + CU['c'])), 14.0,
                 '2c=%.3f' % (2 * CU['c']), orizzontale=False)

T_bb = trasf(95.0, 210.0, 0.0, CO['H'] / 2.0)
etichetta(f2, 95.0, 256.0, 'SEZIONE B-B')
vista(f2, SCATOLA, 'laterale', T_bb, sez=((0, 0, 0), (1, 0, 0)), nascosti=False)
f2.quota_lineare(T_bb((-CO['W'] / 2.0, CO['H'])), T_bb((-CO['W'] / 2.0 + PA['t_y'], CO['H'])),
                 9.0, '%.2f' % PA['t_y'], fuori=True)
f2.quota_lineare(T_bb((-CA['W'] / 2.0, 0)), T_bb((CA['W'] / 2.0, 0)), -14.0, '%.2f' % CA['W'])
f2.quota_lineare(T_bb((CO['W'] / 2.0, 0)), T_bb((CO['W'] / 2.0, CO['H'])), 14.0,
                 '%.2f' % CO['H'], orizzontale=False)

T_cc = trasf(272.0, 100.0, X_MID, 0.0)
etichetta(f2, 272.0, 162.0, 'SEZIONE C-C')
vista(f2, SCATOLA, 'pianta', T_cc, sez=((0, 0, ZC), (0, 0, 1)), nascosti=False, cupola=True)
f2.quota_lineare(T_cc((X_MIN, -CO['W'] / 2.0)), T_cc((X_MAX, -CO['W'] / 2.0)), -16.0,
                 '%.2f' % (X_MAX - X_MIN))
for k, sgn in (('A', 1), ('B', -1)):
    bo = P['scatola']['fori_cupola'][k]
    pt = T_cc((bo['punto'][0] + 3.0, bo['punto'][1]))
    tx, ty = pt[0] - 30.0, pt[1] + sgn * 16.0
    f2.linea(tx + 1.0, ty, pt[0], pt[1], 'quota')
    f2.testo(tx, ty + 1.0, u'foro %s: ellisse %.3f x %.3f' % (k, bo['sez_perp_X_YxZ'][0],
             bo['sez_perp_X_YxZ'][1]), 2.4, anc='end')
    f2.testo(tx, ty - 2.6, u'asse inclinato %.2f° nel piano XY' % bo['angolo_XY_deg'],
             2.4, anc='end')

# riquadro con l'equazione della cupola
bx, by = 22.0, 92.0
f2.polilinea([(bx, by), (bx + 158.0, by), (bx + 158.0, by + 62.0), (bx, by + 62.0)],
             'sottile', chiusa=True)
righe = [('CUPOLA - PARABOLOIDE ELLITTICO', True),
         ('(x - x0)/a  =  1 - ((y-cy)/b)^2 - ((z-cz)/c)^2', False),
         ('', False),
         ('x0 = %.2f    a = %.4f' % (CU['x0'], CU['a']), False),
         ('b  = %.4f   c = %.4f' % (CU['b'], CU['c']), False),
         ('cy = %.4f     cz = %.4f' % (CU['cy'], CU['cz']), False),
         ('', False),
         ('Forma ricavata per fitting sulla mesh:' , False),
         ('esponenti p=1.00 q=2.00, scarto max 0.117 mm', False),
         ('(un ellissoide darebbe 1.610 mm).', False)]
for i, (t, grassetto) in enumerate(righe):
    f2.testo(bx + 4.0, by + 56.0 - 5.6 * i, t, 3.0 if grassetto else 2.5,
             st='contorno', grassetto=grassetto)

# -------------------------------------------------------------- foglio 3
f3 = D.Foglio(*A3)
cornice_e_cartiglio(
    f3, 'CONTENITORE TAISER', 'Coperchio - viste e sezione', 3, 4,
    note=('Lunghezza 73.86 e non 74.00 come da tavola TinkerCAD: nella mesh il coperchio',
          'era scalato di 74/73.86. Riportandolo a 73.86 le 4 asole cadono esattamente',
          'sui fori delle colonnine della scatola (+/-33.0425). Vedi docs/lost+found_lost+found_design.md 5-F.'))

AS = P['coperchio']['asole']
SXL = PL['L'] / PL['_L_mesh']
T_cp = trasf(280.0, 190.0, 0.0, 0.0)
etichetta(f3, 280.0, 244.0, 'PIANTA')
vista(f3, COPERCHIO, 'pianta', T_cp)
f3.quota_lineare(T_cp((-PL['L'] / 2.0, -PL['W'] / 2.0)), T_cp((PL['L'] / 2.0, -PL['W'] / 2.0)),
                 -26.0, '%.2f' % PL['L'])
f3.quota_lineare(T_cp((-AS['cx'] * SXL, -PL['W'] / 2.0)), T_cp((AS['cx'] * SXL, -PL['W'] / 2.0)),
                 -14.0, '%.4f' % (2 * AS['cx'] * SXL))
f3.quota_lineare(T_cp((PL['L'] / 2.0, -PL['W'] / 2.0)), T_cp((PL['L'] / 2.0, PL['W'] / 2.0)),
                 22.0, '%.2f' % PL['W'], orizzontale=False)
f3.quota_lineare(T_cp((PL['L'] / 2.0, -AS['cy'])), T_cp((PL['L'] / 2.0, AS['cy'])),
                 10.0, '%.4f' % (2 * AS['cy']), orizzontale=False)
pt = T_cp((-AS['cx'] * SXL, AS['cy']))
f3.testo(pt[0] - 7.0, pt[1] + 13.0, u'4 asole %.3f x %.3f passanti'
         % (AS['W'] * SXL, AS['L']), 2.5, anc='end')
f3.linea(pt[0] - 6.0, pt[1] + 12.0, pt[0], pt[1], 'quota')
tg = P['coperchio']['tasca_grande']
pt = T_cp((tg['cx'] * SXL, tg['cy']))
f3.testo(pt[0] + 26.0, pt[1] - 26.0, u'tasca %.3f x %.3f prof %.3f'
         % (tg['L_x'] * SXL, tg['W_y'], tg['prof']), 2.5, anc='start')
f3.linea(pt[0], pt[1], pt[0] + 25.0, pt[1] - 25.0, 'quota')

T_cf = trasf(280.0, 100.0, 0.0, PL['S'] / 2.0)
etichetta(f3, 280.0, 88.0, 'PROSPETTO FRONTALE')
vista(f3, COPERCHIO, 'prospetto', T_cf)
f3.quota_lineare(T_cf((PL['L'] / 2.0, 0)), T_cf((PL['L'] / 2.0, PL['S'])), 16.0,
                 '%.2f' % PL['S'], orizzontale=False, fuori=True)

T_dd = trasf(280.0, 62.0, 0.0, PL['S'] / 2.0)
etichetta(f3, 280.0, 50.0, 'SEZIONE D-D  (piano Y = %.4f)' % tg['cy'])
vista(f3, COPERCHIO, 'prospetto', T_dd, sez=((0, tg['cy'], 0), (0, -1, 0)), nascosti=False)

# tabella di confronto con la tavola TinkerCAD (richiesta di FASE 4)
tx, ty, tw = 22.0, 105.0, 162.0
righe_tab = confronto_tavola()
th = 10.0 + 6.0 * (len(righe_tab) + 1)
f3.polilinea([(tx, ty), (tx + tw, ty), (tx + tw, ty + th), (tx, ty + th)], 'sottile', chiusa=True)
f3.testo(tx + 3, ty + th - 6.0, 'VERIFICA CONTRO LA TAVOLA TINKERCAD', 3.0,
         st='contorno', grassetto=True)
yy = ty + th - 13.0
for col, xx, anc in (('quota', tx + 3, 'start'), ('tavola', tx + 104, 'end'),
                     ('modello', tx + 130, 'end'), ('delta', tx + 156, 'end')):
    f3.testo(xx, yy, col, 2.2, st='contorno', anc=anc)
f3.linea(tx + 2, yy - 2.0, tx + tw - 2, yy - 2.0, 'sottile')
for i, (k, lab, tav, mod) in enumerate(righe_tab):
    y = yy - 6.0 - 6.0 * i
    f3.testo(tx + 3, y, '%s  %s' % (k, lab), 2.4, st='contorno')
    f3.testo(tx + 104, y, '%.2f' % tav, 2.4, st='contorno', anc='end')
    f3.testo(tx + 130, y, '%.3f' % mod, 2.4, st='contorno', anc='end')
    f3.testo(tx + 156, y, '%+.3f' % (mod - tav), 2.4,
             st='contorno' if abs(mod - tav) < 0.005 else 'asse', anc='end')

# -------------------------------------------------------------- foglio 4
# L'assonometria non porta quote: porta il colpo d'occhio. Le tre viste
# ortogonali dicono tutto sulle misure e niente sulla forma d'insieme — chi
# guarda una tavola per la prima volta parte da qui e poi va a cercare i numeri.
f4 = D.Foglio(*A3)
cornice_e_cartiglio(
    f4, 'CONTENITORE TAISER', 'Assonometria isometrica', 4, 4,
    note=('Assonometria isometrica: osservatore in (1, -1, 1), asse Z del modello verticale.',
          'Vista di orientamento, non di misura: le quote stanno sui fogli 1, 2 e 3.',
          'Coperchio in posizione di montaggio, appoggiato sul bordo della scatola.'))

assonometria(f4, ASSIEME, 280.0, 175.0, 'ASSIEME  scatola + coperchio', scala=2.0,
             cupola=True)
assonometria(f4, SCATOLA, 95.0, 220.0, 'SCATOLA', scala=1.0, cupola=True)
assonometria(f4, COPERCHIO, 95.0, 120.0, 'COPERCHIO', scala=1.0)


# -------------------------------------------------------------- uscite
fogli = [f1, f2, f3, f4]
D.scrivi_pdf(fogli, os.path.join(OUT, 'drawing.pdf'), 'Contenitore TAISER')
D.scrivi_dxf(fogli, os.path.join(OUT, 'drawing.dxf'))
for i, f in enumerate(fogli, 1):
    D.scrivi_svg([f], os.path.join(OUT, 'drawing_p%d.svg' % i))
if os.environ.get('TAISER_PAGES'):                      # PDF separati per ispezione
    for i, f in enumerate(fogli, 1):
        D.scrivi_pdf([f], os.path.join(os.environ['TAISER_PAGES'], 'p%d.pdf' % i))
print('fogli: ' + ', '.join('%d) %d primitive' % (i, len(f.p)) for i, f in enumerate(fogli, 1)))

print('\n== FASE 4: quote generate vs tavola TinkerCAD ==')
print('  %-4s %-22s %10s %10s %9s' % ('', 'quota', 'tavola', 'modello', 'delta'))
for k, lab, tav, mod in confronto_tavola():
    print('  %-4s %-22s %10.2f %10.3f %9.3f%s'
          % (k, lab, tav, mod, mod - tav, '   <- decisione F' if abs(mod - tav) > 0.005 else ''))

# FreeCAD esce con codice 0 anche dopo un'eccezione: la sentinella dice al runner
# della web app che lo script e' arrivato in fondo. Vedi core/freecad/runner.py.
print('TEISER_OK')
