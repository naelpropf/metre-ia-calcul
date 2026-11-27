"""Quantites peinture PAR PIECE, a partir du contour exact (methode matiere) -- ce que le client paie :
  sol / plafond (m2), perimetre (ml), portes et fenetres qui touchent la piece (U + largeur), plinthes (ml),
  murs bruts et murs a peindre (m2) = perimetre x hauteur - ouvertures deduites.
Regles (Methode du metre peinture, coffre) -- le CCTP du marche PRIME toujours :
  - hauteur sous plafond : donnee (coupes / CCTP / client) ; sinon 2,50 m SIGNALEE comme hypothese ;
  - porte : hauteur 2,04 m par defaut ; fenetre : hauteur INCONNUE sans tableau des menuiseries -> 1,35 m SIGNALEE ;
  - on deduit les ouvertures > 0,5 m2 (convention courante, A VERIFIER contre le CCTP) ;
  - plinthes = perimetre - largeurs des portes.
Usage : python quantites.py plan.pdf [hauteur]"""
import math, sys
sys.stdout.reconfigure(encoding="utf-8")
from shapely.geometry import LineString

H_PORTE, H_FENETRE, SEUIL_DEDUCTION = 2.04, 1.35, 0.5


def ouvertures_de(h, cordes, vitres, m_pt, tol=0.08, murs=None):
    """portes = cordes de porte (gond -> gache) le long du contour ; fenetres = groupes de vitres le long du contour.
    Retourne [(type, largeur_m)]."""
    bord = h.exterior.buffer(tol / m_pt)
    out = []
    vues = []
    for c in cordes:
        if c.length * m_pt < 0.55: continue
        if bord.contains(c.interpolate(0.5, normalized=True)) and bord.intersection(c).length >= 0.6 * c.length:
            if any(c.distance(v) * m_pt < 0.1 for v in vues): continue   # les deux cordes d'une meme porte
            # la corde a ete prolongee de 5 cm de chaque cote (matiere.portes) : on les retire
            vues.append(c); out.append(("porte", round(c.length * m_pt - 0.10, 2)))
    # une fenetre = un GROUPE de vitres paralleles serrees (cadre + vitrage) ; largeur = la plus longue du groupe
    groupes = []
    for v in vitres:
        if v.length * m_pt < 0.4 or not bord.contains(v.interpolate(0.5, normalized=True)): continue
        # une VRAIE vitre est dans un TROU du mur ; un trait qui longe un mur (contour de piece) est SUR le mur
        if murs is not None and v.intersection(murs.buffer(0.01 / m_pt)).length > 0.5 * v.length: continue
        g = next((g for g in groupes if any(v.distance(w) * m_pt < 0.25 for w in g)), None)
        if g is None: groupes.append([v])
        else: g.append(v)
    for g in groupes:
        # largeur = ETENDUE du groupe le long de sa direction (une fenetre a 2 vantaux = 2 vitres bout a bout)
        w0 = max(g, key=lambda w: w.length); (x1, y1), (x2, y2) = w0.coords[0], w0.coords[-1]
        L = math.hypot(x2 - x1, y2 - y1); ux, uy = (x2 - x1) / L, (y2 - y1) / L
        proj = [(px - x1) * ux + (py - y1) * uy for w in g for px, py in (w.coords[0], w.coords[-1])]
        out.append(("fenetre", round((max(proj) - min(proj)) * m_pt, 2)))
    return out


def hauteur_menuiserie(largeur, menuiseries, defaut, portes=False):
    """CASSURE 1 (27/11) : hauteur lue dans la NOMENCLATURE du dossier -- le type dont la largeur colle a 10 cm pres.
    Rend (hauteur, type ou None). Portes : types de hauteur >= 1,90 m ; fenetres : tous les types."""
    # 27/11 : la detection des FENETRES sort des largeurs peu fiables -> une fenetre n'est reliee qu'a un type qui n'est
    # PAS une porte (code en P) et a 5 cm pres ; sinon elle garde la hauteur SUPPOSEE (mieux qu'une fausse precision)
    if portes:
        cand = [(abs(L - largeur), ty, H) for ty, L, H, *_ in (menuiseries or []) if abs(L - largeur) <= 0.10 and (H >= 1.9 or ty.upper().startswith("P"))]
    else:
        cand = [(abs(L - largeur), ty, H) for ty, L, H, *_ in (menuiseries or []) if abs(L - largeur) <= 0.05 and not ty.upper().startswith("P")]
    if not cand: return defaut, None
    _, ty, H = min(cand)
    return H, ty


