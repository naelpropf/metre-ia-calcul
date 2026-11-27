"""Prototype v2 -- pieces = SURFACES FERMEES des traits du PDF (idee « arrangement planaire » lue dans OpenTakeoff,
reecrite ici a notre facon avec shapely). Pas de pixels : la geometrie est exacte.
1. on garde les traits « murs » (epaisseur de stylo >= seuil) ;
2. on ajoute la CORDE de chaque porte (gond -> gache, lue sur l'arc : cercle ajuste sur toute la chaine de l'arc) ;
3. shapely « noue » les traits (soude les coins, coupe aux croisements) et en tire les surfaces fermees ;
4. la piece = la plus petite surface qui contient l'etiquette ; sa surface en m2 avec l'echelle lue sur les cotes.
Usage : python faces.py plan.pdf [seuil_epaisseur]"""
import math, sys
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
import pdfplumber
from shapely.geometry import LineString, Point
from shapely.ops import unary_union, polygonize
from metre import lire_textes, etiquettes, echelle_par_cotes, normaliser, origine, page_plumber, dans_zone
import pypdfium2 as pdfium


def kasa(pts):
    """Cercle ajuste au sens des moindres carres (methode de Kasa) sur une suite de points."""
    P = np.asarray(pts, float)
    if len(P) < 3: return None
    A = np.c_[2 * P[:, 0], 2 * P[:, 1], np.ones(len(P))]
    b = (P ** 2).sum(1)
    try:
        cx, cy, c = np.linalg.lstsq(A, b, rcond=None)[0]
    except Exception:
        return None
    r = math.sqrt(max(c + cx * cx + cy * cy, 0))
    res = np.abs(np.hypot(P[:, 0] - cx, P[:, 1] - cy) - r).max()
    return (cx, cy, r) if r > 0 and res <= max(0.5, 0.05 * r) else None


LUM_MAX = 0.75   # aplats fonces seulement (essai 25/11 : tout accepter jusqu au blanc = pire, la salle d eau tombe a -10 %)
EP_MAX = 0.70    # epaisseur max d un aplat-mur (m)


