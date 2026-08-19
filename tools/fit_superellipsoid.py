"""Fit del profilo della cupola come semi-superellissoide, e rilievo delle asole."""
import numpy as np, math
exec(open('tools/segment_features.py').read().split("V, objs = load")[0])
V, objs = load('input/model.obj')
P0 = V[np.unique(objs['obj_0'])]
P1 = V[np.unique(objs['obj_1'])]

# ---------------------------------------------------------------- CUPOLA
X0 = 30.160                      # piano di attacco (parete destra esterna)
D = P0[P0[:,0] > X0 + 0.02]
cy, cz = -27.9175, 10.7275

# 1) le sezioni a X costante sono ellissi con rapporto b/c costante?
print("== sezioni della cupola a X costante ==")
print(f"{'X':>8} {'n':>5} {'semi-Y':>8} {'semi-Z':>8} {'b/c':>7} {'v=(X-X0)/a':>11}")
a0 = D[:,0].max() - X0
for xv in np.arange(0.5, a0, 0.7):
    S = D[np.abs(D[:,0] - (X0+xv)) < 0.18]
    if len(S) < 20: continue
    b = (S[:,1].max()-S[:,1].min())/2; c = (S[:,2].max()-S[:,2].min())/2
    print(f"{X0+xv:8.3f} {len(S):5d} {b:8.3f} {c:8.3f} {b/c:7.3f} {xv/a0:11.3f}")

b0 = (D[:,1].max()-D[:,1].min())/2
c0 = (D[:,2].max()-D[:,2].min())/2
print(f"\nsemiassi alla base: a={a0:.4f} b={b0:.4f} c={c0:.4f}  (b/c={b0/c0:.3f})")

# 2) fit  v^p + u^q = 1
u = np.hypot((D[:,1]-cy)/b0, (D[:,2]-cz)/c0)
v = (D[:,0]-X0)/a0
m = (u > 0.05) & (u < 0.98) & (v > 0.02) & (v < 0.98)
U, W = u[m], v[m]
best = None
for p in np.arange(1.0, 6.01, 0.05):
    for q in np.arange(1.0, 6.01, 0.05):
        r = W**p + U**q - 1
        e = float(np.sqrt(np.mean(r**2)))
        if best is None or e < best[0]: best = (e, p, q)
e, p, q = best
print(f"fit  v^p + u^q = 1  ->  p={p:.2f}  q={q:.2f}   rms residuo={e:.4f}  (n={m.sum()})")
# scostamento radiale equivalente in mm
vpred = np.clip(1 - U**q, 0, None)**(1/p)
print(f"scostamento su X: medio={np.abs(vpred-W).mean()*a0:.4f} mm  max={np.abs(vpred-W).max()*a0:.4f} mm")
for pp, qq, lab in ((2, 2, 'ellissoide'), (p, q, 'fittato')):
    vp = np.clip(1 - U**qq, 0, None)**(1/pp)
    print(f"   confronto {lab:12s} p={pp:.2f} q={qq:.2f}: max {np.abs(vp-W).max()*a0:6.3f} mm")

# ---------------------------------------------------------------- ASOLE COPERCHIO
print("\n== asole del coperchio (sezione a Z=1.25) ==")
def outline(P, zc, tol=0.30):
    S = P[np.abs(P[:,2]-zc) < tol]
    return S
for xr, yr in ((-43.081,-41.129), (23.129,25.081)):
    for ylo, yhi in ((38.759,42.050), (71.616,74.907)):
        S = P1[(P1[:,0]>xr-0.3)&(P1[:,0]<yr+0.3)&(P1[:,1]>ylo-0.3)&(P1[:,1]<yhi+0.3)]
        if len(S)<10: continue
        w = S[:,0].max()-S[:,0].min(); h = S[:,1].max()-S[:,1].min()
        # fit cerchio sulle due testate
        ymid = (S[:,1].min()+S[:,1].max())/2
        print(f"  asola X[{S[:,0].min():.3f},{S[:,0].max():.3f}] Y[{S[:,1].min():.3f},{S[:,1].max():.3f}]"
              f"  {w:.3f} x {h:.3f}  Z[{S[:,2].min():.3f},{S[:,2].max():.3f}]  n={len(S)}")
        for lab, sel in (('testa Y-', S[S[:,1]<ymid]), ('testa Y+', S[S[:,1]>=ymid])):
            A = np.c_[2*sel[:,0], 2*sel[:,1], np.ones(len(sel))]
            s,*_ = np.linalg.lstsq(A, sel[:,0]**2+sel[:,1]**2, rcond=None)
            r = math.sqrt(max(s[2]+s[0]**2+s[1]**2,0))
            rms = np.sqrt(np.mean((np.hypot(sel[:,0]-s[0], sel[:,1]-s[1])-r)**2))
            print(f"      {lab}: R={r:.4f} c=({s[0]:.3f},{s[1]:.3f}) rms={rms:.4f} n={len(sel)}")
        break

# ---------------------------------------------------------------- APERTURE CUPOLA
print("\n== aperture nella cupola: fit del bordo ==")
for ylo, yhi in ((-24.5,-15.5), (-40.5,-31.5)):
    H = P0[(P0[:,0]>28.8)&(P0[:,1]>ylo)&(P0[:,1]<yhi)&(P0[:,2]>9.3)&(P0[:,2]<13.2)]
    # separa il bordo interno (X piu' grande = superficie esterna della cupola)
    for lab, sel in (('tutto', H), ('X>33', H[H[:,0]>33]), ('X<30.5', H[H[:,0]<30.5])):
        if len(sel)<8: continue
        print(f"  Y[{ylo},{yhi}] {lab:8s} n={len(sel):4d}"
              f"  X[{sel[:,0].min():7.3f},{sel[:,0].max():7.3f}]"
              f"  Y[{sel[:,1].min():8.3f},{sel[:,1].max():8.3f}] d={sel[:,1].max()-sel[:,1].min():6.3f}"
              f"  Z[{sel[:,2].min():7.3f},{sel[:,2].max():7.3f}] d={sel[:,2].max()-sel[:,2].min():6.3f}")
