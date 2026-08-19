import numpy as np, math, sys
exec(open('tools/segment_features.py').read().split("V, objs = load")[0])
V, objs = load('input/model.obj')
T = objs['obj_0']
P = V[np.unique(T)]

# --- cupola: vertici con X > 30.20 ---
D = P[P[:,0] > 30.20]
print(f"CUPOLA: {len(D)} vtx  X {D[:,0].min():.3f}..{D[:,0].max():.3f}"
      f"  Y {D[:,1].min():.3f}..{D[:,1].max():.3f}  Z {D[:,2].min():.3f}..{D[:,2].max():.3f}")
cy, cz = (D[:,1].min()+D[:,1].max())/2, (D[:,2].min()+D[:,2].max())/2
b, c = (D[:,1].max()-D[:,1].min())/2, (D[:,2].max()-D[:,2].min())/2
print(f"  centro Y={cy:.4f} Z={cz:.4f}   semiassi b(Y)={b:.4f} c(Z)={c:.4f}")
x0 = 30.160
for a in (D[:,0].max()-x0,):
    t = ((D[:,1]-cy)/b)**2 + ((D[:,2]-cz)/c)**2 + ((D[:,0]-x0)/a)**2
    print(f"  test ellissoide a(X)={a:.4f}: |t-1| medio={np.abs(t-1).mean():.4f} max={np.abs(t-1).max():.4f}")

# --- fori nella cupola: vertici in fascia Z ---
for ylo, yhi in ((-24,-16), (-40,-32)):
    H = P[(P[:,0] > 28.8) & (P[:,1] > ylo) & (P[:,1] < yhi) & (P[:,2] > 9.5) & (P[:,2] < 13)]
    print(f"\nFORO cupola Y[{ylo},{yhi}]: {len(H)} vtx  X {H[:,0].min():.3f}..{H[:,0].max():.3f}"
          f"  Y {H[:,1].min():.3f}..{H[:,1].max():.3f} (d={H[:,1].max()-H[:,1].min():.3f})"
          f"  Z {H[:,2].min():.3f}..{H[:,2].max():.3f} (d={H[:,2].max()-H[:,2].min():.3f})")
    A = np.c_[2*H[:,1], 2*H[:,2], np.ones(len(H))]
    s,*_ = np.linalg.lstsq(A, H[:,1]**2+H[:,2]**2, rcond=None)
    r = math.sqrt(s[2]+s[0]**2+s[1]**2)
    print(f"   fit cerchio YZ: c=({s[0]:.4f},{s[1]:.4f}) R={r:.4f} D={2*r:.4f}"
          f" rms={np.sqrt(np.mean((np.hypot(H[:,1]-s[0],H[:,2]-s[1])-r)**2)):.4f}")

# --- coperchio: curvatura del fondo ---
L = V[np.unique(objs['obj_1'])]
B = L[L[:,2] < 1.79]
print(f"\nCOPERCHIO fondo (Z<1.79): {len(B)} vtx  Z {B[:,2].min():.4f}..{B[:,2].max():.4f}")
for lab, ax in (('lungo X', 0), ('lungo Y', 1)):
    o = 1 - ax
    m = np.abs(L[:, o] - np.median(L[:, o])) < 3
    S = L[m & (L[:,2] < 1.0)]
    if len(S) > 5:
        print(f"  sezione {lab}: n={len(S)} Z {S[:,2].min():.4f}..{S[:,2].max():.4f}"
              f" freccia={S[:,2].max()-S[:,2].min():.4f}")
