"""BANC DIFFERENTIEL (27/11) -- tester UNE nouvelle variante en 1-3 min au lieu de refaire tout le banc (10-15 min).
Principe : une piece est « sure » des qu'UNE methode tombe a 1 % de l'ecrit ; l'ordre ne change pas le COMPTE.
Donc : total avec la variante = sures deja connues  UNION  pieces que la variante seule rend sures. Aucun plan ne peut perdre.
  python banc_delta.py --complet                       -> refait le banc v3 complet, memorise les sures (sorties/banc_etat.json)
  python banc_delta.py "nom" '{"PARAM": valeur}'       -> fait tourner la SEULE variante matiere(PARAM=valeur) sur le banc
Les plans tournent 2 par 2 (2 coeurs). Ne rien lancer d'autre de lourd en meme temps."""
import glob, json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
BANC = ["3094112", "3081494", "3103962", "3095872", "3102902", "3105572"]
ETAT = os.path.join(ici, "sorties", "banc_etat.json")


def chemin(k):
    return glob.glob(os.path.join(ici, "plans_test", k + "*.pdf"))[0]


def complet(k):
    import metre_v3
    metre_v3.PARALLELE = 1
    R = metre_v3.pieces_v3(chemin(k))
    return k, len(R), [[round(r["e"]["x"], 1), round(r["e"]["y"], 1)] for r in R if r["sure"]], sum(1 for r in R if r["e"].get("coupee_bord"))


def variante(arg):
    k, params = arg
    import metre_v3
    nom, trouves = metre_v3._candidat((chemin(k), "essai", params, None, None, None))
    return k, [[key[0], key[1]] for key, a, h, src in trouves]


if __name__ == "__main__":
    from concurrent.futures import ProcessPoolExecutor
    t0 = time.time()
    if sys.argv[1] == "--complet":
        etat = {}
        with ProcessPoolExecutor(max_workers=int(os.environ.get("BANC_PROC", "2"))) as ex:
            for k, n, sures, cb in ex.map(complet, BANC):
                etat[k] = {"pieces": n, "sures": sures, "coupees_bord": cb}
                print(k, n, "pieces, SURES", len(sures), "| ratees coupees par le bord :", cb, flush=True)
        json.dump(etat, open(ETAT, "w"), indent=0)
        print("TOTAL %d / %d en %d s" % (sum(len(v["sures"]) for v in etat.values()), sum(v["pieces"] for v in etat.values()), time.time() - t0))
    else:
        nom, params = sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        params = {p: (set(tuple(c) for c in v) if isinstance(v, list) else v) for p, v in params.items()}
        etat = json.load(open(ETAT))
        avant = apres = 0
        with ProcessPoolExecutor(max_workers=int(os.environ.get("BANC_PROC", "2"))) as ex:
            for k, trouves in ex.map(variante, [(k, params) for k in BANC]):
                s0 = {tuple(x) for x in etat[k]["sures"]}; s1 = s0 | {tuple(x) for x in trouves}
                avant += len(s0); apres += len(s1)
                print("%s : %d -> %d (+%d)" % (k, len(s0), len(s1), len(s1) - len(s0)), flush=True)
        print("VARIANTE « %s » : %d -> %d (+%d) en %d s" % (nom, avant, apres, apres - avant, time.time() - t0))
