"""CASSURE 1 (27/11) : l'outil lit le DOSSIER de consultation, pas une page.
Brique 1 : inventaire d'un DCE (zip) -- chaque fichier classe par TYPE d'apres son nom :
  plan_niveau (plans d'etage : pieces, murs), coupe (hauteurs), facade (hauteurs de fenetres), nomenclature
  (menuiseries : dimensions), surfaces (tableau des surfaces : arbitre quand le plan n'en ecrit pas), cctp (perimetre
  des travaux), dpgf (quantites de la maitrise d'oeuvre : verite terrain), detail, toiture, masse, autre.
Lecture seule du zip (rien n'est execute). Usage : python -I dossier.py [numero_dossier]"""
import collections, glob, os, re, sys, zipfile

ici = os.path.dirname(os.path.abspath(__file__))
REGLES = [   # l'ordre compte : la 1re regle qui colle gagne
    ("cctp", r"cctp"),
    ("diagnostic", r"plomb|amiante|crep|\bdiag"),   # peinture sur plomb / amiante : change methode et prix
    ("dpgf", r"dpgf|dqe|bpu|d[ée]composition du prix"),
    ("surfaces", r"tableau.{0,8}surface|surfaces? (utiles?|habitables?)|tableausurface"),
    ("nomenclature", r"nomencl|tableau des portes|cahier de menuis|menuiseries? (int|ext)"),
    ("coupe", r"coupe"),
    ("facade", r"fa[cç]ade|[ée]l[ée]vation"),
    ("detail", r"d[ée]tail"),
    ("toiture", r"toiture|couverture"),
    ("masse", r"plan de masse|masse|situation|localisation g"),
    ("plan_niveau", r"plan|rdc|r\+?\d|niveau|[ée]tage|rez|sous-sol|distribution"),
]


def type_de(nom):
    b = os.path.basename(nom)
    return next((t for t, r in REGLES if re.search(r, b, re.I)), "autre")


def inventaire(chemin_zip):
    """{type: [noms dans le zip]} pour les PDF et tableurs"""
    inv = collections.defaultdict(list)
    for n in zipfile.ZipFile(chemin_zip).namelist():
        if n.lower().endswith((".pdf", ".xlsx", ".xls", ".xlsm")):
            inv[type_de(n)].append(n)
    return inv


RX_NIVEAU = re.compile(r"(?<![\d,.])\+\s?(\d{1,2}[.,]\d{2})(?![\d])")


def texte_pdf(donnees):
    """texte de toutes les pages d'un PDF donne en memoire (octets) -- pdfium, lecture seule"""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(donnees)
    t = []
    for p in doc:
        tp = p.get_textpage(); t.append(tp.get_text_range()); tp.close(); p.close()
    doc.close()
    return "\n".join(t)


