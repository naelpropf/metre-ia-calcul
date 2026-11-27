"""FICHES D'EXERCICES « PLAN PUIS REPONSE » pour l'IA (27/11 nuit, demande du porteur : l'IA apprend la LOGIQUE, on lui
EXPLIQUE ; « tel batiment, telle piece, donc tel truc »).
Une fiche par piece SURE (surface mesuree a 1 % de l'ecrit = contour juste) des PLANS D'ENTRAINEMENT (plans_appr ; jamais
plans_neufs = l'examen) :
  - image : la piece et ses abords (marge 1,5 m), 768 px au plus ;
  - question : la piece a trouver (nom + surface ecrite) ;
  - PLAN : batiment (devine par les noms de pieces de la page), piece, ce qu'on s'attend a y trouver, conventions du dessin ;
  - REPONSE : contour (polygone en millimes de l'image), ce que sont les objets du bord et de l'interieur, surface.
Classes d'objets : base objets_appr_mm_mp_au (objets.py). Usage : python exercices_plans.py [--max N]"""
import glob, gzip, json, math, os, re, sys, unicodedata
SOURCE = ""
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
SORTIE = os.environ.get("SORTIE_FICHES") or os.path.join(ici, "sorties", "exercices_v1")   # 28/11 : GitHub, un dossier par page
BASE_OBJ = os.path.join(ici, "sorties", "objets_appr_mm_mp_au")

LEGENDE = ("Bases : un MUR est un trait epais ou une bande remplie qui separe deux espaces ; une PORTE est un arc (le "
           "battant) et se ferme au droit du mur ; une FENETRE est un groupe de traits fins paralleles dans l'epaisseur du "
           "mur ; une COTE est une ligne fine avec des chiffres (une mesure, pas un mur) ; le MOBILIER et les EQUIPEMENTS "
           "(baignoire, lavabo, WC, plan de travail, lit, bureau) sont a l'interieur des pieces et ne sont pas des murs ; "
           "les HACHURES et les TEXTES non plus. La surface d'une piece se mesure au nu interieur des murs.")

# piece -> ce que le metreur s'attend a y trouver (logique « telle piece, donc tel truc »)
ATTENDU = [
    (("SDB", "SALLE DE BAIN", "SALLE D'EAU", "DOUCHE"), "salle de bains", "une baignoire ou une douche, un lavabo, parfois un WC : des equipements, pas des murs"),
    (("WC", "TOILETTE", "SANITAIRE"), "WC / sanitaires", "une cuvette, un lave-mains, des cloisons de cabine fines"),
    (("CUIS", "KITCHEN", "OFFICE", "TISANERIE"), "cuisine", "des plans de travail le long des murs, un evier, des plaques : equipements, pas des murs"),
    (("CH", "CHAMBRE", "DORTOIR"), "chambre", "un lit, un placard : mobilier"),
    (("SEJOUR", "SALON", "SALLE A MANGER", "LIVING"), "sejour", "canape, table : mobilier ; souvent de grandes baies vitrees"),
    (("BUREAU", "BUR.", "DIRECTION", "SECRETARIAT", "MEDECIN", "ACCUEIL"), "bureau", "des bureaux et des chaises : mobilier ; souvent une facade vitree"),
    (("REUNION", "SALLE", "CLASSE", "FORMATION", "BRIEFING"), "salle", "des tables : mobilier"),
    (("DEGT", "DEGAGEMENT", "CIRCULATION", "COULOIR", "HALL", "PALIER", "ENTREE", "ENT.", "SAS"), "circulation",
     "beaucoup de portes sur les bords ; peu de mobilier"),
    (("CAVE", "LOCAL", "STOCK", "RESERVE", "TECHNIQUE", "GAINE", "ARCHIVE"), "local", "peu ou pas de mobilier ; parfois des rayonnages"),
    (("PLACARD", "PL.", "RGT", "RANGEMENT", "DRESSING", "CELLIER"), "rangement", "une petite piece, souvent sans porte dessinee en arc"),
]
BATIMENT = [
    (("SDB", "SEJOUR", "CHAMBRE", "CH.", "T2", "T3", "T4", "CELLIER", "BALCON"), "des logements"),
    (("BUREAU", "REUNION", "ACCUEIL", "DIRECTION", "OPEN"), "des bureaux"),
    (("CLASSE", "PREAU", "DORTOIR", "RESTAURATION", "CANTINE"), "une ecole"),
    (("SOINS", "CONSULT", "MEDECIN", "INFIRM"), "un batiment de sante"),
    (("RESTAURANT", "SALLE", "BAR", "CUISINE"), "un restaurant ou une salle"),
    (("ATELIER", "STOCKAGE", "QUAI", "MAGASIN"), "un batiment d'activite ou de stockage"),
]


def sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if unicodedata.category(c) != "Mn").upper()


def type_piece(nom):
    n = sans_accents(nom)
    for cles, t, att in ATTENDU:
        if any(n.startswith(c) or (" " + c) in (" " + n) for c in cles): return t, att
    return None, None


def type_batiment(noms):
    N = [sans_accents(n) for n in noms]
    score = [(sum(any(c in n for c in cles) for n in N), t) for cles, t in BATIMENT]
    s, t = max(score)
    return t if s >= 2 else "un batiment (type non reconnu sur la page)"


def objets_du_plan(nom_pdf):
    fs = glob.glob(os.path.join(BASE_OBJ, glob.escape(nom_pdf[:60]) + "*.jsonl.gz"))
    if not fs: return None
    out = []
    for l in gzip.open(fs[0], "rt", encoding="utf-8"):
        d = json.loads(l)
        if d.get("classe") in ("", "autre"): continue
        out.append(d)
    return out


def fiche(e, h, m, objets, noms_page, img_page, sc, box_pt, rel_img):
    from shapely.geometry import box as _box
    x0, y0, x1, y1 = box_pt; W = x1 - x0; H = y1 - y0
    k = 1000 / max(W, H)
    poly = h.simplify(0.05 / m)
    if poly.geom_type != "Polygon": poly = max(getattr(poly, "geoms", [poly]), key=lambda g: g.area)
    contour = [[round((x - x0) * k), round((y - y0) * k)] for x, y in list(poly.exterior.coords)[:-1]]
    tp, att = type_piece(e.get("nom"))
    bord = {}; dedans = {}; style = {}
    # 27/11 soir : PENSEE DESSINEE -- les objets que le raisonnement CITE, en millimes de l'image, pour les dessiner et les verifier
    mm = lambda px, py: [round((px - x0) * k), round((py - y0) * k)]
    cites = {"murs": [], "portes": [], "exclus": [], "cotes": []}
    if objets is not None:
        Pm = h  # en points ; objets en metres -> ramener
        from shapely.geometry import LineString, Point
        B = h.exterior.buffer(0.05 / m); I = h.buffer(-0.10 / m)
        zone = _box(x0, y0, x1, y1)
        for d in objets:
            a = (d["_x0"] / m, d["_y0"] / m); b = (d["_x1"] / m, d["_y1"] / m)
            g = LineString([a, b]) if a != b else Point(a)
            if not g.intersects(zone): continue
            c = d["classe"]
            if c in ("mur", "vitre", "porte") and g.intersects(B) and not g.within(I):
                bord[c] = bord.get(c, 0) + 1
                if a != b:
                    # 27/11 soir : on ne cite que le MORCEAU de mur qui longe la piece (avant : murs entiers, hors image)
                    gi = g.intersection(B)
                    parts = [q_ for q_ in getattr(gi, "geoms", [gi]) if q_.geom_type == "LineString" and q_.length > 0]
                    if parts:
                        q_ = max(parts, key=lambda t: t.length); (ax, ay), (bx_, by_) = q_.coords[0], q_.coords[-1]
                        cites["portes" if c == "porte" else "murs"].append((q_.length, mm(ax, ay) + mm(bx_, by_)))
                if c == "mur":
                    st = "bandes remplies" if d.get("rempli") else ("traits epais" if d.get("stylo_pt", 0) >= 0.45 else "traits fins")
                    style[st] = style.get(st, 0) + 1
            elif c in ("mobilier", "cote", "lettre", "fond") and g.intersects(I):
                dedans[c] = dedans.get(c, 0) + 1
                if c == "mobilier" and a != b: cites["exclus"].append((g.length, mm(*a) + mm(*b)))
                # 27/11 nuit : 1re cause des pieces trop petites (hors 548666) = une ligne de COTE prise pour un mur
                # -> la pensee cite les cotes qui traversent la piece, pour que l'IA apprenne a les ecarter
                if c == "cote" and a != b:
                    gi = g.intersection(h)
                    if gi.geom_type == "LineString" and gi.length > 0:
                        (ax, ay), (bx_, by_) = gi.coords[0], gi.coords[-1]; cites["cotes"].append((gi.length, mm(ax, ay) + mm(bx_, by_)))
    noms_c = {"mur": "traits de mur", "vitre": "traits de fenetre", "porte": "arcs de porte", "cote": "lignes de cote",
              "mobilier": "objets de mobilier ou d'equipement", "lettre": "lettres dessinees", "hachure": "traits de hachure",
              "fond": "aplats de fond"}
    # 27/11 soir : seulement de VRAIS noms de pieces (pas « CL98/48 EI60 », « 1 R », « RS06 », « +8.10 NGF ») :
    # un mot d'au moins 4 lettres et aucun code de cloison / revetement / niveau
    CODE = re.compile(r"\b(CL|EI|RS|HSP|NGF|PLAF|SOL|MUR|dB)\b|\d{2}/\d{2}|^[\d\s/.,+=-]", re.I)
    vrais = sorted(set(n for n in noms_page if n and re.search(r"[^\W\d_]{4,}", n) and not CODE.search(n)))
    plan = ["Batiment : %s (pieces lues sur la page : %s)." % (type_batiment(vrais), ", ".join(vrais[:8]) or "aucune"),
            "Piece demandee : etiquette « %s », surface ecrite %.2f m2." % (" / ".join(e.get("_lignes") or [e.get("nom") or "sans nom"]), e["surface_ecrite"])]
    if tp: plan.append("C'est une piece de type %s : on s'attend a y trouver %s." % (tp, att))
    if style: plan.append("Dans ce dessin, les murs sont des %s." % max(style, key=style.get))
    plan.append("Methode : je suis les murs autour de l'etiquette, je ferme les portes au droit du mur, j'ignore ce qui est a l'interieur.")
    # les plus longs d'abord, en nombre limite (8 murs, 4 portes, 4 objets ecartes) : assez pour voir le chemin, sans noyer la fiche
    pensee = {"etiquette": mm(e["x"], e["y"])}
    for cle, nmax in (("murs", 8), ("portes", 4), ("exclus", 4), ("cotes", 3)):
        garde = []
        for _, s_ in sorted(cites[cle], key=lambda t: -t[0]):
            # sans doublon : un trait a moins de 8 millimes d'un trait deja cite (meme mur dessine 2 fois) est saute
            # 27/11 nuit : aussi un trait plus COURT couche le long d'un trait deja cite (ses 2 bouts a moins de 8 millimes de lui)
            if any(LineString([g_[:2], g_[2:]]).distance(Point(s_[:2])) <= 8 and LineString([g_[:2], g_[2:]]).distance(Point(s_[2:])) <= 8 for g_ in garde): continue
            garde.append(s_)
            if len(garde) >= nmax: break
        pensee[cle] = garde
    plan.append("Je lis l'etiquette en %s." % json.dumps(pensee["etiquette"]))
    if pensee["murs"]: plan.append("Je suis ces murs (x0, y0, x1, y1) : %s." % json.dumps(pensee["murs"]))
    if pensee["portes"]: plan.append("Je ferme ces portes : %s." % json.dumps(pensee["portes"]))
    if pensee["exclus"]: plan.append("J'ecarte ces objets, qui sont a l'interieur : %s." % json.dumps(pensee["exclus"]))
    if pensee["cotes"]: plan.append("J'ecarte ces lignes de cote, qui traversent la piece mais ne sont pas des murs : %s." % json.dumps(pensee["cotes"]))
    rep = ["Contour de la piece (millimes de l'image, x puis y) : %s." % json.dumps(contour)]
    if bord: rep.append("Sur le bord : " + ", ".join("%d %s" % (n, noms_c.get(c, c)) for c, n in sorted(bord.items(), key=lambda t: -t[1])) + ".")
    if dedans: rep.append("A l'interieur, et ce ne sont PAS des murs : " + ", ".join("%d %s" % (n, noms_c.get(c, c)) for c, n in sorted(dedans.items(), key=lambda t: -t[1])) + ".")
    rep.append("Surface au nu interieur : %.2f m2, egale a la surface ecrite (%.2f m2) a 1 %% pres : le contour est juste." % (h.area * m * m, e["surface_ecrite"]))
    return {"image": rel_img, "legende": LEGENDE,
            "question": "Voici un extrait de plan. Trouve la piece dont l'etiquette dit « %s » (%.2f m2 ecrits) : decris d'abord le plan, puis donne ta reponse." % (" / ".join(e.get("_lignes") or [e.get("nom") or "sans nom"]), e["surface_ecrite"]),
            "source_contour": SOURCE,
            "plan": " ".join(plan), "reponse": " ".join(rep), "v": 2, "pensee": pensee, "contour": contour,
            "cadre_pt": [round(v, 2) for v in box_pt], "rev": "27-11-nuit"}   # rev : les fiches sans elle sont a refaire


