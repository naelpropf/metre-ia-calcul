"""IA de tri (D-08) : apprend a dire si un objet du PDF est une LIMITE de piece (mur, vitre, seuil...) ou non.
Test honnete : entrainee sur 6 plans, testee sur le 7e jamais vu (x7).
Seuil ecrit AVANT (journal 25/11) : exactitude equilibree >= 90 % sur >= 5 plans etiquetes, ET mieux que la regle a la main.
Usage : python tri.py            -> evaluation plan par plan
        python tri.py --final    -> entraine sur tout et sauve sorties/tri_modele.pkl"""
import glob, json, os, pickle, sys
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score
ici = os.path.dirname(os.path.abspath(__file__))
CARAC = ["type", "n_pts", "ep_stylo_cm", "stylo_pt", "rempli", "trace", "trait_r", "trait_g", "trait_b",
         "rempli_r", "rempli_g", "rempli_b", "longueur_m", "boite_l_m", "boite_c_m", "ferme", "aire_m2",
         "ep_bande_m", "cote_max_m", "angle_mod90", "droit"]


def regle_main(x):
    """la regle actuelle de matiere.py : bande remplie de 2 a 35 cm, ou trait epais (stylo >= 0,45 pt)"""
    return int((x["rempli"] and 0.02 <= x["ep_bande_m"] <= 0.35) or x["stylo_pt"] >= 0.45)


def charger(dossier="objets"):
    """par plan : seulement les objets ETIQUETES, en tableaux compacts (X, y, regle a la main).
    Avant (26/11) : tous les objets en dicts Python -> plusieurs Go, processus tue sans message."""
    import gzip
    plans = {}
    fichiers = sorted(glob.glob(os.path.join(ici, "sorties", dossier, "*.jsonl")) + glob.glob(os.path.join(ici, "sorties", dossier, "*.jsonl.gz")))
    # CACHE COMPACT (27/11 : 99 % du temps d'un essai = relire 1,9 Go de texte ; l'apprentissage lui-meme = 3 s).
    # Par page : tableaux numpy deja prets (caracteristiques + voisinage), recalcules seulement si la source change.
    cache = os.path.join(ici, "sorties", "cache_tri", dossier)
    os.makedirs(cache, exist_ok=True)
    drap = "v%d_c%d" % (AVEC_VOISINAGE, SANS_COURTS)
    for f in fichiers:
        nom = os.path.basename(f)[:40]
        fc = os.path.join(cache, os.path.basename(f).split(".jsonl")[0][:80] + "__" + drap + ".npz")
        if os.path.exists(fc) and os.path.getmtime(fc) >= os.path.getmtime(f):
            z = np.load(fc, allow_pickle=False)
            if len(z["y"]):
                plans[nom] = {"X": z["X"], "y": z["y"], "rg": z["rg"], "cx": z["cx"] if len(z["cx"]) else None}
            continue
        ouvre = (lambda: gzip.open(f, "rt", encoding="utf-8")) if f.endswith(".gz") else (lambda: open(f, encoding="utf-8"))
        with ouvre() as h:
            if not any('"etiquette": 1' in l or '"etiquette": 0' in l for l in h):   # page sans exemple
                np.savez(fc, X=np.zeros((0, 1)), y=np.zeros(0, int), rg=np.zeros(0, int), cx=np.zeros(0)); continue
        with ouvre() as h:
            L = [json.loads(l) for l in h]
        if SANS_COURTS:
            # essai 26/11 : 51-95 % des « limites » etaient des traits fins < 30 cm (hachures, details) = bruit
            for x in L:
                if x["longueur_m"] < 0.3 and not (x["rempli"] and 0.02 <= x["ep_bande_m"] <= 0.35) and x["stylo_pt"] < 0.45:
                    x["etiquette"] = -1
        idx = [i for i, x in enumerate(L) if x["etiquette"] >= 0]
        voisinage(L, idx)
        lt = [L[i] for i in idx]
        del L
        plans[nom] = {"X": matrice(lt), "y": np.array([x["etiquette"] for x in lt], int),
                      "rg": np.array([regle_main(x) for x in lt], int),
                      "cx": np.array([(x["_x0"] + x["_x1"]) / 2 for x in lt]) if lt and "_x0" in lt[0] else None}
        P = plans[nom]
        np.savez(fc, X=P["X"] if len(lt) else np.zeros((0, 1)), y=P["y"], rg=P["rg"], cx=P["cx"] if P["cx"] is not None else np.zeros(0))
        if not len(lt): del plans[nom]
        print("  charge %-40s %6d exemples" % (os.path.basename(f)[:40], len(lt)), flush=True)
    return plans


