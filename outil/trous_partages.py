"""Combien de pieces tombent dans un TROU PARTAGE (meme surface mesuree qu'une autre piece de la page = cloisons interieures
non vues comme murs ; 3068854 R+1/R+2 : 12 pieces a 860,28 m2 = tout l'etage) ? Mesure descriptive (27/11).
  python trous_partages.py <dossier_resultats>"""
import glob, json, os, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
tot = collections.Counter(); par_dos = collections.defaultdict(collections.Counter)
for p in glob.glob(os.path.join(sys.argv[1], "*.json")):
    J = json.load(open(p, encoding="utf-8"))
    # partage = meme surface mesuree pour des pieces aux surfaces ECRITES differentes (des pieces identiques en serie, comme des
    # caves de meme taille, ont legitimement la meme surface : elles ne comptent pas)
    ecrits = collections.defaultdict(set)
    for x in J["detail"]:
        if x["mesuree"]: ecrits[round(x["mesuree"], 2)].add(round(x["ecrite"] or 0, 2))
    for x in J["detail"]:
        if not x["mesuree"]: mode = "non mesuree"
        elif len(ecrits[round(x["mesuree"], 2)]) >= 2: mode = "trou partage"
        elif x["sure"]: mode = "sure"
        else: mode = "trou a elle, fausse"
        tot[mode] += 1; par_dos[J["page"].split("_")[0]][mode] += 1
n = sum(tot.values())
for k, v in tot.most_common(): print("%-20s %4d (%2.0f %%)" % (k, v, 100 * v / n))
print()
for d, c in sorted(par_dos.items(), key=lambda kv: -sum(kv[1].values())):
    print("%-8s " % d + " | ".join("%s %d" % (k, v) for k, v in c.most_common()))
