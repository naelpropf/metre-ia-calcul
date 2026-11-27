"""CONTOURS DE PIECE DESSINES PAR L'ARCHITECTE (26/11, racine Scanner) : beaucoup de logiciels de dessin exportent le
contour de chaque piece (« zone », « piece », « surface ») comme un trace FERME. Quand un trace ferme contient
l'etiquette et que sa surface tombe a 1 % de la surface ecrite, c'est le contour exact, dessine par l'architecte.
Mesure : Scanner, 35 pieces sur 95 retrouvees ainsi (le moteur n'en avait que 19 sures).
Deux sources : (a) chemins fermes d'un seul objet ; (b) polygones formes par les traits d'une MEME couleur."""
import collections, math
import pdfplumber, pypdfium2 as pdfium
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree
from metre import normaliser, origine, lire_textes, etiquettes, echelle_par_cotes, page_plumber, dans_zone

TOL = 0.01


def contours_dessines(chemin, m_force=None, avec_couleurs=True):
    """{(x, y) etiquette arrondie : (polygone, source)} pour les etiquettes retrouvees a 1 % de l'ecrit"""
    ch = normaliser(chemin)
    W, H, etq, _ = lire_textes(ch, 0); etq = etiquettes(etq)
    m = m_force or echelle_par_cotes(ch, 0)[0]
    if not m or not etq: return {}
    doc = pdfium.PdfDocument(ch); OX, OY = origine(doc[0]); doc.close()
    conv = lambda p: (p[0] - OX, p[1] - (H - OY))
    pl = dans_zone(page_plumber(ch), conv)   # lecture unique (26/11) ; zone de travail (27/11)
    fermes, par_coul = [], collections.defaultdict(list)
    for o in pl.lines + pl.rects + pl.curves:
        pts = o.get("pts") or []
        if len(pts) < 2: continue
        c = [conv(p) for p in pts]
        col = o.get("stroking_color"); col = tuple(round(v, 2) for v in col) if isinstance(col, (list, tuple)) else col
        if o.get("object_type") == "rect" and len(c) >= 4: c = c + [c[0]]
        if len(c) >= 4 and math.dist(c[0], c[-1]) * m < 0.01:
            try:
                P = Polygon(c).buffer(0)
                if not P.is_empty and P.area * m * m >= 0.5: fermes.append(P)
            except Exception:
                pass
        if avec_couleurs:
            for a, b in zip(c, c[1:]): par_coul[col].append(LineString([a, b]))
    res = {}
    def cherche(polys, src):
        if not polys: return
        tr = STRtree(polys)
        for e in etq:
            k = (round(e["x"], 1), round(e["y"], 1))
            if k in res: continue
            pt = Point(e["x"], e["y"])
            for j in tr.query(pt):
                P = polys[j]
                if P.contains(pt) and abs(P.area * m * m / e["surface_ecrite"] - 1) <= TOL:
                    res[k] = (P, src); break
    cherche(fermes, "contour dessiné (tracé fermé)")
    if avec_couleurs:
        polys = []
        for col, L in par_coul.items():
            if 4 <= len(L) <= 200000:
                polys += [P for P in polygonize(unary_union(L)) if P.area * m * m >= 0.5]
        cherche(polys, "contour dessiné (traits d'une couleur)")
    return res
