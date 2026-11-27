"""CASSURE 2 (27/11) : l'IA apprend le SENS de chaque objet du plan (mur, vitre, porte, cote, lettre, fond, hachure,
mobilier) a partir des « bases breves » = etiquettes automatiques de objets.py (ce que l'outil sait deja SUR).
Test honnete, ecrit AVANT :
  - MEME plan, autre moitie (zone jamais vue) : exactitude equilibree entre classes >= 90 % -> le sens est appris ;
  - entre ARCHITECTES (autres dossiers) : mesure pour information, sans seuil (on sait que c'est plus dur).
Cache compact par page (comme tri.py) : un essai complet = quelques secondes une fois les pages lues.
Usage : python sens.py [--entre]"""
import glob, gzip, json, os, sys
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score, recall_score
import tri

CLASSES = ["mur", "vitre", "porte", "cote", "lettre", "fond", "hachure", "mobilier", "autre"]   # 27/11 : + autre
COLS = tri.CARAC + tri.VOISINAGE + (["alignes"] if os.environ.get("AUTRE") == "1" else [])   # 27/11
LANGUE = os.environ.get("LANGUE") == "1"   # 27/11 : + avis de l'IA langue (FloorPlanCAD) en indices (langue_cache.py)
LG_COLS = ["lg_mur", "lg_vitre", "lg_porte", "lg_meuble", "lg_autre", "lg_reste"]
CONTEXTE = os.environ.get("CONTEXTE") == "1"   # 27/11 : textes vus d'en haut (contexte.py)


def charger(dossier="objets"):
    cache = os.path.join(ici, "sorties", "cache_sens", dossier + ("_lg" if LANGUE else "") + ("_cx" if CONTEXTE else "")); os.makedirs(cache, exist_ok=True)
    plans = {}
    for f in sorted(glob.glob(os.path.join(ici, "sorties", dossier, "*.jsonl.gz"))):
        nom = os.path.basename(f)[:40]
        fc = os.path.join(cache, os.path.basename(f).split(".jsonl")[0][:80] + ".npz")
        if os.path.exists(fc) and os.path.getmtime(fc) >= os.path.getmtime(f):
            z = np.load(fc, allow_pickle=False)
            if len(z["y"]): plans[nom] = {"X": z["X"], "y": z["y"], "cx": z["cx"]}
            continue
        L = [json.loads(l) for l in gzip.open(f, "rt", encoding="utf-8")]
        idx = [i for i, x in enumerate(L) if x.get("classe") in CLASSES]
        if not idx:
            np.savez(fc, X=np.zeros((0, len(COLS))), y=np.zeros(0, int), cx=np.zeros(0)); continue
        tri.voisinage(L, idx)
        X = np.array([[L[i].get(c, 0) for c in COLS] for i in idx], float)
        if LANGUE:
            fl = os.path.join(ici, "sorties", "langue_cache", os.path.basename(f).split(".jsonl")[0] + ".npy")
            if not os.path.exists(fl): print("  pas d'avis langue :", nom); continue
            V = np.load(fl, allow_pickle=False)
            if len(V) != len(L): print("  ALIGNEMENT langue impossible :", nom, len(V), len(L)); continue
            X = np.hstack([X, V[idx]])
        if CONTEXTE:
            fx = os.path.join(ici, "sorties", "contexte_cache", os.path.basename(f).split(".jsonl")[0][:60] + ".npy")
            if not os.path.exists(fx): print("  pas de contexte :", nom); continue
            V2 = np.load(fx, allow_pickle=False)
            if len(V2) != len(L): print("  ALIGNEMENT contexte impossible :", nom, len(V2), len(L)); continue
            X = np.hstack([X, V2[idx]])
        y = np.array([CLASSES.index(L[i]["classe"]) for i in idx], int)
        cx = np.array([(L[i]["_x0"] + L[i]["_x1"]) / 2 for i in idx])
        np.savez(fc, X=X, y=y, cx=cx)
        plans[nom] = {"X": X, "y": y, "cx": cx}
        print("  lu %-40s %6d exemples" % (nom, len(y)), flush=True)
    return plans


def modele():
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, class_weight="balanced", random_state=0)


