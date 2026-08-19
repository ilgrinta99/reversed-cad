"""Render ortografici z-buffer della mesh OBJ, per ispezione visiva rapida."""
import sys, zlib, struct, math
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

def png(path, rgb):
    h, w, _ = rgb.shape
    raw = b''.join(b'\x00' + rgb[y].tobytes() for y in range(h))
    def ch(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c))
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n'
        + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
        + ch(b'IDAT', zlib.compress(raw, 9)) + ch(b'IEND', b''))

def render(V, T, u, v, d, W=900, pad=20, flip_v=True):
    """u,v = assi immagine; d = asse profondita' (verso l'osservatore)."""
    P = V[:, [u, v]].copy(); D = V[:, d]
    used = np.unique(T)
    lo, hi = P[used].min(0), P[used].max(0)
    s = (W - 2*pad) / max(hi[0]-lo[0], 1e-9)
    H = int((hi[1]-lo[1]) * s) + 2*pad
    img = np.full((H, W, 3), 250, np.uint8)
    zb = np.full((H, W), -1e18)
    tri = V[T]
    n = np.cross(tri[:,1]-tri[:,0], tri[:,2]-tri[:,0])
    ln = np.linalg.norm(n, axis=1); ok = ln > 1e-12
    n[ok] /= ln[ok, None]
    light = n @ np.array([0.35, 0.35, 0.87])
    order = np.argsort(tri[:, :, d].mean(1))
    for ti in order:
        a, b, c = T[ti]
        pts = np.array([[ (P[i,0]-lo[0])*s+pad, (P[i,1]-lo[1])*s+pad ] for i in (a,b,c)])
        if flip_v: pts[:,1] = H - pts[:,1]
        x0,y0 = np.floor(pts.min(0)).astype(int); x1,y1 = np.ceil(pts.max(0)).astype(int)
        x0,y0 = max(x0,0), max(y0,0); x1,y1 = min(x1,W-1), min(y1,H-1)
        if x1 < x0 or y1 < y0: continue
        yy, xx = np.mgrid[y0:y1+1, x0:x1+1]
        (ax,ay),(bx,by),(cx,cy) = pts
        den = (by-cy)*(ax-cx) + (cx-bx)*(ay-cy)
        if abs(den) < 1e-12: continue
        w0 = ((by-cy)*(xx-cx) + (cx-bx)*(yy-cy)) / den
        w1 = ((cy-ay)*(xx-cx) + (ax-cx)*(yy-cy)) / den
        w2 = 1 - w0 - w1
        m = (w0>=-1e-6) & (w1>=-1e-6) & (w2>=-1e-6)
        if not m.any(): continue
        z = w0*D[a] + w1*D[b] + w2*D[c]
        m &= z > zb[y0:y1+1, x0:x1+1]
        if not m.any(): continue
        sh = int(np.clip(60 + 195*abs(light[ti]), 0, 255))
        sub = img[y0:y1+1, x0:x1+1]
        sub[m] = [sh, sh, min(255, sh+18)]
        zbs = zb[y0:y1+1, x0:x1+1]; zbs[m] = z[m]
    return img

V, objs = load(sys.argv[1])
out = sys.argv[2]
VIEWS = {'top': (0,1,2), 'front': (0,2,1), 'right': (1,2,0), 'left': (1,2,0)}
for name, T in objs.items():
    for vn, (u,v,d) in VIEWS.items():
        Vv = V.copy()
        if vn == 'front': Vv[:,1] *= -1          # guarda da -Y
        if vn == 'left':  Vv[:,0] *= -1; Vv[:,1] *= -1
        png(f"{out}/{name}_{vn}.png", render(Vv, T, u, v, d))
        print(f"{out}/{name}_{vn}.png")
