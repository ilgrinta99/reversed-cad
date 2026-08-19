"""Segmenta la mesh in patch di superficie e le classifica (piano/cilindro/sfera/altro).

Usato per recuperare le quote NON presenti sulla tavola TinkerCAD.
"""
import sys, math
from collections import defaultdict
import numpy as np

def load(path):
    objs, cur, V = {}, None, []
    for line in open(path):
        w = line.split()
        if not w: continue
        if w[0] == 'o': cur = w[1]; objs[cur] = []
        elif w[0] == 'v': V.append([float(x) for x in w[1:4]])
        elif w[0] == 'f':
            idx = [int(t.split('/')[0]) - 1 for t in w[1:]]
            for i in range(1, len(idx)-1): objs[cur].append((idx[0], idx[i], idx[i+1]))
    return np.array(V), {k: np.array(v) for k, v in objs.items()}

def weld(V, tol=1e-4):
    key = np.round(V / tol).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    return inv

def patches(V, T, w, ang=25.0):
    """Componenti connesse per spigolo, spezzate dove le normali divergono > ang."""
    n = np.cross(V[T[:,1]]-V[T[:,0]], V[T[:,2]]-V[T[:,0]])
    ln = np.linalg.norm(n, axis=1); good = ln > 1e-12
    n[good] /= ln[good, None]
    edge = defaultdict(list)
    for i, t in enumerate(T):
        a, b, c = w[t[0]], w[t[1]], w[t[2]]
        for e in ((a,b),(b,c),(c,a)):
            edge[tuple(sorted(e))].append(i)
    seen = np.zeros(len(T), bool)
    out = []
    cos = math.cos(math.radians(ang))
    for s in range(len(T)):
        if seen[s] or not good[s]: continue
        seen[s] = True; stack=[s]; comp=[s]
        while stack:
            i = stack.pop()
            a,b,c = w[T[i][0]], w[T[i][1]], w[T[i][2]]
            for e in ((a,b),(b,c),(c,a)):
                for j in edge[tuple(sorted(e))]:
                    if not seen[j] and good[j] and n[i] @ n[j] > cos:
                        seen[j]=True; stack.append(j); comp.append(j)
        out.append((np.array(comp), n[comp], ln[comp]/2))
    return out

def fit_cyl(P, axis):
    o = [i for i in range(3) if i != axis]
    x, y = P[:, o[0]], P[:, o[1]]
    A = np.c_[2*x, 2*y, np.ones(len(x))]
    sol, *_ = np.linalg.lstsq(A, x**2 + y**2, rcond=None)
    cx, cy = sol[0], sol[1]
    r = math.sqrt(max(sol[2] + cx**2 + cy**2, 0))
    rms = float(np.sqrt(np.mean((np.hypot(x-cx, y-cy) - r)**2)))
    return (cx, cy), r, rms, o

def classify(V, T, comp, N, A):
    P = V[np.unique(T[comp])]
    area = A.sum()
    nm = N.mean(0); nm /= np.linalg.norm(nm)
    spread = float(np.degrees(np.arccos(np.clip(N @ nm, -1, 1))).max())
    lo, hi = P.min(0), P.max(0)
    info = {'area': area, 'n': len(P), 'bbox': (lo, hi), 'spread': spread, 'nmean': nm}
    if spread < 1.0:
        info['type'] = 'PIANO'; info['d'] = float(nm @ P.mean(0))
        return info
    best = None
    for ax in range(3):
        if len(P) < 6: break
        c, r, rms, o = fit_cyl(P, ax)
        ext = hi[ax] - lo[ax]
        if r > 1e-6 and rms / r < 0.02 and ext > 1e-6:
            sc = rms / r
            if best is None or sc < best[0]: best = (sc, ax, c, r, rms, o, ext)
    if best:
        _, ax, c, r, rms, o, ext = best
        info.update(type='CILINDRO', axis='XYZ'[ax], center=c, r=r, rms=rms,
                    oax='XYZ'[o[0]] + 'XYZ'[o[1]], length=ext)
        return info
    info['type'] = 'ALTRO'
    return info

V, objs = load(sys.argv[1])
w = weld(V)
for name, T in objs.items():
    print(f"\n{'#'*72}\n# {name}\n{'#'*72}")
    ps = patches(V, T, w)
    rows = [classify(V, T, c, n, a) for c, n, a in ps]
    rows.sort(key=lambda r: -r['area'])
    for r in rows:
        if r['area'] < 0.30: continue
        lo, hi = r['bbox']
        bb = f"X[{lo[0]:8.3f},{hi[0]:8.3f}] Y[{lo[1]:8.3f},{hi[1]:8.3f}] Z[{lo[2]:8.3f},{hi[2]:8.3f}]"
        if r['type'] == 'PIANO':
            nm = r['nmean']
            ax = ''.join(f"{'XYZ'[k]}" for k in range(3) if abs(abs(nm[k])-1) < 1e-3)
            print(f"  PIANO    A={r['area']:9.3f} n=({nm[0]:+.3f},{nm[1]:+.3f},{nm[2]:+.3f})"
                  f"{(' _|_'+ax+f' @ {r['d']*np.sign(nm['XYZ'.index(ax)]):+.4f}') if ax else '':>22}  {bb}")
        elif r['type'] == 'CILINDRO':
            print(f"  CILINDRO A={r['area']:9.3f} asse={r['axis']}  R={r['r']:8.4f} (D={2*r['r']:8.4f})"
                  f" c({r['oax']})=({r['center'][0]:+8.3f},{r['center'][1]:+8.3f}) L={r['length']:7.3f}"
                  f" rms={r['rms']:.4f}  {bb}")
        else:
            print(f"  ALTRO    A={r['area']:9.3f} spread={r['spread']:6.1f}deg  {bb}")
