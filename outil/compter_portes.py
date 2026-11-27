"""Combien de portes ENTROUVERTES (arc de 10-40 deg, non reconnues par matiere.portes qui exige 40-120 deg) sur les pages ?
Regle ecrite avant (journal 27/11) : cause frequente si >= 20 % des arcs de porte ET >= 3 dossiers.
  python compter_portes.py [dossier_de_pdf]   (defaut plans_neufs)"""
import glob, math, os, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
from metre import normaliser, page_plumber, echelle_par_cotes
from faces import kasa
D = sys.argv[1] if len(sys.argv) > 1 else "plans_neufs"
tot = collections.Counter(); par_dossier = collections.defaultdict(collections.Counter)
for f in sorted(glob.glob(os.path.join(ici, D, "*.pdf"))):
    try:
        ch = normaliser(f)
        old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
        try: m = echelle_par_cotes(ch, 0)[0]
        finally: sys.stdout.close(); sys.stdout = old
        if not m: continue
        c = collections.Counter()
        for o in page_plumber(ch).curves:
            pts = o.get("pts") or []
            if len(pts) < 5 or o.get("fill"): continue
            k = kasa(pts)
            if not k: continue
            cx, cy, r = k
            if not (0.55 <= r * m <= 1.3): continue
            a1 = math.atan2(pts[0][1] - cy, pts[0][0] - cx); a2 = math.atan2(pts[-1][1] - cy, pts[-1][0] - cx)
            bal = abs((a2 - a1 + math.pi) % (2 * math.pi) - math.pi)
            if 0.7 <= bal <= 2.1: c["reconnue"] += 1
            elif math.radians(10) <= bal < 0.7: c["entrouverte"] += 1
        nom = os.path.basename(f)
        tot.update(c); par_dossier[nom.split("_")[0]].update(c)
        if c["entrouverte"]: print("%-55s reconnues %3d | entrouvertes %3d" % (nom[:55], c["reconnue"], c["entrouverte"]), flush=True)
    except Exception as ex:
        print("ERREUR", os.path.basename(f)[:50], str(ex)[:60])
n = tot["reconnue"] + tot["entrouverte"]
dos = [k for k, c in par_dossier.items() if c["entrouverte"]]
part = tot["entrouverte"] / max(n, 1)
print("\nTOTAL arcs de porte %d | reconnus %d | entrouverts %d (%.0f %%) | dossiers avec entrouvertes : %d %s" % (
    n, tot["reconnue"], tot["entrouverte"], 100 * part, len(dos), dos))
print("REGLE (>= 20 %% ET >= 3 dossiers) -> %s" % ("CAUSE FREQUENTE" if part >= 0.20 and len(dos) >= 3 else "NON : cause locale"))
