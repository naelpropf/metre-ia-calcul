"""Inventaire des VERITES TERRAIN dans les DCE telecharges (26/11) : DPGF / DQE du lot peinture (quantites de la
maitrise d'oeuvre), tableaux des surfaces, tableaux des portes / nomenclatures menuiseries.
Lecture seule des zips (rien n'est execute) ; les tableurs peinture sont copies dans sorties/verites/<dossier>/.
Sortie : donnees/verites.json + resume a l'ecran.  Usage : python -I inventaire_dpgf.py"""
import glob, json, os, re, sys, zipfile
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
PEINT = re.compile(r"peint", re.I)
PRIX = re.compile(r"DPGF|DQE|BPU|D\.?P\.?G\.?F|decomposition|d[ée]composition", re.I)
SURF = re.compile(r"tableau.{0,5}surface|surfaces", re.I)
MENU = re.compile(r"tableau des portes|nomenclature.{0,20}menuis|menuiseries?.{0,10}(tableau|nomenclature)", re.I)
UNITE = re.compile(r"^(m2|m²|ml|u|m)$", re.I)


def quantites_tableur(chemin):
    """lignes (designation, unite, quantite MOE) d'un tableur ; quantite = 1re valeur numerique > 0 apres l'unite"""
    out = []
    try:
        if chemin.lower().endswith((".xlsx", ".xlsm")):
            import openpyxl
            wb = openpyxl.load_workbook(chemin, data_only=True, read_only=True)
            lignes = [r for ws in wb.worksheets for r in ws.iter_rows(values_only=True)]
        elif chemin.lower().endswith(".xls"):
            import xlrd
            wb = xlrd.open_workbook(chemin)
            lignes = [sh.row_values(i) for sh in wb.sheets() for i in range(sh.nrows)]
        else:
            return None
    except Exception as ex:
        return "illisible : %s" % ex
    for r in lignes:
        v = [x for x in r if x not in (None, "")]
        for i, x in enumerate(v):
            if isinstance(x, str) and UNITE.match(x.strip()):
                des = " ".join(str(y) for y in v[:i] if isinstance(y, str))[:90]
                q = next((y for y in v[i + 1:] if isinstance(y, (int, float)) and y > 0), None)
                if q is not None and PEINT.search(des): out.append((des, x.strip(), round(float(q), 2)))
                break
    return out


res = {}
for z in sorted(glob.glob(os.path.join(ici, "dce", "*", "dce.zip"))):
    dos = os.path.basename(os.path.dirname(z))
    try:
        Z = zipfile.ZipFile(z); noms = Z.namelist()
    except Exception as ex:
        print(dos, "zip illisible", ex); continue
    b = lambda n: n.split("/")[-1]
    r = {"prix_peinture": [], "surfaces": [b(n) for n in noms if SURF.search(b(n))],
         "menuiseries": [b(n) for n in noms if MENU.search(b(n))]}
    for n in noms:
        if PEINT.search(b(n)) and PRIX.search(b(n)) and b(n).lower().endswith((".xlsx", ".xls", ".xlsm")):
            d = os.path.join(ici, "sorties", "verites", dos); os.makedirs(d, exist_ok=True)
            p = os.path.join(d, re.sub(r"[^\w.\- ]", "_", b(n)))
            open(p, "wb").write(Z.read(n))
            q = quantites_tableur(p)
            r["prix_peinture"].append({"fichier": b(n), "lignes_peinture_avec_quantite": q})
    res[dos] = r
    nq = sum(len(x["lignes_peinture_avec_quantite"]) for x in r["prix_peinture"] if isinstance(x["lignes_peinture_avec_quantite"], list))
    print("%s | tableur prix peinture %d (lignes peinture chiffrees %d) | tableaux surfaces %d | menuiseries %d" % (
        dos, len(r["prix_peinture"]), nq, len(r["surfaces"]), len(r["menuiseries"])))
json.dump(res, open(os.path.join(ici, "donnees", "verites.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
