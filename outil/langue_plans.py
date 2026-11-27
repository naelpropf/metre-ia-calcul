"""LA LANGUE DES PLANS (27/11) -- apprendre a lire un plan sur 2 500 plans annotes trait par trait (FloorPlanCAD, en graphes),
puis lire NOS plans avec la meme grammaire. Decision du porteur : « que l'IA comprenne le langage, sinon comment reussir ».
Graphe « a la main » (pas de PyTorch sur la machine) : indices du trait + moyenne des voisins (1 et 2 sauts) + moyenne des liens.
Declaration prealable : coffre « 03 - Outil/Langue des plans - FloorPlanCAD - declaration prealable.md ».
  python langue_plans.py apprendre        -> modele dans sorties/langue_plans.pkl + score sur la validation
Les fichiers telecharges sont lus comme donnees (np.load sans pickle), jamais executes."""
import glob, os, pickle, sys, time
import numpy as np
import scipy.sparse as sp
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(os.path.dirname(ici), "donnees_externes", "floorplancad_graphes")
CLASSES = ["mur", "vitre", "porte", "meuble", "autre", "reste"]
RAW2 = np.full(36, 5, dtype=np.int16)                       # 35 = sans etiquette -> reste
RAW2[[0]] = 0                                                # wall
RAW2[[1, 8, 9, 10]] = 1                                      # curtain wall, window, bay, blind
RAW2[[2, 3, 4, 5, 6, 7, 11]] = 2                             # portes + symbole d'ouverture
RAW2[list(range(12, 29)) + [33]] = 3                         # meubles, cuisine, sanitaires, rangees de sieges
RAW2[[29, 30, 31, 32, 34]] = 4                               # escalier, ascenseur, escalator, garde-corps, parking
GARDE_X = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12]                 # indices du trait (sans la position dans la tuile)
NOMS = (["type_ligne", "type_arc", "type_cercle", "type_ellipse", "type_courbe", "log_long", "cos2a", "sin2a", "balayage",
         "ferme", "log_rayon"])


VUE_LARGE = True   # 27/11 : 3e et 4e sauts + moyenne des traits sur 1,5 m et 4,5 m (le metreur voit la ligne de mur entiere)


def contexte_grille(X, pos, case):
    """moyenne de X sur la case de la grille et ses 8 voisines (fenetre 3 x case) + log du nombre de traits"""
    n = len(X)
    if n == 0: return np.zeros((0, X.shape[1] + 1), np.float32)
    g = np.floor((pos - pos.min(0)) / case).astype(np.int64)
    W = int(g[:, 0].max()) + 3; H = int(g[:, 1].max()) + 3
    gx, gy = g[:, 0] + 1, g[:, 1] + 1
    cell = gx * H + gy
    S = np.zeros((W * H, X.shape[1]), np.float64); C = np.zeros(W * H)
    np.add.at(S, cell, X); np.add.at(C, cell, 1)
    S = S.reshape(W, H, -1); C = C.reshape(W, H)
    S2 = np.zeros_like(S); C2 = np.zeros_like(C)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            S2[1:-1, 1:-1] += S[1 + dx:W - 1 + dx, 1 + dy:H - 1 + dy]; C2[1:-1, 1:-1] += C[1 + dx:W - 1 + dx, 1 + dy:H - 1 + dy]
    m = S2[gx, gy] / np.maximum(C2[gx, gy], 1)[:, None]
    return np.hstack([m, np.log1p(C2[gx, gy])[:, None]]).astype(np.float32)


