"""Moteur v3 -- « regime A » (plans AVEC surfaces ecrites, la majorite des DCE francais) -- 26/11 nuit.
1. plusieurs decoupages EXACTS candidats : matiere (regles) + faces (stylo 0,45 puis 0,25) ;
2. pour chaque etiquette, la SURFACE ECRITE designe le bon contour (a <= 1 %) -> piece SURE, contour exact
   (sert au perimetre, aux murs a peindre, aux plinthes : ce que l'architecte n'ecrit pas) ;
3. sinon : contour de la methode matiere s'il existe, SIGNALE a l'operateur (jamais presente comme sur).
HONNETETE : la surface d'une piece sure vient de l'ecrit (normal : c'est le chiffre de l'architecte) ; ce que l'outil
apporte = le CONTOUR exact et tout ce qui en decoule, et la liste de ce qui reste a verifier.
Chiffre cle (D-10) = part des pieces SURES = charge de relecture.
Usage : python metre_v3.py [plan.pdf]   (sans argument : les 7 plans du banc)"""
import glob, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
import matiere, faces

SURE = 0.01
PROCHE = 0.10   # 27/11 D-13 : releve (mesure seule) des pieces que les variantes mettent a moins de 10 %
PARALLELE = 2   # 27/11 : variantes en parallele (machine : 2 coeurs)
ZONE_DE_TRAVAIL = True   # 27/11 : variantes recalculees seulement autour des pieces douteuses
CHAINE = os.environ.get("V3_CHAINE", "1") == "1"   # 27/11 D-13 : chaine de corrections cumulees v1 (V3_CHAINE=0 pour l ancienne reference)
CANDIDATS = [0.45, 0.25, 0.13]