def dossier_de(nom):
    """les 7 premiers caracteres = numero du dossier d'appel d'offres (un architecte, ses habitudes de dessin)"""
    return nom[:7]


VOISINAGE = ["v_paralleles_30cm", "v_aplats_fonces_20cm", "v_densite_50cm", "v_long_med_m"]
AVEC_VOISINAGE = "--sans-voisinage" not in sys.argv
SANS_COURTS = "--sans-courts" in sys.argv   # ecarte les traits fins < 30 cm (etiquettes bruitees, mesure 26/11)


def voisinage(L, seulement=None):
    """seulement : indices des objets dont on calcule le voisinage (les voisins restent TOUS les objets).
    26/11 : calculer pour les millions d'objets non etiquetes prenait > 45 min pour rien."""
    """Ajoute a chaque objet des caracteristiques de son VOISINAGE (lecon de SymPoint : le contexte compte autant
    que l'objet). Calcule depuis les positions enregistrees par objets.py (_x0.._y1, _angle), sans relire le PDF."""
    from scipy.spatial import cKDTree
    if not L or "_x0" not in L[0]:
        for x in L:
            for c in VOISINAGE: x[c] = -1
        return L
    C = np.array([((x["_x0"] + x["_x1"]) / 2, (x["_y0"] + x["_y1"]) / 2) for x in L])
    ang = np.array([x["_angle"] for x in L]); lon = np.array([x["longueur_m"] for x in L])
    fonce = np.array([x["rempli"] == 1 and 0 <= (x["rempli_r"] + x["rempli_g"] + x["rempli_b"]) / 3 <= 0.75 for x in L])
    arbre = cKDTree(C)
    # VECTORISE (26/11) : avant, une boucle Python par voisin -> > 1 h sur les zones denses (hachures, 64 000 exemples) ;
    # meme resultat, calcule d'un bloc par objet avec numpy
    cinq = np.radians(5)
    for i in (range(len(L)) if seulement is None else seulement):
        x = L[i]
        p50 = np.asarray(arbre.query_ball_point(C[i], 0.5), int)
        x["v_densite_50cm"] = len(p50) - 1
        if len(p50) == 0:
            x["v_paralleles_30cm"] = x["v_aplats_fonces_20cm"] = 0; x["v_long_med_m"] = 0.0; continue
        dist = np.hypot(C[p50, 0] - C[i, 0], C[p50, 1] - C[i, 1])
        autre = p50 != i
        m30 = autre & (dist <= 0.3) & (lon[p50] > 0.2)
        d = np.abs(ang[p50[m30]] - ang[i])
        x["v_paralleles_30cm"] = int(np.sum(np.minimum(d, np.pi - d) < cinq))
        x["v_aplats_fonces_20cm"] = int(np.sum(autre & fonce[p50] & (dist <= 0.2)))
        x["v_long_med_m"] = float(np.median(lon[p50]))
    return L


def matrice(L):
    cols = CARAC + (VOISINAGE if AVEC_VOISINAGE else [])
    return np.array([[x[c] for c in cols] for x in L], float)