def caracteristiques_graphe(x, ei, ea, n, pos=None):
    """x [n,13], ei [2,E] (i<j, non oriente), ea [E,8] -> [n, F] : trait + voisins 1 saut + 2 sauts + liens"""
    X = x[:, GARDE_X].astype(np.float32)
    if ei.shape[1]:
        i, j = ei[0].astype(np.int64), ei[1].astype(np.int64)
        A = sp.coo_matrix((np.ones(2 * len(i), np.float32), (np.r_[i, j], np.r_[j, i])), shape=(n, n)).tocsr()
        deg = np.asarray(A.sum(1)).ravel()
        Dinv = sp.diags(1.0 / np.maximum(deg, 1))
        An = Dinv @ A
        M1 = An @ X
        M2 = An @ M1
        if VUE_LARGE: M3 = An @ M2; M4 = An @ M3
        # moyenne des liens par trait (chaque lien compte pour ses deux bouts) -- sommes directes (27/11 : 1 s/tuile avant)
        bouts = np.r_[i, j]; ea2 = np.vstack([ea, ea]).astype(np.float32)
        L = np.zeros((n, ea.shape[1]), np.float32)
        for k in range(ea.shape[1]):
            L[:, k] = np.bincount(bouts, weights=ea2[:, k], minlength=n)
        n_col = L[:, 6].copy()
        L /= np.maximum(deg, 1)[:, None]
        Lmax_touch = np.zeros(n, np.float32); np.maximum.at(Lmax_touch, bouts, ea2[:, 5])
    else:
        deg = np.zeros(n); M1 = np.zeros_like(X); M2 = np.zeros_like(X); L = np.zeros((n, ea.shape[1]), np.float32)
        M3 = np.zeros_like(X); M4 = np.zeros_like(X)
        Lmax_touch = np.zeros(n); n_col = np.zeros(n)
    base = [X, M1, M2, L, deg[:, None], Lmax_touch[:, None], n_col[:, None]]
    if VUE_LARGE:
        if pos is None: pos = x[:, 10:12].astype(np.float64) * 10000.0   # FloorPlanCAD : centre / taille de tuile (10 m)
        base += [M3, M4, contexte_grille(X, pos, 500.0), contexte_grille(X, pos, 1500.0)]
    return np.hstack(base).astype(np.float32)


GARDER = np.array([80000 / 272039, 1.0, 1.0, 80000 / 329353, 80000 / 121370, 80000 / 562380 * 0.35 * 1.1], np.float64)


def lire_partie(fichier, max_noeuds=None, rng=None, part_reste=0.35):
    z = np.load(fichier, allow_pickle=False)
    nptr, eptr = z["node_ptr"], z["edge_ptr"]
    x, ei_all, ea_all, raw = z["x"], z["edge_index"], z["edge_attr"], z["raw"]
    Fs, ys = [], []
    for t in range(len(nptr) - 1):
        a, b = int(nptr[t]), int(nptr[t + 1]); c, d = int(eptr[t]), int(eptr[t + 1])
        F = caracteristiques_graphe(x[a:b], ei_all[:, c:d], ea_all[c:d], b - a)
        y = RAW2[np.clip(raw[a:b], 0, 35)]
        if rng is not None:   # entrainement : on garde tous les traits etiquetes et une part des « reste »
            garde = rng.random(len(y)) < np.minimum(GARDER[y], 1.0)   # ~80 000 traits par classe au total
            F, y = F[garde], y[garde]
        Fs.append(F); ys.append(y)
    return np.vstack(Fs), np.concatenate(ys)


MAX_PRIM_MM, RAYON_MM, MAX_VOISINS = 2000.0, 300.0, 30
SANS_LETTRES = os.environ.get("SANS_LETTRES", "1") == "1"   # 27/11 : lettres et petits symboles mis de cote
COL_OFF_MM, COL_GAP_MM, TOUCHE_MM = 20.0, 1000.0, 5.0   # alignes : 2 deg (dans graphe_pdf), 20 mm, 1 m ; contact 5 mm


