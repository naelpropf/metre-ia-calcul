"""Test 3 de la declaration « Test IA dossiers neufs » (ecrite le 26/11, avant la recolte) : l'outil v3 sur les pages NEUVES.
Mesure : part des pieces « sures » (< 1 % de la surface ecrite), comparee au banc (125/224 = 56 %).
Si les neufs sont a plus de 15 points sous le banc -> on a sur-appris le banc.
  python un_par_un.py test_neufs.py plans_neufs      (une page par programme : memoire rendue a chaque page)
  python test_neufs.py --bilan
Rien n'est regle ici : on mesure seulement."""
import glob, json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
SORTIE = os.path.join(ici, "sorties", "neufs_v3"); os.makedirs(SORTIE, exist_ok=True)
BANC = 125 / 224

if sys.argv[1] == "--page":
    f = sys.argv[2]
    nom = os.path.splitext(os.path.basename(f))[0][:80]
    js = os.path.join(SORTIE, nom + ".json")
    if os.path.exists(js): print("%-60s deja fait" % nom[:60]); sys.exit(0)
    t = time.time()
    import metre_v3
    metre_v3.PARALLELE = int(os.environ.get("PARALLELE_PAGE", "1"))   # 27/11 : pages longues -> variantes en parallele
    old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
    try:
        R = metre_v3.pieces_v3(f)
    finally:
        sys.stdout.close(); sys.stdout = old
    duree = round(time.time() - t)   # duree du METRE seul (le diagnostic ci-dessous n'est pas compte)
    n, s = len(R), sum(1 for r in R if r["sure"])
    cb = sum(1 for r in R if r["e"].get("coupee_bord"))
    # 27/11 DIAGNOSTIC (mesure seule, ne change rien au metre) : longueur du contour de chaque piece a moins de 3 cm d'une
    # LIGNE DE COTE reconnue par la lecture de l'echelle (cause vue sur 548666 CAVE 11 : la cote prise pour un mur)
    bord_cote = {}
    try:
        import metre
        from shapely.geometry import LineString
        from shapely.ops import unary_union
        ch = metre.normaliser(f); m = metre.echelle_par_cotes(ch, 0)[0]
        import matiere as _mat   # echelle de secours (etiquettes) : celle du dernier passage de matiere
        m = m or (_mat.DERNIERE_MATIERE[1] if _mat.DERNIERE_MATIERE else None)
        from diag_cotes import lignes_de_cote   # 27/11 : instrument v2 (courbes decoupees ; LIGNES_COTES ratait la CAVE 11)
        cl = lignes_de_cote(ch)
        if m and cl:
            zone = unary_union([LineString([(a, b), (c, d)]) for a, b, c, d in cl]).buffer(0.03 / m)
            for i, r in enumerate(R):
                h = r.get("h")
                if h is not None and hasattr(h, "exterior"):
                    bord_cote[i] = round(h.exterior.intersection(zone).length * m, 2)
    except Exception as ex:
        bord_cote = {"erreur": str(ex)[:80]}
    # 27/11 DIAGNOSTIC 2 : surface de chaque piece dans les SECTEURS DE DEBATTEMENT des portes (diag_portes)
    aire_portes = {}
    try:
        import matiere as _mat2
        from diag_portes import secteurs
        from shapely.ops import unary_union as _uu
        m2 = metre.echelle_par_cotes(metre.normaliser(f), 0)[0] or (_mat2.DERNIERE_MATIERE[1] if _mat2.DERNIERE_MATIERE else None)
        S = secteurs(f, m2) if m2 else []
        if S:
            zs = _uu(S)
            for i, r in enumerate(R):
                h = r.get("h")
                if h is not None and hasattr(h, "exterior"):
                    aire_portes[i] = round(h.intersection(zs).area * m2 * m2, 3)
    except Exception as ex:
        aire_portes = {"erreur": str(ex)[:80]}
    # 27/11 DIAGNOSTIC 3 : longueur du contour posee sur une COURBE non remplie sans cote (arcs, battants de portes)
    # INVALIDE (548666 p02 : 103 pieces sur 104 touchees, des contours de murs sont des courbes) -> desactive
    bord_courbe = {}
    # 27/11 DIAGNOSTIC 4 : poteaux dessines en rectangle a trait fin, colles aux murs (compter_poteaux), matiere de la passe
    # principale refaite ici (DERNIERE_MATIERE vient de la derniere variante)
    # 27/11 DIAGNOSTIC 5 : pourquoi une piece n'est PAS mesuree ? etiquette SUR la matiere (mur, cartouche rempli) ou piece
    # OUVERTE (aucun trou ne la contient). Matiere de la passe PRINCIPALE refaite ici (DERNIERE_MATIERE = derniere variante).
    pourquoi_non = {}
    try:
        if any(not r.get("a") for r in R):
            import matiere as _m5
            from shapely.geometry import Point as _Pt
            _o = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
            try: _m5.pieces_par_matiere(metre.normaliser(f), verbeux=False)
            finally: sys.stdout.close(); sys.stdout = _o
            if _m5.DERNIERE_MATIERE:
                MAT5 = _m5.DERNIERE_MATIERE[0]
                for i, r in enumerate(R):
                    if not r.get("a"):
                        pourquoi_non[i] = "sur la matiere" if MAT5.contains(_Pt(r["e"]["x"], r["e"]["y"])) else "piece ouverte"
    except Exception as ex:
        pourquoi_non = {"erreur": str(ex)[:80]}
    # 27/11 DIAGNOSTIC 6 (mesure de cause, pas une correction) : matiere de la passe principale FERMEE de 0,6 m (epaissir puis
    # amincir, angles droits) -> les ouvertures < 1,2 m se bouchent ; pour chaque piece : seule dans son trou ? surface du trou ?
    ferme = {}
    try:
        import matiere as _m6
        from shapely.geometry import Point as _Pt6, Polygon as _Pg6
        from shapely.strtree import STRtree as _ST6
        if not (_m6.DERNIERE_MATIERE and pourquoi_non):   # la passe principale n'a pas ete refaite par le diagnostic 5
            _o = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
            try: _m6.pieces_par_matiere(metre.normaliser(f), verbeux=False)
            finally: sys.stdout.close(); sys.stdout = _o
        if _m6.DERNIERE_MATIERE:
            MAT6, m6 = _m6.DERNIERE_MATIERE
            r6 = 0.6 / m6
            MATc = MAT6.buffer(r6, join_style=2, mitre_limit=5).buffer(-r6, join_style=2, mitre_limit=5)
            trous = [_Pg6(a) for g in getattr(MATc, "geoms", [MATc]) for a in g.interiors]
            arbre = _ST6(trous) if trous else None
            ou = {}
            for i, r in enumerate(R):
                p = _Pt6(r["e"]["x"], r["e"]["y"])
                cand = [j for j in (arbre.query(p) if arbre is not None else []) if trous[j].contains(p)]
                ou[i] = min(cand, key=lambda j: trous[j].area) if cand else None
            compte = {}
            for j in ou.values():
                if j is not None: compte[j] = compte.get(j, 0) + 1
            for i, j in ou.items():
                ferme[i] = None if j is None else {"seule": compte[j] == 1, "surface": round(trous[j].area * m6 * m6, 2)}

            def _seules(MATx, rr):   # 27/11 : pieces SEULES dans un trou apres fermeture de rr metres
                Mc = MATx.buffer(rr / m6, join_style=2, mitre_limit=5).buffer(-rr / m6, join_style=2, mitre_limit=5)
                T = [_Pg6(a) for g in getattr(Mc, "geoms", [Mc]) for a in g.interiors]
                A = _ST6(T) if T else None
                o2 = {}
                for i, r in enumerate(R):
                    p = _Pt6(r["e"]["x"], r["e"]["y"])
                    t = [j for j in (A.query(p) if A is not None else []) if T[j].contains(p)]
                    o2[i] = min(t, key=lambda j: T[j].area) if t else None
                cpt = {}
                for j in o2.values():
                    if j is not None: cpt[j] = cpt.get(j, 0) + 1
                return {i: (j is not None and cpt[j] == 1) for i, j in o2.items()}
            s10 = _seules(MAT6, 1.0)
            for i in ferme:
                if ferme[i] is not None or s10.get(i): ferme[i] = dict(ferme[i] or {"seule": False}, seule_10=s10.get(i, False))
            # (b) traits fins >= 0,08 ajoutes a la matiere (comme des murs), fermeture 0,6 m ; sautee si > 60 000 traits
            pl6 = metre.page_plumber(metre.normaliser(f))
            # 27/11 : (b) RETIREE de l'examen (3 machines tuees par manque de memoire, code 143) -> sur quelques pages, au PC
            if os.environ.get("DIAG_TRAITS_FINS") and len(pl6.lines) + len(pl6.curves) <= 60000:
                import pypdfium2 as _pd6
                from shapely.geometry import LineString as _Ls6
                from shapely.ops import unary_union as _uu6
                W6, H6, _, _ = metre.lire_textes(metre.normaliser(f), 0); d6 = _pd6.PdfDocument(metre.normaliser(f))
                OX6, OY6 = metre.origine(d6[0]); d6.close(); dy6 = H6 - OY6
                fins = [_Ls6([(p[0] - OX6, p[1] - dy6) for p in o["pts"]]) for o in pl6.lines + pl6.curves
                        if not o.get("fill") and len(o.get("pts") or []) >= 2 and 0.08 <= (o.get("linewidth") or 0) < 0.45]
                if fins:
                    MATf = _uu6([MAT6] + [g.buffer(0.001 / m6, cap_style=2) for g in fins])
                    sf = _seules(MATf, 0.6)
                    for i in ferme:
                        if ferme[i] is not None or sf.get(i): ferme[i] = dict(ferme[i] or {"seule": False}, seule_fins=sf.get(i, False))
    except Exception as ex:
        ferme = {"erreur": str(ex)[:80]}
    # 27/11 DIAGNOSTIC 7 : « mur en trop » (borne basse) -- piece trop petite recuperable en regroupant les trous voisins
    # separes seulement par un trait (mur_en_trop.py ; matiere de la passe principale du diagnostic 6)
    recup = {}
    try:
        if isinstance(ferme, dict) and "erreur" not in ferme and _m6.DERNIERE_MATIERE:
            from mur_en_trop import recuperable
            recup = recuperable(MAT6, m6, [(r["e"]["x"], r["e"]["y"], r["e"].get("surface_ecrite"), r.get("a")) for r in R])
    except Exception as ex:
        recup = {"erreur": str(ex)[:80]}
    # 27/11 DIAGNOSTIC 8 : « renflement de porte » -- surface du contour OUVERT de 0,45 m (retrecir puis regonfler, angles droits)
    ouvert = {}   # INVALIDE (27/11 : rogne aussi des recoins legitimes) -> desactive
    if False:
        m8 =metre.echelle_par_cotes(metre.normaliser(f), 0)[0] or (m6 if isinstance(ferme, dict) and "erreur" not in ferme else None)
        if m8:
            r8 = 0.45 / m8
            for i, r in enumerate(R):
                h = r.get("h")
                if h is not None and hasattr(h, "exterior") and r.get("a"):
                    ouvert[i] = round(h.buffer(-r8, join_style=2, mitre_limit=5).buffer(r8, join_style=2, mitre_limit=5).area * m8 * m8, 3)
    n_poteaux = None   # INVALIDE (27/11 : sur 3068854 les poteaux sont 4 TRAITS separes, pas des rectangles) -> desactive
    if False:
        import matiere as _m4, pypdfium2 as _pdf
        from compter_poteaux import poteaux
        from shapely.geometry import Polygon as _Poly
        ch4 = metre.normaliser(f)
        _o = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
        try: _m4.pieces_par_matiere(ch4, verbeux=False)
        finally: sys.stdout.close(); sys.stdout = _o
        if _m4.DERNIERE_MATIERE:
            MAT4, m4 = _m4.DERNIERE_MATIERE
            W4, H4, _, _ = metre.lire_textes(ch4, 0); d4 = _pdf.PdfDocument(ch4); OX4, OY4 = metre.origine(d4[0]); d4.close()
            n_poteaux = 0
            for P in poteaux(metre.page_plumber(ch4), m4):
                g = _Poly([(p[0] - OX4, p[1] - (H4 - OY4)) for p in P])
                if g.distance(MAT4) * m4 <= 0.05 and not MAT4.contains(g): n_poteaux += 1
    det = [{"nom": r["e"].get("nom", ""), "ecrite": r["e"].get("surface_ecrite"), "mesuree": r.get("a"), "sure": bool(r["sure"]),
            "coupee_bord": bool(r["e"].get("coupee_bord")), "bord_cote_m": bord_cote.get(i) if isinstance(bord_cote, dict) else None,
            "aire_portes_m2": aire_portes.get(i) if isinstance(aire_portes, dict) else None,
            "bord_courbe_m": bord_courbe.get(i) if isinstance(bord_courbe, dict) else None,
            "pourquoi_non_mesuree": pourquoi_non.get(i) if isinstance(pourquoi_non, dict) else None,
            "apres_fermeture": ferme.get(i) if isinstance(ferme, dict) else None,
            # 27/11 : identifiant du CONTOUR (boite arrondie au cm) -> « meme trou » exact (la meme surface ne suffit pas :
            # 548666 a 13 logements identiques et un tableau de cases de meme taille)
            "trou": ([round(v, 1) for v in r["h"].bounds] if r.get("h") is not None and hasattr(r["h"], "bounds") else None),
            # 27/11 soir : le CONTOUR lui-meme (points de la page, simplifie a 0,3 pt) -> on dessine les echecs au PC sans recalcul
            "contour": ([[round(x, 1), round(y, 1)] for x, y in r["h"].simplify(0.3).exterior.coords]
                        if r.get("h") is not None and getattr(r["h"], "geom_type", "") == "Polygon" else None),
            "x": round(r["e"]["x"], 1), "y": round(r["e"]["y"], 1),
            "mur_en_trop_recuperable": recup.get(i) if isinstance(recup, dict) else None,
            "aire_ouverte_045": ouvert.get(i) if isinstance(ouvert, dict) else None,
            # 27/11 D-13 (mesure seule) : quelle passe a donne la surface, et meilleur ecart atteint par une variante (< 10 %)
            "source": r.get("source"), "meilleur_ecart_variantes": r.get("meilleur_ecart"),
            # 27/11 soir (mesure seule) : ecart et contour de CHAQUE variante (< 10 %) -> dessiner une piece perdue sans recalcul
            "variantes": r.get("variantes")}
           for i, r in enumerate(R)]   # detail par piece (pour le livre des pieces, mesure seule)
    json.dump({"page": nom, "pieces": n, "sures": s, "coupees_bord": cb, "secondes": duree, "detail": det,
               "diag_erreur": bord_cote.get("erreur") if isinstance(bord_cote, dict) else None,
               "diag_portes_erreur": aire_portes.get("erreur") if isinstance(aire_portes, dict) else None,
               "poteaux_trait_fin": n_poteaux},
              open(js, "w", encoding="utf-8"), ensure_ascii=False)
    print("%-60s pieces %4d | sures %4d | coupees bord %3d | %d s" % (nom[:60], n, s, cb, time.time() - t), flush=True)

elif sys.argv[1] == "--bilan":
    L = [json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob(os.path.join(SORTIE, "*.json")))]
    N = sum(x["pieces"] for x in L); S = sum(x["sures"] for x in L)
    par_dossier = {}
    for x in L:
        d = par_dossier.setdefault(x["page"].split("_")[0], [0, 0]); d[0] += x["pieces"]; d[1] += x["sures"]
    for k, (n, s) in sorted(par_dossier.items()):
        print("%-10s %4d pieces | %4d sures (%3.0f %%)" % (k, n, s, 100 * s / max(n, 1)))
    part = S / max(N, 1)
    print("TOTAL %d pages | %d pieces | %d sures = %.0f %% | banc %.0f %% | ecart %+.0f pts -> %s" % (
        len(L), N, S, 100 * part, 100 * BANC, 100 * (part - BANC),
        "SUR-APPRIS LE BANC (> 15 pts sous)" if part < BANC - 0.15 else "pas de sur-apprentissage"))
