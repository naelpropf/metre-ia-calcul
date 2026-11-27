"""S0 -- les plans des dossiers peinture sont-ils des PDF VECTORIELS (traits lisibles) ou des SCANS (images) ?
Declare AVANT la mesure (regle 8) :
- plan = page de PDF au moins format A3 (un cote > 1 190 pt), dans un fichier du dossier.
- page VECTORIELLE : >= 500 objets traces et images < 50 % de la page ; SCAN : une image couvre >= 50 % de la page
  et < 500 traces ; sinon MIXTE.
- un dossier est « vectoriel » si >= 70 % de ses pages de plan sont vectorielles.
- SEUIL : >= 6 dossiers vectoriels sur 10 -> on code la methode « lecture des traits ». Sinon : methode image d'abord.
- on note aussi : etiquettes de surface lisibles (texte « m2 » / « m² » sur la page) -> l'astuce des etiquettes marche-t-elle ?
Fichiers non fiables : on n'extrait que les .pdf (et les .zip imbriques), noms nettoyes, jamais executes."""
import io, json, os, re, sys, zipfile, collections
import pypdfium2 as pdfium
import pypdfium2.raw as raw
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(ici, "dce")
def pdfs_du_zip(data, prefixe=""):
    try: z = zipfile.ZipFile(io.BytesIO(data))
    except Exception: return
    for n in z.namelist():
        b = n.lower()
        if b.endswith(".pdf"): yield prefixe + n, z.read(n)
        elif b.endswith(".zip"):
            yield from pdfs_du_zip(z.read(n), prefixe + n + "/")
def analyse_page(p):
    W, H = p.get_size(); aire = W * H
    tr = img = txt = 0; couv = 0.0
    for o in p.get_objects(max_depth=3):
        if o.type == raw.FPDF_PAGEOBJ_PATH: tr += 1
        elif o.type == raw.FPDF_PAGEOBJ_TEXT: txt += 1
        elif o.type == raw.FPDF_PAGEOBJ_IMAGE:
            img += 1
            try:
                l, b, r, t = o.get_pos(); couv = max(couv, (r - l) * (t - b) / aire)
            except Exception: pass
    if tr >= 500 and couv < 0.5: k = "vectoriel"
    elif couv >= 0.5 and tr < 500: k = "scan"
    else: k = "mixte"
    tp = p.get_textpage(); s = tp.get_text_range(); tp.close()
    m2 = len(re.findall(r"\d[\d ,.]*\s?m(?:2|²)", s))
    return k, tr, txt, round(couv, 2), m2
res = {}
for idc in sorted(os.listdir(D)):
    z = os.path.join(D, idc, "dce.zip")
    if not os.path.exists(z): continue
    pages = []
    for nom, data in pdfs_du_zip(open(z, "rb").read()):
        try: doc = pdfium.PdfDocument(data)
        except Exception: continue
        for i in range(min(len(doc), 6)):
            p = doc[i]; W, H = p.get_size()
            if max(W, H) > 1190:
                k, tr, txt, couv, m2 = analyse_page(p)
                pages.append({"fichier": nom[-70:], "page": i + 1, "type": k, "traces": tr, "textes": txt, "image_max": couv, "etiquettes_m2": m2})
            p.close()
        doc.close()
    c = collections.Counter(x["type"] for x in pages)
    n = len(pages)
    part = c["vectoriel"] / n if n else 0
    res[idc] = {"pages_plan": n, "types": dict(c), "part_vectoriel": round(part, 2), "verdict": "vectoriel" if part >= 0.7 else ("aucun plan" if not n else "non"),
                "pages_avec_etiquettes_m2": sum(1 for x in pages if x["etiquettes_m2"] >= 3), "detail": pages}
    print("%s : %3d pages de plan | %s | part vectorielle %.0f %% | pages avec >= 3 etiquettes m2 : %d -> %s" % (
        idc, n, dict(c), 100 * part, res[idc]["pages_avec_etiquettes_m2"], res[idc]["verdict"]), flush=True)
json.dump(res, open(os.path.join(ici, "donnees", "s0_resultats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
nv = sum(1 for r in res.values() if r["verdict"] == "vectoriel")
print("\nDOSSIERS VECTORIELS : %d sur %d -> %s" % (nv, len(res), "SEUIL PASSE" if nv >= 6 else "SEUIL RATE"))
