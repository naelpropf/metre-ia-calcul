"""Gros plans de pieces d'une page neuve, pour REGARDER pourquoi la surface est fausse (27/11, diagnostic).
  python voir_pieces.py <debut du nom de page> <sortie.png> [bande]   bande : "presque" (1-10 % d'ecart, defaut), "grande" (> 2x),
                                                                      "petite" (< 0,5x), "sure"
Chaque case : rendu du plan autour de la piece (marge 1,5 m), contour trouve (vert), etiquette (point rouge),
texte « ecrit / mesure / rapport ». 12 pieces max, triees par rapport."""
import glob, math, os, sys
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
import metre_v3, pypdfium2 as pdfium
from metre import normaliser
from PIL import Image, ImageDraw
f = glob.glob(os.path.join(ici, "plans_neufs", glob.escape(sys.argv[1]) + "*.pdf"))[0]
sortie = sys.argv[2]; bande = sys.argv[3] if len(sys.argv) > 3 else "presque"
metre_v3.PARALLELE = 1
import matiere
if os.environ.get("POINTILLES"): matiere.PORTES_POINTILLES = True
if os.environ.get("OUVERTURES"): matiere.OUVERTURES = True   # 27/11 : voir les ponts de la variante « ouvertures de mur »
old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
if os.environ.get("MATIERE_SEUIL"):   # 27/11 : pieces d'UNE passe matiere a seuil donne (essais avant variante)
    R = [{"e": e, "a": a, "h": h, "sure": bool(a and abs(a / e["surface_ecrite"] - 1) <= 0.01)}
         for e, a, h in matiere.pieces_par_matiere(normaliser(f), seuil=float(os.environ["MATIERE_SEUIL"]), verbeux=False, rendre=True)]
else:
    R = metre_v3.pieces_v3(f)
sys.stdout.close(); sys.stdout = old
# matiere de la passe PRINCIPALE (celle qui donne la plupart des pieces) : ce que l'outil a pris pour des murs, en rouge
if os.environ.get("POINTILLES"): matiere.PORTES_POINTILLES = True   # 27/11 : voir la matiere AVEC les portes en tirets fermees
old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
matiere.pieces_par_matiere(f, seuil=float(os.environ.get("MATIERE_SEUIL", "0.45")), verbeux=False)
sys.stdout.close(); sys.stdout = old
MAT = matiere.DERNIERE_MATIERE[0] if matiere.DERNIERE_MATIERE else None
m_pt = matiere.DERNIERE_MATIERE[1] if matiere.DERNIERE_MATIERE else None
FILTRE = os.environ.get("NOMS")   # ex. NOMS="CAVE 11,CAVE 3" : seulement ces pieces


def rapport(r):
    return r["a"] / r["e"]["surface_ecrite"] if r.get("a") and r["e"].get("surface_ecrite") else None


m_pt0 = None


choix = []
for r in R:
    q = rapport(r)
    if q is None or r.get("h") is None: continue
    if FILTRE:
        if any(k.strip().upper() == (r["e"].get("nom") or "").strip().upper() for k in FILTRE.split(",")): choix.append((q, r))
        continue
    if (bande == "presque" and 0.01 < abs(q - 1) <= 0.10) or (bande == "grande" and q > 2) or \
       (bande == "petite" and q < 0.5) or (bande == "sure" and r["sure"]):
        choix.append((q, r))
if bande == "non":   # 27/11 : pieces NON mesurees (aucun contour ferme) -> case de 6 m autour de l'etiquette
    from shapely.geometry import Point
    for r in R:
        if not r.get("a") and m_pt:
            r = dict(r); r["h"] = Point(r["e"]["x"], r["e"]["y"]).buffer(1.5 / m_pt); r["a"] = 0.0
            choix.append((0.0, r))
choix.sort(key=lambda t: t[0])
if len(choix) > 12:   # 12 cases reparties sur toute la plage des rapports
    choix = [choix[int(i * (len(choix) - 1) / 11)] for i in range(12)]
