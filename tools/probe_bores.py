import numpy as np, math
exec(open('tools/segment_features.py').read().split("V, objs = load")[0])
src=open("tools/slice_mesh.py").read().split("if __name__")[0]
exec(src[src.index("def section"):])
V, objs = load('input/model.obj'); T = objs['obj_0']
import sys; sys.setrecursionlimit(20000)

for lab, xv in (('X=29.5 (subito fuori parete interna)', 29.5), ('X=32.0 (dentro la cupola)', 32.0),
                ('X=34.0', 34.0), ('X=35.4', 35.4)):
    segs = section(V, T, 0, xv); ch = chains(segs)
    small = [c for c in ch if len(c) < 200]
    print(f"\n### {lab}: {len(ch)} contorni ({len(small)} piccoli)")
    for P in sorted(ch, key=len, reverse=True):
        Y, Z = P[:,1], P[:,2]
        dy, dz = Y.max()-Y.min(), Z.max()-Z.min()
        if dy > 30: kind = 'sagoma esterna'
        else: kind = 'FORO/canale'
        A = np.c_[2*Y, 2*Z, np.ones(len(P))]
        s,*_ = np.linalg.lstsq(A, Y**2+Z**2, rcond=None)
        r = math.sqrt(max(s[2]+s[0]**2+s[1]**2, 0))
        rms = np.sqrt(np.mean((np.hypot(Y-s[0], Z-s[1])-r)**2))
        print(f"  {kind:14s} n={len(P):4d}  Y[{Y.min():8.3f},{Y.max():8.3f}] dY={dy:6.3f}"
              f"  Z[{Z.min():7.3f},{Z.max():7.3f}] dZ={dz:6.3f}"
              f"  | cerchio c=({s[0]:7.3f},{s[1]:6.3f}) R={r:6.3f} rms={rms:.4f}")
