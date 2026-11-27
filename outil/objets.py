"""Base d'exemples de l'IA de tri (D-08) : chaque objet vectoriel des plans d'essai + ses caracteristiques
+ une etiquette AUTOMATIQUE tiree des pieces SURES (surface calculee a <= 1 % de la surface ecrite) :
  1 = sur le bord d'une piece sure (mur, vitre, seuil...) ; 0 = a l'interieur, a > 10 cm du bord (meuble, cote, texte...) ;
  -1 = pas d'etiquette.
Deux sources de pieces sures, de methodes DIFFERENTES (limite le risque que l'IA recopie une seule regle) :
  - methode matiere (matiere.py, trous exacts) ;
  - methode pixels v1h (contours dans sorties/v1h/*_metre.json).
Usage : python objets.py  -> sorties/objets/<plan>.jsonl + resume"""
import glob, json, math, os, sys, time
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
import pdfplumber, pypdfium2 as pdfium
from shapely.geometry import LineString, Polygon, Point
from shapely.strtree import STRtree
from metre import lire_textes, etiquettes, echelle_par_cotes, normaliser, origine, page_plumber
import matiere
import metre as metre_mod   # lignes de cote memorisees (cassure 2)

BORD = 0.04      # m : objet a moins de 4 cm du bord d'une piece sure -> limite
DEDANS = 0.10    # m : objet entierement a plus de 10 cm du bord, dedans -> pas une limite
SURE = 0.01      # piece sure : ecart <= 1 %
LIMITE_STRICTE = True   # 26/11 : « limite » = longe le bord (>= 20 cm, parallele) ; avant : tout ce qui frolait le bord
CANDIDATS_FACES = [0.13, 0.25, 0.45]   # epaisseurs de stylo des decoupages candidats (arbitres par la surface ecrite)


def couleur(c):
    if isinstance(c, (list, tuple)) and all(isinstance(v, (int, float)) for v in c):
        if len(c) == 1: return [c[0]] * 3
        if len(c) == 3: return list(c)
        if len(c) == 4: k = c[3]; return [(1 - min(1, v + k)) for v in c[:3]]
    return [-1, -1, -1]


def caracteristiques(o, conv, m):
    pts = [conv(p) for p in (o.get("pts") or [])]
    if len(pts) < 2: return None, None
    if o.get("object_type") == "rect" and len(pts) >= 4: pts = pts + [pts[0]]
    ligne = LineString(pts)
    L = ligne.length * m
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    w, h = (max(xs) - min(xs)) * m, (max(ys) - min(ys)) * m
    ferme = math.dist(pts[0], pts[-1]) * m < 0.005
    ep = 0.0; aire = 0.0
    if len(pts) >= 3:
        try:
            P = Polygon(pts).buffer(0)
            if not P.is_empty and P.length:
                aire = P.area * m * m; ep = 2 * P.area / P.length * m
        except Exception:
            pass
    # orientation du plus long cote
    best, ang = 0, 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        if d > best: best, ang = d, math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
    sc, fc = couleur(o.get("stroking_color")), couleur(o.get("non_stroking_color"))
    f = {
        "type": {"line": 0, "rect": 1, "curve": 2}.get(o.get("object_type"), 3),
        "n_pts": len(o.get("pts") or []), "ep_stylo_cm": (o.get("linewidth") or 0) * m * 100,
        "stylo_pt": o.get("linewidth") or 0, "rempli": int(bool(o.get("fill"))), "trace": int(bool(o.get("stroke", True))),
        "trait_r": sc[0], "trait_g": sc[1], "trait_b": sc[2], "rempli_r": fc[0], "rempli_g": fc[1], "rempli_b": fc[2],
        "longueur_m": L, "boite_l_m": max(w, h), "boite_c_m": min(w, h), "ferme": int(ferme), "aire_m2": aire,
        "ep_bande_m": ep, "cote_max_m": best * m, "angle_mod90": (ang % (math.pi / 2)) * 180 / math.pi,
        "droit": int(min(ang % (math.pi / 2), math.pi / 2 - ang % (math.pi / 2)) < math.radians(2)),
        # POSITION en metres (pour calculer le VOISINAGE ensuite sans relire le PDF -- lecon de SymPoint)
        "_x0": min(xs) * m, "_y0": min(ys) * m, "_x1": max(xs) * m, "_y1": max(ys) * m, "_angle": ang,
    }
    geom = ligne if not (f["rempli"] and len(pts) >= 3) else (Polygon(pts).buffer(0) if aire else ligne)
    return f, geom


