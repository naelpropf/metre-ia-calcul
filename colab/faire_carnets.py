"""Fabrique un carnet Colab par entrainement (28/11, specialistes en meme temps sur plusieurs comptes).
  python colab/faire_carnets.py
Chaque carnet s'ouvre par https://colab.research.google.com/github/naelpropf/metre-ia-calcul/blob/main/colab/<nom>.ipynb
(processeur graphique T4 deja choisi) ; « Executer tout » suffit. Journal : /content/run.log ; sortie : /content/sortie_<nom>."""
import json, os

ICI = os.path.dirname(os.path.abspath(__file__))
LOTS = ["20261128-0048-d38d25f", "20261128-0205-791d21d", "20261128-1329-a1717dc", "20261128-1505-890df2d"]   # 28/11 apres-midi : +18 dossiers neufs (32 en tout)
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
    "specialiste_tri_visuel_x3": ("tri_visuel", 600, None, "EXAMEN_APPR=1 TIRAGES=3"),   # 3 tirages de traits par fiche
    "tri_visuel_4b_large": ("tri_visuel", 300, "unsloth/Qwen3-VL-4B-Instruct-unsloth-bnb-4bit", "EXAMEN_APPR=1"),   # 28/11 : 32 dossiers (contre 14), memes reglages
    "tri_visuel_4b_large600": ("tri_visuel", 600, "unsloth/Qwen3-VL-4B-Instruct-unsloth-bnb-4bit", "EXAMEN_APPR=1"),   # idem, 600 pas (~ autant de passages par fiche qu'avant)
    "tri_visuel_4b_cadre": ("tri_visuel", 300, "unsloth/Qwen3-VL-4B-Instruct-unsloth-bnb-4bit", "EXAMEN_APPR=1 DESSIN=cadre"),   # 28/11 soir : traits ENCADRES (plus caches)
    "tri_visuel_4b_cadre600": ("tri_visuel", 600, "unsloth/Qwen3-VL-4B-Instruct-unsloth-bnb-4bit", "EXAMEN_APPR=1 DESSIN=cadre"),
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


# 28/11 : Colab bloque donne parfois une machine SANS GPU (« nvidia-smi: command not found ») -> on arrete tout de suite
VERIF = ("import shutil, subprocess\n"
         "assert shutil.which('nvidia-smi') and subprocess.run(['nvidia-smi', '-L']).returncode == 0, "
         "'PAS DE GPU : Colab a donne une machine sans GPU (limites d utilisation) -> rien n est lance'")


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
                    cellule(VERIF), cellule(PREP), cellule(lance)]}
    nb["cells"][0]["cell_type"] = "markdown"; del nb["cells"][0]["execution_count"]; del nb["cells"][0]["outputs"]
    json.dump(nb, open(os.path.join(ICI, nom + ".ipynb"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    # 28/11 : meme carnet pour KAGGLE (1 seul compte, 30 h de GPU par semaine) : une seule carte (unsloth n'en veut
    # qu'une, Kaggle en donne 2 x T4), dossier /content cree ; a importer par File > Import Notebook > GitHub
    kg = json.loads(json.dumps(nb))
    kg["metadata"] = {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                      "language_info": {"name": "python"},
                      "kaggle": {"accelerator": "nvidiaTeslaT4", "isInternetEnabled": True, "isGpuEnabled": True}}
    kg["cells"].insert(1, cellule("import os\nos.environ['CUDA_VISIBLE_DEVICES'] = '0'   # une seule carte\n"
                                  "os.makedirs('/content', exist_ok=True)"))
    json.dump(kg, open(os.path.join(ICI, "kaggle_" + nom + ".ipynb"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("ecrit", nom + ".ipynb")


# 28/11 : KAGGLE DOUBLE = deux entrainements en meme temps dans UNE seance (une carte T4 chacun ; Kaggle compte le
# temps de seance, pas le nombre de cartes -> deux fois plus de travail pour les memes 30 h). Journal entrelace,
# chaque ligne prefixee [nom]. Paires : # 28/11 soir : sous Kaggle, seul /kaggle/working est garde a la fin -> on y copie les sorties (examen, bilan)
GARDER = "!cp -r /content/sortie_* /content/run.log /kaggle/working/ 2>/dev/null; ls -R /kaggle/working | head -30"
DOUBLES = {nom_du_carnet: (run_carte_0, run_carte_1)} (noms de RUNS).
DOUBLES = {"double_4b_large": ("tri_visuel_4b_large", "tri_visuel_4b_large600"),
           "double_4b_cadre": ("tri_visuel_4b_cadre", "tri_visuel_4b_cadre600")}


def commande(nom):
    sujets, pas, *opt = RUNS[nom]
    env = "EXAMEN_SEUL=unsloth/Qwen3-VL-2B-Instruct-unsloth-bnb-4bit " if pas == 0 else ""
    if opt and opt[0]: env += "MODELE=%s " % opt[0]
    if len(opt) > 1: env += opt[1] + " "
    return ("%sSUJETS=%s PAS=%d DOSSIER_EXAMEN=696398 EXAMEN_SUJETS=%s ENTREE=/content SORTIE=/content/sortie_%s "
            "python -u depot/colab/entrainer_qwen3vl.py" % (env, sujets, pas, sujets if (pas == 0 or sujets in ("tout", "tri_visuel")) else TOUS, nom))


for nom, (a, b) in DOUBLES.items():
    lance = ("!cd /content && ( CUDA_VISIBLE_DEVICES=0 %s 2>&1 | sed -u 's/^/[%s] /' & "
             "CUDA_VISIBLE_DEVICES=1 %s 2>&1 | sed -u 's/^/[%s] /' & wait ) | tee /content/run.log"
             % (commande(a), a, commande(b), b))
    nb = {"nbformat": 4, "nbformat_minor": 0,
          "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                       "language_info": {"name": "python"},
                       "kaggle": {"accelerator": "nvidiaTeslaT4", "isInternetEnabled": True, "isGpuEnabled": True}},
          "cells": [cellule("# Metre IA -- DOUBLE (Kaggle, 2 cartes T4) : %s (carte 0) + %s (carte 1). Executer tout." % (a, b)),
                    cellule("import os\nos.makedirs('/content', exist_ok=True)"),
                    cellule(VERIF + "\nimport torch\nassert torch.cuda.device_count() >= 2, 'UNE SEULE CARTE : choisir GPU T4 x2'"),
                    cellule(PREP), cellule(lance), cellule(GARDER)]}
    nb["cells"][0]["cell_type"] = "markdown"; del nb["cells"][0]["execution_count"]; del nb["cells"][0]["outputs"]
    json.dump(nb, open(os.path.join(ICI, "kaggle_" + nom + ".ipynb"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("ecrit kaggle_" + nom + ".ipynb")