def primitives_pdf(chemin):
    """Nos traits PDF dans la grammaire FloorPlanCAD : (ptype, pts[4,2] en mm, longueur, rayon, balayage, objet d'origine).
    ptype 0 droite, 1 arc, 4 courbe. Polylignes et rectangles -> segments ; courbe de >= 5 points ajustee a un cercle -> arc."""
    import math
    sys.path.insert(0, ici)
    import matiere
    from faces import kasa
    from metre import page_plumber, lire_textes, normaliser, origine
    import pypdfium2 as pdfium
    f = normaliser(chemin)
    m = matiere.echelle_par_cotes(f, 0)[0]   # echelle lue sur les cotes (comme matiere.py l.94)
    if not m:   # secours de l'outil : etiquettes de surface concordantes (metre_v3)
        import metre_v3; m = metre_v3.echelle_par_etiquettes(f)[0]
    if not m: raise ValueError("echelle introuvable")
    W, H, _, _ = lire_textes(f, 0); d = pdfium.PdfDocument(f); OX, OY = origine(d[0]); d.close()
    k = m * 1000.0
    conv = lambda p: ((p[0] - OX) * k, (p[1] - (H - OY)) * k)
    pl = page_plumber(f)
    T, P4, LG, R, SW, OB = [], [], [], [], [], []

    def seg(a, b, o):
        L = math.dist(a, b)
        if L <= 1e-6: return
        n = max(1, int(math.ceil(L / MAX_PRIM_MM)))
        for s in range(n):
            q0 = (a[0] + (b[0] - a[0]) * s / n, a[1] + (b[1] - a[1]) * s / n)
            q1 = (a[0] + (b[0] - a[0]) * (s + 1) / n, a[1] + (b[1] - a[1]) * (s + 1) / n)
            T.append(0); P4.append([q0, (q0[0] + (q1[0] - q0[0]) / 3, q0[1] + (q1[1] - q0[1]) / 3),
                                   (q0[0] + 2 * (q1[0] - q0[0]) / 3, q0[1] + 2 * (q1[1] - q0[1]) / 3), q1])
            LG.append(L / n); R.append(0.0); SW.append(0.0); OB.append(o)

    objs = [o for o in pl.lines + pl.rects + pl.curves if len(o.get("pts") or []) >= 2]
    from scipy.spatial import cKDTree
    arbre = cKDTree(np.array([conv(p) for o in objs for p in o["pts"]], float))
    for io, o in enumerate(objs):
        pts = [conv(p) for p in o["pts"]]
        if SANS_LETTRES and len(pts) >= 2:
            # 27/11 : 78 % des segments de 3102902 = 16 % des objets : petits (< 30 cm) et remplis ou detailles (>= 6 points)
            # = LETTRES, chiffres, petits symboles. FloorPlanCAD n'a pas de texte, et ils faisaient exploser le graphe (3 h/page).
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            if max(max(xs) - min(xs), max(ys) - min(ys)) < 300.0 and len(pts) >= 6: continue   # petit rectangle plein = bout de mur : garde
        if o.get("object_type") == "rect" and len(pts) >= 4: pts = pts + [pts[0]]
        if o.get("object_type") == "curve" and len(pts) == 4:
            # courbe de Bezier (debut, 2 points de controle, fin) : centre = croisement des perpendiculaires aux tangentes
            (ax, ay), (bx, by), (qx, qy), (ex, ey) = pts
            t1 = (bx - ax, by - ay); t2 = (ex - qx, ey - qy)
            det = t1[0] * t2[1] - t1[1] * t2[0]
            kk = None
            if abs(det) > 1e-9:
                # centre C : (C-A).t1 = 0 et (C-E).t2 = 0
                c1 = ax * t1[0] + ay * t1[1]; c2 = ex * t2[0] + ey * t2[1]
                cx = (c1 * t2[1] - t1[1] * c2) / det; cy = (t1[0] * c2 - c1 * t2[0]) / det
                r1, r2 = math.hypot(ax - cx, ay - cy), math.hypot(ex - cx, ey - cy)
                if r1 > 0 and abs(r1 - r2) <= 0.05 * max(r1, r2): kk = (cx, cy, (r1 + r2) / 2)
        elif o.get("object_type") == "curve" and len(pts) >= 5:
            kk = kasa(pts)
        else:
            kk = None
        if not kk and o.get("object_type") == "curve" and not o.get("fill") and 2 <= len(pts) <= 8:   # 27/11 : arcs stockes en 2 points (3081494, 61 portes ratees)
            # arc de porte stocke en peu de points (Guyane : 3) : methode du metreur (matiere.portes) -- quart de cercle,
            # corde = rayon x racine(2), gond = le coin (le cote ou il y a le plus de traits, le dormant)
            (ax, ay), (bx, by) = pts[0], pts[-1]
            cl = math.hypot(bx - ax, by - ay)
            if cl and 550 <= cl / math.sqrt(2) <= 1300:
                mx, my = (ax + bx) / 2, (ay + by) / 2; nx, ny = -(by - ay) / cl, (bx - ax) / cl
                cands = [(mx + nx * cl / 2, my + ny * cl / 2), (mx - nx * cl / 2, my - ny * cl / 2)]
                v = [len(arbre.query_ball_point(q, 100.0)) for q in cands]
                if v[0] != v[1]:
                    g = cands[0] if v[0] > v[1] else cands[1]
                    kk = (g[0], g[1], cl / math.sqrt(2))
        if kk:
            cx, cy, r = kk
            a1 = math.atan2(pts[0][1] - cy, pts[0][0] - cx); a2 = math.atan2(pts[-1][1] - cy, pts[-1][0] - cx)
            da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
            sw = abs(da)
            if sw > 0.05:
                q = [(cx + r * math.cos(a1 + da * t), cy + r * math.sin(a1 + da * t)) for t in (0, 1 / 3, 2 / 3, 1)]
                T.append(1); P4.append(q); LG.append(r * sw); R.append(r); SW.append(sw); OB.append(io)
                continue
        for i in range(len(pts) - 1):
            seg(pts[i], pts[i + 1], io)
    return {"ptype": np.array(T, np.int8), "pts": np.array(P4, np.float64).reshape(-1, 4, 2), "length": np.array(LG),
            "radius": np.array(R), "sweep": np.array(SW), "objet": np.array(OB, np.int64), "n_objets": len(objs), "m": m}


