"""Combinaison (27/11) : l'avis de l'IA « langue » (FloorPlanCAD) sur CHAQUE objet de nos pages, mis en cache, pour servir
d'indices a notre IA sens (qui, elle, voit couleur et remplissage). Meme ordre d'objets que objets.py.
Sortie : sorties/langue_cache/<nom[:60]>.npy  [n_objets, 6] probabilites (mur, vitre, porte, meuble, autre, reste).
Usage : python langue_cache.py plans_test plans_appr"""
import glob, os, sys, time, pickle
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
import langue_plans as LP

MODELE = os.environ.get("MODELE", "langue_plans.pkl")
CACHE = os.path.join(ici, "sorties", "langue_cache"); os.makedirs(CACHE, exist_ok=True)


def probas(chemin, M):
    LP.VUE_LARGE = M.get("vue_large", False)
    P = LP.primitives_pdf(chemin)
    F = LP.traits_par_tuiles(P)
    pr = M["modele"].predict_proba(F)
    vote = np.zeros((P["n_objets"], 6))
    cols = [int(c) for c in M["modele"].classes_]
    V = np.zeros((P["n_objets"], len(cols)))
    np.add.at(V, P["objet"], pr * P["length"][:, None])
    vote[:, cols] = V
    s = vote.sum(1, keepdims=True)
    return np.where(s > 0, vote / np.maximum(s, 1e-12), 0).astype(np.float32)


def chemin_cache(f):
    return os.path.join(CACHE, os.path.splitext(os.path.basename(f))[0][:60] + ".npy")


if __name__ == "__main__":
    M = pickle.load(open(os.path.join(ici, "sorties", MODELE), "rb"))
    pages = [sys.argv[2]] if sys.argv[1] == "--page" else [f for D in sys.argv[1:] for f in sorted(glob.glob(os.path.join(ici, D, "*.pdf")))]
    for f in pages:
        if True:
            c = chemin_cache(f)
            if os.path.exists(c): continue
            t = time.time()
            try:
                V = probas(f, M)
            except Exception as e:
                print("%-60s ERREUR %s" % (os.path.basename(f)[:60], str(e)[:80]), flush=True); continue
            np.save(c, V)
            print("%-60s %6d objets | %d s" % (os.path.basename(f)[:60], len(V), time.time() - t), flush=True)
