"""Planche d'une page neuve : etiquettes (rouge = coupee par le bord, bleu = sure, orange = mesuree fausse, gris = non mesuree)
et contours trouves. Usage : python voir_neuf.py <debut du nom de la page> <sortie.png>"""
import glob, os, sys
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
import metre_v3, pypdfium2 as pdfium
from metre import normaliser, echelle_par_cotes
from PIL import Image, ImageDraw
f = glob.glob(os.path.join(ici, "plans_neufs", glob.escape(sys.argv[1]) + "*.pdf"))[0]
metre_v3.PARALLELE = 1
old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
R = metre_v3.pieces_v3(f)
sys.stdout.close(); sys.stdout = old
ch = normaliser(f); m = echelle_par_cotes(ch, 0)[0]
d = pdfium.PdfDocument(ch); W, H = d[0].get_size()
sc = 2000 / max(W, H)
im = d[0].render(scale=sc, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB")
dr = ImageDraw.Draw(im, "RGBA")
for r in R:
    e = r["e"]; x, y = e["x"] * sc, e["y"] * sc
    coul = (220, 0, 0) if e.get("coupee_bord") else (0, 90, 255) if r["sure"] else (255, 140, 0) if r.get("a") else (120, 120, 120)
    if r.get("h") is not None and getattr(r["h"], "exterior", None) is not None:
        dr.polygon([(px * sc, py * sc) for px, py in r["h"].exterior.coords], outline=coul + (255,), fill=coul + (40,))
    dr.ellipse([x - 6, y - 6, x + 6, y + 6], fill=coul + (255,))
    dr.text((x + 7, y - 6), "%.1f/%s" % (e["surface_ecrite"], "%.1f" % r["a"] if r.get("a") else "-"), fill=coul + (255,))
im.save(sys.argv[2])
print("pieces %d | coupees %d | sures %d | m=%.4f | page %.0f x %.0f m" % (len(R), sum(1 for r in R if r["e"].get("coupee_bord")), sum(r["sure"] for r in R), m or 0, W * (m or 0), H * (m or 0)))
