"""Instrument de diagnostic (27/11) : SECTEURS DE DEBATTEMENT des portes, dans les coordonnees des pieces.
Cause observee (548666) : le contour d'une piece suit le battant de la porte ouverte et bombe dans l'ouverture du mur ;
le metreur ferme l'ouverture au NU du mur. Mesure seule : ne change rien au metre.
  secteurs(chemin) -> [Polygon]   (meme detection des portes que matiere.portes : gond + 2 bouts d'arc)"""
import math
from shapely.geometry import Polygon
import pypdfium2 as pdfium
import matiere
from metre import normaliser, origine, page_plumber, lire_textes, echelle_par_cotes


def secteurs(chemin, m_pt=None):
    chemin = normaliser(chemin)
    W, H, _, _ = lire_textes(chemin, 0)
    m_pt = m_pt or echelle_par_cotes(chemin, 0)[0]
    if not m_pt: return []
    doc = pdfium.PdfDocument(chemin); OX, OY = origine(doc[0]); doc.close()
    dy = H - OY
    conv = lambda p: (p[0] - OX, p[1] - dy)
    cordes = matiere.portes(page_plumber(chemin), m_pt, conv)   # 2 cordes par porte, a la suite (gond -> bout)
    out = []
    paires, i, tol = [], 0, 2.5 * 0.05 / m_pt   # les 2 cordes d'une porte partent du gond (decale de 5 cm) : a la suite
    while i + 1 < len(cordes):
        if math.dist(cordes[i].coords[0], cordes[i + 1].coords[0]) <= tol:
            paires.append((cordes[i], cordes[i + 1])); i += 2
        else:
            i += 1
    for c1, c2 in paires:
        (gx1, gy1), e1 = c1.coords[0], c1.coords[-1]
        (gx2, gy2), e2 = c2.coords[0], c2.coords[-1]
        g = ((gx1 + gx2) / 2, (gy1 + gy2) / 2)
        r = (math.dist(g, e1) + math.dist(g, e2)) / 2
        a1 = math.atan2(e1[1] - g[1], e1[0] - g[0]); a2 = math.atan2(e2[1] - g[1], e2[0] - g[0])
        d = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi          # le plus petit angle entre les 2 bouts
        arc = [(g[0] + r * math.cos(a1 + d * k / 16), g[1] + r * math.sin(a1 + d * k / 16)) for k in range(17)]
        P = Polygon([g] + arc)
        if P.is_valid and P.area > 0: out.append(P)
    return out