def pieces_sures(chemin, nom, m, OX, dy, lourd=False):
    """liste de polygones (coord. de travail) des pieces sures, avec leur source"""
    # La surface ECRITE sert d'ARBITRE entre plusieurs decoupages candidats (reglages differents) : une surface fermee
    # a <= 1 % de l'ecrit n'est presque jamais un hasard -> c'est la vraie piece. On ne s'en sert QUE pour fabriquer
    # les exemples, jamais pour mesurer. Une seule piece sure par etiquette (la premiere source qui la trouve).
    # 27/11 : CACHE des pieces sures par page. Les bases ont ete reconstruites 4 fois en une nuit (seules les ETIQUETTES
    # changeaient) en refaisant chaque fois tout le metre (faces : le plus lent). Pieces sures = fonction du PDF seul.
    import pickle, shapely
    fc = os.path.join(ici, "sorties", "cache_sures", nom[:80] + ".pkl")
    if os.path.exists(fc) and os.path.getmtime(fc) >= os.path.getmtime(chemin) and os.environ.get("SURES_FRAIS") != "1":
        matiere.pieces_par_matiere(chemin, verbeux=False)   # remet a jour la matiere du plan (utilisee par les etiquettes)
        return [(shapely.from_wkb(w), s) for w, s in pickle.load(open(fc, "rb"))]
    sures = _pieces_sures(chemin, nom, m, OX, dy, lourd)
    os.makedirs(os.path.dirname(fc), exist_ok=True)
    pickle.dump([(shapely.to_wkb(P), s) for P, s in sures], open(fc, "wb"))
    matiere.pieces_par_matiere(chemin, verbeux=False)   # la matiere par defaut doit etre la DERNIERE calculee
    return sures


def _pieces_sures(chemin, nom, m, OX, dy, lourd=False):
    sures, vues = [], set()
    def prendre(e, a, h, src):
        k = (round(e["x"], 1), round(e["y"], 1))
        if a and h is not None and k not in vues and abs(a / e["surface_ecrite"] - 1) <= SURE:
            vues.add(k); sures.append((h, src))
    try:
        for e, a, h in matiere.pieces_par_matiere(chemin, verbeux=False, rendre=True): prendre(e, a, h, "matiere")
    except Exception as ex:
        print("  matiere en erreur :", ex)
    if CANDIDATS_FACES:
        import faces
        for s in [c for c in CANDIDATS_FACES if not (lourd and c < 0.25)]:   # plan tres charge : pas de stylo fin (des heures)
            try:
                for e, a, h in faces.pieces_par_faces(chemin, s, verbeux=False, avec_remplis=False, rendre_faces=True):
                    prendre(e, a, h, "faces")
            except Exception as ex:
                print("  faces %.2f en erreur : %s" % (s, ex))
    js = os.path.join(ici, "sorties", "v1j", nom + "_metre.json")   # v1j = v1h + contours enregistres
    if os.path.exists(js):
        for p in json.load(open(js, encoding="utf-8"))["pieces"]:
            c = p.get("contour_pt")
            if c and p.get("ecart_pct") is not None and abs(p["ecart_pct"]) <= SURE * 100 and len(c) >= 3:
                try:
                    P = Polygon(c).buffer(0)
                    k = (round(p["x"], 1), round(p["y"], 1))
                    if not P.is_empty and k not in vues: vues.add(k); sures.append((P, "pixels"))
                except Exception:
                    pass
    return sures


