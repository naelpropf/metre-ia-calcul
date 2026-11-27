"""Pourquoi nos murs sont-ils lus comme des vitres ? On compare les indices (moyennes) :
  - FloorPlanCAD validation : vrais murs, vraies vitres ;
  - un de nos plans : murs lus « mur », murs lus « vitre ».
Usage : python diag_langue.py 3103962"""
import glob, gzip, json, os, sys, pickle
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
import langue_plans as LP

NOMS = (LP.NOMS + ["v1_" + n for n in LP.NOMS] + ["v2_" + n for n in LP.NOMS] +
        ["l_dist", "l_centre_m", "l_cos", "l_sin", "l_ratio", "l_touche", "l_aligne", "l_decal_m", "degre", "touche_max", "n_alignes"])
M = pickle.load(open(os.path.join(ici, "sorties", "langue_plans.pkl"), "rb"))
Xv, yv = LP.lire_partie(os.path.join(LP.EXT, "graphs", "val", "val-00000.npz"))
k = sys.argv[1]
f = glob.glob(os.path.join(ici, "plans_test", k + "*.pdf"))[0]
P = LP.primitives_pdf(f)
F = LP.traits_par_tuiles(P)
pr = M["modele"].predict(F)
L = [json.loads(l) for l in gzip.open(glob.glob(os.path.join(ici, "sorties", "objets", k + "*.jsonl.gz"))[0], "rt", encoding="utf-8")]
mur_obj = np.array([x.get("etiquette") == 1 and x.get("classe") == "mur" for x in L])
est_mur = mur_obj[P["objet"]]
groupes = {"FPCAD mur": Xv[yv == 0], "FPCAD vitre": Xv[yv == 1], "FPCAD reste": Xv[yv == 5],
           "NOUS mur->mur": F[est_mur & (pr == 0)], "NOUS mur->vitre": F[est_mur & (pr == 1)], "NOUS tout": F}
print("%-14s" % "indice" + "".join("%15s" % g for g in groupes))
print("%-14s" % "nombre" + "".join("%15d" % len(v) for v in groupes.values()))
for c, n in enumerate(NOMS):
    if n.startswith("type_") and not n.startswith("type_ligne"): continue
    if n.startswith(("v1_type_a", "v1_type_c", "v1_type_e", "v2_")): continue
    print("%-14s" % n + "".join("%15.3f" % (np.median(v[:, c]) if len(v) else np.nan) for v in groupes.values()))
# longueur reelle (m) : log1p(L/1000)
print("longueur mediane (m) :", {g: round(float(np.expm1(np.median(v[:, 5]))), 2) if len(v) else None for g, v in groupes.items()})
