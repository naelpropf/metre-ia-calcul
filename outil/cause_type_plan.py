"""Test de cause « type de plan » (regle ecrite AVANT au journal du 27/11) : les pages de lots techniques, de demolition ou
d'existant ratent-elles beaucoup plus que les plans de projet d'architecte ?   python cause_type_plan.py <dossier_resultats>"""
import glob, json, os, re, sys, collections
sys.stdout.reconfigure(encoding="utf-8")


def type_de(nom):
    n = nom.upper().replace("_", " ").replace("-", " ")
    if re.search(r"\bLOT\b|LOTS|CVC|PLOMB|ELEC|CALEPINAGE|FX PLA|\bPIC\b|PHASAGE", n): return "technique"
    if re.search(r"D.MOLITION", n): return "demolition"
    if re.search(r"\bEDL\b|EXISTANT|ETAT DES LIEUX", n): return "existant"
    return "projet archi"


G = collections.defaultdict(lambda: [0, 0, 0])   # pieces, sures, non mesurees
pages = collections.defaultdict(list)
for p in glob.glob(os.path.join(sys.argv[1], "*.json")):
    J = json.load(open(p, encoding="utf-8")); t = type_de(J["page"])
    G[t][0] += J["pieces"]; G[t][1] += J["sures"]; G[t][2] += sum(1 for x in J["detail"] if not x["mesuree"])
    pages[t].append(J["page"][:60])
for t, (n, s, nm) in sorted(G.items(), key=lambda kv: -kv[1][0]):
    print("%-13s %2d pages | %4d pieces | sures %3d (%4.1f %%) | non mesurees %3d (%2.0f %%)" % (t, len(pages[t]), n, s, 100 * s / max(n, 1), nm, 100 * nm / max(n, 1)))
autres = [G[t] for t in ("technique", "demolition", "existant")]
n_a = sum(x[0] for x in autres); s_a = sum(x[1] for x in autres)
n_p, s_p = G["projet archi"][0], G["projet archi"][1]
ta, tp = s_a / max(n_a, 1), s_p / max(n_p, 1)
print("\nnon-projet : %d pieces, sures %.1f %% | projet archi : %d pieces, sures %.1f %%" % (n_a, 100 * ta, n_p, 100 * tp))
print("REGLE (>= 30 pieces ET taux <= moitie du projet) -> %s" % ("CAUSE PROBABLE" if n_a >= 30 and ta <= tp / 2 else "NON"))
for t in ("technique", "demolition", "existant"):
    print("\n%s :" % t); [print("   ", x) for x in sorted(pages[t])]
