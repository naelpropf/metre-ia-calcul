"""BOUCLE DE CORRECTION (facon Togal) -- les decisions de l'operateur deviennent des exemples d'entrainement.
Entree : corrections/*.json, exportes par l'ecran v2 (bouton « Exemples IA ») : contours VALIDES (automatiques
confirmes) et CORRIGES (traces a la main). Chaque contour confirme par un humain = une piece sure, sans arbitre ecrit.
Sortie : sorties/objets_corr/<plan>.jsonl.gz (meme format que objets.py ; tri.py les prend en apprentissage).
Usage : python corrections_vers_exemples.py [dossier_essai]"""
import glob, json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
from shapely.geometry import Polygon
import objets

ESSAI = len(sys.argv) > 1          # un dossier en argument = essai : sortie separee, jamais melangee aux vrais exemples
fichiers = sorted(glob.glob(os.path.join(sys.argv[1] if ESSAI else os.path.join(ici, "corrections"), "*.json")))
if not fichiers: print("aucun fichier dans corrections/ (exporter depuis l'ecran v2, bouton « Exemples IA »)")
par_plan = {}
for f in fichiers:
    d = json.load(open(f, encoding="utf-8"))
    k = d["k"]
    for ex in d["exemples"]:
        c = ex.get("contour_px")
        if ex["etat"] not in ("valide", "corrigee") or not c or len(c) < 3: continue
        P = Polygon([(x / k, y / k) for x, y in c]).buffer(0)       # image -> coordonnees de travail du PDF
        if P.is_empty: continue
        # plusieurs exports du meme plan : le DERNIER contour d'une piece l'emporte
        par_plan.setdefault(d["chemin"], {})[ex["nom"] + "#" + str(ex["id"])] = (P, "main" if ex["etat"] == "corrigee" else "valide")
for chemin, pieces in par_plan.items():
    if not os.path.exists(chemin): print("plan introuvable :", chemin); continue
    r = objets.traiter(chemin, sures_donnees=list(pieces.values()), sortie="objets_corr_essai" if ESSAI else "objets_corr")
    if r:
        nom, n, n1, n0, _ = r
        print("%-55s %d contours confirmes (%d traces) -> objets %d | limite %d | pas limite %d" % (
            nom[:55], len(pieces), sum(1 for _, s in pieces.values() if s == "main"), n, n1, n0))
