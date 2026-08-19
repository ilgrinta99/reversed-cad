"""Estrae TUTTI i parametri geometrici dalla mesh e li scrive in cad/params.json.

Sistema di riferimento del modello (lost+found_design.md 5-G):
origine al centro della base del corpo rettangolare della scatola,
X = lunghezza, Y = larghezza, Z = verso l'alto.
    x' = x + 6.77      y' = y + 27.90      z' = z
"""
import json, math
import numpy as np
exec(open('tools/segment_features.py').read().split("V, objs = load")[0])

DX, DY = 6.77, 27.90
V, objs = load('input/model.obj')
P0 = V[np.unique(objs['obj_0'])]
P1 = V[np.unique(objs['obj_1'])]
def to_model(p): return np.array([p[0]+DX, p[1]+DY, p[2]])

# ---- piani di smusso delle 4 colonnine: ricavo n e d esatti
w = weld(V)
cham = []
for comp, N, A in patches(V, objs['obj_0'], w):
    if A.sum() < 40: continue
    nm = N.mean(0); nm /= np.linalg.norm(nm)
    if abs(nm[2]) > 0.9 or abs(nm[2]) < 0.1: continue
    if min(abs(nm[0]), abs(nm[1])) < 0.2: continue
    Q = V[np.unique(objs['obj_0'][comp])]
    d = float(nm @ Q.mean(0))
    # riscrivo il piano nel riferimento del modello: n . (p' - t) = d  ->  d' = d + n.t
    dp = d + float(nm @ np.array([DX, DY, 0.0]))
    cham.append({'n': [round(float(x), 4) for x in nm], 'd': round(dp, 4),
                 'area': round(float(A.sum()), 3),
                 'bbox': [round(float(x), 3) for x in
                          list(to_model(Q.min(0))) + list(to_model(Q.max(0)))]})
cham.sort(key=lambda c: (-c['n'][0], -c['n'][1]))

# ---- assi dei due fori inclinati nella cupola (via contorni di sezione)
src = open('tools/slice_mesh.py').read().split("if __name__")[0]
exec(src[src.index("def section"):])
import sys; sys.setrecursionlimit(20000)

def bores():
    """Isola i 2 canali sezionando la scatola con piani X e prendendo i contorni piccoli."""
    XS = [29.2, 30.0, 31.0, 32.0, 33.0, 34.0, 34.8]
    tracks = {'A': [], 'B': []}
    for xv in XS:
        for C in chains(section(V, objs['obj_0'], 0, xv)):
            Y, Z = C[:, 1], C[:, 2]
            dy, dz = Y.max()-Y.min(), Z.max()-Z.min()
            if not (1.5 < dy < 4.0 and 1.5 < dz < 4.0): continue   # solo i canali
            zc = (Z.min()+Z.max())/2
            if not (10.0 < zc < 12.5): continue                     # esclude il foro D3
            yc = (Y.min()+Y.max())/2
            tracks['A' if yc > -28 else 'B'].append((xv, yc, zc, dy, dz))
    out = {}
    for k, pts in tracks.items():
        A = np.array(pts)
        sy = np.polyfit(A[:,0], A[:,1], 1); sz = np.polyfit(A[:,0], A[:,2], 1)
        xr = 28.867
        res = np.abs(np.polyval(sy, A[:,0]) - A[:,1]).max()
        out[k] = {'punto': [round(xr+DX, 4), round(float(np.polyval(sy, xr))+DY, 4),
                            round(float(np.polyval(sz, xr)), 4)],
                  'dir': [1.0, round(float(sy[0]), 5), round(float(sz[0]), 5)],
                  'angolo_XY_deg': round(math.degrees(math.atan(abs(sy[0]))), 3),
                  'sez_perp_X_YxZ': [round(float(A[:,3].mean()), 4), round(float(A[:,4].mean()), 4)],
                  '_n_sezioni': len(A), '_residuo_max_mm': round(float(res), 4)}
    return out
_bores = bores()

