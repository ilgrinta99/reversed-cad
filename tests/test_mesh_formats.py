"""Quattro formati, una sola geometria.

Non basta che ogni lettore restituisca «una mesh»: deve restituire *la stessa*
mesh. Questi test scrivono lo stesso cubo in OBJ, STL (ASCII e binario), PLY
(ASCII e binario) e VRML (1.0 e 2.0), poi confrontano quello che l'analisi ne
misura. Se un lettore sbaglia l'ordine dei vertici, perde un Transform o non
salda la topologia, il confronto lo dice subito.

I file li scriviamo qui invece di committarli: un binario nel repo è un file che
nessuno rilegge, e la sua struttura — proprio quella che il lettore deve capire —
resta invisibile alla revisione.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from core.mesh.analysis import analyze
from core.mesh.loader import SUFFISSI, load_mesh
from core.mesh.mesh import MeshNonLeggibile

#: Il cubo di prova: quote note per costruzione, come nel resto dei test.
LX, LY, LZ = 40.0, 25.0, 12.0

VERTICI = np.array([
    (0, 0, 0), (LX, 0, 0), (LX, LY, 0), (0, LY, 0),
    (0, 0, LZ), (LX, 0, LZ), (LX, LY, LZ), (0, LY, LZ),
], dtype=float)

#: Quadrilateri con la normale verso l'esterno: l'analisi legge il verso.
QUAD = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
        (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]

TRIANGOLI = [t for q in QUAD for t in ((q[0], q[1], q[2]), (q[0], q[2], q[3]))]


# ---------------------------------------------------------------- scrittori


def scrivi_obj(path: Path) -> Path:
    righe = ["o cubo"]
    righe += [f"v {x} {y} {z}" for x, y, z in VERTICI]
    righe += ["f " + " ".join(str(i + 1) for i in q) for q in QUAD]
    path.write_text("\n".join(righe) + "\n")
    return path


def scrivi_stl_ascii(path: Path) -> Path:
    righe = ["solid cubo"]
    for a, b, c in TRIANGOLI:
        n = _normale(a, b, c)
        righe += [f"  facet normal {n[0]} {n[1]} {n[2]}", "    outer loop"]
        righe += [f"      vertex {VERTICI[i][0]} {VERTICI[i][1]} {VERTICI[i][2]}"
                  for i in (a, b, c)]
        righe += ["    endloop", "  endfacet"]
    righe.append("endsolid cubo")
    path.write_text("\n".join(righe) + "\n")
    return path


def scrivi_stl_binario(path: Path) -> Path:
    # L'intestazione comincia con «solid»: è la trappola che fa sbagliare i
    # lettori che distinguono i due STL dalla prima parola.
    buf = bytearray(b"solid esportato da un test".ljust(80, b"\0"))
    buf += struct.pack("<I", len(TRIANGOLI))
    for a, b, c in TRIANGOLI:
        buf += struct.pack("<3f", *_normale(a, b, c))
        for i in (a, b, c):
            buf += struct.pack("<3f", *VERTICI[i])
        buf += struct.pack("<H", 0)
    path.write_bytes(bytes(buf))
    return path


def scrivi_ply_ascii(path: Path) -> Path:
    righe = ["ply", "format ascii 1.0", "element vertex 8",
             "property float x", "property float y", "property float z",
             # I colori stanno in mezzo apposta: vanno saltati contando i campi.
             "property uchar red", "property uchar green", "property uchar blue",
             "element face 6", "property list uchar int vertex_indices", "end_header"]
    righe += [f"{x} {y} {z} 200 200 200" for x, y, z in VERTICI]
    righe += ["4 " + " ".join(str(i) for i in q) for q in QUAD]
    path.write_text("\n".join(righe) + "\n")
    return path


def scrivi_ply_binario(path: Path, ordine: str = "<") -> Path:
    endian = "binary_little_endian" if ordine == "<" else "binary_big_endian"
    testa = (f"ply\nformat {endian} 1.0\nelement vertex 8\n"
             "property float x\nproperty float y\nproperty float z\n"
             "property uchar red\nproperty uchar green\nproperty uchar blue\n"
             "element face 6\nproperty list uchar int vertex_indices\nend_header\n")
    buf = bytearray(testa.encode())
    for x, y, z in VERTICI:
        buf += struct.pack(f"{ordine}3f3B", x, y, z, 10, 20, 30)
    for q in QUAD:
        buf += struct.pack(f"{ordine}B4i", 4, *q)
    path.write_bytes(bytes(buf))
    return path


def scrivi_wrl2(path: Path) -> Path:
    """VRML 2.0 con la geometria unitaria e la scala nel Transform.

    È il caso che distingue un lettore che applica i Transform da uno che li
    ignora: senza scala il cubo misurerebbe 1 × 1 × 1.
    """
    punti = ", ".join(f"{x / LX} {y / LY} {z / LZ}" for x, y, z in VERTICI)
    indici = ", ".join(" ".join(str(i) for i in q) + " -1" for q in QUAD)
    path.write_text(f"""#VRML V2.0 utf8