if __name__ == "__main__":
    import io, contextlib, random
    import matiere, pypdfium2 as pdfium
    from metre import normaliser
    nmax = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 10 ** 9
    os.makedirs(os.path.join(SORTIE, "img"), exist_ok=True)
    fj = os.path.join(SORTIE, "exercices.jsonl")
    faits = set()   # REPRISE : les plans deja passes (fiche ecrite ou plan sans piece sure note) sont sautes
    if os.path.exists(fj): faits |= {json.loads(l)["image"].split("/")[1].rsplit("_", 1)[0] for l in open(fj, encoding="utf-8")}
    fv = os.path.join(SORTIE, "plans_faits.txt")
    if os.path.exists(fv): faits |= set(open(fv, encoding="utf-8").read().splitlines())
    sortie = open(fj, "a", encoding="utf-8"); vus = open(fv, "a", encoding="utf-8")
    n = 0
    liste = [sys.argv[sys.argv.index("--une") + 1]] if "--une" in sys.argv else sorted(glob.glob(os.path.join(ici, "plans_appr", "*.pdf")))
    for f in liste:
        if n >= nmax: break
        nom = os.path.splitext(os.path.basename(f))[0]
        if nom in faits: continue   # 27/11 soir : nom COMPLET (coupe a 50, p5 et p6 d'un carnet se confondaient)
        try:
            ch = normaliser(f)
            import metre_v3
            metre_v3.PARALLELE = 1   # 27/11 nuit : 2 variantes en parallele = RAM libre 434 Mo sur ce PC -> une a la fois
            with contextlib.redirect_stdout(io.StringIO()): RV = metre_v3.pieces_v3(ch)
            R = [(r["e"], r["a"], r["h"]) for r in RV]; SRC = {id(r["e"]): r.get("source") for r in RV}
        except Exception as ex:
            print("%-50s erreur %s" % (nom[:50], str(ex)[:60]), flush=True); continue
        if not matiere.DERNIERE_MATIERE: continue
        m = matiere.DERNIERE_MATIERE[1]
        sures = [(e, h) for e, a, h in R if a and h is not None and e.get("surface_ecrite") and abs(a / e["surface_ecrite"] - 1) <= 0.01]
        if not sures:
            vus.write(nom + "\n"); vus.flush(); print("%-50s 0 piece sure" % nom[:50], flush=True); continue
        objets = objets_du_plan(nom); noms_page = [e.get("nom") for e, a, h in R]
        pg = pdfium.PdfDocument(ch)[0]; Wp, Hp = pg.get_size()
        k = 0
        for e, h in sures:
            if n >= nmax: break
            bx0, by0, bx1, by1 = h.bounds; d = 1.5 / m
            box_pt = (max(bx0 - d, 0), max(by0 - d, 0), min(bx1 + d, Wp), min(by1 + d, Hp))
            # 27/11 nuit : chaque piece est rendue SEULE, a une finesse qui donne ~768 px de cote long (avant : page entiere
            # a 1,5 puis decoupe -> 35 images sur 115 sous 300 px, etiquette illisible). Essai : meme image a 0,1 niveau pres.
            sc = max(1.5, min(16.0, 768 / max(box_pt[2] - box_pt[0], box_pt[3] - box_pt[1])))
            im = pg.render(scale=sc, crop=(box_pt[0], Hp - box_pt[3], Wp - box_pt[2], box_pt[1])).to_pil().convert("RGB")
            im.thumbnail((768, 768)); img = None
            # 27/11 soir : plans traces en gris tres pale (3095872 : pixel le plus sombre 118/255) -> contraste etire ;
            # sans effet sur une image qui a deja du noir
            from PIL import ImageOps
            im = ImageOps.autocontrast(im, cutoff=0.5)
            rel = "img/%s_%02d.png" % (nom, k); im.save(os.path.join(SORTIE, rel))
            sortie.write(json.dumps(fiche(e, h, m, objets, noms_page, img, sc, box_pt, rel), ensure_ascii=False) + "\n")
            k += 1; n += 1
        sortie.flush()
        vus.write(nom + "\n"); vus.flush()
        print("%-50s fiches %3d (objets %s) | total %d" % (nom[:50], k, "oui" if objets is not None else "non", n), flush=True)
    print("FIN fiches", n)