# ---- rilievo asolato dentro la tasca sulla faccia X-: sagoma dai vertici della faccia
def rilievo_tasca_sx():
    Q = P0.copy(); Q = np.c_[Q[:,0]+DX, Q[:,1]+DY, Q[:,2]]
    S = Q[(np.abs(Q[:,0] + 36.93) < 1e-6) & (Q[:,1] > -16) & (Q[:,1] < -3)
          & (Q[:,2] > 19) & (Q[:,2] < 25)]
    S = S[np.argsort(S[:,1])]
    gaps = np.where(np.diff(S[:,1]) > 0.35)[0]
    G = np.split(S, gaps + 1)
    heads = []
    for g in G:
        if len(g) < 10: continue                      # scarto i lati dritti
        A = np.c_[2*g[:,1], 2*g[:,2], np.ones(len(g))]
        sol, *_ = np.linalg.lstsq(A, g[:,1]**2 + g[:,2]**2, rcond=None)
        r = math.sqrt(max(sol[2] + sol[0]**2 + sol[1]**2, 0))
        heads.append((float(sol[0]), float(sol[1]), r))
    assert len(heads) == 2, 'attese 2 testate, trovate %d' % len(heads)
    (y1, z1, r1), (y2, z2, r2) = heads
    R = (r1 + r2) / 2.0
    return {'forma': 'asola', 'W_z': round(float(S[:,2].max() - S[:,2].min()), 4),
            'L_y': round(abs(y2 - y1) + 2 * R, 4),
            'cy': round((y1 + y2) / 2.0, 4), 'cz': round((z1 + z2) / 2.0, 4),
            '_R_testate': [round(r1, 4), round(r2, 4)],
            '_nota': 'a filo della faccia esterna, quindi alto quanto la tasca (0.690)'}
_ril = rilievo_tasca_sx()


# I piani di smusso sono 3, non 4: la colonnina (x<0, y<0) non e' una colonnina
# alta smussata ma un blocco basso z 24.002..27 (verificato con sezioni in pianta).
assert len(cham) == 3, 'attesi 3 piani di smusso, trovati %d' % len(cham)

