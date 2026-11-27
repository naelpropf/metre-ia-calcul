"""DIAGNOSTIC AUTOMATIQUE DES FUITES (26/11) -- trouver la RACINE de chaque piece ratee, sans deviner.
Pour chaque piece etiquetee mal mesuree par la methode matiere :
  1. zone libre autour de l'etiquette (tout ce qui n'est pas « mur ») ;
  2. on la RETRECIT (ouverture morphologique de rayon r croissant) jusqu'a ce que la piece retrouve ~ sa surface
     ecrite : le plus petit r qui y arrive = demi-largeur du PASSAGE par ou elle fuit ;
  3. le passage (« goulot ») = ce que l'ouverture a coupe, contre la piece ;
  4. on liste ce que le PDF contient dans le goulot (rien, traits fins, arcs, aplats...) et on CLASSE la cause.
Sortie : tableau des causes par plan (a traiter par ordre de poids : regle 80/20) + images dans sorties/diag/<plan>/.
Usage : python diag_fuites.py plan.pdf [plan2.pdf ...] [--images N]"""
import collections, math, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
import pdfplumber
from shapely.geometry import Point, LineString, Polygon, box
from shapely.strtree import STRtree
from shapely.ops import unary_union
from shapely.validation import make_valid
import matiere
from metre import normaliser, origine, lire_textes

TOL_OK = 0.03          # piece consideree juste a 3 %
DERNIERES_LIGNES = []
RAYONS = [0.01, 0.02, 0.035, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.75, 0.90]   # demi-largeurs testees (m) ; porte double 1,8 m


