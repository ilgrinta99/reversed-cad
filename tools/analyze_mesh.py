"""Estrae quote geometriche dalla mesh OBJ di riferimento.

NON produce quote 'di progetto': misura la tassellazione grezza. I valori
vanno arrotondati/interpretati a mano in docs/lost+found_design.md.
"""
import sys, math
from collections import defaultdict
import numpy as np

def load(path):
    objs, cur, V = {}, None, []
    for line in open(path):
        w = line.split()
        if not w: continue
        if w[0] == 'o':
            cur = w[1]; objs[cur] = []
        elif w[0] == 'v':
            V.append([float(x) for x in w[1:4]])
        elif w[0] == 'f':
            idx = [int(t.split('/')[0]) - 1 for t in w[1:]]
            for i in range(1, len(idx) - 1):
                objs[cur].append((idx[0], idx[i], idx[i+1]))
    return np.array(V), objs

def planes(V, tris, ang_tol=1.0, d_tol=1e-3):
    """Raggruppa i triangoli in piani (normale + offset). Ritorna lista ordinata per area."""
    groups = []  # (normal, d, area, [tri])
    for t in tris:
        a, b, c = V[list(t)]
        n = np.cross(b - a, c - a)
        area = np.linalg.norm(n) / 2
        if area < 1e-9: continue
        n = n / (2 * area)
        d = float(n @ a)
        for g in groups:
            if g[0] @ n > math.cos(math.radians(ang_tol)) and abs(g[1] - d) < d_tol:
                g[2] += area; g[3].append(t); break
        else:
            groups.append([n, d, area, [t]])
    groups.sort(key=lambda g: -g[2])
    return groups

def fit_circle_xy(P):
    """Fit minimi quadrati di un cerchio sulle proiezioni XY. Ritorna (cx, cy, r, rms)."""
    x, y = P[:, 0], P[:, 1]
    A = np.c_[2*x, 2*y, np.ones(len(x))]
    sol, *_ = np.linalg.lstsq(A, x**2 + y**2, rcond=None)
    cx, cy = sol[0], sol[1]
    r = math.sqrt(sol[2] + cx**2 + cy**2)
    rms = float(np.sqrt(np.mean((np.hypot(x-cx, y-cy) - r)**2)))
    return cx, cy, r, rms

def report(name, V, tris):
    idx = sorted({i for t in tris for i in t})
    P = V[idx]
    print(f"\n{'='*70}\n{name}: {len(tris)} tri, {len(idx)} vertici unici")
    lo, hi = P.min(0), P.max(0)
    print(f"  bbox  X {lo[0]:9.4f}..{hi[0]:9.4f}  dX={hi[0]-lo[0]:8.4f}")
    print(f"        Y {lo[1]:9.4f}..{hi[1]:9.4f}  dY={hi[1]-lo[1]:8.4f}")
    print(f"        Z {lo[2]:9.4f}..{hi[2]:9.4f}  dZ={hi[2]-lo[2]:8.4f}")

    g = planes(V, tris)
    print(f"\n  -- piani (area >= 1 mm^2), {len(g)} gruppi totali --")
    axis = {0: 'X', 1: 'Y', 2: 'Z'}
    for n, d, area, ts in g:
        if area < 1.0: continue
        lab = ''
        for k in range(3):
            if abs(abs(n[k]) - 1) < 1e-3: lab = f"  _|_{axis[k]} @ {axis[k]}={d*np.sign(n[k]):.4f}"
        print(f"    n=({n[0]:+.4f},{n[1]:+.4f},{n[2]:+.4f}) d={d:+9.4f} area={area:9.3f}{lab}")

    curved = [t for n, d, a, ts in g if a < 1.0 for t in ts]
    if curved:
        ci = sorted({i for t in curved for i in t})
        C = V[ci]
        print(f"\n  -- superfici curve: {len(curved)} tri, {len(ci)} vertici --")
        # separa per componenti connesse in XY (clustering grezzo sulla distanza)
        clusters, used = [], set()
        for i in ci:
            if i in used: continue
            stack, comp = [i], []
            used.add(i)
            while stack:
                j = stack.pop(); comp.append(j)
                for k in ci:
                    if k not in used and np.linalg.norm(V[j][:2] - V[k][:2]) < 1.5:
                        used.add(k); stack.append(k)
            clusters.append(comp)
        for ci2 in clusters:
            Q = V[ci2]
            cx, cy, r, rms = fit_circle_xy(Q)
            print(f"    cluster {len(ci2):4d} vtx  Z {Q[:,2].min():7.3f}..{Q[:,2].max():7.3f}"
                  f"  cerchio XY: c=({cx:8.4f},{cy:8.4f}) R={r:8.4f} rms={rms:.5f}")

V, objs = load(sys.argv[1])
for name, tris in objs.items():
    report(name, V, tris)