def modele():
    # poids equilibres : autant d'importance aux deux classes
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, class_weight="balanced", random_state=0)


if __name__ == "__main__":
    if "--intra" in sys.argv:
        # APPRENDRE SUR LE PLAN LUI-MEME (26/11) : les pieces sures d'un plan montrent les habitudes de CET architecte.
        # Test honnete : apprendre sur la moitie GAUCHE du plan, tester sur la DROITE (et l'inverse) -> zones jamais vues.
        # Ecrit avant : >= 90 % sur >= 4 plans -> direction « apprendre plan par plan ».
        passe = n_eval = 0
        for test, P in charger().items():
            if P["cx"] is None or len(set(P["y"])) < 2: continue
            med = np.median(P["cx"]); res_ = []
            for g in (P["cx"] < med, P["cx"] >= med):
                a, t = ~g, g
                if len(set(P["y"][a])) < 2 or len(set(P["y"][t])) < 2: continue
                m = modele().fit(P["X"][a], P["y"][a])
                res_.append((balanced_accuracy_score(P["y"][t], m.predict(P["X"][t])), balanced_accuracy_score(P["y"][t], P["rg"][t])))
            if not res_: continue
            ia = np.mean([r[0] for r in res_]); rg = np.mean([r[1] for r in res_])
            n_eval += 1; passe += ia >= 0.90
            print("%-40s etiquetes %5d | IA (meme plan, autre moitie) %5.1f %% | regle a la main %5.1f %%" % (test, len(P["y"]), 100 * ia, 100 * rg), flush=True)
        print("\nINTRA : IA >= 90 %% sur %d / %d plans -> %s" % (passe, n_eval, "DIRECTION VALIDEE" if passe >= 4 else "PAS ATTEINT"))
        sys.exit()
    plans = charger()                       # le banc (7 pages) : sert au TEST
    appr = charger("objets_appr")           # pages d'apprentissage des memes 10 dossiers (jamais testees)
    corr = charger("objets_corr")          # contours CONFIRMES par l'operateur (boucle de correction, ecran v2)
    tous = {**appr, **corr, **plans}
    if "--final" in sys.argv:
        X = np.vstack([P["X"] for P in tous.values()]); y = np.concatenate([P["y"] for P in tous.values()])
        m = modele().fit(X, y)
        pickle.dump({"modele": m, "carac": CARAC + (VOISINAGE if AVEC_VOISINAGE else [])}, open(os.path.join(ici, "sorties", "tri_modele.pkl"), "wb"))
        print("modele final entraine sur %d objets etiquetes" % len(y)); sys.exit()
    passe, n_eval, gagne = 0, 0, 0
    for test, Pt in plans.items():
        y = Pt["y"]
        # apprentissage : TOUTES les pages (banc + apprentissage) des AUTRES dossiers -> jamais l'architecte teste
        autres = [P for p, P in tous.items() if dossier_de(p) != dossier_de(test)]
        if len(set(y)) < 2 or not autres:
            print("%-40s pas assez d'etiquettes pour tester (%d)" % (test, len(y))); continue
        m = modele().fit(np.vstack([P["X"] for P in autres]), np.concatenate([P["y"] for P in autres]))
        ia = balanced_accuracy_score(y, m.predict(Pt["X"]))
        rg = balanced_accuracy_score(y, Pt["rg"])
        n_eval += 1; passe += ia >= 0.90; gagne += ia > rg
        print("%-40s etiquetes %5d (limite %4d) | IA %5.1f %% | regle a la main %5.1f %%" % (
            test, len(y), int(y.sum()), 100 * ia, 100 * rg), flush=True)
    print("\nIA >= 90 %% sur %d plans / %d testes ; IA meilleure que la regle sur %d / %d -> %s" % (
        passe, n_eval, gagne, n_eval, "SEUIL PASSE" if passe >= 5 and gagne > n_eval / 2 else "SEUIL PAS ATTEINT"))
