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
old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
R = metre_v3.pieces_v3(f)
sys.stdout.close(); sys.stdout = old
import matiere
# matiere de la passe PRINCIPALE (celle qui donne la plupart des pieces) : ce que l'outil a pris pour des murs, en rouge
old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
matiere.pieces_par_matiere(f, verbeux=False)
sys.stdout.close(); sys.stdout = old
MAT = matiere.DERNIERE_MATIERE[0] if matiere.DERNIERE_MATIERE else None
m_pt = matiere.DERNIERE_MATIERE[1] if matiere.DERNIERE_MATIERE else None
FILTRE = os.environ.get("NOMS")   # ex. NOMS="CAVE 11,CAVE 3" : seulement ces pieces


def rapport(r):
    return r["a"] / r["e"]["surface_ecrite"] if r.get("a") and r["e"].get("surface_ecrite") else None


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
    pts =[((px - ox) * sc, (py - oy) * sc) for px, py in r["h"].exterior.coords]
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