def composante(g, p):
    """morceau de g qui contient p (ou le plus proche)"""
    parts = [q for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon" and not q.is_empty]
    if not parts: return None
    dedans = [q for q in parts if q.contains(p)]
    return dedans[0] if dedans else min(parts, key=lambda q: q.distance(p))


def objets_pdf(pl, conv, m_pt):
    geoms, info = [], []
    for o in pl.lines + pl.rects + pl.curves:
        pts = o.get("pts") or []
        if len(pts) < 2: continue
        c = [conv(p) for p in pts]
        if o.get("object_type") == "rect" and len(c) >= 4: c = c + [c[0]]
        g = LineString(c)
        if g.length == 0: continue
        fc = o.get("non_stroking_color"); lum = None
        if o.get("fill") and isinstance(fc, (list, tuple)) and fc and all(isinstance(v, (int, float)) for v in fc):
            lum = (sum(fc) / len(fc)) if len(fc) in (1, 3) else 1 - min(1, sum(fc) / 4)
        geoms.append(g)
        info.append({"type": o.get("object_type"), "stylo_pt": round(o.get("linewidth") or 0, 2),
                     "rempli": bool(o.get("fill")), "lum": lum, "n_pts": len(pts), "long_m": g.length * m_pt,
                     "corde_m": math.dist(c[0], c[-1]) * m_pt})
    return geoms, info


def verites_connues(chemin):
    """{(x,y) etiquette: (contour, source)} : contours SURS trouves par une AUTRE methode que la matiere standard
    (moteur v3 : double trait, faces, pixels -- a 1 % de l'ecrit) + contours traces par l'operateur (corrections/)."""
    import json, glob as _g
    from shapely.geometry import Polygon
    V = {}
    try:
        import metre_v3
        for r in metre_v3.pieces_v3(chemin):
            if r["sure"] and r["source"] != "matiere" and r["h"] is not None:
                V[(round(r["e"]["x"], 1), round(r["e"]["y"], 1))] = (r["h"], r["source"])
    except Exception as ex:
        print("  v3 en erreur :", ex)
    ab = os.path.abspath(chemin)
    for f in _g.glob(os.path.join(ici, "corrections", "*.json")):
        d = json.load(open(f, encoding="utf-8"))
        if os.path.abspath(d.get("chemin", "")) != ab: continue
        for ex in d["exemples"]:
            if ex["etat"] == "corrigee" and ex.get("contour_px") and len(ex["contour_px"]) >= 3:
                P = Polygon([(x / d["k"], y / d["k"]) for x, y in ex["contour_px"]]).buffer(0)
                # retrouver l'etiquette : la plus proche du contour trace (cle approchee)
                V[("main", ex["id"])] = (P, "trace operateur")
    return V


def classer(dans, largeur, seuil):
    """cause en mots, a partir des objets PDF trouves dans le goulot"""
    if not dans:
        if largeur <= 0.07: return "micro-trou sans trait (%d cm)" % round(largeur * 100)
        if 0.60 <= largeur <= 1.30: return "passage ~porte, AUCUN trait (porte sans arc ou baie libre)"
        return "ouverture libre sans trait (%d cm)" % round(largeur * 100)
    # FONDS de piece (aplats remplis de plus de 3 m de tour) : sous tout le dessin -> jamais une cause (bug 26/11 :
    # ils faisaient conclure « arc present » partout)
    dans = [o for o in dans if not (o["rempli"] and o["long_m"] > 3)]
    if not dans: return classer([], largeur, seuil)
    t = collections.Counter(o["type"] for o in dans)
    if any(o["type"] == "curve" and not o["rempli"] and 0.4 <= o["corde_m"] <= 1.9 for o in dans):
        return "arc de porte present (corde manquante ou mal placee)"
    aplats = [o for o in dans if o["rempli"]]
    if aplats and all((o["lum"] or 0) > 0.75 for o in aplats) and len(aplats) >= len(dans) / 2:
        return "aplat CLAIR non pris pour un mur (lum > 0,75)"
    fins = [o for o in dans if not o["rempli"] and o["stylo_pt"] < seuil]
    if fins:
        st = collections.Counter(o["stylo_pt"] for o in fins).most_common(1)[0][0]
        courts = sum(1 for o in fins if o["long_m"] < 0.3)
        if courts >= 6 and courts >= 0.7 * len(fins): return "hachures / petits traits fins (stylo %.2f pt)" % st
        return "traits FINS seulement (stylo %.2f pt) : mur dessine autrement ou vitre non reconnue" % st
    return "objets presents mais ecartes (%s)" % ", ".join("%s x%d" % kv for kv in t.most_common(3))


def diagnostiquer(chemin, n_images=8):
    t0 = time.time()
    verites = verites_connues(chemin)          # vrais contours (autre methode a 1 %, ou trace de l'operateur)
    res = matiere.pieces_par_matiere(chemin, verbeux=False, rendre=True)   # EN DERNIER : DERNIERE_MATIERE = matiere standard
    if not matiere.DERNIERE_MATIERE: print("  pas d'echelle"); return None
    mat, m_pt = matiere.DERNIERE_MATIERE
    ch = normaliser(chemin)
    W, H, _, _ = lire_textes(ch, 0)
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(ch); OX, OY = origine(doc[0])
    conv = lambda p: (p[0] - OX, p[1] - (H - OY))
    pl = pdfplumber.open(ch).pages[0]
    geoms, info = objets_pdf(pl, conv, m_pt)
    arbre = STRtree(geoms)
    lignes, causes = [], collections.Counter()
    for e, a, h in res:
        S = e.get("surface_ecrite")
        if not S: continue
        if a and abs(a / S - 1) <= TOL_OK: continue
        p = Point(e["x"], e["y"])
        nom = (e.get("nom") or "?").strip()[:24]
        V = verites.get((round(e["x"], 1), round(e["y"], 1))) or next(
            (v for kk, v in verites.items() if kk[0] == "main" and v[0].contains(p)), None)
        if V is not None:
            # DIAGNOSTIC EXACT : on connait le vrai contour T
            T, srcT = V
            tolm = (0.03 if "pixels" in srcT else 0.015) / m_pt
            manque = T.exterior.difference(mat.buffer(tolm))
            segs = [s for s in getattr(manque, "geoms", [manque]) if s.geom_type == "LineString" and s.length * m_pt >= 0.05]
            intr = mat.intersection(T.buffer(-0.05 / m_pt))
            intrus = [g for g in getattr(intr, "geoms", [intr]) if g.geom_type == "Polygon" and g.area * m_pt * m_pt >= 0.002]
            details, dessin = [], []
            if a and a < S * (1 - TOL_OK) and intrus:
                # on nomme les MORCEAUX DE MUR eux-memes (signature : bande/trait, couleur, epaisseur) -- avant (26/11) :
                # tous les objets PDF filtres, et le filtre « fonds de piece » cachait justement les bandes coupables
                for g in sorted(intrus, key=lambda g: -g.area)[:3]:
                    st = collections.Counter()
                    for mg, sg in matiere.DERNIERS_MORCEAUX:
                        if mg.intersects(g): st[sg] += mg.intersection(g).area * m_pt * m_pt
                    if not st: st["vitre ou corde de porte"] = 0
                    details.append("objet INTERIEUR pris pour un mur (%s)" % ", ".join("%s %.2f m2" % (s, v) for s, v in st.most_common(2))); dessin.append(g)
            for s in sorted(segs, key=lambda s: -s.length)[:4]:
                zs = s.buffer(0.03 / m_pt)
                dans = [info[i] for i in arbre.query(zs) if geoms[i].intersects(zs)]
                details.append("%s | %.2f m" % (classer(dans, s.length * m_pt, 0.45), s.length * m_pt)); dessin.append(s.buffer(0.04 / m_pt))
            if not details: details = ["vrai contour entierement couvert : ecart venu d'ailleurs (etiquette, echelle ?)"]
            c = details[0] + " [vrai contour : %s]" % srcT + ((" || autres : " + " ; ".join(d.split(" (")[0] for d in details[1:])) if len(details) > 1 else "")
            causes["(exact) " + details[0].split(" (")[0].split(" |")[0]] += 1
            lignes.append((nom, S, c, (T, unary_union(dessin)) if dessin else None)); continue
        if a and a < S * (1 - TOL_OK):
            c = "piece COUPEE (trop petite %+.0f %%) : un objet interieur pris pour un mur" % (100 * (a / S - 1))
            causes[c.split(" (")[0]] += 1; lignes.append((nom, S, c, None)); continue
        if mat.contains(p):
            c = "etiquette posee SUR de la matiere (texte dans un aplat ?)"
            causes[c] += 1; lignes.append((nom, S, c, None)); continue
        R = max(3 * math.sqrt(S), 4.0) / m_pt
        cadre = box(p.x - R, p.y - R, p.x + R, p.y + R)
        # PIECE COUPEE PAR LE BORD DE LA FEUILLE (racine 26/11, Pithiviers « Lingerie propre ») : la zone libre de
        # l'etiquette touche le bord de la page -> la piece continue hors du plan : aucune regle ne la fermera
        feuille = box(0, 0, W, H)
        z0 = composante(cadre.intersection(feuille).difference(mat), p)
        # 27/11 : on ne dit « coupee par le bord » que si l'etiquette est PRES du bord (le metreur le voit d'un coup d'oeil) ;
        # sinon la zone libre a seulement FUI (porte...) jusqu'au bord -> on continue l'analyse de la fuite (salles de radio)
        pres_du_bord = feuille.exterior.distance(p) * m_pt <= 1.2 * math.sqrt(S) + 1.0
        if z0 is not None and pres_du_bord and z0.intersects(feuille.exterior.buffer(0.05 / m_pt)) and z0.area * m_pt * m_pt > 1.5 * S:
            c = "HORS FEUILLE : la piece continue au-dela du bord du plan (a l'operateur)"
            causes[c.split(" :")[0]] += 1; lignes.append((nom, S, c, None)); continue
        loc = make_valid(mat.intersection(cadre.buffer(1.5 / m_pt))).buffer(0)
        trouve = None; trop_petit = None
        for r in RAYONS:
            # FERMETURE morphologique : rebouche les trous des murs de largeur < 2r, sans manger la piece
            rr = r / m_pt
            matc = make_valid(loc.buffer(rr, join_style=1).buffer(-rr, join_style=1)).buffer(0)
            k = composante(cadre.difference(matc), p)
            if k is None: break
            ak = k.area * m_pt * m_pt
            if S * 0.85 <= ak <= S * 1.15:
                trouve = (r, k, matc); break
            if ak < S * 0.85:
                # borne basse (bug 26/11 : la table de la salle de reunion, entouree de chaises, prise pour la piece)
                trop_petit = r; break
        if trop_petit is not None:
            c = "NON LOCALISABLE : le rebouchage enferme l'etiquette (mobilier ?) avant de fermer la piece (%d cm)" % round(200 * trop_petit)
            causes[c.split(" :")[0]] += 1; lignes.append((nom, S, c, None)); continue
        if trouve is None:
            c = "OUVERTE en grand (> 1,8 m sans aucune limite : espace ouvert ou mur absent)"
            causes[c] += 1; lignes.append((nom, S, c, None)); continue
        r, k, matc = trouve
        # la FUITE = ce qui a ete REBOUCHE et qui touche la piece : chaque bouchon = une ouverture ; sa longueur
        # = largeur de l'ouverture ; les objets PDF dedans = la cause.
        bouche = matc.difference(loc)
        # une VRAIE fuite separe la piece d'un AUTRE espace libre ; un coin de piece ou un creux de facade rebouche
        # ne touche que la piece (ou pas du tout) -> ecarte
        dehors = cadre.difference(matc).difference(k.buffer(0.005 / m_pt))
        tol = 0.02 / m_pt
        bouchons = [b for b in getattr(bouche, "geoms", [bouche]) if b.geom_type == "Polygon"
                    and b.distance(k) < tol and b.distance(dehors) < tol and b.area * m_pt * m_pt > 0.0005]
        def largeur(b):
            # largeur de l'ouverture = longueur de contact avec la piece
            return k.exterior.intersection(b.buffer(tol)).length * m_pt
        segs = [b for b in bouchons if largeur(b) >= 0.05]
        if not segs:
            c = "fuite non localisee"; causes[c] += 1; lignes.append((nom, S, c, None)); continue
        details = []
        for s in sorted(segs, key=lambda b: -largeur(b)):
            zs = s.buffer(0.02 / m_pt)
            dans = [info[i] for i in arbre.query(zs) if geoms[i].intersects(zs)]
            details.append((s, classer(dans, largeur(s), 0.45)))
        s0, c = details[0]                      # ouverture principale (la plus large)
        causes[c.split(" (")[0]] += 1
        autres = "; ".join("%s %.2f m" % (cc.split(" (")[0].split(",")[0], largeur(ss)) for ss, cc in details[1:3])
        lignes.append((nom, S, "%s | ouverture %.2f m (%d bouchon(s))%s" % (c, largeur(s0), len(details), (" | autres : " + autres) if autres else ""),
                       (k, unary_union([s.buffer(0.03 / m_pt) for s, _ in details]))))
    # images des premieres fuites (pour verifier le diagnostic a l'oeil, pas pour le faire)
    dossier = os.path.join(ici, "sorties", "diag", os.path.basename(chemin)[:40])
    os.makedirs(dossier, exist_ok=True)
    from PIL import Image, ImageDraw
    kz = min(6, 9000 / max(W, H))
    page = None
    for i, (nom, S, c, geo) in enumerate([l for l in lignes if l[3]][:n_images]):
        if page is None: page = doc[0].render(scale=kz).to_pil().convert("RGB")
        k, g = geo
        x0, y0, x1, y1 = k.union(g).bounds; mg = 1.0 / m_pt
        x0, y0, x1, y1 = (x0 - mg) * kz, (y0 - mg) * kz, (x1 + mg) * kz, (y1 + mg) * kz
        img = page.crop((int(x0), int(y0), int(x1), int(y1))).point(lambda v: 150 + v * 105 // 255).convert("RGBA")
        cal = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(cal)
        for geom, coul in ((k, (0, 90, 255, 70)), (g, (0, 200, 0, 200))):
            for q in getattr(geom, "geoms", [geom]):
                if q.geom_type == "Polygon":
                    d.polygon([(x * kz - x0, y * kz - y0) for x, y in q.exterior.coords], fill=coul)
        Image.alpha_composite(img, cal).convert("RGB").save(os.path.join(dossier, "%02d_%s.png" % (i, "".join(ch_ for ch_ in nom if ch_.isalnum())[:20])))
    doc.close()
    print("\n== %s (%d pieces etiquetees, %d ratees, %d s)" % (os.path.basename(chemin)[:60], sum(1 for e, _, _ in res if e.get("surface_ecrite")), len(lignes), time.time() - t0))
    for c, n in causes.most_common(): print("  %3d  %s" % (n, c))
    print("  -- detail --")
    for nom, S, c, _ in lignes: print("  %-24s %7.2f m2 | %s" % (nom, S, c))
    print("  images : %s" % dossier)
    DERNIERES_LIGNES[:] = lignes   # (nom, S, cause, (piece, fuites)) : pour les sondes
    return causes


if __name__ == "__main__":
    n = int(sys.argv[sys.argv.index("--images") + 1]) if "--images" in sys.argv else 8
    total = collections.Counter()
    for f in [a for a in sys.argv[1:] if a.lower().endswith(".pdf")]:
        c = diagnostiquer(f, n)
        if c: total.update(c)
    if total:
        print("\n== TOTAL des causes (traiter la plus lourde d'abord)")
        for c, k in total.most_common(): print("  %3d  %s" % (k, c))