def quantites_piece(e, a, h, cordes, vitres, m_pt, hauteur=None, murs=None, hauteur_note=None, menuiseries=None):
    hyp = []
    if hauteur is None: hauteur = 2.50; hyp.append("hauteur 2,50 m supposée")
    elif hauteur_note: hyp.append(hauteur_note)   # hauteur lue dans le DOSSIER (coupes) : source dite (27/11)
    per = h.exterior.length * m_pt
    ouv = ouvertures_de(h, cordes, vitres, m_pt, murs=murs)
    portes = [l for t, l in ouv if t == "porte"]; fen = [l for t, l in ouv if t == "fenetre"]
    hp = [hauteur_menuiserie(l, menuiseries, H_PORTE, portes=True) for l in portes]
    hf = [hauteur_menuiserie(l, menuiseries, H_FENETRE) for l in fen]
    lues = ["%s %.2f×%.2f" % (ty, l, H) for (H, ty), l in zip(hp + hf, portes + fen) if ty]
    if lues: hyp.append(("hauteurs lues dans la nomenclature des menuiseries : " + ", ".join(lues)).replace(".", ","))
    if any(ty is None for _, ty in hf):
        hyp.append("fenêtres à vérifier (reconnues par règles, pas encore par l’IA) ; hauteur %.2f m supposée" % H_FENETRE)
    deduc = sum(l * H for l, (H, _) in zip(portes, hp) if l * H > SEUIL_DEDUCTION) + \
            sum(l * H for l, (H, _) in zip(fen, hf) if l * H > SEUIL_DEDUCTION)
    brut = per * hauteur
    return {"piece": e.get("nom"), "sol_m2": round(a, 2), "plafond_m2": round(a, 2), "perimetre_ml": round(per, 2),
            "portes_U": len(portes), "portes_larg_m": portes, "fenetres_U": len(fen), "fenetres_larg_m": fen,
            "plinthes_ml": round(max(per - sum(portes), 0), 2), "murs_bruts_m2": round(brut, 2),
            "ouvertures_deduites_m2": round(deduc, 2), "murs_a_peindre_m2": round(brut - deduc, 2),
            "hauteur_m": hauteur, "hypotheses": hyp, "doutes": e.get("doutes", [])}


if __name__ == "__main__":
    import glob
    import matiere
    capt = {}
    _portes = matiere.portes
    def espion(pl, m_pt, conv):
        r = _portes(pl, m_pt, conv); capt["cordes"] = r; return r
    matiere.portes = espion
    # les vitres retenues : on les recupere a la construction de la matiere
    from shapely.geometry import LineString as _LS
    res = matiere.pieces_par_matiere(sys.argv[1], verbeux=False, rendre=True)
    from metre import normaliser, echelle_par_cotes
    m_pt = echelle_par_cotes(normaliser(sys.argv[1]), 0)[0]
    vitres = capt.get("vitres", [])
    haut = float(sys.argv[2]) if len(sys.argv) > 2 else None
    for e, a, h in res:
        if not a: continue
        q = quantites_piece(e, a, h, capt["cordes"], matiere.DERNIERES_VITRES, m_pt, haut,
                            murs=matiere.DERNIERS_MURS_REELS[0] if matiere.DERNIERS_MURS_REELS else None)
        print("%-16s sol %6.2f | per %5.2f | portes %d %s | fen %d %s | plinthes %5.2f | murs a peindre %6.2f | %s" % (
            (q["piece"] or "")[:16], q["sol_m2"], q["perimetre_ml"], q["portes_U"], q["portes_larg_m"], q["fenetres_U"],
            q["fenetres_larg_m"], q["plinthes_ml"], q["murs_a_peindre_m2"], "; ".join(q["hypotheses"] + q["doutes"])))
