"""Rapport surface mesuree / surface ecrite, par dossier et par page, sur un examen (27/11, mesure seulement).
Si le rapport est CONSTANT sur une page (x4, x0,25...) -> l'echelle est fausse d'un facteur ; s'il est disperse -> autre cause.
  python rapports_neufs.py <dossier_resultats>"""
import glob, json, os, sys, collections
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
d = sys.argv[1]
par_dossier = collections.defaultdict(list)
for p in sorted(glob.glob(os.path.join(d, "*.json"))):
    J = json.load(open(p, encoding="utf-8"))
    r = [x["mesuree"] / x["ecrite"] for x in J["detail"] if x["mesuree"] and x["ecrite"]]
    nm = sum(1 for x in J["detail"] if not x["mesuree"])
    par_dossier[J["page"].split("_")[0]] += r
    if J["pieces"] >= 10:
        q = np.percentile(r, [25, 50, 75]) if r else [0, 0, 0]
        print("%-55s pieces %3d | non mesurees %3d | sures %3d | rapport q25 %.2f mediane %.2f q75 %.2f" % (
            J["page"][:55], J["pieces"], nm, J["sures"], *q))
print()
for k, r in sorted(par_dossier.items(), key=lambda kv: -len(kv[1])):
    if not r: print("%-8s aucune piece mesuree" % k); continue
    r = np.array(r)
    print("%-8s mesurees %3d | mediane %.2f | dans +-1 %% : %3d | +-10 %% : %3d | x0,9-1,1 hors 1 %% : %3d | < 0,5 : %3d | > 2 : %3d" % (
        k, len(r), np.median(r), np.sum(abs(r - 1) <= 0.01), np.sum(abs(r - 1) <= 0.10), np.sum((abs(r - 1) > 0.01) & (abs(r - 1) <= 0.10)),
        np.sum(r < 0.5), np.sum(r > 2)))
