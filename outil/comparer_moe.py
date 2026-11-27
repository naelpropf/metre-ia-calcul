"""Compare le metre COMPLET de l'outil (moteur v3 + quantites) a la quantite de la maitrise d'oeuvre (DPGF peinture).
Usage : python comparer_moe.py plan1.pdf [plan2.pdf ...] --moe-murs 479 [--moe-plafond 28] [--hauteur 2.5]
Somme sur toutes les pages donnees (un lot couvre souvent plusieurs niveaux).
Ce qui est dit en sortie : pieces fermees / total, et la part des etiquettes NON fermees (manque connu)."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
from metre import normaliser, echelle_par_cotes
import matiere, quantites, metre_v3
metre_v3.PARALLELE = 1   # script sans garde __main__ : pas de processus paralleles (ils relanceraient le script)


def arg(nom, defaut=None):
    return float(sys.argv[sys.argv.index(nom) + 1]) if nom in sys.argv else defaut


plans = [a for a in sys.argv[1:] if a.lower().endswith(".pdf")]
moe_m, moe_p, haut = arg("--moe-murs"), arg("--moe-plafond"), arg("--hauteur")
T = {"murs": 0.0, "murs_sures": 0.0, "sol": 0.0, "n": 0, "fermees": 0, "sures": 0, "ecrit_non_fermees": 0.0, "ecrit": 0.0}
for chemin in plans:
    capt = {}
    _p = matiere.portes
    matiere.portes = lambda pl, m_pt, conv: capt.setdefault("cordes", _p(pl, m_pt, conv))
    try:
        R = metre_v3.pieces_v3(chemin)
    finally:
        matiere.portes = _p
    m_pt = echelle_par_cotes(normaliser(chemin), 0)[0]
    murs = matiere.DERNIERS_MURS_REELS[0] if matiere.DERNIERS_MURS_REELS else None
    for r in R:
        e = r["e"]; T["n"] += 1; T["ecrit"] += e.get("surface_ecrite") or 0
        if not r["a"]:
            T["ecrit_non_fermees"] += e.get("surface_ecrite") or 0; continue
        q = quantites.quantites_piece(e, r["a"], r["h"], capt.get("cordes", []), matiere.DERNIERES_VITRES, m_pt, haut, murs=murs)
        T["fermees"] += 1; T["murs"] += q["murs_a_peindre_m2"]; T["sol"] += q["sol_m2"]
        if r["sure"]: T["sures"] += 1; T["murs_sures"] += q["murs_a_peindre_m2"]
    print("%s : %d pieces, %d fermees, %d sures" % (os.path.basename(chemin)[:50], len(R), sum(1 for r in R if r["a"]), sum(r["sure"] for r in R)))
print("\nOUTIL : murs a peindre %.0f m2 (dont pieces sures %.0f) sur %d/%d pieces fermees ; sol/plafond %.0f m2" % (
    T["murs"], T["murs_sures"], T["fermees"], T["n"], T["sol"]))
print("Surface ecrite des pieces NON fermees : %.0f m2 sur %.0f (%.0f %%) -> manque connu" % (
    T["ecrit_non_fermees"], T["ecrit"], 100 * T["ecrit_non_fermees"] / max(T["ecrit"], 1)))
if moe_m: print("MOE   : murs %.0f m2 -> ecart outil %+.0f %%" % (moe_m, 100 * (T["murs"] / moe_m - 1)))
if moe_p: print("MOE   : plafond peint %.0f m2 (l'outil donne la surface de plafond TOTALE : faux plafonds non deduits)" % moe_p)
