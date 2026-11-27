"""Regle ecrite AVANT (journal 27/11) : « mur en trop » cause probable si >= 50 % des pieces TROP PETITES (rapport < 0,9)
sont recuperables en regroupant les trous voisins separes par un trait. L'instrument est une BORNE BASSE (il rate des cas vus
en image) : sous 50 %, on ne conclut pas.   python cause_mur_en_trop.py <dossier_resultats>"""
import glob, json, os, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
n = k = 0; par = collections.defaultdict(lambda: [0, 0])
for p in glob.glob(os.path.join(sys.argv[1], "*.json")):
    J = json.load(open(p, encoding="utf-8"))
    for x in J["detail"]:
        v = x.get("mur_en_trop_recuperable")
        if v is None: continue
        n += 1; k += bool(v); d = par[J["page"].split("_")[0]]; d[0] += 1; d[1] += bool(v)
print("pieces trop petites mesurees : %d | recuperables : %d (%.0f %%)" % (n, k, 100 * k / max(n, 1)))
print("REGLE (>= 50 %%, borne basse) -> %s" % ("CAUSE PROBABLE" if k / max(n, 1) >= 0.5 else "PAS DE CONCLUSION (borne basse sous 50 %)"))
for d, (a, b) in sorted(par.items(), key=lambda kv: -kv[1][0]): print("  %-8s %4d / %4d" % (d, b, a))
