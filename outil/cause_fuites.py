"""Regle ecrite AVANT (journal 27/11) : la cause « fuites par les ouvertures de porte » est prouvee si >= 50 % des pieces qui
FUIENT (trou partage ou piece ouverte) se retrouvent SEULES dans un trou apres fermeture de la matiere de 0,6 m.
  python cause_fuites.py <dossier_resultats>"""
import glob, json, os, sys, collections
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
fuit, seules, q_seules, tous_q = 0, 0, [], []
par_dos = collections.defaultdict(lambda: [0, 0])
for p in glob.glob(os.path.join(sys.argv[1], "*.json")):
    J = json.load(open(p, encoding="utf-8"))
    ecrits = collections.defaultdict(set)
    for x in J["detail"]:
        if x["mesuree"]: ecrits[round(x["mesuree"], 2)].add(round(x["ecrite"] or 0, 2))
    for x in J["detail"]:
        partage = x["mesuree"] and len(ecrits[round(x["mesuree"], 2)]) >= 2
        ouverte = (not x["mesuree"]) and x.get("pourquoi_non_mesuree") == "piece ouverte"
        af = x.get("apres_fermeture")
        if af and af.get("seule") and x["ecrite"]: tous_q.append(af["surface"] / x["ecrite"])
        if not (partage or ouverte): continue
        fuit += 1; d = par_dos[J["page"].split("_")[0]]; d[0] += 1
        if af and af.get("seule"):
            seules += 1; d[1] += 1
            if x["ecrite"]: q_seules.append(af["surface"] / x["ecrite"])
part = seules / max(fuit, 1)
print("pieces qui fuient : %d | seules apres fermeture : %d (%.0f %%)" % (fuit, seules, 100 * part))
print("REGLE (>= 50 %%) -> %s" % ("CAUSE PROUVEE" if part >= 0.5 else "NON"))
if q_seules:
    q = np.array(q_seules)
    print("ces pieces, rapport surface / ecrit apres fermeture : mediane %.2f | a 3 %% : %d | a 10 %% : %d" % (
        np.median(q), np.sum(abs(q - 1) <= 0.03), np.sum(abs(q - 1) <= 0.10)))
if tous_q:
    q = np.array(tous_q)
    print("(info) toutes les pieces seules apres fermeture : %d | a 1 %% : %d | a 3 %% : %d | a 10 %% : %d" % (
        len(q), np.sum(abs(q - 1) <= 0.01), np.sum(abs(q - 1) <= 0.03), np.sum(abs(q - 1) <= 0.10)))
# 27/11 regle 2 (ecrite avant) : fuites RESTANTES (pas seules a 0,6 m) -> a 1,0 m ? avec traits fins ? cause principale si >= 50 %
reste, s10, sfin, mesure_fins = 0, 0, 0, 0
for p in glob.glob(os.path.join(sys.argv[1], "*.json")):
    J = json.load(open(p, encoding="utf-8"))
    ecrits = collections.defaultdict(set)
    for x in J["detail"]:
        if x["mesuree"]: ecrits[round(x["mesuree"], 2)].add(round(x["ecrite"] or 0, 2))
    for x in J["detail"]:
        partage = x["mesuree"] and len(ecrits[round(x["mesuree"], 2)]) >= 2
        ouverte = (not x["mesuree"]) and x.get("pourquoi_non_mesuree") == "piece ouverte"
        af = x.get("apres_fermeture") or {}
        if not (partage or ouverte) or af.get("seule"): continue
        reste += 1; s10 += bool(af.get("seule_10")); sfin += bool(af.get("seule_fins")); mesure_fins += "seule_fins" in af
if reste:
    print("\nfuites restantes (pas seules a 0,6 m) : %d | seules a 1,0 m : %d (%.0f %%) | seules avec traits fins : %d (%.0f %%) [pages mesurees traits fins : %d pieces]" % (
        reste, s10, 100 * s10 / reste, sfin, 100 * sfin / reste, mesure_fins))
    print("REGLE 2 (>= 50 %%) -> %s" % ("ouvertures larges = cause principale" if s10 / reste >= 0.5 else
          "murs fins absents = cause principale" if sfin / reste >= 0.5 else "causes melangees"))
print("\npar dossier (fuient / seules apres fermeture) :")
for k, (a, b) in sorted(par_dos.items(), key=lambda kv: -kv[1][0]): print("  %-8s %4d / %4d" % (k, a, b))