print("%d pieces dans la bande %s | m_pt %s" % (len(choix), bande, m_pt))
ch = normaliser(f)
d = pdfium.PdfDocument(ch); page = d[0]; W, H = page.get_size()
CASE = 600
planche = Image.new("RGB", (CASE * 4, CASE * math.ceil(max(len(choix), 1) / 4)), "white")
for i, (q, r) in enumerate(choix):
    x0, y0, x1, y1 = r["h"].bounds
    if os.environ.get("ZOOM_ETIQ") and m_pt:   # 27/11 : case de 8 m autour de l'etiquette (trous geants = tout l'etage)
        z = float(os.environ["ZOOM_ETIQ"]) / m_pt
        x0, y0, x1, y1 = r["e"]["x"] - z, r["e"]["y"] - z, r["e"]["x"] + z, r["e"]["y"] + z
    marge = (1.5 / m_pt) if m_pt else 40
    x0 -= marge; y0 -= marge; x1 += marge; y1 += marge
    cote = max(x1 - x0, y1 - y0); sc = CASE / cote
    # rendu de la page entiere a l'echelle sc, limite par securite, puis decoupe
    sc = min(sc, 12000 / max(W, H))
    im = page.render(scale=sc, crop=(max(x0, 0), max(H - y1, 0), max(W - x1, 0), max(y0, 0)),
                     fill_color=(255, 255, 255, 255)).to_pil().convert("RGB")
    dr = ImageDraw.Draw(im, "RGBA")
    ox, oy = max(x0, 0), max(y0, 0)
    if MAT is not None:   # murs vus par l'outil = voile rouge (masque : exterieur plein, trous = pieces vides)
        from shapely.geometry import box as _b
        loc = MAT.intersection(_b(x0, y0, x1, y1))
        masque = Image.new("L", im.size, 0); dm = ImageDraw.Draw(masque)
        for g in getattr(loc, "geoms", [loc]):
            if g.is_empty or not hasattr(g, "exterior"): continue
            dm.polygon([((px - ox) * sc, (py - oy) * sc) for px, py in g.exterior.coords], fill=255)
            for t in g.interiors:
                dm.polygon([((px - ox) * sc, (py - oy) * sc) for px, py in t.coords], fill=0)
        im = Image.composite(Image.blend(im, Image.new("RGB", im.size, (255, 0, 0)), 0.45), im, masque)
        dr = ImageDraw.Draw(im, "RGBA")
    if os.environ.get("COTES"):   # 27/11 : lignes de cote detectees (diag_cotes) en BLEU epais
        from diag_cotes import lignes_de_cote
        if "_LC" not in globals(): globals()["_LC"] = lignes_de_cote(f)
        for a, b, c, d_ in _LC:
            if max(a, c) < x0 or min(a, c) > x1 or max(b, d_) < y0 or min(b, d_) > y1: continue
            dr.line([((a - ox) * sc, (b - oy) * sc), ((c - ox) * sc, (d_ - oy) * sc)], fill=(0, 60, 255, 255), width=4)
    if os.environ.get("PORTES"):   # 27/11 : secteurs de debattement reconnus (diag_portes) en MAGENTA
        from diag_portes import secteurs
        if "_SP" not in globals(): globals()["_SP"] = secteurs(f, m_pt)
        for S in _SP:
            a, b, c, d_ = S.bounds
            if c < x0 or a > x1 or d_ < y0 or b > y1: continue
            dr.polygon([((px - ox) * sc, (py - oy) * sc) for px, py in S.exterior.coords], outline=(220, 0, 220, 255), fill=(220, 0, 220, 60))
    pts = [((px - ox) * sc, (py - oy) * sc) for px, py in r["h"].exterior.coords]
    dr.line(pts + [pts[0]], fill=(0, 170, 0, 255), width=3)
    ex, ey = (r["e"]["x"] - ox) * sc, (r["e"]["y"] - oy) * sc
    dr.ellipse([ex - 6, ey - 6, ex + 6, ey + 6], fill=(230, 0, 0, 255))
    dr.rectangle([0, 0, CASE, 22], fill=(255, 255, 255, 230))
    dr.text((4, 4), "%s | ecrit %.2f | mesure %.2f | x%.3f" % ((r["e"].get("nom") or "")[:18], r["e"]["surface_ecrite"], r["a"], q),
            fill=(0, 0, 0, 255))
    planche.paste(im.crop((0, 0, CASE, CASE)), ((i % 4) * CASE, (i // 4) * CASE))
d.close()
planche.save(sortie)
print("planche :", sortie)
