"""Banc honnete de la methode matiere pilotee par l'IA : pour chaque plan du banc, l'IA est RE-ENTRAINEE sans le
dossier de ce plan (jamais l'architecte mesure), puis on mesure ses pieces. Comparaison, sur les memes pieces :
pixels v1h / matiere a regles / matiere + IA. Seuil S1 (ecrit le 25/11, inchange) : >= 5 plans sur 7 avec >= 80 %
des pieces a 3 %.
Usage : python banc_ia.py [seuil_proba=0.5]"""
import glob, json, os, sys, time
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
import tri, matiere, ia_matiere

seuil = float(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else 0.5
plans = tri.charger(); appr = tri.charger("objets_appr"); tous = {**appr, **plans}
cols = tri.CARAC + (tri.VOISINAGE if tri.AVEC_VOISINAGE else [])
tot = {"pixels": 0, "regles": 0, "ia": 0, "n": 0}; passe = {"pixels": 0, "regles": 0, "ia": 0}
lignes = []
for f in sorted(glob.glob(os.path.join(ici, "plans_test", "*.pdf"))):
    t = time.time()
    nom = os.path.splitext(os.path.basename(f))[0]
    d = tri.dossier_de(nom)
    autres = [P for p, P in tous.items() if tri.dossier_de(p) != d]
    M = tri.modele().fit(np.vstack([P["X"] for P in autres]), np.concatenate([P["y"] for P in autres]))
    ia_matiere._MODELE = {"modele": M, "carac": cols}
    def compte(res):
        return sum(1 for e, a in res if a and abs(a / e["surface_ecrite"] - 1) <= 0.03)
    r_ia = ia_matiere.pieces_par_ia(f, seuil, verbeux=False)
    r_rg = matiere.pieces_par_matiere(f, verbeux=False)
    v1 = json.load(open(os.path.join(ici, "sorties", "v1j", nom + "_metre.json"), encoding="utf-8"))["pieces"]
    n = len(r_ia)
    c = {"pixels": sum(1 for p in v1 if p.get("ecart_pct") is not None and abs(p["ecart_pct"]) <= 3),
         "regles": compte(r_rg), "ia": compte(r_ia)}
    for k in c:
        tot[k] += c[k]; passe[k] += n > 0 and c[k] >= 0.8 * n
    tot["n"] += n
    alertes = sum(1 for e, a in r_ia if a and e.get("doutes"))
    justes_sans_alerte = sum(1 for e, a in r_ia if a and not e.get("doutes") and abs(a / e["surface_ecrite"] - 1) <= 0.03)
    faux_sans_alerte = sum(1 for e, a in r_ia if a and not e.get("doutes") and abs(a / e["surface_ecrite"] - 1) > 0.03)
    l = {"plan": nom[:45], "pieces": n, **c, "alertes": alertes, "faux_sans_alerte": faux_sans_alerte, "s": round(time.time() - t)}
    lignes.append(l)
    print("%-45s %3d pieces | a 3 %% : pixels %3d  regles %3d  IA %3d | IA : alertes %d, FAUX SANS ALERTE %d | %d s" % (
        l["plan"], n, c["pixels"], c["regles"], c["ia"], alertes, faux_sans_alerte, l["s"]), flush=True)
print("\nTOTAL %d pieces a 3 %% : pixels %d | regles %d | IA %d" % (tot["n"], tot["pixels"], tot["regles"], tot["ia"]))
print("Plans qui passent S1 (>= 80 %% a 3 %%) : pixels %d, regles %d, IA %d sur 7" % (passe["pixels"], passe["regles"], passe["ia"]))
os.makedirs(os.path.join(ici, "sorties", "banc_ia"), exist_ok=True)
json.dump(lignes, open(os.path.join(ici, "sorties", "banc_ia", "resultats_%.2f.json" % seuil), "w", encoding="utf-8"), indent=1)
