"""Pieces « presque justes » (1-10 % d'ecart) : ecart FIXE le long des murs (H1) ou ECHELLE un peu fausse (H2) ? (27/11)
REGLE ECRITE AVANT : H1 tient si d = (ecrit - mesure) / perimetre a un coefficient de variation < 30 % ;
                     H2 tient si le rapport ecrit / mesure a un coefficient de variation < 2 %. Sinon : cause piece par piece.
  python ecart_presque.py <debut de nom de page> [...]"""
import glob, os, sys
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
import metre_v3, matiere
metre_v3.PARALLELE = 1
for deb in sys.argv[1:]:
    f = glob.glob(os.path.join(ici, "plans_neufs", glob.escape(deb) + "*.pdf"))[0]
    old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
    R = metre_v3.pieces_v3(f)
    sys.stdout.close(); sys.stdout = old
    m = matiere.DERNIERE_MATIERE[1]
    D, Q = [], []
    for r in R:
        if not r.get("a") or r.get("h") is None: continue
        e = r["e"]["surface_ecrite"]; q = e / r["a"]
        if 0.01 < abs(q - 1) <= 0.10:
            P = r["h"].length * m
            D.append((e - r["a"]) / P); Q.append(q)
    D, Q = np.array(D), np.array(Q)
    if len(D) < 5: print("%s : %d pieces presque justes, trop peu" % (deb, len(D))); continue
    cv_d = np.std(D) / abs(np.mean(D)); cv_q = np.std(Q) / np.mean(Q)
    print("%-28s n=%3d | d = (ecrit-mesure)/perimetre : mediane %+.3f m, CV %.0f %% -> H1 %s | rapport ecrit/mesure : mediane %.3f, CV %.1f %% -> H2 %s" % (
        deb[:28], len(D), np.median(D), 100 * cv_d, "TIENT" if cv_d < 0.30 else "non", np.median(Q), 100 * cv_q, "TIENT" if cv_q < 0.02 else "non"))
    print("    d par piece (cm) :", " ".join("%+.0f" % (100 * x) for x in sorted(D)))