def hauteurs_coupes(chemin_zip):
    """Brique 2 : HAUTEURS lues dans les COUPES (cotes de niveau « +2.78 »). Rend un dict :
    niveaux (m) trouves, hauteur sous plafond probable (niveau le plus frequent entre 2,20 et 4,50 m), source.
    ESTIMATION assumee : sans relier chaque piece a sa coupe, c'est une valeur de DOSSIER, affichee comme telle."""
    Z = zipfile.ZipFile(chemin_zip)
    niveaux, plafonds, fichiers = [], [], []
    for n in inventaire(chemin_zip).get("coupe", []):
        if not n.lower().endswith(".pdf"): continue
        try:
            t = texte_pdf(Z.read(n))
        except Exception:
            continue
        trouve = False
        for mo in RX_NIVEAU.finditer(t):
            v = float(mo.group(1).replace(",", ".")); niveaux.append(v); trouve = True
            # comme le metreur : la cote ecrite A COTE du mot plafond / FP / HSP (27/11 : la 1re version prenait
            # le haut d'un RAMPANT, 3,46 m, au lieu du faux plafond 2,76-2,87 m sur la Guyane)
            autour = t[max(0, mo.start() - 40):mo.end() + 40]
            if 2.0 <= v <= 4.5 and re.search(r"plafond|\bF\.?P\b|H\.?S\.?P", autour, re.I): plafonds.append(round(v, 2))
        if trouve: fichiers.append(os.path.basename(n))
    if plafonds:
        p = sorted(plafonds)
        return {"niveaux": sorted(set(niveaux)), "hauteur": p[len(p) // 2], "plage": (p[0], p[-1]),
                "n_cotes": len(p), "methode": "cotes écrites à côté de « plafond / FP »", "source": fichiers}
    hsp = sorted(round(x, 2) for x in niveaux if 2.2 <= x <= 4.5)
    if not hsp:
        return {"niveaux": sorted(set(niveaux)), "hauteur": None, "source": fichiers}
    # sinon : le PREMIER palier au-dessus du sol (les plafonds sont sous les toitures et les acroteres)
    palier = [x for x in hsp if x - hsp[0] < 0.15]
    return {"niveaux": sorted(set(niveaux)), "hauteur": palier[len(palier) // 2], "plage": (palier[0], palier[-1]),
            "n_cotes": len(palier), "methode": "premier palier de niveaux au-dessus de 2,20 m", "source": fichiers}


RX_LIGNE_SURF = re.compile(r"^\s*([A-Za-zÀ-ÿ'’/+\-\. ]{3,60}?)\s+(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:m[2²])?\s*$")


def tableau_surfaces(chemin_zip):
    """Brique 3 : TABLEAU DES SURFACES du dossier -> [(nom de piece, surface m2)].
    Sert de « corrige » quand le plan n'ecrit pas les surfaces, et de controle des etiquettes lues sur le plan.
    Les lignes de total (total, sous-total, synthese) sont ecartees."""
    Z = zipfile.ZipFile(chemin_zip)
    out = []
    for n in inventaire(chemin_zip).get("surfaces", []):
        if not n.lower().endswith(".pdf"): continue
        try:
            t = texte_pdf(Z.read(n))
        except Exception:
            continue
        for ligne in t.splitlines():
            mo = RX_LIGNE_SURF.match(ligne)
            if not mo: continue
            nom = mo.group(1).strip(" .-")
            if re.search(r"total|synth|surface|niveau|phase|indice|page", nom, re.I) or len(nom) < 3: continue
            v = float(mo.group(2).replace(",", "."))
            if 0.5 <= v <= 2000: out.append((nom, v, os.path.basename(n)))
    return out


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def rapprocher(tableau, etiquettes_plan, tol=0.005):
    """relie chaque ligne du tableau a une etiquette du plan : meme surface (a 0,5 %) ET un mot du nom en commun.
    Rend [(ligne, etiquette ou None)]"""
    res = []
    for nom, v, src in tableau:
        mots = set(_norm(nom).split())
        cand = [e for e in etiquettes_plan if e.get("surface_ecrite") and abs(e["surface_ecrite"] / v - 1) <= tol]
        bons = [e for e in cand if mots & set(_norm(e.get("nom") or "").split())]
        res.append(((nom, v), (bons or cand or [None])[0]))
    return res


RX_BLOC_MENU = re.compile(
    r"Quantit[ée]\s+((?:\d+\s+)+)Type\s+((?:[A-Z][A-Z0-9]*\s+)+?)Largeur[^0-9]{0,40}?((?:\d+,\d+\s+)+)Hauteur[^0-9]{0,40}?((?:\d+,\d+\s*)+)", re.I)


def nomenclature_menuiseries(chemin_zip):
    """Brique 4 : NOMENCLATURE / cahier des menuiseries -> [(type, largeur m, hauteur m, quantite)].
    Format reconnu (Guyane) : blocs « Quantite ... Type ... Largeur ... Hauteur ... ». Les nomenclatures dont les
    dimensions sont DESSINEES (Numericum : codes seuls) ne sont pas lisibles par le texte -> liste vide, dit tel quel."""
    Z = zipfile.ZipFile(chemin_zip)
    out = []
    for n in inventaire(chemin_zip).get("nomenclature", []):
        if not n.lower().endswith(".pdf"): continue
        try:
            t = re.sub(r"\s+", " ", texte_pdf(Z.read(n)))
        except Exception:
            continue
        for mo in RX_BLOC_MENU.finditer(t):
            q = [int(x) for x in mo.group(1).split()]
            ty = mo.group(2).split()
            L = [float(x.replace(",", ".")) for x in mo.group(3).split()]
            H = [float(x.replace(",", ".")) for x in mo.group(4).split()]
            for i in range(min(len(ty), len(L), len(H))):
                out.append((ty[i], L[i], H[i], q[i] if i < len(q) else None, os.path.basename(n)))
    return out


def cctp_peinture(chemin_zip):
    """Brique 5 : le PERIMETRE du lot peinture lu dans le CCTP (version a regles, gratuite) -> [(article, localisation)].
    Chaque « Localisation : ... » est relie au dernier TITRE d'article en majuscules qui le precede. Ne transforme pas
    encore le texte en regles de calcul (travail de l'IA, cassure 2) : sert a MONTRER a l'operateur ce qui est a peindre."""
    Z = zipfile.ZipFile(chemin_zip)
    out = []
    for n in inventaire(chemin_zip).get("cctp", []):
        b = os.path.basename(n)
        if not (n.lower().endswith(".pdf") and re.search(r"peint", b, re.I)): continue
        try:
            t = texte_pdf(Z.read(n))
        except Exception:
            continue
        lignes = [l.strip() for l in t.splitlines() if l.strip()]
        titre = None
        for i, l in enumerate(lignes):
            mt = re.match(r"^(?:\d[\w.\-]*\s+)?([A-ZÀÂÉÈÊÎÔÛÇ][A-ZÀÂÉÈÊÎÔÛÇ0-9 '’/,\-()]{8,90})$", l)
            # les en-tetes de page (architecte, maitre d'ouvrage, BET, CCTP) ne sont pas des titres d'article
            if mt and sum(c.islower() for c in l) == 0 and not re.search(r"ARCHITECTE|MANDATAIRE|MA[IÎ]TRE|\bBET\b|CCTP|LOT\s|PAGE", l):
                titre = mt.group(1).strip()
            ml = re.match(r"^Localisation\s*:?\s*(.*)$", l, re.I)
            if ml:
                txt = ml.group(1)
                j = i + 1
                while len(txt) < 160 and j < len(lignes) and not re.match(r"^(Localisation|\d[\w.\-]*\s+[A-Z])", lignes[j]):
                    txt += " " + lignes[j]; j += 1
                out.append((titre or "?", re.sub(r"\s+", " ", txt).strip()[:220], b))
    return out


def contexte(chemin_plan):
    """Ce que le DOSSIER apprend sur un plan : hauteur (coupes) et tableau des surfaces.
    Le dossier = les 7 premiers caracteres du nom du plan (numero de consultation) -> dce/<numero>/dce.zip."""
    num = os.path.basename(chemin_plan)[:7]
    z = os.path.join(ici, "dce", num, "dce.zip")
    if not os.path.exists(z): return {"dossier": None}
    h = hauteurs_coupes(z)
    return {"dossier": num, "hauteur": h.get("hauteur"), "hauteur_plage": h.get("plage"),
            "hauteur_methode": h.get("methode"), "hauteur_source": h.get("source"),
            "tableau": tableau_surfaces(z), "menuiseries": nomenclature_menuiseries(z), "cctp": cctp_peinture(z), "inventaire": {k: len(v) for k, v in inventaire(z).items()}}


def controle_tableau(tableau, etiquettes_plan, tol=0.005):
    """{id(etiquette): message} : desaccord entre le plan et le tableau des surfaces (meme nom, surface differente)"""
    msg = {}
    for nom, v, src in tableau:
        mots = set(_norm(nom).split()) - {"de", "du", "la", "le", "salle", "local"}
        for e in etiquettes_plan:
            me = set(_norm(e.get("nom") or "").split())
            if mots and mots <= me and e.get("surface_ecrite") and abs(e["surface_ecrite"] / v - 1) > tol:
                msg[id(e)] = ("tableau des surfaces : %s = %.2f m² (plan : %.2f m²)" % (nom, v, e["surface_ecrite"])).replace(".", ",")
    return msg


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    zips = sorted(glob.glob(os.path.join(ici, "dce", sys.argv[1] if len(sys.argv) > 1 else "*", "dce.zip")))
    total = collections.Counter()
    for z in zips:
        inv = inventaire(z)
        c = {t: len(v) for t, v in inv.items()}
        total.update(c)
        print("%s %4d fichiers | %s" % (os.path.basename(os.path.dirname(z)), sum(c.values()), dict(sorted(c.items()))))
    print("TOTAL", dict(sorted(total.items())))
