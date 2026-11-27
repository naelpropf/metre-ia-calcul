"""S1 (debut) : sur la page de plan qui a le plus d'etiquettes « xx,xx m2 », lire chaque etiquette (nom de piece +
surface + position) et dessiner une image du plan avec les etiquettes reperees en rouge.
Usage : python -I s1_etiquettes.py [id_dossier]"""
import io, json, os, re, sys, zipfile
import pypdfium2 as pdfium
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(ici, "donnees", "s0_resultats.json"), encoding="utf-8"))
idc = sys.argv[1] if len(sys.argv) > 1 else max(R, key=lambda k: R[k]["pages_avec_etiquettes_m2"])
best = max(R[idc]["detail"], key=lambda x: x["etiquettes_m2"])
print("dossier", idc, "| fichier", best["fichier"], "| page", best["page"], "| etiquettes m2 :", best["etiquettes_m2"])
def trouver(data, cible, prefixe=""):
    z = zipfile.ZipFile(io.BytesIO(data))
    for n in z.namelist():
        if n.lower().endswith(".pdf") and (prefixe + n).endswith(cible): return z.read(n)
        if n.lower().endswith(".zip"):
            r = trouver(z.read(n), cible, prefixe + n + "/")
            if r: return r
data = trouver(open(os.path.join(ici, "dce", idc, "dce.zip"), "rb").read(), best["fichier"])
doc = pdfium.PdfDocument(data); p = doc[best["page"] - 1]; W, H = p.get_size()
tp = p.get_textpage()
txt = tp.get_text_range()
RX = re.compile(r"(\d{1,4}[,.]\d{1,2})\s?m(?:2|²)")
etiq = []
for m in RX.finditer(txt):
    # position de la surface sur la page (rectangles des caracteres)
    try:
        boxes = [tp.get_charbox(i) for i in range(m.start(), m.end())]
        l = min(b[0] for b in boxes); b_ = min(b[1] for b in boxes); r = max(b[2] for b in boxes); t = max(b[3] for b in boxes)
    except Exception:
        continue
    avant = txt[max(0, m.start() - 60):m.start()]
    nom = [x.strip() for x in re.split(r"[\r\n]+", avant) if x.strip()]
    etiq.append({"surface_m2": float(m.group(1).replace(",", ".")), "nom": nom[-1][:40] if nom else "", "x": round(l), "y": round(b_)})
print("etiquettes lues :", len(etiq), "| total des surfaces :", round(sum(e["surface_m2"] for e in etiq), 2), "m2")
for e in etiq[:15]: print("  %-40s %8.2f m2  (x %d, y %d)" % (e["nom"], e["surface_m2"], e["x"], e["y"]))
# image du plan, etiquettes entourees
ech = 2000 / max(W, H)
img = p.render(scale=ech).to_pil().convert("RGB")
from PIL import ImageDraw
d = ImageDraw.Draw(img)
for e in etiq:
    x, y = e["x"] * ech, (H - e["y"]) * ech
    d.rectangle([x - 6, y - 14, x + 60, y + 6], outline=(220, 0, 0), width=3)
os.makedirs(os.path.join(ici, "sorties"), exist_ok=True)
sortie = os.path.join(ici, "sorties", "s1_%s_etiquettes.png" % idc)
img.save(sortie)
json.dump(etiq, open(os.path.join(ici, "sorties", "s1_%s_etiquettes.json" % idc), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("image :", sortie)