def candidats_alignes(pts, theta, is_line):
    """paires CANDIDATES de lignes presque alignees (le test exact angle 2 deg / decalage 20 mm est refait ensuite).
    En zone dense, chercher « tout ce qui est a 1 m » donnait des millions de paires (12 s par tuile, 27/11). Ici : on range
    les lignes par direction (cases de 2 deg) ; deux cases voisines sont mesurees sur un AXE COMMUN (long / travers),
    puis rangees dans une grille 3 m x 0,4 m : seules les cases voisines de la grille sont comparees."""
    import math
    L = np.where(is_line)[0]
    vide = (np.zeros(0, np.int64), np.zeros(0, np.int64))
    if len(L) < 2: return vide
    th = np.mod(theta[L], np.pi)
    PAS = math.radians(2.0); nb = int(round(np.pi / PAS))
    ba = np.minimum(np.floor(th / PAS).astype(np.int64), nb - 1)
    mid = (pts[L, 0] + pts[L, 3]) / 2
    I, J = [], []
    for a in range(nb):
        g = np.where((ba == a) | (ba == (a + 1) % nb))[0]
        if len(g) < 2: continue
        phi = (a + 1) * PAS
        u = np.array([math.cos(phi), math.sin(phi)]); n = np.array([-u[1], u[0]])
        s_ = mid[g] @ u; r_ = mid[g] @ n
        cs = np.floor(s_ / 3000.0).astype(np.int64); cr = np.floor(r_ / 400.0).astype(np.int64)
        cases = {}
        for k in range(len(g)): cases.setdefault((int(cs[k]), int(cr[k])), []).append(k)
        for (x, y), mem in cases.items():
            vois = [k for dx in (-1, 0, 1) for dy in (-1, 0, 1) for k in cases.get((x + dx, y + dy), [])]
            A = np.array(mem); B = np.array(vois)
            ga, gb = np.meshgrid(A, B, indexing="ij"); ga, gb = g[ga.ravel()], g[gb.ravel()]
            ok = ga < gb
            I.append(L[ga[ok]]); J.append(L[gb[ok]])
    if not I: return vide
    I = np.concatenate(I); J = np.concatenate(J)
    m = len(pts) + 1; k = np.unique(I * m + J)
    I, J = (k // m).astype(np.int64), (k % m).astype(np.int64)
    # distance reelle entre les deux segments <= 1 m (comme « dwithin » avant)
    import shapely
    d = shapely.distance(shapely.linestrings(pts[I][:, [0, 3]]), shapely.linestrings(pts[J][:, [0, 3]]))
    ok = d <= COL_GAP_MM
    return I[ok], J[ok]


def graphe_pdf(P):
    """meme construction que FloorPlanCAD : voisins a <= 300 mm + alignes (2 deg, 20 mm, 1 m), 30 voisins max, liens decrits"""
    import math, shapely
    from shapely import STRtree
    from shapely.geometry import LineString
    pts, ptype, length = P["pts"], P["ptype"], P["length"]
    n = len(ptype)
    geoms = np.array([LineString(pts[i]) for i in range(n)], dtype=object)
    tree = STRtree(geoms)
    pi, pj = tree.query(geoms, predicate="dwithin", distance=RAYON_MM)
    mm = pi < pj; pairs = set(zip(pi[mm].tolist(), pj[mm].tolist()))
    dv = pts[:, 3] - pts[:, 0]; theta = np.arctan2(dv[:, 1], dv[:, 0]); is_line = ptype == 0
    ci, cj = candidats_alignes(pts, theta, is_line)   # 27/11 : rangement par direction et par droite (au lieu de 1 m alentour)
    dth = np.abs(np.sin(theta[ci] - theta[cj]))
    u = np.stack([np.cos(theta[ci]), np.sin(theta[ci])], 1)
    cr = lambda a, b: a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    off = np.maximum(np.abs(cr(u, pts[cj, 0] - pts[ci, 0])), np.abs(cr(u, pts[cj, 3] - pts[ci, 0])))
    colin = (dth < math.sin(math.radians(2.0))) & (off < COL_OFF_MM)
    col_pairs = set(zip(ci[colin].tolist(), cj[colin].tolist()))
    allp = sorted(pairs | col_pairs)
    ei = np.array([p[0] for p in allp], np.int64); ej = np.array([p[1] for p in allp], np.int64)
    is_col = np.array([p in col_pairs for p in allp], bool)
    dist = shapely.distance(geoms[ei], geoms[ej]) if len(ei) else np.zeros(0)
    if len(ei):
        order = np.lexsort((dist, ~is_col)); ei, ej, dist, is_col = ei[order], ej[order], dist[order], is_col[order]
        deg = np.zeros(n, np.int32); keep = np.zeros(len(ei), bool)
        for e in range(len(ei)):
            a, b = ei[e], ej[e]
            if deg[a] < MAX_VOISINS and deg[b] < MAX_VOISINS: keep[e] = True; deg[a] += 1; deg[b] += 1
        ei, ej, dist, is_col = ei[keep], ej[keep], dist[keep], is_col[keep]
    mid = pts.mean(1)
    x = np.zeros((n, 13), np.float32)
    x[np.arange(n), ptype.astype(int)] = 1
    x[:, 5] = np.log1p(length / 1000); x[:, 6] = np.cos(2 * theta); x[:, 7] = np.sin(2 * theta)
    x[:, 8] = np.abs(P["sweep"]) / (2 * math.pi); x[:, 9] = 0; x[:, 12] = np.log1p(P["radius"] / 1000)
    ends = pts[:, [0, 3]]
    ea = np.zeros((len(ei), 8), np.float32)
    if len(ei):
        dd = np.linalg.norm(ends[ei][:, :, None, :] - ends[ej][:, None, :, :], axis=-1).reshape(len(ei), -1).min(1)
        both = is_line[ei] & is_line[ej]
        u = np.stack([np.cos(theta[ei]), np.sin(theta[ei])], 1)
        perp = np.where(both, np.abs(cr(u, mid[ej] - pts[ei, 0])), 0.0)
        dt = theta[ei] - theta[ej]
        ea[:, 0] = dist / RAYON_MM; ea[:, 1] = np.linalg.norm(mid[ei] - mid[ej], axis=1) / 1000
        ea[:, 2] = np.cos(dt); ea[:, 3] = np.abs(np.sin(dt)); ea[:, 4] = np.log((length[ei] + 1) / (length[ej] + 1))
        ea[:, 5] = dd <= TOUCHE_MM; ea[:, 6] = is_col; ea[:, 7] = perp / 1000
    return x, np.stack([ei, ej]), ea


TUILE_MM, MARGE_MM = 10000.0, 1000.0


MAX_NOEUDS = 4096   # comme FloorPlanCAD (max_nodes) : une tuile plus dense est coupee en 4


def traits_par_tuiles(P):
    """comme FloorPlanCAD : la page est decoupee en tuiles (10 m, marge 1 m pour les voisins) ; un graphe par tuile ;
    une tuile de plus de 4 096 traits est recoupee en 4 (sinon zones de hachures -> memoire pleine, 27/11)."""
    mid = P["pts"].mean(1); n = len(mid)
    F = [None]

    def faire(ax0, ay0, T, prof):
        coeur = np.where((mid[:, 0] >= ax0) & (mid[:, 0] < ax0 + T) & (mid[:, 1] >= ay0) & (mid[:, 1] < ay0 + T))[0]
        if not len(coeur): return
        mg = min(MARGE_MM, T / 4)
        ax, ay = ax0 - mg, ay0 - mg
        sel = np.where((mid[:, 0] >= ax) & (mid[:, 0] < ax0 + T + mg) & (mid[:, 1] >= ay) & (mid[:, 1] < ay0 + T + mg))[0]
        if len(sel) > MAX_NOEUDS and prof < 8:
            h = T / 2
            for dx in (0, h):
                for dy in (0, h): faire(ax0 + dx, ay0 + dy, h, prof + 1)
            return
        Q = {k: P[k][sel] for k in ("ptype", "pts", "length", "radius", "sweep")}
        x, ei, ea = graphe_pdf(Q)
        Fq = caracteristiques_graphe(x, ei, ea, len(x), pos=Q["pts"].mean(1) - np.array([ax, ay]))
        if F[0] is None: F[0] = np.zeros((n, Fq.shape[1]), np.float32)
        F[0][coeur] = Fq[np.searchsorted(sel, coeur)]

    x0, y0 = mid.min(0); x1, y1 = mid.max(0)
    for tx in np.arange(x0, x1 + 1, TUILE_MM):
        for ty in np.arange(y0, y1 + 1, TUILE_MM):
            faire(tx, ty, TUILE_MM, 0)
    return F[0]


def lire_pdf(chemin, M=None):
    """classe « langue » de chaque OBJET du PDF (vote des morceaux) -> (liste de classes, P)"""
    global VUE_LARGE
    if M is None: M = pickle.load(open(os.path.join(ici, "sorties", "langue_plans.pkl"), "rb"))
    VUE_LARGE = M.get("vue_large", False)
    P = primitives_pdf(chemin)
    F = traits_par_tuiles(P)
    pr = M["modele"].predict_proba(F)
    vote = np.zeros((P["n_objets"], pr.shape[1]))
    np.add.at(vote, P["objet"], pr * P["length"][:, None])
    cls = [M["classes"][M["modele"].classes_[j]] if vote[i].sum() else "" for i, j in enumerate(vote.argmax(1))]
    return cls, P


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "apprendre":
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import balanced_accuracy_score, recall_score, confusion_matrix
    t0 = time.time(); rng = np.random.default_rng(0)
    Xs, ys = [], []
    for f in sorted(glob.glob(os.path.join(EXT, "graphs", "train", "*.npz"))):
        X, y = lire_partie(f, rng=rng); Xs.append(X); ys.append(y)
        print("  lu %s : %d traits (%d s)" % (os.path.basename(f), len(y), time.time() - t0), flush=True)
    X, y = np.vstack(Xs), np.concatenate(ys); del Xs, ys
    CAP = int(os.environ.get("CAP", "80000"))  # plafond par classe (memoire : ~400 Mo libres)
    garde = np.concatenate([rng.permutation(np.where(y == c)[0])[:CAP] for c in range(6)])
    X, y = X[garde], y[garde]
    print("entrainement :", len(y), "traits |", {CLASSES[c]: int((y == c).sum()) for c in range(6)}, flush=True)
    mdl = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, max_leaf_nodes=63, class_weight="balanced",
                                         random_state=0).fit(X, y)
    print("appris en %d s" % (time.time() - t0), flush=True)
    Xv, yv = lire_partie(os.path.join(EXT, "graphs", "val", "val-00000.npz"))
    p = mdl.predict(Xv)
    ba = balanced_accuracy_score(yv, p)
    rec = recall_score(yv, p, labels=list(range(6)), average=None, zero_division=0)
    print("VALIDATION (projets jamais vus) : exactitude equilibree %.1f %% | %s" % (
        100 * ba, " ".join("%s %d%%" % (CLASSES[c], 100 * r) for c, r in enumerate(rec))))
    print("matrice (lignes = vrai, colonnes = predit) :", CLASSES)
    print(confusion_matrix(yv, p, labels=list(range(6))))
    print("SEUIL ecrit avant (>= 80 %) :", "REUSSI" if ba >= 0.80 else "ECHEC")
    pickle.dump({"modele": mdl, "classes": CLASSES, "garde_x": GARDE_X, "vue_large": VUE_LARGE},
                open(os.path.join(ici, "sorties", "langue_plans_large.pkl" if VUE_LARGE else "langue_plans.pkl"), "wb"))
