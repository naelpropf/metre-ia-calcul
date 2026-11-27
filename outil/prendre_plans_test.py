"""Jeu d'essai S1 : pour chaque dossier, la page de plan qui a le plus de surfaces ecrites (>= 3), extraite en PDF
d'une page dans plans_test/. Les fichiers viennent de dossiers publics : usage interne de test seulement."""
import io, json, os, re, sys, zipfile
import pypdfium2 as pdfium
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(ici, "donnees", "s0_resultats.json"), encoding="utf-8"))
os.makedirs(os.path.join(ici, "plans_test"), exist_ok=True)
def trouver(data, cible, prefixe=""):
    try: z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile: return None
    for n in z.namelist():
        if n.lower().endswith(".pdf") and (prefixe + n).endswith(cible): return z.read(n)
        if n.lower().endswith(".zip"):
            r = trouver(z.read(n), cible, prefixe + n + "/")
            if r: return r
# Regle fixee AVANT de mesurer le moteur (25/11) : un plan d'ETAGE d'architecte -- nom du fichier avec
# plan / niveau / RDC / R+ / etage / distribution, et SANS masse / toiture / tableau / facade / coupe / detail / CVC /
# electricite / plomberie / radiateur / VRD / structure ; puis la page qui a le plus de surfaces ecrites (>= 3).
OUI = re.compile(r"plan|niveau|rdc|r\+\d|r\d|etage|étage|distribution|pg\d", re.I)
NON = re.compile(r"masse|toiture|tableau|fa[cç]ade|coupe|d[ée]tail|cvc|[ée]lec|plomb|radiateur|vrd|structure|charpente|"
                 r"fluide|chauff|ventil|incendie|ssi|courant|cfo|cfa|r[ée]seau|implantation|situation|terrassement", re.I)
for idc, r in sorted(R.items()):
    cand = sorted([x for x in r["detail"] if x["etiquettes_m2"] >= 3 and OUI.search(os.path.basename(x["fichier"]))
                   and not NON.search(x["fichier"])], key=lambda x: -x["etiquettes_m2"])
    if not cand: print(idc, ": aucune page avec surfaces ecrites"); continue
    b = cand[0]
    data = trouver(open(os.path.join(ici, "dce", idc, "dce.zip"), "rb").read(), b["fichier"])
    src = pdfium.PdfDocument(data); dst = pdfium.PdfDocument.new()
    dst.import_pages(src, [b["page"] - 1])
    nom = "%s_%s_p%d.pdf" % (idc, re.sub(r"[^\w-]+", "_", os.path.basename(b["fichier"]))[:50], b["page"])
    dst.save(os.path.join(ici, "plans_test", nom))
    print(idc, "->", nom, "| surfaces ecrites :", b["etiquettes_m2"])
