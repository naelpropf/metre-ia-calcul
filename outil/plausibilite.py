"""Plausibilite des pieces (declaration au coffre, 27/11) : une surface invraisemblable pour le NOM de la piece = doute.
Bornes tirees du livre des pieces (Swiss Dwellings, CC BY 4.0) : [centile 1 / 1,5 ; centile 99 x 1,5].
  python plausibilite.py --test     (sur sorties/neufs_v3/*.json : fausses alarmes sur l'ecrit, utilite sur le mesure)"""
import glob, gzip, json, os, re, sys, unicodedata
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
TYPES = [  # (mots-cles du nom, types du livre) -- fixe dans la declaration
    (("wc", "sanitaire", "douche"), ("BATHROOM",)),
    (("circulation", "degagement", "couloir", "hall"), ("CORRIDOR",)),
    (("bureau",), ("OFFICE", "ROOM")),
    (("cuisine", "office"), ("KITCHEN",)),
    (("rangement", "local menage", "reserve", "stockage"), ("STOREROOM",)),
    (("escalier",), ("STAIRCASE",)),
    (("ascenseur",), ("ELEVATOR",)),
    (("chambre",), ("BEDROOM",)),
    (("sejour",), ("LIVING_ROOM", "LIVING_DINING")),
]
_BORNES = None


def sans_accent(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def bornes():
    global _BORNES
    if _BORNES is None:
        cache = os.path.join(ici, "sorties", "livre_bornes.json")
        if os.path.exists(cache):
            _BORNES = json.load(open(cache))
        else:
            S = {}
            for l in gzip.open(os.path.join(ici, "sorties", "livre_des_pieces.jsonl.gz"), "rt", encoding="utf-8"):
                x = json.loads(l); S.setdefault(x["type"], []).append(x["surface"])
            _BORNES = {t: [float(np.quantile(v, .01)) / 1.5, float(np.quantile(v, .99)) * 1.5] for t, v in S.items() if len(v) >= 50}
            json.dump(_BORNES, open(cache, "w"))
    return _BORNES


def type_de(nom):
    n = " " + re.sub(r"[^a-z0-9 ]", " ", sans_accent(nom or "")) + " "
    for mots, types in TYPES:
        if any(re.search(r"\b" + re.escape(m) + r"\b", n) for m in mots): return types
    return None


def invraisemblable(nom, surface):
    """None = pas juge ; sinon (bool, intervalle)"""
    t = type_de(nom)
    if not t or not surface: return None
    B = bornes(); iv = [B[x] for x in t if x in B]
    if not iv: return None
    lo, hi = min(a for a, _ in iv), max(b for _, b in iv)
    return (not (lo <= surface <= hi)), (round(lo, 1), round(hi, 1))


if __name__ == "__main__" and "--test" in sys.argv:
    P = [p for f in sorted(glob.glob(os.path.join(ici, "sorties", "neufs_v3", "*.json")))
         for p in json.load(open(f, encoding="utf-8")).get("detail", [])]
    jug = [p for p in P if invraisemblable(p["nom"], p["ecrite"]) is not None]
    fa = sum(invraisemblable(p["nom"], p["ecrite"])[0] for p in jug)
    print("pieces : %d | jugees (type reconnu, surface ecrite) : %d" % (len(P), len(jug)))
    print("1) fausses alarmes sur l'ECRIT : %d / %d = %.1f %% (seuil <= 5 %%) -> %s" % (
        fa, len(jug), 100 * fa / max(len(jug), 1), "OK" if fa <= 0.05 * len(jug) else "REJETE"))
    mes = [p for p in jug if p["mesuree"]]
    juste = [p for p in mes if abs(p["mesuree"] / p["ecrite"] - 1) <= 0.01]
    faux = [p for p in mes if abs(p["mesuree"] / p["ecrite"] - 1) > 0.01]
    rj = np.mean([invraisemblable(p["nom"], p["mesuree"])[0] for p in juste]) if juste else 0
    rf = np.mean([invraisemblable(p["nom"], p["mesuree"])[0] for p in faux]) if faux else 0
    print("2) signalees : justes %.1f %% (%d) | fausses %.1f %% (%d) | rapport %.1f (seuil >= 3) -> %s" % (
        100 * rj, len(juste), 100 * rf, len(faux), rf / rj if rj else float("inf"), "OK" if rf >= 3 * max(rj, 1e-9) else "REJETE"))
