"""Regle ecrite AVANT (journal 27/11) : « renflement de porte » cause probable si, parmi les pieces avec un contour A ELLES
un peu trop grandes (1,01 < rapport <= 1,15), >= 30 % tombent a 1 % de l'ecrit apres ouverture de 0,45 m.
  python cause_renflement.py <dossier_resultats>"""
import glob, json, os, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
n = k = 0; gagne_tout = 0; perd = 0; par = collections.defaultdict(lambda: [0, 0])
for p in glob.glob(os.path.join(sys.argv[1], "*.json")):
    J = json.load(open(p, encoding="utf-8"))
    trous = collections.Counter(tuple(x["trou"]) for x in J["detail"] if x.get("trou"))
    for x in J["detail"]:
        ao, me, ec = x.get("aire_ouverte_045"), x["mesuree"], x["ecrite"]
        if ao is None or not me or not ec: continue
        if ao and abs(ao / ec - 1) <= 0.01 and not x["sure"]: gagne_tout += 1
        if x["sure"] and not (ao and abs(ao / ec - 1) <= 0.01): perd += 1
        if not x.get("trou") or trous[tuple(x["trou"])] > 1: continue
        q = me / ec
        if 1.01 < q <= 1.15:
            n += 1; ok = bool(ao and abs(ao / ec - 1) <= 0.01); k += ok
            d = par[J["page"].split("_")[0]]; d[0] += 1; d[1] += ok
print("pieces a elles un peu trop grandes : %d | a 1 %% apres ouverture : %d (%.0f %%)" % (n, k, 100 * k / max(n, 1)))
print("REGLE (>= 30 %%) -> %s" % ("CAUSE PROBABLE" if k / max(n, 1) >= 0.30 else "NON"))
print("(info) toutes pieces : deviendraient a 1 %% apres ouverture : %d | sures qui ne le seraient plus : %d" % (gagne_tout, perd))
for d, (a, b) in sorted(par.items(), key=lambda kv: -kv[1][0]): print("  %-8s %3d / %3d" % (d, b, a))
