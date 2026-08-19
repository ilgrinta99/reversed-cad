# -*- coding: utf-8 -*-
"""Motore di disegno 2D minimale: una lista di primitive, tre backend (SVG, PDF, DXF).

Coordinate del foglio in millimetri, origine in basso a sinistra, Y verso l'alto
(convenzione CAD). Il backend SVG ribalta Y internamente.

Nessuna dipendenza esterna: il PDF e il DXF sono scritti a mano.
"""
import math, zlib

# ------------------------------------------------------------------ stili
# (colore RGB, spessore mm, pattern tratteggio in mm, layer DXF, colore DXF)
STILI = {
    'contorno':  ((0, 0, 0),       0.50, None,          'CONTORNO',  7),
    'nascosto':  ((0.40,) * 3,     0.25, (2.0, 1.0),    'NASCOSTO',  8),
    'asse':      ((0.65, 0, 0),    0.25, (6, 1.2, 1, 1.2), 'ASSI',    1),
    'quota':     ((0, 0.30, 0.60), 0.25, None,          'QUOTE',     5),
    'tratteggio':((0.55,) * 3,     0.18, None,          'SEZIONE',   9),
    'cornice':   ((0, 0, 0),       0.70, None,          'CORNICE',   7),
    'sottile':   ((0, 0, 0),       0.25, None,          'CORNICE',   7),
}
ALTEZZA_TESTO = 2.5          # mm
FRECCIA_L, FRECCIA_W = 3.0, 1.0