def alignes_par_objet(pl, conv, m):
    """27/11 : indice « alignes » = nombre de petits traits sur la MEME droite (+-1 deg, a 2 cm, centres a < 3 m).
    Le PDF n'a pas l'info « pointille » : un trait de coupe y est une suite de petits traits alignes."""
    al = {}
    segs = []
    for o in pl.lines:
        q = o.get("pts") or []
        if len(q) != 2: continue
        (ax, ay), (bx, by) = conv(q[0]), conv(q[1])
        L = math.hypot(bx - ax, by - ay)
        if not L: continue
        segs.append((id(o), (ax + bx) / 2, (ay + by) / 2, math.atan2(by - ay, bx - ax) % math.pi, (bx - ax) / L, (by - ay) / L))
    if segs:
        arbre_s = STRtree([Point(x, y) for _, x, y, _, _, _ in segs])
        for i, (oid, x, y, an, ux, uy) in enumerate(segs):
            n_ = 0
            for j in arbre_s.query(Point(x, y).buffer(3.0 / m)):
                if j == i: continue
                _, x2, y2, an2, _, _ = segs[j]
                if min(abs(an - an2), math.pi - abs(an - an2)) > math.radians(1): continue
                if abs((x2 - x) * (-uy) + (y2 - y) * ux) * m > 0.02: continue
                n_ += 1
            al[oid] = n_
    return al


