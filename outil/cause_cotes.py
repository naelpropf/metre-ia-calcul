"""Test de cause « bord sur une ligne de cote » (regle ecrite AVANT au journal du 27/11, coffre 05 - Journal/2026-11-27 jour.md) :
cause probable si les pieces avec >= 0,30 m de contour a moins de 3 cm d'une ligne de cote sont >= 30
ET ont un taux de pieces sures <= la moitie de celui des autres.   python cause_cotes.py <dossier_resultats>"""
import glob, json, os, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
P = []
for p in glob.glob(os.path.join(sys.argv[1], "*.json")):
    J = json.load(open(p, encoding="utf-8"))
    for x in J["detail"]:
        q = x["mesuree"] / x["ecrite"] if x["mesuree"] and x["ecrite"] else None
        mode = "sure" if x["sure"] else "non mesuree" if q is None else "presque (1-10 %)" if abs(q - 1) <= 0.10 else "trop grande" if q > 1 else "trop petite"
        P.append({"dossier": J["page"].split("_")[0], "touche": (x.get("bord_cote_m") or 0) >= 0.30, "mesuree": q is not None,
                  "sure": x["sure"], "mode": mode, "bc": x.get("bord_cote_m")})
mes = [p for p in P if p["mesuree"]]
t = [p for p in mes if p["touche"]]; a = [p for p in mes if not p["touche"]]
st = sum(p["sure"] for p in t) / max(len(t), 1); sa = sum(p["sure"] for p in a) / max(len(a), 1)
print("pieces mesurees %d (diagnostic present : %d)" % (len(mes), sum(p["bc"] is not None for p in mes)))
print("bord sur une cote >= 0,30 m : %d pieces, sures %.1f %% | autres : %d pieces, sures %.1f %%" % (len(t), 100 * st, len(a), 100 * sa))
ok = len(t) >= 30 and st <= sa / 2
print("REGLE : >= 30 pieces ET taux <= moitie des autres -> %s" % ("CAUSE PROBABLE" if ok else "NON (pas une cause prouvee)"))
print("\npart des pieces touchees, par mode d'echec :")
for mode in ("sure", "presque (1-10 %)", "trop petite", "trop grande"):
    g = [p for p in mes if p["mode"] == mode]
    print("  %-18s %4d pieces | touchees %4d (%.0f %%)" % (mode, len(g), sum(p["touche"] for p in g), 100 * sum(p["touche"] for p in g) / max(len(g), 1)))
print("\npar dossier (touchees / mesurees) :")
c = collections.defaultdict(lambda: [0, 0])
for p in mes: c[p["dossier"]][0] += p["touche"]; c[p["dossier"]][1] += 1
for k, (n1, n2) in sorted(c.items(), key=lambda kv: -kv[1][1]): print("  %-8s %3d / %3d" % (k, n1, n2))
