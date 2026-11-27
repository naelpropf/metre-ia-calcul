"""Quels objets du dessin separent deux etiquettes tombees dans le MEME trou ? (27/11, mesure seule)
Pour chaque paire d'etiquettes voisines du meme trou : le segment qui les relie coupe forcement la cloison manquante.
On releve les objets coupes (type, epaisseur, couleur, rempli) et pourquoi matiere ne les a pas pris.
  python cloisons_non_vues.py <debut du nom de page>"""
import glob, os, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
import matiere, pypdfium2 as pdfium
from metre import normaliser, page_plumber, lire_textes, origine
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree
f = normaliser(glob.glob(os.path.join(ici, "plans_neufs", glob.escape(sys.argv[1]) + "*.pdf"))[0])
old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
R = matiere.pieces_par_matiere(f, verbeux=False, rendre=True)
sys.stdout.close(); sys.stdout = old
m = matiere.DERNIERE_MATIERE[1]
W, H, _, _ = lire_textes(f, 0); d = pdfium.PdfDocument(f); OX, OY = origine(d[0]); d.close(); dy = H - OY
conv = lambda p: (p[0] - OX, p[1] - dy)
pl = page_plumber(f)
objs = [(typ, o) for typ, L in (("line", pl.lines), ("rect", pl.rects), ("curve", pl.curves)) for o in L if len(o.get("pts") or []) >= 2]
geoms = [LineString([conv(p) for p in o["pts"]]) for _, o in objs]
arbre = STRtree(geoms)
# trous partages : etiquettes dont le contour h est le meme objet
groupes = collections.defaultdict(list)
for e, a, h in R:
    if h is not None: groupes[round(a, 3)].append(e)
paires = []
for g in groupes.values():
    if len(g) < 2: continue
    for e in g:   # chaque etiquette avec sa plus proche voisine du meme trou
        v = min((x for x in g if x is not e), key=lambda x: (x["x"] - e["x"]) ** 2 + (x["y"] - e["y"]) ** 2)
        if (v["x"] - e["x"]) ** 2 + (v["y"] - e["y"]) ** 2 < (12 / m) ** 2: paires.append((e, v))
print("page : %s | m_pt %.5f | seuil trait %.2f | paires d'etiquettes du meme trou : %d" % (os.path.basename(f)[:50], m, 0.45, len(paires)))
vus = collections.Counter(); exemples = {}
for e, v in paires:
    s = LineString([(e["x"], e["y"]), (v["x"], v["y"])])
    for i in arbre.query(s):
        if not geoms[i].intersects(s): continue
        typ, o = objs[i]
        lw = round(o.get("linewidth") or 0, 2); col = o.get("stroking_color"); fcol = o.get("non_stroking_color")
        col = tuple(round(x, 2) for x in col) if isinstance(col, (list, tuple)) else col
        fcol = tuple(round(x, 2) for x in fcol) if isinstance(fcol, (list, tuple)) else fcol
        raison = "rempli" if o.get("fill") else ("trait >= seuil (DEVRAIT etre mur)" if lw >= 0.45 else "trait FIN < seuil")
        cle = (typ, lw, str(col), ("rempli " + str(fcol)) if o.get("fill") else "-", raison)
        vus[cle] += 1
print("\nobjets coupes entre deux etiquettes du meme trou (type | epaisseur | couleur trait | remplissage | statut) :")
for (typ, lw, col, rem, raison), n in vus.most_common(25):
    print("%5d  %-5s | trait %.2f | %-18s | %-28s | %s" % (n, typ, lw, col, rem, raison))
