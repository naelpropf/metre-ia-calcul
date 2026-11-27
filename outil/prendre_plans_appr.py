"""Pages d'APPRENTISSAGE pour l'IA de tri (D-08) : toutes les pages de plans d'etage des 10 dossiers qui portent
>= 5 surfaces ecrites (meme regle OUI / NON que prendre_plans_test.py), SAUF les 7 pages du banc (reservees au test),
plafonnees a 10 pages par dossier (les plus riches en surfaces), doublons exacts ecartes.
Sortie : plans_appr/<dossier>_<fichier>_p<page>.pdf (une page). Fichiers publics : usage interne de test seulement."""
import glob, hashlib, io, json, os, re, sys, zipfile
import pypdfium2 as pdfium
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
R = json.load(open(os.path.join(ici, "donnees", "s0_resultats.json"), encoding="utf-8"))
OUI = re.compile(r"plan|niveau|rdc|r\+\d|r\d|etage|étage|distribution|pg\d", re.I)
NON = re.compile(r"masse|toiture|tableau|fa[cç]ade|coupe|d[ée]tail|cvc|[ée]lec|plomb|radiateur|vrd|structure|charpente|"
                 r"fluide|chauff|ventil|incendie|ssi|courant|cfo|cfa|r[ée]seau|implantation|situation|terrassement", re.I)
PAR_DOSSIER = 10
banc = {os.path.basename(f) for f in glob.glob(os.path.join(ici, "plans_test", "*.pdf"))}
os.makedirs(os.path.join(ici, "plans_appr"), exist_ok=True)


def tous_les_pdf(data, prefixe=""):
    try: z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile: return {}
    out = {}
    for n in z.namelist():
        if n.lower().endswith(".pdf"): out[prefixe + n] = z.read(n)
        elif n.lower().endswith(".zip"): out.update(tous_les_pdf(z.read(n), prefixe + n + "/"))
    return out


vus, total = set(), 0
for idc, r in sorted(R.items()):
    cand = sorted([x for x in r["detail"] if x["etiquettes_m2"] >= 5 and OUI.search(os.path.basename(x["fichier"]))
                   and not NON.search(x["fichier"])], key=lambda x: -x["etiquettes_m2"])
    if not cand: continue
    pdfs = tous_les_pdf(open(os.path.join(ici, "dce", idc, "dce.zip"), "rb").read())
    pris = 0
    for b in cand:
        if pris >= PAR_DOSSIER: break
        nom = "%s_%s_p%d.pdf" % (idc, re.sub(r"[^\w-]+", "_", os.path.basename(b["fichier"]))[:50], b["page"])
        if nom in banc: continue
        data = next((d for k, d in pdfs.items() if k.endswith(b["fichier"])), None)
        if data is None: continue
        src = pdfium.PdfDocument(data)
        page = src[b["page"] - 1]
        empreinte = hashlib.md5(page.get_textpage().get_text_range().encode("utf-8", "ignore")).hexdigest()
        if empreinte in vus: continue   # meme page deja prise (plan repete d'un lot a l'autre)
        vus.add(empreinte)
        dst = pdfium.PdfDocument.new(); dst.import_pages(src, [b["page"] - 1])
        dst.save(os.path.join(ici, "plans_appr", nom))
        pris += 1; total += 1
    print(idc, ":", pris, "pages d'apprentissage")
print("TOTAL", total, "pages dans plans_appr/")
