"""SCORES SECONDAIRES (D-13, 27/11) -- mesure seule, a cote du score principal (pieces sures a 1 %) qui reste LE critere.
  python scores_secondaires.py <dossier_resultats> [<dossier_reference>]
- justes a 3 % et a 10 % : progres de structure (une piece fausse qui devient presque juste) ;
- score principal SANS les etiquettes qui ne sont pas des pieces (regles de etiquettes_non_pieces.py, appliquees a la
  REFERENCE pour les deux examens, afin que la liste ecartee ne bouge pas avec la variante) :
  « total de groupe ? » = la plus grande etiquette d'un contour partage dont l'ecrit depasse de > 50 % la plus petite ;
  « case de tableau ? » = contour de moins de 0,5 m2.
- seuil de chaque score = 2 sigma binomial sur la reference : 2 * racine(N p (1 - p))."""
import glob, json, math, os, sys, collections
sys.stdout.reconfigure(encoding="utf-8")


def charger(d):
    return {json.load(open(p, encoding="utf-8"))["page"]: json.load(open(p, encoding="utf-8"))
            for p in glob.glob(os.path.join(d, "*.json"))}


def non_pieces(J):
    """indices des etiquettes ecartees sur UNE page (regles de etiquettes_non_pieces.py)"""
    g = collections.defaultdict(list); ex = set()
    for i, x in enumerate(J["detail"]):
        if x.get("trou"): g[tuple(x["trou"])].append(i)
    for idx in g.values():
        if len(idx) < 2: continue
        ecr = sorted((J["detail"][i]["ecrite"] or 0, i) for i in idx)
        if ecr[-1][0] > 1.5 * max(ecr[0][0], 0.01): ex.add(ecr[-1][1])
    for i, x in enumerate(J["detail"]):
        if x["mesuree"] is not None and x["mesuree"] < 0.5: ex.add(i)
    return ex


def cle(x):
    return (x.get("nom"), x.get("ecrite"), round(x.get("x") or 0, 1), round(x.get("y") or 0, 1))


def scores(R, ecart):
    s = collections.Counter()
    for page, J in R.items():
        exclus = ecart.get(page, set())
        for x in J["detail"]:
            e, m = x["ecrite"], x["mesuree"]
            ec = abs(m / e - 1) if (e and m) else None
            mv = x.get("meilleur_ecart_variantes")   # meilleur ecart d'une variante (< 10 %), releve D-13
            if mv is not None: ec = mv if ec is None else min(ec, mv)
            s["N"] += 1; s["sures"] += bool(x["sure"])
            s["3 %"] += ec is not None and ec <= 0.03; s["10 %"] += ec is not None and ec <= 0.10
            if cle(x) not in exclus:
                s["N hors non-pieces"] += 1; s["sures hors non-pieces"] += bool(x["sure"])
    return s


def ecartees(REF):
    return {p: {cle(J["detail"][i]) for i in non_pieces(J)} for p, J in REF.items()}


if __name__ == "__main__":
    A = charger(sys.argv[1]); REF = charger(sys.argv[2]) if len(sys.argv) > 2 else A
    ec = ecartees(REF); sa = scores(A, ec); sr = scores(REF, ec)
    print("pages %d | etiquettes ecartees (non-pieces, fixees sur la reference) : %d" % (len(A), sum(len(v) for v in ec.values())))
    for k, n in (("sures", "N"), ("3 %", "N"), ("10 %", "N"), ("sures hors non-pieces", "N hors non-pieces")):
        p = sr[k] / max(sr[n], 1); seuil = 2 * math.sqrt(sr[n] * p * (1 - p))
        ligne = "%-24s %4d / %4d (%4.1f %%)" % (k, sa[k], sa[n], 100 * sa[k] / max(sa[n], 1))
        if len(sys.argv) > 2:
            ligne += " | reference %4d | ecart %+4d | seuil 2 sigma +%.0f" % (sr[k], sa[k] - sr[k], seuil)
        else:
            ligne += " | seuil 2 sigma +%.0f" % seuil
        print(ligne)
