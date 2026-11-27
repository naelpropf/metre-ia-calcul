"""« Mur en trop » (27/11, mesure de cause) : une piece TROP PETITE est-elle une vraie piece DECOUPEE par des traits interieurs
(carrelage, plan de travail, sanitaires, cotes) ? On regroupe son trou avec les trous voisins separes seulement par un TRAIT
(< 3 cm : jamais a travers une cloison pleine), du plus proche au plus lointain (60 trous max) ; « recuperable » si un
regroupement tombe a +-10 % de l'ecrit.
  recuperable(MAT, m_pt, pieces) -> {indice: True/False} pour les pieces trop petites (rapport < 0,9)
  python mur_en_trop.py <debut de nom de page>   (validation : affiche chaque piece trop petite et son regroupement)"""
import glob, os, sys, heapq
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree


def recuperable(MAT, m_pt, pieces, ecart_trait=0.03, max_trous=60):
    trous = [Polygon(a) for g in getattr(MAT, "geoms", [MAT]) for a in g.interiors]
    if not trous: return {}
    arbre = STRtree(trous); tol = ecart_trait / m_pt
    out = {}
    for i, (x, y, ecrite, mesuree) in enumerate(pieces):
        if not (mesuree and ecrite and mesuree / ecrite < 0.9): continue
        p = Point(x, y)
        dep = [j for j in arbre.query(p) if trous[j].contains(p)]
        if not dep: continue
        j0 = min(dep, key=lambda j: trous[j].area)
        vus = {j0}; tas = [(0.0, j0)]; aire = 0.0; ok = False
        while tas and len(vus) <= max_trous:
            d, j = heapq.heappop(tas)
            aire += trous[j].area * m_pt * m_pt
            if abs(aire / ecrite - 1) <= 0.10: ok = True; break
            if aire > ecrite * 1.10: break
            zone = trous[j].buffer(tol)
            for k in arbre.query(zone):
                if k not in vus and trous[k].distance(trous[j]) <= tol:
                    vus.add(k); heapq.heappush(tas, (trous[k].distance(p), k))
        out[i] = ok
    return out


if __name__ == "__main__":
    import matiere
    from metre import normaliser
    f = normaliser(glob.glob(os.path.join(ici, "plans_neufs", glob.escape(sys.argv[1]) + "*.pdf"))[0])
    old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
    R = matiere.pieces_par_matiere(f, verbeux=False, rendre=True)
    sys.stdout.close(); sys.stdout = old
    MAT, m = matiere.DERNIERE_MATIERE
    P = [(e["x"], e["y"], e.get("surface_ecrite"), a) for e, a, h in R]
    res = recuperable(MAT, m, P)
    for i, ok in sorted(res.items()):
        x, y, ec, me = P[i]
        print("%-14s ecrit %6.2f mesure %6.2f -> %s" % ((R[i][0].get("nom") or "")[:14], ec, me, "RECUPERABLE" if ok else "non"))
    n = len(res); k = sum(res.values())
    print("trop petites %d | recuperables %d (%.0f %%)" % (n, k, 100 * k / max(n, 1)))