class Foglio(object):
    """Un foglio di disegno. Accumula primitive in coordinate carta (mm)."""

    def __init__(self, larghezza=420.0, altezza=297.0, titolo=''):
        self.w, self.h, self.titolo = larghezza, altezza, titolo
        self.p = []                                    # primitive

    # -- primitive di base ------------------------------------------------
    def linea(self, x1, y1, x2, y2, st='contorno'):
        if abs(x1 - x2) > 1e-9 or abs(y1 - y2) > 1e-9:
            self.p.append(('line', x1, y1, x2, y2, st))

    def polilinea(self, pts, st='contorno', chiusa=False):
        q = list(pts) + ([pts[0]] if chiusa and len(pts) > 2 else [])
        for a, b in zip(q, q[1:]):
            self.linea(a[0], a[1], b[0], b[1], st)

    def arco(self, cx, cy, r, a1, a2, st='contorno'):
        """Angoli in gradi, senso antiorario da a1 ad a2."""
        if r > 1e-9:
            self.p.append(('arc', cx, cy, r, a1, a2, st))

    def cerchio(self, cx, cy, r, st='contorno'):
        if r > 1e-9:
            self.p.append(('circle', cx, cy, r, st))

    def testo(self, x, y, s, h=ALTEZZA_TESTO, anc='start', rot=0.0, st='quota', grassetto=False):
        if s:
            self.p.append(('text', x, y, s, h, anc, rot, st, grassetto))

    def tratteggio(self, poligoni, passo=2.0, ang=45.0):
        """Campitura di sezione: rette parallele ritagliate sui poligoni."""
        pts = [q for poly in poligoni for q in poly]
        if not pts: return
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
        diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / 2.0 + passo
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        k = int(diag / passo) + 1
        for i in range(-k, k + 1):
            # retta passante per (cx,cy) + i*passo*normale, direzione (ca,sa)
            px, py = cx - sa * i * passo, cy + ca * i * passo
            a = (px - ca * diag, py - sa * diag)
            b = (px + ca * diag, py + sa * diag)
            for s0, s1 in _clip_segmento(a, b, poligoni):
                self.linea(s0[0], s0[1], s1[0], s1[1], 'tratteggio')

    # -- quotatura ---------------------------------------------------------
    def quota_lineare(self, p1, p2, offset, testo=None, orizzontale=True, fuori=None):
        """Quota fra due punti, con linee di riferimento, frecce e testo.

        offset = distanza (con segno) della linea di quota dai punti quotati.
        """
        st = 'quota'
        if orizzontale:
            yq = max(p1[1], p2[1]) + offset if offset >= 0 else min(p1[1], p2[1]) + offset
            for p in (p1, p2):
                sgn = 1.0 if yq > p[1] else -1.0
                self.linea(p[0], p[1] + sgn * 1.0, p[0], yq + sgn * 1.5, st)
            a, b = (min(p1[0], p2[0]), yq), (max(p1[0], p2[0]), yq)
            val = abs(p2[0] - p1[0])
        else:
            xq = max(p1[0], p2[0]) + offset if offset >= 0 else min(p1[0], p2[0]) + offset
            for p in (p1, p2):
                sgn = 1.0 if xq > p[0] else -1.0
                self.linea(p[0] + sgn * 1.0, p[1], xq + sgn * 1.5, p[1], st)
            a, b = (xq, min(p1[1], p2[1])), (xq, max(p1[1], p2[1]))
            val = abs(p2[1] - p1[1])

        lungh = math.hypot(b[0] - a[0], b[1] - a[1])
        esterno = fuori if fuori is not None else lungh < 3.2 * FRECCIA_L
        self.linea(a[0], a[1], b[0], b[1], st)
        ux, uy = ((b[0] - a[0]) / lungh, (b[1] - a[1]) / lungh) if lungh > 1e-9 else (1.0, 0.0)
        if esterno:
            self.linea(a[0] - ux * FRECCIA_L * 2, a[1] - uy * FRECCIA_L * 2, a[0], a[1], st)
            self.linea(b[0], b[1], b[0] + ux * FRECCIA_L * 2, b[1] + uy * FRECCIA_L * 2, st)
            self._freccia(a, (-ux, -uy)); self._freccia(b, (ux, uy))
        else:
            self._freccia(a, (ux, uy)); self._freccia(b, (-ux, -uy))

        txt = testo if testo is not None else '%.2f' % val
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        if orizzontale:
            self.testo(mx, my + 0.9, txt, anc='middle')
        else:
            self.testo(mx - 0.9, my, txt, anc='middle', rot=90.0)

    def _freccia(self, p, u):
        """Punta di freccia piena in p, che punta in direzione -u."""
        bx, by = p[0] + u[0] * FRECCIA_L, p[1] + u[1] * FRECCIA_L
        nx, ny = -u[1] * FRECCIA_W / 2.0, u[0] * FRECCIA_W / 2.0
        self.p.append(('fill', [(p[0], p[1]), (bx + nx, by + ny), (bx - nx, by - ny)], 'quota'))

    def quota_diametro(self, c, r, testo=None, ang=45.0, sbalzo=7.0):
        """Quota di diametro con linea di richiamo obliqua."""
        st = 'quota'
        a = math.radians(ang)
        p0 = (c[0] + r * math.cos(a), c[1] + r * math.sin(a))
        p1 = (c[0] + (r + sbalzo) * math.cos(a), c[1] + (r + sbalzo) * math.sin(a))
        p2 = (p1[0] + (2.0 if math.cos(a) >= 0 else -2.0), p1[1])
        self.linea(p0[0], p0[1], p1[0], p1[1], st)
        self.linea(p1[0], p1[1], p2[0], p2[1], st)
        self._freccia(p0, (math.cos(a), math.sin(a)))
        self.testo(p2[0] + (0.8 if math.cos(a) >= 0 else -0.8), p2[1] + 0.6,
                   testo if testo is not None else u'Ø%.2f' % (2 * r),
                   anc='start' if math.cos(a) >= 0 else 'end')

    def croce_asse(self, cx, cy, r):
        self.linea(cx - r, cy, cx + r, cy, 'asse')
        self.linea(cx, cy - r, cx, cy + r, 'asse')


