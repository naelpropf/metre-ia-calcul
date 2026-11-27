"""Instrument de diagnostic (27/11) : zone des COURBES non remplies qui ne portent pas de cote (arcs et battants de portes,
souvent entrouvertes a ~30 deg et non reconnues par matiere.portes). Coordonnees des pieces. Mesure seule.
  zone_courbes(chemin, m_pt) -> geometrie (courbes elargies de 2 cm) ou None"""
from shapely.geometry import LineString
from shapely.ops import unary_union
import pypdfium2 as pdfium
from metre import normaliser, origine, page_plumber, lire_textes
from diag_cotes import ids_objets_de_cote


def zone_courbes(chemin, m_pt):
    chemin = normaliser(chemin)
    W, H, _, _ = lire_textes(chemin, 0)
    doc = pdfium.PdfDocument(chemin); OX, OY = origine(doc[0]); doc.close()
    dy = H - OY
    conv = lambda p: (p[0] - OX, p[1] - dy)
    cotes = ids_objets_de_cote(chemin)
    L = [LineString([conv(p) for p in o["pts"]]) for o in page_plumber(chemin).curves
         if not o.get("fill") and len(o.get("pts") or []) >= 2 and id(o) not in cotes]
    return unary_union(L).buffer(0.02 / m_pt) if L else None
