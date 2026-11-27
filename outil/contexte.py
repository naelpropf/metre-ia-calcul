"""CONTEXTE vu d'en haut (27/11, idee du porteur : l'IA regarde chaque trait de trop pres et rate les lettres).
Le metreur reconnait un MOT de loin sans lire chaque lettre. Pour chaque objet de la page (meme ordre que objets.py) :
  0 dans_texte_vrai  : le centre de l'objet est dans la boite d'un caractere du PDF (texte « vrai »)
  1 mot_dessine      : petit objet (< 30 cm, >= 6 points) qui a au moins 2 voisins de meme sorte a moins de 15 cm (lettres dessinees)
  2 log_bloc         : log(1 + nb de petits objets du meme bloc) -- taille du bloc de texte dessine
Sortie : sorties/contexte_cache/<nom[:60]>.npy
  python un_par_un.py contexte.py plans_test plans_appr"""
import glob, os, sys, time, math
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
CACHE = os.path.join(ici, "sorties", "contexte_cache"); os.makedirs(CACHE, exist_ok=True)


def contexte(f):
    import pypdfium2 as pdfium
    from shapely import STRtree, points, box
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from metre import page_plumber, lire_textes, normaliser, origine, echelle_par_cotes
    ch = normaliser(f)
    W, H, _, _ = lire_textes(ch, 0)
    m = echelle_par_cotes(ch, 0)[0]
    if not m:
        import metre_v3; m = metre_v3.echelle_par_etiquettes(ch)[0]
    doc = pdfium.PdfDocument(ch); p = doc[0]; OX, OY = origine(p)
    tp = p.get_textpage(); boites = []
    for i in range(tp.count_chars()):
        try: l, b, r, t = tp.get_charbox(i)
        except Exception: continue
        if r > l and t > b: boites.append(box(l - OX, OY - t, r - OX, OY - b))
    doc.close()
    dy = H - OY
    pl = page_plumber(ch)
    objs = [o for o in pl.lines + pl.rects + pl.curves if len(o.get("pts") or []) >= 2]
    n = len(objs)
    C = np.zeros((n, 2)); T = np.zeros(n); N = np.zeros(n, int)
    for i, o in enumerate(objs):
        xs = [q[0] - OX for q in o["pts"]]; ys = [q[1] - dy for q in o["pts"]]
        C[i] = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        T[i] = max(max(xs) - min(xs), max(ys) - min(ys)) * (m or 0)
        N[i] = len(xs)
    X = np.zeros((n, 3), np.float32)
    if boites and n:
        arbre = STRtree(boites)
        oi, _ = arbre.query(points(C), predicate="within")
        X[np.unique(oi), 0] = 1
    petits = np.where((T < 0.30) & (N >= 6))[0]
    if len(petits) >= 3 and m:
        from scipy.spatial import cKDTree
        pr = cKDTree(C[petits]).query_pairs(0.15 / m, output_type="ndarray")
        if len(pr):
            A = coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(petits),) * 2)
            nc, lab = connected_components(A, directed=False)
            taille = np.bincount(lab)
            deg = np.bincount(pr.ravel(), minlength=len(petits))
            X[petits, 1] = (deg >= 2).astype(np.float32)
            X[petits, 2] = np.log1p(taille[lab]).astype(np.float32)
    return X


if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[1] == "--page":
    f = sys.argv[2]
    c = os.path.join(CACHE, os.path.splitext(os.path.basename(f))[0][:60] + ".npy")
    if os.path.exists(c): print("%-60s deja fait" % os.path.basename(f)[:60]); sys.exit(0)
    t = time.time(); X = contexte(f); np.save(c, X)
    print("%-60s %6d objets | texte vrai %d | mots dessines %d | %d s" % (
        os.path.basename(f)[:60], len(X), int(X[:, 0].sum()), int(X[:, 1].sum()), time.time() - t), flush=True)