def _clip_segmento(a, b, poligoni):
    """Interseca il segmento a-b con i poligoni e restituisce i tratti interni."""
    ts = [0.0, 1.0]
    dx, dy = b[0] - a[0], b[1] - a[1]
    for poly in poligoni:
        n = len(poly)
        for i in range(n):
            c, d = poly[i], poly[(i + 1) % n]
            ex, ey = d[0] - c[0], d[1] - c[1]
            den = dx * ey - dy * ex
            if abs(den) < 1e-12: continue
            t = ((c[0] - a[0]) * ey - (c[1] - a[1]) * ex) / den
            u = ((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / den
            if 0.0 <= u <= 1.0 and 0.0 < t < 1.0:
                ts.append(t)
    ts = sorted(set(ts))
    out = []
    for t0, t1 in zip(ts, ts[1:]):
        tm = (t0 + t1) / 2.0
        pm = (a[0] + dx * tm, a[1] + dy * tm)
        if sum(1 for poly in poligoni if _dentro(pm, poly)) % 2 == 1:
            out.append(((a[0] + dx * t0, a[1] + dy * t0), (a[0] + dx * t1, a[1] + dy * t1)))
    return out


def _dentro(p, poly):
    x, y = p; c = False; n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-300) + x1:
            c = not c
    return c


def _arco_bezier(cx, cy, r, a1, a2):
    """Spezza un arco in segmenti di Bezier cubiche da <=90 gradi."""
    a1, a2 = math.radians(a1), math.radians(a2)
    if a2 < a1: a2 += 2 * math.pi
    n = max(1, int(math.ceil((a2 - a1) / (math.pi / 2)) ))
    step = (a2 - a1) / n
    k = 4.0 / 3.0 * math.tan(step / 4.0)
    out = []
    for i in range(n):
        t0 = a1 + i * step; t1 = t0 + step
        p0 = (cx + r * math.cos(t0), cy + r * math.sin(t0))
        p3 = (cx + r * math.cos(t1), cy + r * math.sin(t1))
        c0 = (p0[0] - k * r * math.sin(t0), p0[1] + k * r * math.cos(t0))
        c1 = (p3[0] + k * r * math.sin(t1), p3[1] - k * r * math.cos(t1))
        out.append((p0, c0, c1, p3))
    return out


# ------------------------------------------------------------------ SVG
def scrivi_svg(fogli, path):
    f = fogli[0]
    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%gmm" height="%gmm" '
         'viewBox="0 0 %g %g">' % (f.w, f.h, f.w, f.h),
         '<rect width="100%%" height="100%%" fill="white"/>']
    Y = lambda y: f.h - y
    for pr in f.p:
        st = STILI[pr[-1] if pr[0] != 'text' else pr[7]]
        col = 'rgb(%d,%d,%d)' % tuple(int(255 * c) for c in st[0])
        dash = ' stroke-dasharray="%s"' % ','.join('%g' % v for v in st[2]) if st[2] else ''
        com = 'stroke="%s" stroke-width="%g" fill="none"%s' % (col, st[1], dash)
        if pr[0] == 'line':
            o.append('<line x1="%g" y1="%g" x2="%g" y2="%g" %s/>'
                     % (pr[1], Y(pr[2]), pr[3], Y(pr[4]), com))
        elif pr[0] == 'circle':
            o.append('<circle cx="%g" cy="%g" r="%g" %s/>' % (pr[1], Y(pr[2]), pr[3], com))
        elif pr[0] == 'arc':
            cx, cy, r, a1, a2 = pr[1:6]
            if a2 < a1: a2 += 360.0
            x1, y1 = cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1))
            x2, y2 = cx + r * math.cos(math.radians(a2)), cy + r * math.sin(math.radians(a2))
            o.append('<path d="M %g %g A %g %g 0 %d 0 %g %g" %s/>'
                     % (x1, Y(y1), r, r, 1 if (a2 - a1) > 180 else 0, x2, Y(y2), com))
        elif pr[0] == 'fill':
            pts = ' '.join('%g,%g' % (q[0], Y(q[1])) for q in pr[1])
            o.append('<polygon points="%s" fill="%s" stroke="none"/>' % (pts, col))
        elif pr[0] == 'text':
            _, x, y, s, hh, anc, rot, _, bold = pr
            tr = ' transform="rotate(%g %g %g)"' % (-rot, x, Y(y)) if rot else ''
            o.append('<text x="%g" y="%g" font-family="Helvetica,Arial" font-size="%g" '
                     'text-anchor="%s" fill="%s"%s%s>%s</text>'
                     % (x, Y(y), hh, anc, col, ' font-weight="bold"' if bold else '', tr,
                        s.replace('&', '&amp;').replace('<', '&lt;')))
    o.append('</svg>')
    open(path, 'w', encoding='utf-8').write('\n'.join(o))


