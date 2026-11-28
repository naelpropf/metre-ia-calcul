"""Fabrique un carnet Colab par entrainement (28/11, specialistes en meme temps sur plusieurs comptes).
  python colab/faire_carnets.py
Chaque carnet s'ouvre par https://colab.research.google.com/github/naelpropf/metre-ia-calcul/blob/main/colab/<nom>.ipynb
(processeur graphique T4 deja choisi) ; « Executer tout » suffit. Journal : /content/run.log ; sortie : /content/sortie_<nom>."""
import json, os

ICI = os.path.dirname(os.path.abspath(__file__))
LOTS = ["20261128-0048-d38d25f", "20261128-0205-791d21d"]
TOUS = "etiquette,murs,tri,contour"
RUNS = {  # nom : (SUJETS, PAS)
    "specialiste_etiquette": ("etiquette", 300),
    "specialiste_murs": ("murs", 300),
    "specialiste_tri": ("tri", 300),
    "specialiste_contour": ("contour", 300),
    "melange_4_sujets": (TOUS, 1200),
    "base_etiquette": ("etiquette", 0),
    "tout_v3": ("tout", 300),
    "specialiste_tri_visuel": ("tri_visuel", 300),   # 28/11 : traits dessines et numerotes, l'IA dit MUR / OBJET / COTE
    "base_tri_visuel": ("tri_visuel", 0),
    "specialiste_tri_visuel_v2": ("tri_visuel", 300, None, "EXAMEN_APPR=1"),   # chiffres lisibles (26 px) + couleurs nommees
    "specialiste_tri_visuel_4b": ("tri_visuel", 300, "unsloth/Qwen3-VL-4B-Instruct-unsloth-bnb-4bit", "EXAMEN_APPR=1"),   # l'ancien exercice entier (plan + contour), relance de la v3 coupee a 03 h 28   # PAS=0 : modele de BASE sans entrainement (EXAMEN_SEUL)
}
PREP = "\n".join([
    "!nvidia-smi -L",
    "!rm -rf /content/depot && git clone -q --depth 1 --filter=blob:none --sparse https://github.com/naelpropf/metre-ia-calcul /content/depot",
    "!cd /content/depot && git sparse-checkout set colab fiches " + " ".join("fiches_resultats/" + l for l in LOTS),
    "!rm -rf /content/fiches && mkdir -p /content/fiches && cp /content/depot/fiches_resultats/%s/exercices.jsonl /content/fiches/ && cp -r /content/depot/fiches_resultats/%s/img /content/fiches/" % (LOTS[0], LOTS[0]),
] + ["!python /content/depot/fiches/fusionner_colab.py /content/depot/fiches_resultats/%s /content/fiches" % l for l in LOTS[1:]] + [
    "!pip install -q unsloth",
])


def cellule(src):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src.splitlines(True)}


for nom, (sujets, pas, *opt) in RUNS.items():
    modele = [opt[0]] if opt and opt[0] else []
    seul = "EXAMEN_SEUL=unsloth/Qwen3-VL-2B-Instruct-unsloth-bnb-4bit " if pas == 0 else ""
    if modele: seul += "MODELE=%s " % modele[0]
    if len(opt) > 1: seul += opt[1] + " "
    lance = ("!cd /content && %sSUJETS=%s PAS=%d DOSSIER_EXAMEN=696398 EXAMEN_SUJETS=%s ENTREE=/content SORTIE=/content/sortie_%s "
             "python depot/colab/entrainer_qwen3vl.py 2>&1 | tee /content/run.log" % (seul, sujets, pas, sujets if (pas == 0 or sujets in ("tout", "tri_visuel")) else TOUS, nom))
    nb = {"nbformat": 4, "nbformat_minor": 0,
          "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "T4"},
                       "kernelspec": {"name": "python3", "display_name": "Python 3"}, "language_info": {"name": "python"}},
          "cells": [cellule("# Metre IA -- %s (SUJETS=%s, %d pas). Executer tout." % (nom, sujets, pas)),
                    cellule(PREP), cellule(lance)]}
    nb["cells"][0]["cell_type"] = "markdown"; del nb["cells"][0]["execution_count"]; del nb["cells"][0]["outputs"]
    json.dump(nb, open(os.path.join(ICI, nom + ".ipynb"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("ecrit", nom + ".ipynb")