def traiter(f, sures_donnees=None, sortie=None):
    """sures_donnees : contours deja CONFIRMES par un humain (ecran v2 : valides ou traces a la main) ;
    s'ils sont donnes, ils remplacent la recherche automatique des pieces sures."""
    nom = os.path.splitext(os.path.basename(f))[0]
    ch = normaliser(f)
    W, H, _, _ = lire_textes(ch, 0)
    m = echelle_par_cotes(ch, 0)[0]
    if not m: return None
    doc = pdfium.PdfDocument(ch); OX, OY = origine(doc[0]); doc.close()
    dy = H - OY
    conv = lambda p: (p[0] - OX, p[1] - dy)
    pl = page_plumber(ch)   # lecture unique (26/11)
    sures = sures_donnees if sures_donnees is not None else \
        pieces_sures(f, nom, m, OX, dy, lourd=len(pl.lines) + len(pl.rects) + len(pl.curves) > 100000)
    bords = [P.exterior for P, _ in sures]
    arbre_b = STRtree(bords) if bords else None
    # interieurs retrecis calcules UNE fois (avant : recalcules pour chaque objet -> des heures)
    dedans_l = [P.buffer(-DEDANS / m) for P, _ in sures]
    pieces_l = [P for P, _ in sures]
    arbre_p = STRtree(pieces_l) if pieces_l else None
    pl = page_plumber(ch)   # lecture unique (26/11)
    # --- CASSURE 2 (27/11) : ETIQUETTES DE SENS automatiques, tirees de ce que l'outil sait deja SUR ---
    if sures_donnees is not None or not matiere.DERNIERE_MATIERE:
        matiere.pieces_par_matiere(f, verbeux=False)          # vitres et matiere du plan
    mat = matiere.DERNIERE_MATIERE[0] if matiere.DERNIERE_MATIERE else None
    from shapely.prepared import prep
    mat_p = prep(mat) if mat is not None else None
    vitres = {tuple(round(v, 3) for xy in g_.coords for v in xy) for g_ in matiere.DERNIERES_VITRES}
    # 27/11 (VITRE_BAIE) -- vu en image (3103962) : les CHASSIS (rectangles, polylignes) le long d'une piece etaient
    # etiquetes « mur » car seul le segment exact de la vitre l'etait. Le metreur : tout ce qui est DANS la baie = fenetre.
    baie_p = None
    if VITRE_BAIE and matiere.DERNIERES_VITRES:
        from shapely.ops import unary_union as _uu3
        baie_p = _uu3([g_ for g_ in matiere.DERNIERES_VITRES]).buffer(0.15 / m, cap_style=2)
    # 27/11 (MOBILIER_PARTOUT) : le metreur reconnait un meuble partout : trait fin, dans une piece fermee, loin des murs
    loin_p = None
    if MOBILIER_PARTOUT and mat is not None:
        from shapely.geometry import Polygon as _Pg
        from shapely.ops import unary_union as _uu
        trous = [_Pg(r) for g_ in getattr(mat, "geoms", [mat]) for r in g_.interiors]
        trous = [t for t in trous if 2 <= t.area * m * m <= 200]
        if trous: loin_p = prep(_uu(trous).difference(mat.buffer(0.20 / m)))
    # 27/11 (AUTRE) -- cause trouvee en image (Guyane) : l'IA prenait cadre, cartouche, traits de coupe et cotes pour des
    # murs car ces objets n'avaient AUCUNE etiquette (elle devait choisir parmi 8 cases). Le metreur sait :
    #   - hors du batiment (cadre, cartouche, axes et cotes exterieurs) = « autre » ;
    #   - un trait qui TRAVERSE les murs (axe de coupe, cote mur a mur) = « autre » ;
    #   - un trait de la matiere n'est un MUR que si son style de dessin borde une piece juste (sinon : bureau dans la matiere).
    bati_p = sig_vrais = None
    if AUTRE and mat is not None:
        from shapely.geometry import Polygon as _Pg2
        from shapely.ops import unary_union as _uu2
        tr2 = [_Pg2(r) for g_ in getattr(mat, "geoms", [mat]) for r in g_.interiors]
        # le BATIMENT = les grands ensembles, pas les petites taches isolees (fleches de coupe, nord) -- vu en image 27/11
        u2 = _uu2([mat] + tr2).buffer(0.30 / m)
        gs2 = list(getattr(u2, "geoms", [u2])); amax = max(g_.area for g_ in gs2)
        bati_p = prep(_uu2([g_ for g_ in gs2 if g_.area >= 0.05 * amax]))
        if bords:
            bu = _uu2(bords).buffer(0.03 / m)
            sig_vrais = {s_ for gg, s_ in matiere.DERNIERS_MORCEAUX if gg.intersects(bu)}
    al = alignes_par_objet(pl, conv, m) if AUTRE else {}
    cordes = matiere.portes(pl, m, conv)
    bouts = STRtree([Point(c.coords[-1]) for c in cordes]) if cordes else None
    cotes = {tuple(round(v, 3) for v in c) for c in metre_mod.LIGNES_COTES.get(os.path.abspath(ch), [])}
    lignes, n1, n0 = [], 0, 0
    for o in pl.lines + pl.rects + pl.curves:
        fe, g = caracteristiques(o, conv, m)
        if fe is None: continue
        fe["alignes"] = al.get(id(o), 0)
        pts_c = [conv(p) for p in (o.get("pts") or [])]
        lab = -1
        if arbre_b is not None:
            idx = arbre_b.query(g.buffer(BORD / m))
            # 1 : l'objet longe un bord sur au moins la moitie de sa longueur (ou s'il est petit, il le touche)
            for i in idx:
                b = bords[i]
                if g.distance(b) * m <= BORD:
                    part = g.boundary if g.geom_type == "Polygon" else g
                    pres = part.intersection(b.buffer(BORD / m)).length / max(part.length, 1e-9)
                    if pres >= 0.5:
                        # un objet REMPLI qui recouvre l'interieur de la piece (fond de piece colore, meuble plein
                        # contre le mur) n'est PAS une limite, meme si son contour suit le bord (bug trouve le 26/11)
                        if g.geom_type == "Polygon" and g.area > 0:
                            P = sures[i][0]
                            if g.intersection(P.buffer(-BORD / m)).area > 0.10 * g.area: lab = 0; break
                        if LIMITE_STRICTE and not (fe["rempli"] and 0.02 <= fe["ep_bande_m"] <= 0.35):
                            # 26/11 : 51-95 % des « limites » etaient des traits fins < 30 cm (hachures, details).
                            # Une LIMITE longe le bord : >= 20 cm et parallele au bord local (10 deg) ; sinon : pas d'etiquette
                            if fe["longueur_m"] < 0.20: lab = -1; break
                            c0 = g.centroid; s0 = b.project(c0)
                            q1, q2 = b.interpolate(max(0, s0 - 0.05 / m)), b.interpolate(min(b.length, s0 + 0.05 / m))
                            ab = math.atan2(q2.y - q1.y, q2.x - q1.x) % math.pi
                            if min(abs(ab - fe["_angle"]), math.pi - abs(ab - fe["_angle"])) > math.radians(10): lab = -1; break
                        lab = 1; break
            if lab == -1:
                # 0 : l'objet TRAVERSE ou occupe l'interieur d'une piece sure (cote qui va d'un mur a l'autre, meuble,
                # texte...) : plus de la moitie de lui est a plus de 10 cm du bord, a l'interieur (bug trouve le 26/11 :
                # les cotes touchant les murs n'etaient jamais etiquetees -> l'IA les prenait pour des murs)
                for j in arbre_p.query(g):
                    P = pieces_l[j]
                    if not P.intersects(g): continue
                    dedans = dedans_l[j]
                    if g.geom_type == "Polygon":
                        if g.area > 0 and g.intersection(dedans).area > 0.5 * g.area: lab = 0; break
                    elif g.length > 0 and g.intersection(dedans).length > 0.5 * g.length: lab = 0; break
        fe["etiquette"] = lab
        # classe de SENS (priorite du plus sur au moins sur) -- « bases breves » de l'IA
        cl = ""
        if fe["rempli"] and fe["n_pts"] > 40 and fe["ep_bande_m"] < 0.04: cl = "lettre"
        elif fe["type"] == 2 and not fe["rempli"] and bouts is not None and len(pts_c) >= 2 \
                and 0.4 <= math.dist(pts_c[0], pts_c[-1]) * m <= 1.9 and any(
                Point(pts_c[-1]).distance(Point(cordes[i].coords[-1])) * m < 0.08 or Point(pts_c[0]).distance(Point(cordes[i].coords[-1])) * m < 0.08
                for i in bouts.query(Point(pts_c[-1]).buffer(0.1 / m)).tolist() + bouts.query(Point(pts_c[0]).buffer(0.1 / m)).tolist()):
            cl = "porte"
        elif fe["type"] == 0 and len(pts_c) == 2 and tuple(round(v, 3) for p in pts_c for v in p) in cotes: cl = "cote"
        elif fe["rempli"] and fe["longueur_m"] > 3 and lab == 0: cl = "fond"
        elif lab == 1 and len(pts_c) == 2 and tuple(round(v, 3) for p in pts_c for v in p) in vitres: cl = "vitre"
        elif lab == 1 and baie_p is not None and (g.boundary if g.geom_type == "Polygon" else g).length > 0 and                 (g.boundary if g.geom_type == "Polygon" else g).intersection(baie_p).length >= 0.5 * (g.boundary if g.geom_type == "Polygon" else g).length:
            cl = "vitre"
        elif lab == 1: cl = "mur"
        # 27/11 (MUR_MATIERE) : le metreur reconnait un mur PARTOUT a son dessin, pas seulement autour des pieces deja
        # reussies (cause de l'echec de sens.py : murs etiquetes d'un seul cote du plan). Trait >= 20 cm dans la matiere.
        elif MUR_MATIERE and fe["longueur_m"] >= 0.20 and lab != 0 and mat_p is not None and mat_p.contains(g.centroid) \
                and (bati_p is None or bati_p.contains(g.centroid)) \
                and (sig_vrais is None or (matiere.signature(o, fe["ep_bande_m"]) if fe["rempli"] else matiere.signature(o)) in sig_vrais): cl = "mur"
        elif not fe["rempli"] and fe["stylo_pt"] < 0.45 and fe["longueur_m"] < 0.3 and mat_p is not None and mat_p.contains(g.centroid): cl = "hachure"
        elif lab == 0: cl = "mobilier"
        elif loin_p is not None and not fe["rempli"] and fe["stylo_pt"] < 0.45 and fe["longueur_m"] >= 0.10                 and loin_p.contains(g): cl = "mobilier"
        if not cl and bati_p is not None:
            if not bati_p.contains(g.centroid): cl = "autre"
            elif g.geom_type == "LineString" and fe["longueur_m"] >= 1.0 and mat is not None:
                ix = g.intersection(mat)
                if len(getattr(ix, "geoms", [ix] if not ix.is_empty else [])) >= 2: cl = "autre"
        fe["classe"] = cl
        n1 += lab == 1; n0 += lab == 0
        lignes.append(fe)
    dos = sortie or SORTIE
    os.makedirs(os.path.join(ici, "sorties", dos), exist_ok=True)
    import gzip   # compresse (~10x) : disque C: presque plein (26/11)
    with gzip.open(os.path.join(ici, "sorties", dos, nom[:60] + ".jsonl.gz"), "wt", encoding="utf-8") as s:
        for l in lignes: s.write(json.dumps(l) + "\n")
    src = {k: sum(1 for _, s2 in sures if s2 == k) for k in ("matiere", "faces", "pixels")}
    return nom, len(lignes), n1, n0, src