# ------------------------------------------------------------------ PDF
def scrivi_pdf(fogli, path, titolo='Disegno'):
    MM = 72.0 / 25.4
    pagine = []
    for f in fogli:
        c = ['1 J 1 j']
        cur = None
        for pr in f.p:
            st = STILI[pr[-1] if pr[0] != 'text' else pr[7]]
            key = (st[0], st[1], st[2])
            if pr[0] == 'text':
                _, x, y, s, hh, anc, rot, _, bold = pr
                wtxt = 0.52 * hh * len(s)
                ox = {'start': 0.0, 'middle': -wtxt / 2.0, 'end': -wtxt}[anc]
                oy = -hh * 0.35
                a = math.radians(rot); ca, sa = math.cos(a), math.sin(a)
                px, py = x + ox * ca - oy * sa, y + ox * sa + oy * ca
                c.append('BT /%s %g Tf %.3f %.3f %.3f rg %.4f %.4f %.4f %.4f %.3f %.3f Tm (%s) Tj ET'
                         % ('F2' if bold else 'F1', hh * MM, st[0][0], st[0][1], st[0][2],
                            ca, sa, -sa, ca, px * MM, py * MM,
                            s.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')))
                cur = None
                continue
            if key != cur:
                c.append('%.3f %.3f %.3f RG %g w' % (st[0][0], st[0][1], st[0][2], st[1] * MM))
                c.append('[%s] 0 d' % ' '.join('%g' % (v * MM) for v in st[2]) if st[2] else '[] 0 d')
                cur = key
            if pr[0] == 'line':
                c.append('%.3f %.3f m %.3f %.3f l S'
                         % (pr[1] * MM, pr[2] * MM, pr[3] * MM, pr[4] * MM))
            elif pr[0] in ('arc', 'circle'):
                if pr[0] == 'circle': cx, cy, r, a1, a2 = pr[1], pr[2], pr[3], 0.0, 360.0
                else: cx, cy, r, a1, a2 = pr[1:6]
                segs = _arco_bezier(cx, cy, r, a1, a2)
                c.append('%.3f %.3f m' % (segs[0][0][0] * MM, segs[0][0][1] * MM))
                for p0, c0, c1, p3 in segs:
                    c.append('%.3f %.3f %.3f %.3f %.3f %.3f c'
                             % (c0[0]*MM, c0[1]*MM, c1[0]*MM, c1[1]*MM, p3[0]*MM, p3[1]*MM))
                c.append('S')
            elif pr[0] == 'fill':
                pts = pr[1]
                c.append('%.3f %.3f %.3f rg' % st[0])
                c.append('%.3f %.3f m' % (pts[0][0] * MM, pts[0][1] * MM))
                for q in pts[1:]: c.append('%.3f %.3f l' % (q[0] * MM, q[1] * MM))
                c.append('h f')
                cur = None
        pagine.append((f, zlib.compress('\n'.join(c).encode('latin-1', 'replace'))))

    objs, out = [], []
    def add(body): objs.append(body); return len(objs)
    font1 = add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')
    font2 = add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>')
    n_pag = len(pagine)
    root_pages = len(objs) + 1 + 2 * n_pag + 1                  # calcolato dopo
    kids, pageobjs = [], []
    for f, data in pagine:
        cid = add(b'<< /Length %d /Filter /FlateDecode >>\nstream\n' % len(data) + data + b'\nendstream')
        pid = add(None)                                          # placeholder
        pageobjs.append((pid, cid, f)); kids.append(pid)
    pages_id = add(None)
    for pid, cid, f in pageobjs:
        objs[pid - 1] = (b'<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] '
                         b'/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>'
                         % (pages_id, f.w * MM, f.h * MM, font1, font2, cid))
    objs[pages_id - 1] = (b'<< /Type /Pages /Count %d /Kids [%s] >>'
                          % (n_pag, b' '.join(b'%d 0 R' % k for k in kids)))
    cat = add(b'<< /Type /Catalog /Pages %d 0 R >>' % pages_id)
    info = add(('<< /Title (%s) /Producer (Teiser draft2d) >>' % titolo).encode('latin-1', 'replace'))

    buf = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offs = []
    for i, body in enumerate(objs):
        offs.append(len(buf))
        buf += b'%d 0 obj\n' % (i + 1) + body + b'\nendobj\n'
    xref = len(buf)
    buf += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objs) + 1)
    for o in offs: buf += b'%010d 00000 n \n' % o
    buf += (b'trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n'
            % (len(objs) + 1, cat, info, xref))
    open(path, 'wb').write(bytes(buf))