def rapport(y, p):
    rec = recall_score(y, p, labels=sorted(set(y)), average=None, zero_division=0)
    return " ".join("%s %d%%" % (CLASSES[c][:6], 100 * r) for c, r in zip(sorted(set(y)), rec))


if __name__ == "__main__" and "--c" not in sys.argv:
    plans = charger(sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "objets")
    print("\n== MEME plan, autre moitie (seuil ecrit avant : >= 90 % d'exactitude equilibree) ==")
    ok = n = 0
    for nom, P in plans.items():
        if len(set(P["y"])) < 2 or len(P["y"]) < 200: continue
        med = np.median(P["cx"]); sc = []; tous_y, tous_p = [], []
        for g in (P["cx"] < med, P["cx"] >= med):
            a, t = ~g, g
            if len(set(P["y"][a])) < 2: continue
            gard = np.isin(P["y"][a], [c for c in set(P["y"][a]) if (P["y"][a] == c).sum() >= 2])   # classe a 1 exemple : plantait (27/11)
            a = np.where(a)[0][gard]
            m = modele().fit(P["X"][a], P["y"][a]); p = m.predict(P["X"][t])
            tous_y += list(P["y"][t]); tous_p += list(p)
        if not tous_y: continue
        ba = balanced_accuracy_score(tous_y, tous_p); n += 1; ok += ba >= 0.90
        print("%-40s %6d ex. | %5.1f %% | %s" % (nom, len(P["y"]), 100 * ba, rapport(np.array(tous_y), np.array(tous_p))), flush=True)
    print("-> %d / %d plans >= 90 %%" % (ok, n))
    if "--entre" in sys.argv:
        print("\n== ENTRE architectes (pour information) ==")
        for nom, P in plans.items():
            autres = [Q for k, Q in plans.items() if k[:7] != nom[:7]]
            if not autres or len(P["y"]) < 200: continue
            m = modele().fit(np.vstack([Q["X"] for Q in autres]), np.concatenate([Q["y"] for Q in autres]))
            p = m.predict(P["X"])
            print("%-40s %5.1f %% | %s" % (nom, 100 * balanced_accuracy_score(P["y"], p), rapport(P["y"], p)), flush=True)


def test_c():
    """TEST C (declare le 27/11, coffre : « Test C sens - meme dossier autres pages ») : apprendre sur les AUTRES pages du
    MEME dossier (objets_appr_mm), tester sur la page du banc (objets_mm). Classes notees : >= 20 ex. en test ET en appr."""
    suf = sys.argv[sys.argv.index("--suf") + 1] if "--suf" in sys.argv else "_mm"   # 27/11 : _mm_mp = meubles partout
    app, test = charger("objets_appr" + suf), charger("objets" + suf)
    for avec_autres in (False, True):
        print("\n== TEST C %s ==" % ("+ pages des AUTRES dossiers (info)" if avec_autres else "meme dossier, autres pages (seuil : >= 90 % sur >= 2/3)"))
        ok = n = 0
        for nom, T in test.items():
            k = nom[:7]
            A = [P for kk, P in app.items() if kk[:7] == k or avec_autres]
            if not A: print("%-40s pas de pages d'apprentissage" % nom); continue
            X = np.vstack([P["X"] for P in A]); y = np.concatenate([P["y"] for P in A])
            g2 = np.isin(y, [c for c in set(y) if (y == c).sum() >= 2]); X, y = X[g2], y[g2]   # classe a 1 exemple : plantait
            notees = [c for c in set(T["y"]) if (T["y"] == c).sum() >= 20 and (y == c).sum() >= 20]
            if len(T["y"]) < 1000 or len(notees) < 2:
                print("%-40s non compte (%d ex., %d classes notees)" % (nom, len(T["y"]), len(notees))); continue
            p = modele().fit(X, y).predict(T["X"])
            g = np.isin(T["y"], notees)
            ba = balanced_accuracy_score(T["y"][g], p[g]); n += 1; ok += ba >= 0.90
            print("%-40s appr %6d ex. | %5.1f %% | %s" % (nom, len(y), 100 * ba, rapport(T["y"][g], p[g])), flush=True)
        print("-> %d / %d dossiers >= 90 %%%s" % (ok, n, ("  => REUSSI" if n and ok >= 2 * n / 3 else "  => ECHEC") if not avec_autres else ""))


if __name__ == "__main__" and "--c" in sys.argv:
    test_c()
