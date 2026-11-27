"""Vrais trous partages (meme CONTOUR exact) et etiquettes qui ne sont PAS des pieces (27/11, mesure).
- trou partage = au moins 2 etiquettes dans le meme contour (identifiant `trou` de l'examen) ;
- « total de groupe » probable = l'etiquette la plus grande d'un trou partage dont l'ecrit depasse de > 50 % la plus petite
  (ex. 548666 : 57,85 m2 ecrit dans une piece de 15,47 m2) ;
- « case de tableau » probable = contour de moins de 0,5 m2.
  python etiquettes_non_pieces.py <dossier_resultats>"""
import glob, json, os, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
tot = collections.Counter(); par = collections.defaultdict(collections.Counter)
for p in glob.glob(os.path.join(sys.argv[1], "*.json")):
    J = json.load(open(p, encoding="utf-8")); d = J["page"].split("_")[0]
    g = collections.defaultdict(list)
    for i, x in enumerate(J["detail"]):
        if x.get("trou"): g[tuple(x["trou"])].append(i)
    etat = {}
    for t, idx in g.items():
        if len(idx) < 2: continue
        ecr = sorted((J["detail"][i]["ecrite"] or 0, i) for i in idx)
        for e, i in ecr: etat[i] = "trou partage"
        if ecr[-1][0] > 1.5 * max(ecr[0][0], 0.01): etat[ecr[-1][1]] = "total de groupe ?"
    for i, x in enumerate(J["detail"]):
        if x["mesuree"] is not None and x["mesuree"] < 0.5 and i not in etat: etat[i] = "case de tableau ?"
        k = etat.get(i, "sure" if x["sure"] else "non mesuree" if not x["mesuree"] else "trou a elle, fausse")
        tot[k] += 1; par[d][k] += 1
n = sum(tot.values())
for k, v in tot.most_common(): print("%-20s %4d (%2.0f %%)" % (k, v, 100 * v / n))
print()
for d, c in sorted(par.items(), key=lambda kv: -sum(kv[1].values())):
    print("%-8s " % d + " | ".join("%s %d" % (k, v) for k, v in c.most_common()))