# ------------------------------------------------------------------ DXF
def scrivi_dxf(fogli, path, gap=20.0):
    """Scrive i fogli in un unico modelspace, affiancati lungo X con un margine.

    Senza l'affiancamento i fogli finirebbero sovrapposti, avendo tutti
    coordinate 0..larghezza.
    """
    o = []
    w = lambda c, v: o.extend(('%d' % c, v if isinstance(v, str) else '%.6f' % v))
    layers = sorted({(s[3], s[4]) for s in STILI.values()})
    o += ['0', 'SECTION', '2', 'TABLES', '0', 'TABLE', '2', 'LAYER', '70', '%d' % len(layers)]
    for name, col in layers:
        o += ['0', 'LAYER', '2', name, '70', '0', '62', '%d' % col, '6', 'CONTINUOUS']
    o += ['0', 'ENDTAB', '0', 'ENDSEC', '0', 'SECTION', '2', 'ENTITIES']
    ox = 0.0
    for f in fogli:
        for pr in f.p:
            st = STILI[pr[-1] if pr[0] != 'text' else pr[7]]
            lay = st[3]
            if pr[0] == 'line':
                o += ['0', 'LINE', '8', lay]
                w(10, pr[1] + ox); w(20, pr[2]); w(11, pr[3] + ox); w(21, pr[4])
            elif pr[0] == 'circle':
                o += ['0', 'CIRCLE', '8', lay]; w(10, pr[1] + ox); w(20, pr[2]); w(40, pr[3])
            elif pr[0] == 'arc':
                o += ['0', 'ARC', '8', lay]
                w(10, pr[1] + ox); w(20, pr[2]); w(40, pr[3]); w(50, pr[4]); w(51, pr[5])
            elif pr[0] == 'fill':
                pts = pr[1]
                for a, b in zip(pts, pts[1:] + [pts[0]]):
                    o += ['0', 'LINE', '8', lay]
                    w(10, a[0] + ox); w(20, a[1]); w(11, b[0] + ox); w(21, b[1])
            elif pr[0] == 'text':
                _, x, y, s, hh, anc, rot, stn, bold = pr
                o += ['0', 'TEXT', '8', lay]
                w(10, x + ox); w(20, y); w(40, hh); o += ['1', s]
                w(50, rot); w(72, {'start': 0, 'middle': 1, 'end': 2}[anc])
                w(11, x + ox); w(21, y)
        ox += f.w + gap
    o += ['0', 'ENDSEC', '0', 'EOF']
    # in DXF il diametro si scrive col codice di controllo AutoCAD %%c
    o = [t.replace(u'\u00d8', '%%c').replace(u'\u00b0', '%%d') for t in o]
    open(path, 'w', encoding='utf-8').write('\n'.join(o) + '\n')