# un commento con una graffa }} dentro, per il tokenizzatore
DEF cubo Transform {{
  translation 0 0 0
  scale {LX} {LY} {LZ}
  children [
    Shape {{
      appearance Appearance {{ material Material {{ diffuseColor 0.8 0.8 0.8 }} }}
      geometry IndexedFaceSet {{
        coord Coordinate {{ point [ {punti} ] }}
        coordIndex [ {indici} ]
      }}
    }}
  ]
}}
""")
    return path


def scrivi_wrl1(path: Path) -> Path:
    """VRML 1.0: Coordinate3 fratello dell'IndexedFaceSet, dentro un Separator."""
    punti = ",\n".join(f"{x} {y} {z}" for x, y, z in VERTICI)
    indici = ",\n".join(" ".join(f"{i}," for i in q) + " -1" for q in QUAD)
    path.write_text(f"""#VRML V1.0 ascii
Separator {{
  Coordinate3 {{ point [ {punti} ] }}
  IndexedFaceSet {{ coordIndex [ {indici} ] }}
}}
""")
    return path


def _normale(a: int, b: int, c: int) -> np.ndarray:
    n = np.cross(VERTICI[b] - VERTICI[a], VERTICI[c] - VERTICI[a])
    return n / np.linalg.norm(n)


SCRITTORI = {
    "cubo.obj": scrivi_obj,
    "cubo_ascii.stl": scrivi_stl_ascii,
    "cubo.stl": scrivi_stl_binario,
    "cubo_ascii.ply": scrivi_ply_ascii,
    "cubo.ply": scrivi_ply_binario,
    "cubo_be.ply": lambda p: scrivi_ply_binario(p, ">"),
    "cubo.wrl": scrivi_wrl2,
    "cubo_v1.wrl": scrivi_wrl1,
}


