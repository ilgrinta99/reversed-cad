import numpy as np, math, sys
exec(open('tools/segment_features.py').read().split("V, objs = load")[0])
src = open('tools/slice_mesh.py').read().split("if __name__")[0]
exec(src[src.index("def section"):])
sys.setrecursionlimit(20000)
V, objs = load('input/model.obj')
DX, DY = 6.77, 27.9

print("### nervature nella tasca faccia X- (sezione X=-43.35 mesh)")
for C in chains(section(V, objs['obj_0'], 0, -43.35)):
    Y, Z = C[:,1]+DY, C[:,2]
    if Y.max()-Y.min() > 25: lab='contorno esterno'
    else: lab='FEATURE'
    A = np.c_[2*Y, 2*Z, np.ones(len(C))]
    s,*_ = np.linalg.lstsq(A, Y**2+Z**2, rcond=None)
    r = math.sqrt(max(s[2]+s[0]**2+s[1]**2,0))
    print(f"  {lab:16s} n={len(C):4d} Y[{Y.min():8.3f},{Y.max():8.3f}] d={Y.max()-Y.min():6.3f}"
          f" Z[{Z.min():7.3f},{Z.max():7.3f}] d={Z.max()-Z.min():6.3f}"
          f" | R={r:6.3f} c=({s[0]:7.3f},{s[1]:6.3f})")

print("\n### colonnine: pianta a Z=25.5 e Z=20.0 (mesh -> modello)")
for zv in (25.5, 22.0, 20.0):
    print(f"  -- Z={zv} --")
    for C in chains(section(V, objs['obj_0'], 2, zv)):
        X, Y = C[:,0]+DX, C[:,1]+DY
        if X.max()-X.min() > 60: continue
        print(f"     n={len(C):4d} X[{X.min():8.3f},{X.max():8.3f}] Y[{Y.min():8.3f},{Y.max():8.3f}]"
              f"  {X.max()-X.min():6.3f} x {Y.max()-Y.min():6.3f}")

print("\n### coperchio: raggi d'angolo delle tasche")
P1 = V[np.unique(objs['obj_1'])]
SX = 73.86/74.0
def corners(zc, xr, yr, lab):
    S = P1[(np.abs(P1[:,2]-zc) < 0.02)]
    S = S[(S[:,0] > xr[0]-0.2) & (S[:,0] < xr[1]+0.2) & (S[:,1] > yr[0]-0.2) & (S[:,1] < yr[1]+0.2)]
    if len(S) < 8: print(f"  {lab}: nessun punto"); return
    print(f"  {lab}: n={len(S)} X[{S[:,0].min():.3f},{S[:,0].max():.3f}] Y[{S[:,1].min():.3f},{S[:,1].max():.3f}]")
    for cx, cy in ((xr[0], yr[0]), (xr[1], yr[0]), (xr[0], yr[1]), (xr[1], yr[1])):
        q = S[(np.abs(S[:,0]-cx) < 2.2) & (np.abs(S[:,1]-cy) < 2.2)]
        if len(q) < 4: continue
        A = np.c_[2*q[:,0], 2*q[:,1], np.ones(len(q))]
        s,*_ = np.linalg.lstsq(A, q[:,0]**2+q[:,1]**2, rcond=None)
        r = math.sqrt(max(s[2]+s[0]**2+s[1]**2,0))
        rms = np.sqrt(np.mean((np.hypot(q[:,0]-s[0], q[:,1]-s[1])-r)**2))
        print(f"     angolo ({cx:8.3f},{cy:8.3f}) n={len(q):3d}  R={r:6.3f} rms={rms:.4f}")
corners(1.998, (-36.290,-24.260), (39.766,52.631), 'tasca_grande  (fondo z=1.998)')
corners(0.998, (-32.590,-27.960), (43.723,48.674), 'tasca_annidata(fondo z=0.998)')
corners(0.998, (12.735,15.515), (51.637,54.610), 'tasca_piccola1(fondo z=0.998)')
