# Ajoute un lot de fiches GitHub (fiches_resultats/<lot>) aux fiches deja dans Colab (/content/fiches), SANS doublon.
# Les nouvelles fiches vont A LA FIN : les 16 premieres fiches du dossier d'examen restent les memes (scores comparables).
#   python fusionner_colab.py /content/metre-ia-calcul/fiches_resultats/<lot> /content/fiches
import json, os, shutil, sys

src, dst = sys.argv[1], sys.argv[2]
FJ = [os.path.join(dp, f) for dp, _, fs in os.walk(dst) for f in fs if f == "exercices.jsonl"][0]
base = os.path.dirname(FJ)
deja = {json.loads(l)["image"] for l in open(FJ, encoding="utf-8") if l.strip()}
n = 0
with open(FJ, "a", encoding="utf-8") as g:
    for l in open(os.path.join(src, "exercices.jsonl"), encoding="utf-8"):
        if not l.strip(): continue
        f = json.loads(l)
        if f["image"] in deja: continue
        os.makedirs(os.path.dirname(os.path.join(base, f["image"])), exist_ok=True)
        shutil.copy(os.path.join(src, f["image"]), os.path.join(base, f["image"]))
        g.write(json.dumps(f, ensure_ascii=False) + "\n"); deja.add(f["image"]); n += 1
print("fiches ajoutees :", n, "| total :", len(deja))