def echelle_par_etiquettes(chemin, min_voix=3):
    """Secours quand les cotes ne donnent pas l'echelle (ex. Numericum) : surfaces fermees en unites PDF (pt2),
    chacune comparee a la surface ecrite de son etiquette -> au vrai facteur, beaucoup de pieces S'ACCORDENT.
    On garde la valeur qui reunit le plus de pieces (a 1 % pres), s'il y en a >= min_voix. Sinon None."""
    import math
    r = []
    for s in (0.45, 0.25):
        for e, a, h in faces.pieces_par_faces(chemin, s, verbeux=False, avec_remplis=False, rendre_faces=True, m_force=1.0):
            if a and e.get("surface_ecrite"): r.append(math.sqrt(e["surface_ecrite"] / a))
    best, voix = None, 0
    for x in r:
        v = [y for y in r if abs(math.log(y / x)) <= 0.01]
        if len(v) > voix: best, voix = sorted(v)[len(v) // 2], len(v)
    return (best, voix) if voix >= min_voix else (None, voix)


def _zone(res, m_pt):
    """ZONE DE TRAVAIL (27/11) : boites autour des pieces encore DOUTEUSES (rayon = 3 x racine de la surface, >= 4 m).
    Les variantes ne recalculent que la (avant : tout le plan 5 fois = 58 s sur 80 pour Briffaut)."""
    import metre, math
    from shapely.geometry import box
    from shapely.ops import unary_union
    b = []
    for r in res.values():
        if r["sure"]: continue
        e = r["e"]; R = max(3 * math.sqrt(e["surface_ecrite"]), 4.0) / m_pt
        b.append(box(e["x"] - R, e["y"] - R, e["x"] + R, e["y"] + R))
    metre.ZONE = unary_union(b) if b else None


def pieces_v3(chemin):
    import metre
    metre.ZONE = None
    try:
        return _pieces_v3(chemin)
    finally:
        metre.ZONE = None


def _fiche(chemin):
    """27/11 : fiche de conventions du dossier (legende lue par Claude ou l'operateur) -> couleurs « pas un mur »"""
    import json
    f = os.path.join(ici, "conventions", os.path.basename(chemin)[:7] + ".json")
    if not os.path.exists(f): return set()
    return {tuple(round(x, 2) for x in c) for c in json.load(open(f, encoding="utf-8")).get("pas_mur", [])}


def _candidat(arg):
    """une variante, executee dans un processus a part : rend les pieces tombant a 1 % de l'ecrit"""
    chemin, nom, params, m_force, m_pt, zone_wkb = arg
    import metre, matiere, faces, shapely
    metre.ZONE = shapely.from_wkb(zone_wkb) if zone_wkb else None
    def _cc(h):   # 27/11 soir (MESURE SEULE) : contour simplifie de la variante, pour dessiner une piece perdue sans recalcul
        try:
            g = h if h.geom_type == "Polygon" else max(h.geoms, key=lambda q: q.area)
            return [[round(x, 1), round(y, 1)] for x, y in g.simplify(0.3).exterior.coords]
        except Exception:
            return None
    out = []
    proches = []   # 27/11 D-13 (MESURE SEULE) : pieces que la variante met entre 1 % et 10 % -> score secondaire 3 % / 10 %
    try:
        if nom == "contours":
            import contours_dessines
            for k, (P, src) in contours_dessines.contours_dessines(chemin, m_force=m_force).items():
                out.append((k, P.area * m_pt ** 2 if m_pt else None, P, src))
        elif nom.startswith("faces"):
            for e, a, h in faces.pieces_par_faces(chemin, params["seuil"], verbeux=False, avec_remplis=False, rendre_faces=True, m_force=m_force):
                if a and abs(a / e["surface_ecrite"] - 1) <= SURE:
                    out.append(((round(e["x"], 1), round(e["y"], 1)), a, h, nom))
                elif a and abs(a / e["surface_ecrite"] - 1) <= PROCHE:
                    proches.append(((round(e["x"], 1), round(e["y"], 1)), abs(a / e["surface_ecrite"] - 1), _cc(h)))
        else:
            params = dict(params, CALCUL_DOUTES=False)   # 27/11 : la variante ne garde que la surface (vitesse, meme resultat)
            ancien = {k: getattr(matiere, k) for k in params}
            for k, v in params.items(): setattr(matiere, k, v)
            try:
                for e, a, h in matiere.pieces_par_matiere(chemin, verbeux=False, rendre=True, m_force=m_force):
                    if a and abs(a / e["surface_ecrite"] - 1) <= SURE:
                        out.append(((round(e["x"], 1), round(e["y"], 1)), a, h, nom))
                    elif a and abs(a / e["surface_ecrite"] - 1) <= PROCHE:
                        proches.append(((round(e["x"], 1), round(e["y"], 1)), abs(a / e["surface_ecrite"] - 1), _cc(h)))
            finally:
                for k, v in ancien.items(): setattr(matiere, k, v)
    except Exception as ex:
        print("  variante %s en erreur : %s" % (nom, ex))
    finally:
        metre.ZONE = None
    return nom, out, proches


def _pieces_v3(chemin):
    res = {}
    from metre import echelle_par_cotes, normaliser
    m_force, source_ech = None, "cotes"
    if not echelle_par_cotes(normaliser(chemin), 0)[0]:
        m_force, voix = echelle_par_etiquettes(chemin)
        print("  echelle de secours :", "%d etiquettes concordantes" % voix if m_force else "INTROUVABLE (%d voix)" % voix)
        if not m_force: return []
    # 1. methode matiere (porte la confiance)
    for e, a, h in matiere.pieces_par_matiere(chemin, verbeux=False, rendre=True, m_force=m_force):
        k = (round(e["x"], 1), round(e["y"], 1))
        res[k] = {"e": e, "a": a, "h": h, "source": "matiere", "sure": bool(a and abs(a / e["surface_ecrite"] - 1) <= SURE)}
    # 1 0 a 2 : VARIANTES CANDIDATES, calculees EN PARALLELE (27/11) puis fusionnees dans l'ORDRE HISTORIQUE
    # (conventions, double trait, fenetres en paquet, sans fonds blancs, contours dessines, faces 0.45/0.25/0.13) :
    # une piece prend la 1re variante qui tombe a 1 % de l'ecrit, exactement comme en sequentiel.
    if not all(r["sure"] for r in res.values()):
        m_pt = m_force or (matiere.DERNIERE_MATIERE[1] if matiere.DERNIERE_MATIERE else None)
        if ZONE_DE_TRAVAIL and m_pt: _zone(res, m_pt)
        import metre, shapely
        zone_wkb = shapely.to_wkb(metre.ZONE) if metre.ZONE is not None else None
        taches = []
        # conventions du plan (26/11) : conventions qui ne bordent AUCUNE piece sure -> retirees
        if any(r["sure"] for r in res.values()) and matiere.DERNIERS_MORCEAUX and m_pt:
            from shapely.ops import unary_union
            mx = matiere.DERNIERS_MORCEAUX
            bords = unary_union([r["h"].exterior for r in res.values() if r["sure"]]).buffer(0.02 / m_pt)
            exclure = {s_ for _, s_ in mx} - {s_ for g, s_ in mx if g.intersects(bords)}
            if exclure: taches.append(("matiere conventions du plan", {"EXCLURE_SIG": exclure}))
        taches += [("matiere double trait", {"DOUBLE_TRAIT": True}),        # 26/11 racine Scanner
                   ("matiere fenetres en paquet", {"BAIES_PAQUET": True}),  # 26/11 racine Guyane
                   ("matiere sans fonds blancs", {"SANS_BLANC": True}),     # 26/11 racine Briffaut
                   ("matiere murs neutres", {"NEUTRES": True}),           # 27/11 racine 3102902 (couleur = annotation)
                   ] + ([   # 27/11 D-13 : CHAINE DE CORRECTIONS CUMULEES v1, jugee d'UN BLOC (declaration au coffre)
                   ("matiere sans cotes", {"SANS_COTES": True}),
                   ("matiere ouvertures de mur", {"OUVERTURES": True}),
                   ("matiere portes en pointilles", {"PORTES_POINTILLES": True}),
                   ("matiere chaine", {"SANS_COTES": True, "OUVERTURES": True, "PORTES_POINTILLES": True}),
                   ("matiere fermeture poteaux", {"FERMETURE": 1.2}),   # 27/11 nuit : chaine v2 (facade vitree)
                   # 27/11 soir : facade vitree en 2 longs traits fins a 3 cm (3068854) = matiere, puis pont poteau-facade
                   ("matiere double trait serre", {"DOUBLE_TRAIT": True, "ECART_MIN_DT": 0.01, "FERMETURE": 1.2}),
                   ] if CHAINE else []) + [
                   # 27/11 « portes entrouvertes » (arcs 10-40 deg) ESSAYE puis retire : 118 -> 118, +150 s
                   # 27/11 « portes en pointilles » SEULE : 118 -> 121 (< +21), +900 s -> retiree ; fuites EN SERIE (poteaux)
                   # 27/11 « ouvertures de mur » v2 (murs epais) ESSAYE puis retire : 118 -> 125 (+7 < +21), examen 10 min
                   # 27/11 « ouvertures de mur » v1 ESSAYE puis retire : 118 -> 126 (+8 < +21), examen 9 min 45 ; faux ponts
                   # entre un mur et un battant/meuble dessine (548666) -> a reprendre : ponts entre DEUX bouts de MUR seulement
                   # 27/11 « traits fins 0,08 + pointilles » ESSAYE puis retire : +9 sur 59 pages, 1 machine plantee (memoire),
                   # 11 pages perdues, page max 480 s. A reprendre SEULEMENT sur les pages aux cloisons en traits fins.
                   # 27/11 « matiere sans cotes » ESSAYE puis retire : +10 sures sur les neufs (118 -> 128) < seuil +21, +100 s
                   # 27/11 : « matiere etiquette proche » ESSAYE puis retire (banc 125 -> 125, aucun gain, +temps)
                   ] + ([("matiere fiche de conventions", {"PAS_MUR": _fiche(chemin)})] if _fiche(chemin) else []) + (
                   [("matiere + murs IA", {"IA_MURS": True})] if os.environ.get("V3_IA", "1") == "1" and glob.glob(os.path.join(ici, "sorties", "objets_appr_mm*", os.path.basename(chemin)[:7] + "*")) else []) + [
                   ("contours", {}),                                       # 26/11 contours dessines par l'archi
                   ] + [("faces %.2f" % s_, {"seuil": s_}) for s_ in CANDIDATS]
        args = [(chemin, nom, p, m_force, m_pt, zone_wkb) for nom, p in taches]
        import multiprocessing as _mp
        if PARALLELE > 1 and _mp.current_process().name == "MainProcess":
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=PARALLELE) as ex:
                resultats = list(ex.map(_candidat, args))
        else:
            resultats = [_candidat(a) for a in args]
        for nom, trouves, proches in resultats:   # ORDRE HISTORIQUE conserve
            for k, a, h, src in trouves:
                r = res.get(k)
                if r: r.setdefault("variantes", {})[nom] = {"ecart": round(abs(a / r["e"]["surface_ecrite"] - 1), 4) if a else None}
                if r and not r["sure"]:
                    r.update({"a": a, "h": h, "source": src, "sure": True})
            for k, ec, cc in proches:             # MESURE SEULE (D-13) : ne change ni la surface ni « sure »
                r = res.get(k)
                if r:
                    r["meilleur_ecart"] = min(ec, r.get("meilleur_ecart", 9.0))
                    r.setdefault("variantes", {})[nom] = {"ecart": round(ec, 4), "contour": cc}   # 27/11 soir : pour dessiner
    import metre as _m; _m.ZONE = None   # les contours pixels (fichiers) ne dependent pas de la zone
    # 3. dernier recours : contours de la methode PIXELS (sorties/v1j), contour approche (+-1-2 cm), marque comme tel
    import json
    from shapely.geometry import Polygon
    js = os.path.join(ici, "sorties", "v1j", os.path.splitext(os.path.basename(chemin))[0] + "_metre.json")
    if os.path.exists(js) and not all(r["sure"] for r in res.values()):
        for p in json.load(open(js, encoding="utf-8"))["pieces"]:
            r = res.get((round(p["x"], 1), round(p["y"], 1)))
            c = p.get("contour_pt")
            if r and not r["sure"] and c and len(c) >= 3 and p.get("ecart_pct") is not None and abs(p["ecart_pct"]) <= SURE * 100:
                r.update({"a": p["surface_calc"], "h": Polygon(c).buffer(0), "source": "pixels (contour approché ±2 cm)", "sure": True})
    out = []
    # 27/11 : le metreur signale une piece COUPEE PAR LE BORD de la feuille (diag : 22 pieces ratees sur le banc ; sur Scanner,
    # toutes les feuilles du dossier ont le meme cadrage -> hors perimetre). Etiquette pres du bord = signal, pas une correction.
    import math
    from metre import lire_textes, normaliser
    from shapely.geometry import box, Point
    m_b = m_force or (matiere.DERNIERE_MATIERE[1] if matiere.DERNIERE_MATIERE else None)
    W_, H_ = lire_textes(normaliser(chemin), 0)[:2]
    bord = box(0, 0, W_, H_).exterior
    for r in res.values():
        e = r["e"]
        if r["sure"]: e["doutes"] = [d for d in e.get("doutes", []) if not d.startswith("écart")]
        elif r["a"] is None: e["doutes"] = ["pièce non fermée : à tracer à la main"]
        # 27/11 soir : 57 « coupees » mesurees sur 64 avaient un contour LOIN du bord (fuites vers une piece voisine, pas des
        # pieces coupees) -> si un contour existe, la piece n'est coupee que s'il touche le bord de la feuille (50 cm)
        h_ = r.get("h")
        touche = h_ is None or bord.distance(h_) * m_b <= 0.5 if m_b else True
        if not r["sure"] and m_b and e.get("surface_ecrite") and touche and \
                bord.distance(Point(e["x"], e["y"])) * m_b <= 1.2 * math.sqrt(e["surface_ecrite"]) + 1.0:
            e["coupee_bord"] = True
            e.setdefault("doutes", []).insert(0, "coupée par le bord de la feuille ? hors périmètre, ou feuille voisine à fournir")
        out.append(r)
    return out


if __name__ == "__main__":
    plans = sys.argv[1:] or sorted(glob.glob(os.path.join(ici, "plans_test", "*.pdf")))
    T = {"n": 0, "sures": 0, "fermees_non_sures": 0, "ouvertes": 0}
    for f in plans:
        t = time.time()
        R = pieces_v3(f)
        n = len(R); s = sum(r["sure"] for r in R); o = sum(r["a"] is None for r in R)
        T["n"] += n; T["sures"] += s; T["ouvertes"] += o; T["fermees_non_sures"] += n - s - o
        print("%-50s %3d pieces | SURES %3d (%3.0f %%) | a verifier %3d | non fermees %3d | %d s" % (
            os.path.basename(f)[:50], n, s, 100 * s / max(n, 1), n - s - o, o, time.time() - t), flush=True)
    if len(plans) > 1:
        print("\nTOTAL %d pieces : SURES %d (%.0f %%), a verifier %d, non fermees %d" % (
            T["n"], T["sures"], 100 * T["sures"] / max(T["n"], 1), T["fermees_non_sures"], T["ouvertes"]))
