"""TEST 2 de la declaration « Langue des plans » (ecrit avant) : l'IA apprise sur FloorPlanCAD lit-elle NOS plans ?
  a) 6 pages du banc, contre nos etiquettes les plus sures (base sorties/objets) :
     - mur = objet au bord d'une piece juste (etiquette 1) et classe « mur » -> rappel « mur » >= 80 % ;
     - porte = arc de porte reconnu (classe « porte ») -> rappel « porte » >= 70 %.
  b) cas tranches a l'oeil (page « Traits a trancher ») : reponses du porteur d'abord, sinon celles de Claude « sur / plutot sur » ;
     l'IA « langue » doit faire mieux que notre IA actuelle (son 1er choix, enregistre dans les cas).
Les objets de nos bases suivent l'ordre lines + rects + curves en sautant ceux de moins de 2 points (comme ici)."""
import glob, gzip, json, os, sys, pickle
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
import langue_plans as LP

M = pickle.load(open(os.path.join(ici, "sorties", os.environ.get("MODELE", "langue_plans.pkl")), "rb"))
BANC = ["3094112", "3081494", "3103962", "3095872", "3102902", "3105572"]
tm = tp = nm = np_ = 0
preds = {}
for k in BANC:
    fs = glob.glob(os.path.join(ici, "plans_test", k + "*.pdf"))
    if not fs: print(k, "pas de PDF"); continue
    f = fs[0]
    cls, P = LP.lire_pdf(f, M)
    preds[k] = cls
    fo = glob.glob(os.path.join(ici, "sorties", os.environ.get("REF", "objets"), k + "*.jsonl.gz"))
    if not fo: print(k, "pas de base d'etiquettes"); continue
    L = [json.loads(l) for l in gzip.open(fo[0], "rt", encoding="utf-8")]
    if len(L) != len(cls): print(k, "ALIGNEMENT impossible", len(L), len(cls)); continue
    im = [i for i, x in enumerate(L) if x.get("etiquette") == 1 and x.get("classe") == "mur"]
    ip = [i for i, x in enumerate(L) if x.get("classe") == "porte"]
    hm = sum(cls[i] == "mur" for i in im); hp = sum(cls[i] == "porte" for i in ip)
    tm += hm; nm += len(im); tp += hp; np_ += len(ip)
    from collections import Counter
    print("%s : mur %d/%d | porte %d/%d | murs vus comme %s | portes vues comme %s" % (
        k, hm, len(im), hp, len(ip), dict(Counter(cls[i] for i in im).most_common(3)), dict(Counter(cls[i] for i in ip).most_common(3))), flush=True)
rm, rp = tm / max(nm, 1), tp / max(np_, 1)
print("a) rappel mur %.0f %% (seuil 80) | rappel porte %.0f %% (seuil 70) -> %s" % (
    100 * rm, 100 * rp, "REUSSI" if rm >= 0.8 and rp >= 0.7 else "ECHEC"))
# b) cas tranches a l'oeil
cas = json.load(open(sys.argv[1], encoding="utf-8")) if len(sys.argv) > 1 else []
juge = json.load(open(sys.argv[2], encoding="utf-8")) if len(sys.argv) > 2 else {}
VERS = {"mur": "mur", "vitre": "vitre", "porte": "porte", "mobilier": "meuble", "cote": "reste", "hachure": "reste",
        "autre": "autre", "lettre": "reste", "fond": "reste"}
ok_l = ok_a = n = 0
for c in cas:
    v = juge.get(c["id"])
    if not v or v == "?": continue
    attendu = VERS.get(v, v)
    lang = preds.get(c["plan"], [None] * (c["obj"] + 1))[c["obj"]] if c["plan"] in preds else None
    actuelle = VERS.get(c["ia"][0][0], c["ia"][0][0])
    n += 1; ok_l += (lang == attendu) or (attendu in ("autre", "reste") and lang in ("autre", "reste"))
    ok_a += (actuelle == attendu) or (attendu in ("autre", "reste") and actuelle in ("autre", "reste"))
print("b) cas tranches : %d | IA langue %d juste(s) | IA actuelle %d juste(s) -> %s" % (
    n, ok_l, ok_a, "IA langue MIEUX" if ok_l > ok_a else "pas mieux"))
