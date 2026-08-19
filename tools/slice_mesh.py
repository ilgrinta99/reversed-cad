"""Sezioni piane della mesh: restituisce le polilinee di intersezione, semplificate."""
import sys, math
import numpy as np
exec(open('tools/segment_features.py').read().split("V, objs = load")[0])

def section(V, T, axis, val):
    segs = []
    for t in T:
        p = V[list(t)]; d = p[:, axis] - val
        s = np.sign(d); 
        if abs(s.sum()) == 3: continue
        pts = []
        for i in range(3):
            j = (i+1) % 3
            if d[i] == 0: pts.append(p[i])
            elif d[i]*d[j] < 0:
                pts.append(p[i] + (p[j]-p[i]) * (d[i]/(d[i]-d[j])))
        if len(pts) >= 2: segs.append((pts[0], pts[1]))
    return segs

def chains(segs, tol=1e-4):
    """Concatena i segmenti in polilinee."""
    from collections import defaultdict
    key = lambda p: tuple(np.round(p/tol).astype(np.int64))
    adj = defaultdict(list); pos = {}
    for a, b in segs:
        ka, kb = key(a), key(b); pos[ka], pos[kb] = a, b
        adj[ka].append(kb); adj[kb].append(ka)
    seen, out = set(), []
    for k in adj:
        if k in seen: continue
        ch = [k]; seen.add(k); cur = k
        while True:
            nxt = [x for x in adj[cur] if x not in seen]
            if not nxt: break
            cur = nxt[0]; seen.add(cur); ch.append(cur)
        if len(ch) > 2: out.append(np.array([pos[c] for c in ch]))
    return out

def simplify(P, tol):
    """Douglas-Peucker."""
    if len(P) < 3: return P
    d = P[-1] - P[0]; L = np.linalg.norm(d)
    if L < 1e-12:
        dist = np.linalg.norm(P - P[0], axis=1)
    else:
        u = d / L; W = P - P[0]
        dist = np.abs(W[:,0]*u[1] - W[:,1]*u[0])
    i = int(dist.argmax())
    if dist[i] <= tol: return np.array([P[0], P[-1]])
    return np.vstack([simplify(P[:i+1], tol)[:-1], simplify(P[i:], tol)])

if __name__ == '__main__':
    V, objs = load('input/model.obj')
    sys.setrecursionlimit(10000)
    for obj, axis, val, tol in [('obj_0', 2, 10.7275, 0.05),   # pianta a meta' cupola
                                ('obj_0', 1, -27.9175, 0.05),  # sezione longitudinale
                                ('obj_1', 1, 56.833, 0.02),    # coperchio, sez. trasversale
                                ('obj_1', 0, -9.0, 0.02)]:
        segs = section(V, objs[obj], axis, val)
        ch = chains(segs)
        ax = 'XYZ'[axis]
        print(f"\n### {obj}  sezione {ax}={val}  -> {len(ch)} contorni")
        for P in sorted(ch, key=len, reverse=True)[:6]:
            keep = [i for i in range(3) if i != axis]
            Q = simplify(P[:, keep], tol)
            print(f"  contorno {len(P)} pt -> {len(Q)} vertici ({'XYZ'[keep[0]]},{'XYZ'[keep[1]]}):")
            print('   ', ' '.join(f"({a:.3f},{b:.3f})" for a, b in Q))