# ---- raccolta
p = {
  '_nota': 'Tutti i valori in mm, misurati da input/model.obj. Riferimento: lost+found_design.md 5-G.',
  '_offset_mesh_modello': {'dx': DX, 'dy': DY, 'dz': 0.0},
  'scatola': {
    'corpo': {'L': 73.86, 'W': 46.0, 'H': 27.0,
              '_H_misurata': 26.999, '_L_note': 'senza cupola; con cupola 80.00 = tavola T1'},
    'pareti': {'t_x': 1.3, 't_y': 2.2, '_t_x_misurato': 1.293, '_t_y_misurato': 2.188},
    'fondo':  {'t': 1.6, '_misurato': 1.634},
    'raccordo_base': {'R': 1.5, '_misurato_ellittico': [1.514, 1.422],
                      '_nota': 'reso circolare per decisione A'},
    'cavita': {'L': 71.26, 'W': 41.60, 'z_fondo': 1.6, 'z_top': 27.0,
               '_misurata': [71.274, 41.624, 25.365]},
    'cupola': {
      'tipo': 'paraboloide ellittico',
      'eq': "(x - x0)/a = 1 - ((y-cy)/b)^2 - ((z-cz)/c)^2",
      'x0': 36.93, 'a': 6.1400, 'b': 17.3810, 'c': 8.1880,
      'cy': 0.0, 'cz': 10.7275,
      '_cy_misurato': round(-27.9175 + DY, 4),
      '_fit': {'p': 1.00, 'q': 2.00, 'scarto_max_mm': 0.117,
               '_confronto_ellissoide_max_mm': 1.610},
      'piena': True},
    'foro_parete_dx': {'D': 3.002, 'asse': 'X', 'y': round(-46.0+DY, 3), 'z': 4.25,
                       '_R_fit': 1.501, '_rms_fit': 0.0016},
    'fori_cupola': {'A': _bores['A'], 'B': _bores['B'],
                    '_forma': 'ellisse in sezione perpendicolare a X'},
    'asola_frontale': {'L_x': 6.467, 'H_z': 4.005,
                       'cx': round((-8.157 + -1.690)/2 + DX, 4), 'cz': 23.7495,
                       'parete': 'Y-'},
    'tasca_sx': {'prof': 0.690, 'W_y': 19.790, 'H_z': 11.005,
                 'cy': round((-48.677 + -28.887)/2 + DY, 4), 'cz': 18.4995,
                 'faccia': 'X-',
                 'rilievo': _ril},
    'colonnine': {
      '_nota': 'NON sono 4 uguali: 3 colonnine alte con smusso + 1 blocco basso diverso '
               '(vedi BUILD-LOG 2026-08-19 FASE 5)',
      'standard': {'n': 3, 'segni_xy': [[1, 1], [1, -1], [-1, 1]],
                   'L_x': 5.183, 'W_y': 8.762, 'z_base': 14.191, 'z_top': 27.0,
                   'x_int': 30.451, 'x_est': 35.634, 'y_int': 12.048, 'y_est': 20.810,
                   'smusso_z_top': 23.171, 'piani_smusso': cham,
                   'foro': {'forma': 'asola', 'W': 1.625, 'L': 2.743,
                            'z_base': 17.687, 'cx': 33.0425, 'cy': 16.4285}},
      'speciale': {'n': 1, 'segni_xy': [[-1, -1]],
                   'L_x': 5.183, 'W_y': 10.090, 'z_base': 24.002, 'z_top': 27.0,
                   'x_int': 30.451, 'x_est': 35.634, 'y_int': 10.720, 'y_est': 20.810,
                   'smusso': None,
                   'foro': {'forma': 'asola', 'W': 1.625, 'L': 3.158,
                            'z_base': 24.002, 'cx': 33.0425, 'cy': 15.765}}},
    'nervature': {'n': 2, 'parete': 'Y-', 't_x': 1.846,
                  'x_centri': [round((1.078+2.924)/2 + DX, 4), round((-12.771+-10.925)/2 + DX, 4)],
                  'y_da': round(-48.712+DY, 3), 'y_a': round(-42.861+DY, 3),
                  'z_min': 23.202, 'z_max': 24.890, '_R_arco_fit': 2.986},
  },
  'coperchio': {
    'piastra': {'L': 73.86, 'W': 46.0, 'S': 2.5,
                '_L_mesh': 74.0, '_L_tavola': 74.0,
                '_nota': 'portato a 73.86 per decisione F (filo esterno corpo scatola)'},
    'raccordo_base': {'R': 1.5, '_misurato_ellittico': [1.484, 1.801],
                      'z_fascia_netta': 1.801},
    'asole': {'n': 4, 'W': 1.952, 'L': 3.291, 'R_testa': 0.976,
              '_R_fit': [0.929, 0.998], 'cx': 33.105, 'cy': 16.4285, 'passanti': True},
    'tasca_grande': {'forma': 'rettangolo', 'L_x': 12.030, 'W_y': 12.865, 'prof': 0.502,
                     'cx': round((-36.290 + -24.260)/2 + 9.0, 4),
                     'cy': round((39.766 + 52.631)/2 - 56.833, 4)},
    'tasca_annidata': {'forma': 'ellisse', '_R_angoli_fit': 2.400,
                       'L_x': 4.630, 'W_y': 4.951, 'prof': 1.502,
                       'cx': round((-32.590 + -27.960)/2 + 9.0, 4),
                       'cy': round((43.723 + 48.674)/2 - 56.833, 4)},
    'tasche_piccole': {'n': 2, 'forma': 'ellisse', '_R_angoli_fit': 1.429,
                       'L_x': 2.780, 'W_y': 2.973, 'prof': 1.502,
                       'cx': [round((12.735+15.515)/2 + 9.0, 4), round((17.360+20.140)/2 + 9.0, 4)],
                       'cy': round((51.637 + 54.610)/2 - 56.833, 4)},
    '_nota_riferimento': 'coperchio ricentrato: cx = x_mesh + 9.0, cy = y_mesh - 56.833',
  },
}
json.dump(p, open('cad/params.json', 'w'), indent=2, ensure_ascii=False)
print(json.dumps(p['scatola']['fori_cupola'], indent=2, ensure_ascii=False))
print(f"\npiani smusso colonnine: {len(cham)}")
for c in cham: print("  n=", c["n"], " d=", c["d"], "", c.get("_nota", ""))
print("\nscritto cad/params.json")