@pytest.fixture(scope="module")
def cubi(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("formati")
    return {nome: scrittore(d / nome) for nome, scrittore in SCRITTORI.items()}


# ---------------------------------------------------------------- i test


@pytest.mark.parametrize("nome", sorted(SCRITTORI))
def test_ogni_formato_da_la_stessa_geometria(cubi, nome):
    """Otto vertici, dodici triangoli, 40 × 25 × 12. In tutti e quattro i formati."""
    mesh = load_mesh(cubi[nome])
    assert mesh.format == Path(nome).suffix.lstrip(".")
    # Lo STL dichiara 36 vertici: se ne restano 8, la saldatura ha funzionato.
    assert len(mesh) == 8
    assert len(mesh.faces) == 12
    assert mesh.extents == pytest.approx([LX, LY, LZ], abs=1e-5)
    assert mesh.vertices.min(axis=0) == pytest.approx([0.0, 0.0, 0.0], abs=1e-5)


@pytest.mark.parametrize("nome", sorted(SCRITTORI))
def test_ogni_formato_si_misura_allo_stesso_modo(cubi, nome):
    """Quello che conta non è caricare: è che l'analisi legga le stesse quote."""
    analisi = analyze(cubi[nome])
    assert len(analisi.bodies) == 1
    quote = {m.id: m.value for m in analisi.measurements}
    assert quote["c1_ingombro_x"] == pytest.approx(LX, abs=1e-5)
    assert quote["c1_ingombro_y"] == pytest.approx(LY, abs=1e-5)
    assert quote["c1_ingombro_z"] == pytest.approx(LZ, abs=1e-5)
    assert analisi.bodies[0].body.closed is True


def test_lo_stl_binario_non_si_riconosce_dalla_parola_solid(cubi):
    """L'intestazione binaria comincia con «solid», e va letta come binaria.

    È l'errore classico dei lettori STL: molti esportatori scrivono `solid` nei
    primi byte anche in binario, e chi si fida della parola legge spazzatura.
    """
    grezzo = cubi["cubo.stl"].read_bytes()
    assert grezzo[:5] == b"solid"
    assert len(load_mesh(cubi["cubo.stl"]).faces) == 12


def test_i_nomi_dei_corpi_vengono_dal_file_quando_ci_sono(cubi):
    """Ogni formato nomina i corpi a modo suo, e due non li nominano affatto."""
    assert load_mesh(cubi["cubo.obj"]).group_names == ("cubo",)      # `o`
    assert load_mesh(cubi["cubo_ascii.stl"]).group_names == ("cubo",)  # `solid`
    assert load_mesh(cubi["cubo.wrl"]).group_names == ("cubo",)      # `DEF`
    # Nel PLY e nello STL binario non c'è posto per un nome: inventarne uno
    # sarebbe una informazione che il file non contiene.
    assert load_mesh(cubi["cubo.stl"]).group_names == ()
    assert load_mesh(cubi["cubo.ply"]).group_names == ()


def test_il_transform_vrml_viene_applicato(cubi):
    """La geometria nel file è un cubo unitario: senza la scala misurerebbe 1 mm."""
    testo = cubi["cubo.wrl"].read_text()
    assert "scale 40.0 25.0 12.0" in testo
    assert load_mesh(cubi["cubo.wrl"]).extents == pytest.approx([LX, LY, LZ])


def test_un_formato_sconosciuto_si_rifiuta_dicendo_quali_va_bene(tmp_path):
    brutto = tmp_path / "modello.3mf"
    brutto.write_text("non importa")
    with pytest.raises(MeshNonLeggibile) as exc:
        load_mesh(brutto)
    for suffisso in SUFFISSI:
        assert suffisso in str(exc.value)


def test_un_file_vuoto_dice_perche_non_va(tmp_path):
    vuoto = tmp_path / "vuoto.obj"
    vuoto.write_text("# solo un commento\n")
    with pytest.raises(MeshNonLeggibile):
        load_mesh(vuoto)


def test_il_vrml_di_sole_primitive_nomina_quello_che_non_sa_leggere(tmp_path):
    """Una scena fatta di Box e Sphere non è una mesh, e il messaggio lo dice.

    Approssimarla con l'ingombro sarebbe inventare geometria: qui si preferisce
    fermarsi e spiegare come riesportare.
    """
    scena = tmp_path / "primitive.wrl"
    scena.write_text("#VRML V2.0 utf8\n"
                     "Shape { geometry Box { size 10 20 30 } }\n"
                     "Shape { geometry Sphere { radius 5 } }\n")
    with pytest.raises(MeshNonLeggibile) as exc:
        load_mesh(scena)
    assert "Box" in str(exc.value) and "Sphere" in str(exc.value)
    assert "IndexedFaceSet" in str(exc.value)


def test_la_saldatura_non_sposta_i_vertici(cubi):
    """Lo STL si salda per ricostruire la topologia, non per arrotondare le quote."""
    vertici = load_mesh(cubi["cubo.stl"]).vertices
    for atteso in VERTICI:
        assert np.isclose(vertici, atteso, atol=0).all(axis=1).any(), \
            f"il vertice {atteso} non è più esattamente quello del file"
