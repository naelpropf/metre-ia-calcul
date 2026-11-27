"""Methode matiere PILOTEE PAR L'IA DE TRI (D-08) : la matiere = les objets que l'IA classe « limite de piece »
(au lieu des regles ecrites a la main de matiere.py) + les cordes de portes (geometrie pure) ; piece = trou qui
contient l'etiquette ; surface exacte. Confiance : comme matiere.py + objets limites douteux (probabilite 0,35-0,65).
Usage : python ia_matiere.py plan.pdf [seuil_proba=0.5]"""
import os, pickle, sys
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
import pdfplumber, pypdfium2 as pdfium
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from metre import lire_textes, etiquettes, echelle_par_cotes, normaliser, origine, page_plumber
from objets import caracteristiques
from matiere import portes, DEMI_TRAIT
import tri

_MODELE = None


def modele():
    global _MODELE
    if _MODELE is None:
        _MODELE = pickle.load(open(os.path.join(ici, "sorties", "tri_modele.pkl"), "rb"))
    return _MODELE


def pieces_par_ia(chemin, seuil=0.5, verbeux=True, rendre=False):
    chemin = normaliser(chemin)
    W, H, etq, _ = lire_textes(chemin, 0)
    etq = etiquettes(etq)
    m_pt = echelle_par_cotes(chemin, 0)[0]
    if not m_pt: return []
    doc = pdfium.PdfDocument(chemin); OX, OY = origine(doc[0]); doc.close()
    pl = page_plumber(chemin)   # lecture unique (26/11)
    dy = H - OY
    conv = lambda p: (p[0] - OX, p[1] - dy)
    objs, geoms = [], []
    for o in pl.lines + pl.rects + pl.curves:
        f, g = caracteristiques(o, conv, m_pt)
        if f is None: continue
        objs.append(f); geoms.append(g)
    tri.voisinage(objs)
    M = modele()
    X = np.array([[x[c] for c in M["carac"]] for x in objs], float)
    proba = M["modele"].predict_proba(X)[:, 1] if len(X) else np.array([])
    morceaux, douteux = [], []
    for g, p in zip(geoms, proba):
        if p < seuil: continue
        piece = g if g.geom_type in ("Polygon", "MultiPolygon") else g.buffer(DEMI_TRAIT / m_pt, cap_style=2, join_style=2)
        morceaux.append(piece)
        if p < 0.65: douteux.append(piece)
    cordes = portes(pl, m_pt, conv)
    reels = unary_union(morceaux).buffer(0.03 / m_pt) if morceaux else None
    morceaux += [c.buffer(DEMI_TRAIT / m_pt, cap_style=2) for c in cordes]
    mat = unary_union(morceaux).buffer(0.01 / m_pt, join_style=2)
    zone_douteuse = unary_union(douteux).buffer(0.03 / m_pt) if douteux else None
    trous = [Polygon(a) for g in getattr(mat, "geoms", [mat]) for a in g.interiors]
    res = []
    for e in etq:
        pt = Point(e["x"], e["y"])
        t = [h for h in trous if h.contains(pt)]
        if not t: res.append((e, None, None)); continue
        h = min(t, key=lambda h: h.area).buffer(0.01 / m_pt, join_style=2)
        a = h.area * m_pt * m_pt
        bord = h.exterior
        e["part_inventee"] = round(1 - bord.intersection(reels).length / max(bord.length, 1e-9), 3) if reels else 1.0
        e["part_douteuse"] = round(bord.intersection(zone_douteuse).length / max(bord.length, 1e-9), 3) if zone_douteuse else 0.0
        e["ecart_ecrit_pct"] = round(100 * (a / e["surface_ecrite"] - 1), 2) if e.get("surface_ecrite") else None
        d = []
        if e["ecart_ecrit_pct"] is not None and abs(e["ecart_ecrit_pct"]) > 1: d.append("ecart %+.1f %% avec l'ecrit" % e["ecart_ecrit_pct"])
        if e["part_inventee"] > 0.25: d.append("%d %% du contour ferme artificiellement" % (100 * e["part_inventee"]))
        if e["part_douteuse"] > 0.25: d.append("%d %% du contour sur des objets douteux pour l'IA" % (100 * e["part_douteuse"]))
        if not (0.5 <= a <= 400): d.append("taille peu plausible (%.1f m2)" % a)
        e["doutes"] = d
        res.append((e, a, h))
    if verbeux:
        ok = [(e, a) for e, a, _ in res if a]
        n3 = sum(1 for e, a in ok if abs(a / e["surface_ecrite"] - 1) <= 0.03)
        print("objets %d | limites IA %d | portes %d | pieces %d | trouvees %d | a 3%% : %d" % (
            len(objs), int((proba >= seuil).sum()), len(cordes) // 2, len(res), len(ok), n3))
    return res if rendre else [(e, a) for e, a, _ in res]


if __name__ == "__main__":
    for e, a in pieces_par_ia(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.5):
        print("  %-28s ecrite %7.2f | %s %s" % ((e.get("nom") or "")[:28], e["surface_ecrite"],
              "%7.2f (%+.1f %%)" % (a, 100 * (a / e["surface_ecrite"] - 1)) if a else "   -- non fermee",
              "| " + "; ".join(e.get("doutes", [])) if a else ""))
