"""L'IA « SENS » BRANCHEE DANS L'OUTIL (27/11) -- architecture voulue : l'IA dit ce que chaque trait SIGNIFIE, le code calcule.
Le metreur reconnait un mur a son dessin (ex. 3102902 : cloisons en DEUX TRAITS FINS mauves, invisibles pour la matiere).
Ici : modele de sens appris sur les AUTRES pages du MEME dossier (test C : 50-93 %, murs 91-98 %), puis les traits classes
« mur » ou « vitre » sur la page s'ajoutent a la matiere (variante v3 « matiere + murs IA » ; la surface ecrite tranche).
Modele mis en cache par dossier : sorties/modeles_sens/<dossier>.pkl"""
import glob, os, pickle, sys
import numpy as np
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
MURS = ("mur", "vitre")
BASES = ("objets_appr_mm_mp_au", "objets_appr_mm_mp", "objets_appr_mm")   # la meilleure base disponible d'abord
MAX_EX = 200000
_CACHE = {}


def modele_dossier(num):
    if num in _CACHE: return _CACHE[num]
    import sens
    d = os.path.join(ici, "sorties", "modeles_sens"); os.makedirs(d, exist_ok=True)
    f = os.path.join(d, num + ".pkl")
    if os.path.exists(f):
        _CACHE[num] = pickle.load(open(f, "rb")); return _CACHE[num]
    for base in BASES:
        if glob.glob(os.path.join(ici, "sorties", base, num + "*.jsonl.gz")): break
    else:
        _CACHE[num] = None; return None
    old = sys.stdout
    try:
        sys.stdout = open(os.devnull, "w")
        P = {k: v for k, v in sens.charger(base).items() if k[:7] == num}
    finally:
        sys.stdout.close(); sys.stdout = old
    if not P: _CACHE[num] = None; return None
    X = np.vstack([v["X"] for v in P.values()]); y = np.concatenate([v["y"] for v in P.values()])
    g = np.isin(y, [c for c in set(y) if (y == c).sum() >= 2]); X, y = X[g], y[g]
    if len(y) > MAX_EX:
        idx = np.random.default_rng(0).choice(len(y), MAX_EX, replace=False); X, y = X[idx], y[idx]
    m = sens.modele().fit(X, y)
    _CACHE[num] = {"modele": m, "classes": sens.CLASSES, "cols": sens.COLS, "base": base, "n": len(y)}
    pickle.dump(_CACHE[num], open(f, "wb"))
    return _CACHE[num]


P_MIN = 0.8   # 27/11 : essai Guyane sans garde-fous = 357 « murs » en trop (cotes, axes, bureaux) -> 8 pieces justes -> 0


def murs_ia(chemin, pl, conv, m_pt, mat=None):
    """geometries (deja epaissies) des traits que l'IA classe mur / vitre, avec les GARDE-FOUS du metreur :
    l'IA en est sure (>= P_MIN) ; une cloison part d'un mur et arrive sur un mur (2 bouts a <= 5 cm de la matiere) ;
    elle ne traverse pas les murs (< 10 % de sa longueur dans la matiere ; un axe de coupe, lui, traverse tout)."""
    import tri
    from objets import caracteristiques, alignes_par_objet
    from matiere import DEMI_TRAIT
    M = modele_dossier(os.path.basename(chemin)[:7])
    if M is None: return []
    objs, geoms = [], []
    al = alignes_par_objet(pl, conv, m_pt) if "alignes" in M["cols"] else {}
    for o in pl.lines + pl.rects + pl.curves:
        f, g = caracteristiques(o, conv, m_pt)
        if f is None: continue
        f["alignes"] = al.get(id(o), 0)
        objs.append(f); geoms.append(g)
    if not objs: return []
    tri.voisinage(objs)
    X = np.array([[x.get(c, 0) for c in M["cols"]] for x in objs], float)
    pr = M["modele"].predict_proba(X); cl = list(M["modele"].classes_)
    garde = [cl.index(M["classes"].index(c)) for c in MURS if M["classes"].index(c) in cl]
    p_mur = pr[:, garde].sum(axis=1) if garde else np.zeros(len(X))
    from shapely.geometry import Point
    from shapely.prepared import prep
    mp = prep(mat.buffer(0.05 / m_pt)) if mat is not None else None
    mi = mat.buffer(0.02 / m_pt) if mat is not None else None
    out = []
    for g, pm in zip(geoms, p_mur):
        if pm < P_MIN: continue
        if g.geom_type != "LineString": continue   # les murs REMPLIS sont deja dans la matiere : l'IA sert aux TRAITS fins
        if mp is not None:
            c = list(g.coords)
            if not (mp.contains(Point(c[0])) and mp.contains(Point(c[-1]))): continue
            if g.length and g.intersection(mi).length > 0.10 * g.length: continue
        if True:
            out.append(g if g.geom_type in ("Polygon", "MultiPolygon") else g.buffer(DEMI_TRAIT / m_pt, cap_style=2, join_style=2))
    return out