# usage : python objets.py [plans_test|plans_appr] -> sorties/objets ou sorties/objets_appr
DOSSIER = sys.argv[1] if len(sys.argv) > 1 else "plans_test"
MUR_MATIERE = os.environ.get("MUR_MATIERE") == "1"
MOBILIER_PARTOUT = os.environ.get("MOBILIER_PARTOUT") == "1"
VITRE_BAIE = os.environ.get("VITRE_BAIE") == "1"   # 27/11 : chassis dans la baie = vitre (pas mur)
AUTRE = os.environ.get("AUTRE") == "1"   # 27/11 : classe « autre » + murs a style verifie + indice « alignes »
_suf = ("_mm" if MUR_MATIERE else "") + ("_mp" if MOBILIER_PARTOUT else "") + ("_au" if AUTRE else "") + ("_vb" if VITRE_BAIE else "")
SORTIE = ("objets" + _suf) if DOSSIER == "plans_test" else ("objets_appr" + _suf)
if DOSSIER != "plans_test":
    CANDIDATS_FACES = [0.45]   # pages d apprentissage : le stylo fin (0,13) coute des heures sur les grands plans (EFS) pour peu d exemples en plus

if __name__ == "__main__":
    # 27/11 : PART=i/n -> ne traite qu'une part des pages (2 processus en parallele, un par coeur)
    i_, n_ = map(int, os.environ.get("PART", "1/1").split("/"))
    _S = os.environ.get("SEULEMENT", "")   # nom exact d'une page (un_par_un.py) ou prefixe de dossier
    for f in [f_ for f_ in sorted(glob.glob(os.path.join(ici, DOSSIER, "*.pdf"))) if os.path.basename(f_).startswith(_S)][i_ - 1::n_]:
        t = time.time()
        rep = float(os.environ.get("REPRENDRE_HEURES", "0"))   # 27/11 : reprise apres plantage memoire
        if rep:
            sor = glob.glob(os.path.join(ici, "sorties", SORTIE, glob.escape(os.path.splitext(os.path.basename(f))[0][:60]) + ".jsonl.gz"))
            if sor and time.time() - os.path.getmtime(sor[0]) < rep * 3600: continue
        r = traiter(f)
        if r:
            nom, n, n1, n0, src = r
            print("%-55s objets %6d | limite %5d | pas limite %6d | pieces sures : matiere %d, faces %d, pixels %d | %d s" % (
                nom[:55], n, n1, n0, src["matiere"], src["faces"], src["pixels"], time.time() - t), flush=True)