def pieces_par_faces(chemin, seuil=0.45, verbeux=True, souder=0.0, avec_remplis=True, rendre_faces=False, m_force=None):
    chemin = normaliser(chemin)
    W, H, etq, ech = lire_textes(chemin, 0)
    etq = etiquettes(etq)
    m_pt, voix, part = (m_force, 0, 0) if m_force else echelle_par_cotes(chemin, 0)
    doc = pdfium.PdfDocument(chemin); OX, OY = origine(doc[0]); doc.close()
    pl = page_plumber(chemin)   # lecture unique (26/11)
    dy = H - OY
    pl = dans_zone(pl, lambda p: (p[0] - OX, p[1] - dy))   # 27/11 : seulement la ou il reste du travail
    segs = []
    def ajoute(a, b):
        if a != b: segs.append(LineString([(a[0] - OX, a[1] - dy), (b[0] - OX, b[1] - dy)]))
    def aplat_mur(o):
        """Aplat qui ressemble a un MUR : fonce (pas un cache blanc ni un fond de piece pale) et en forme de bande
        (2 a 70 cm d'epaisseur moyenne = 2 x aire / perimetre)."""
        if not o.get("fill") or not m_pt: return False
        c = o.get("non_stroking_color")
        if isinstance(c, (list, tuple)) and len(c) in (1, 3) and all(isinstance(v, (int, float)) for v in c):
            lum = sum(c) / len(c)
        elif isinstance(c, (list, tuple)) and len(c) == 4 and all(isinstance(v, (int, float)) for v in c):
            lum = 1 - min(1, c[3] + sum(c[:3]) / 3)   # CMJN approx
        else:
            return False
        if lum > LUM_MAX: return False
        pts = o.get("pts") or []
        if len(pts) < 3: return False
        from shapely.geometry import Polygon
        try:
            P = Polygon(pts).buffer(0)
        except Exception:
            return False
        if P.is_empty or P.length == 0: return False
        ep = 2 * P.area / P.length * m_pt
        return 0.02 <= ep <= EP_MAX
    for o in pl.lines + pl.rects + pl.curves:
        if avec_remplis == "murs":
            if (o.get("linewidth") or 0) < seuil and not aplat_mur(o): continue
        elif (o.get("linewidth") or 0) < seuil and not (avec_remplis and o.get("fill")): continue
        pts = o.get("pts") or []
        for a, b in zip(pts, pts[1:]): ajoute(a, b)
        if o.get("object_type") == "rect" and len(pts) >= 4: ajoute(pts[-1], pts[0])
    # portes : corde gond -> gache
    n_portes = 0
    def gond_quart(pts):
        """Porte en quart de cercle dont le PDF ne donne que quelques points (courbe de Bezier) : le gond est le sommet
        du triangle rectangle isocele construit sur les deux bouts, du cote OPPOSE au bombe de l'arc."""
        (ax, ay), (bx, by) = pts[0], pts[-1]
        cl = math.hypot(bx - ax, by - ay)
        if cl == 0: return None
        r = cl / math.sqrt(2)
        if not (0.55 <= r * m_pt <= 1.3): return None
        mx, my = (ax + bx) / 2, (ay + by) / 2
        nx, ny = -(by - ay) / cl, (bx - ax) / cl          # normale a la corde
        h = cl / 2                                           # distance milieu -> gond pour un angle droit
        cands = [(mx + nx * h, my + ny * h), (mx - nx * h, my - ny * h)]
        # le VRAI gond touche le dessin (battant, mur) ; le faux tombe dans le vide de la piece
        rayon = 0.10 / m_pt
        votes = [len(arbre.query_ball_point(cnd, rayon)) if arbre is not None else 0 for cnd in cands]
        if votes[0] == votes[1]: return None
        g = cands[0] if votes[0] > votes[1] else cands[1]
        return g[0], g[1], r
    from scipy.spatial import cKDTree
    tous = [p for o in pl.lines + pl.rects + pl.curves for p in (o.get("pts") or [])]
    arbre = cKDTree(np.asarray(tous, float)) if tous else None
    for c in pl.curves:
        pts = c.get("pts") or []
        if not m_pt or len(pts) < 2 or c.get("fill"): continue
        k = kasa(pts) if len(pts) >= 5 else None   # 3-4 points : un cercle passe toujours, le controle ne prouve rien
        ok = False
        if k:
            cx, cy, r = k
            rm = r * m_pt
            a1 = math.atan2(pts[0][1] - cy, pts[0][0] - cx); a2 = math.atan2(pts[-1][1] - cy, pts[-1][0] - cx)
            bal = abs((a2 - a1 + math.pi) % (2 * math.pi) - math.pi)
            ok = 0.55 <= rm <= 1.3 and 0.7 <= bal <= 2.1
        if not ok and len(pts) <= 8:
            g = gond_quart(pts)
            if g:
                cx, cy, r = g; ok = True
        if not ok: continue
        # gache = le bout de l'arc le plus proche d'un trait mur ; on trace gond -> l'AUTRE bout aussi (simple : les deux cordes)
        for e in (pts[0], pts[-1]):
            # prolonge de 5 cm de chaque cote : le gond est CALCULE, il peut tomber a un cheveu du mur
            L = math.hypot(e[0] - cx, e[1] - cy)
            if L == 0: continue
            ux, uy = (e[0] - cx) / L, (e[1] - cy) / L; pr = 0.05 / m_pt
            ajoute((cx - ux * pr, cy - uy * pr), (e[0] + ux * pr, e[1] + uy * pr))
        n_portes += 1
    # SOUDER (lecon OpenTakeoff) : on prolonge chaque trait de `souder` metres aux deux bouts et on aimante les
    # coordonnees sur une grille fine -> les coins presque jointifs se rejoignent (le DAO laisse des micro-ecarts)
    if m_pt and souder:
        tol = souder / m_pt
        lon = []
        for sg in segs:
            (x1, y1), (x2, y2) = sg.coords
            L = math.hypot(x2 - x1, y2 - y1)
            if L == 0: continue
            ux, uy = (x2 - x1) / L, (y2 - y1) / L
            lon.append(LineString([(x1 - ux * tol, y1 - uy * tol), (x2 + ux * tol, y2 + uy * tol)]))
        segs = lon
        import shapely
        segs = [shapely.set_precision(sg, tol / 2) for sg in segs]
    reseau = unary_union(segs)
    faces = list(polygonize(reseau))
    res = []
    for e in etq:
        pt = Point(e["x"], e["y"])
        dedans = [f for f in faces if f.contains(pt)]
        if not dedans or not m_pt:
            res.append((e, None, None)); continue
        f = min(dedans, key=lambda f: f.area)
        res.append((e, f.area * m_pt * m_pt, f))
    if verbeux:
        n3 = sum(1 for e, a, _ in res if a and abs(a / e["surface_ecrite"] - 1) <= 0.03)
        n10 = sum(1 for e, a, _ in res if a and abs(a / e["surface_ecrite"] - 1) <= 0.10)
        print("seuil %.2f | traits %d | portes %d | surfaces %d | pieces %d | a 3%% : %d | a 10%% : %d | echelle 1/%s" % (
            seuil, len(segs), n_portes, len(faces), len(res), n3, n10, round(m_pt / (0.0254 / 72)) if m_pt else "-"))
    return res if rendre_faces else [(e, a) for e, a, _ in res]


if __name__ == "__main__":
    for s in ([float(sys.argv[2])] if len(sys.argv) > 2 else [0.13, 0.3, 0.45, 0.6]):
        pieces_par_faces(sys.argv[1], s)
