"""Hybride v2 : surface EXACTE (faces des traits, faces.py) quand elle est plausible, sinon methode pixels (v1h).
Regle de choix fixee AVANT la mesure (journal 25/11) -- elle n'utilise JAMAIS la surface ecrite :
  - la face qui contient l'etiquette fait entre 0,5 et 400 m2 ;
  - elle ne contient qu'UNE etiquette (deux = pieces fusionnees).
Epaisseur de stylo des murs choisie par plan : celle qui donne le plus de faces plausibles (sans surface ecrite).
Usage : python hybride.py [dossier_pixels=v1h]"""
import glob, json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
from faces import pieces_par_faces

SEUILS = [0.13, 0.25, 0.35, 0.45, 0.6]
pix = sys.argv[1] if len(sys.argv) > 1 else "v1h"


def plausibles(res):
    """res = [(etiquette, surface_face, face)] -> dict index -> surface si la face est plausible"""
    ok = {}
    for i, (e, a, f) in enumerate(res):
        if a is None or not (0.5 <= a <= 400): continue
        n_etq = sum(1 for e2, a2, f2 in res if f2 is not None and f2.equals(f))
        if n_etq == 1: ok[i] = a
    return ok


def ecart(a, e):
    return None if a is None or not e["surface_ecrite"] else 100 * (a / e["surface_ecrite"] - 1)


tot = {"faces": [0, 0], "pixels": [0, 0], "hybride": [0, 0], "n": 0}
lignes = []
for f in sorted(glob.glob(os.path.join(ici, "plans_test", "*.pdf"))):
    t = time.time()
    nom = os.path.splitext(os.path.basename(f))[0]
    v1 = json.load(open(os.path.join(ici, "sorties", pix, nom + "_metre.json"), encoding="utf-8"))["pieces"]
    meilleur = None
    for s in SEUILS:
        try:
            res = pieces_par_faces(f, s, verbeux=False, avec_remplis=False, rendre_faces=True)
        except Exception as ex:
            print("  erreur seuil", s, ex); continue
        ok = plausibles(res)
        if meilleur is None or len(ok) > len(meilleur[2]): meilleur = (s, res, ok)
    s, res, ok = meilleur
    c = {"faces": [0, 0], "pixels": [0, 0], "hybride": [0, 0]}
    choix_faces = 0
    for i, (e, a, fa) in enumerate(res):
        # la meme etiquette cote pixels (meme surface ecrite, meme position a 1 pt pres)
        p = next((q for q in v1 if q["surface_ecrite"] == e["surface_ecrite"] and abs(q["x"] - e["x"]) < 1 and abs(q["y"] - e["y"]) < 1), None)
        ep = p.get("ecart_pct") if p else None
        ef = ecart(ok.get(i), e)
        eh = ef if i in ok else ep
        choix_faces += i in ok
        for k, v in (("faces", ef), ("pixels", ep), ("hybride", eh)):
            if v is not None and abs(v) <= 3: c[k][0] += 1
            if v is not None and abs(v) <= 10: c[k][1] += 1
    n = len(res)
    for k in c: tot[k][0] += c[k][0]; tot[k][1] += c[k][1]
    tot["n"] += n
    l = {"plan": nom[:50], "pieces": n, "seuil": s, "faces_choisies": choix_faces, **{k: c[k] for k in c}, "secondes": round(time.time() - t)}
    lignes.append(l)
    print("%-50s %3d pieces | stylo %.2f | faces prises %3d | a 3%% : pixels %3d  hybride %3d | a 10%% : pixels %3d  hybride %3d | %d s" % (
        l["plan"], n, s, choix_faces, c["pixels"][0], c["hybride"][0], c["pixels"][1], c["hybride"][1], l["secondes"]), flush=True)
print("\nTOTAL %d pieces | a 3 %% : faces seules %d, pixels %d, HYBRIDE %d | a 10 %% : faces %d, pixels %d, HYBRIDE %d" % (
    tot["n"], tot["faces"][0], tot["pixels"][0], tot["hybride"][0], tot["faces"][1], tot["pixels"][1], tot["hybride"][1]))
os.makedirs(os.path.join(ici, "sorties", "v2_hybride"), exist_ok=True)
json.dump(lignes, open(os.path.join(ici, "sorties", "v2_hybride", "hybride.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
