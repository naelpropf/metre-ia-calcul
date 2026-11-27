"""Batterie de causes : pourquoi l'outil v3 rate sur les dossiers neufs (regle ecrite avant au journal du 27/11)."""
import glob, json, os, re, sys, collections
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
from metre import normaliser, echelle_par_cotes, page_plumber
import pypdfium2 as pdfium
CACHE = os.path.join(ici, "sorties", "causes_neufs_pages.json")
info = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
for f in sorted(glob.glob(os.path.join(ici, "sorties", "neufs_v3", "*.json"))):
    nom = os.path.basename(f)[:-5]
    if nom in info: continue
    pdf = glob.glob(os.path.join(ici, "plans_neufs", glob.escape(nom[:60]) + "*.pdf"))
    if not pdf: continue
    try:
        ch = normaliser(pdf[0]); m, v, p = echelle_par_cotes(ch, 0)
        d = pdfium.PdfDocument(ch); W, H = d[0].get_size(); d.close()
        pl = page_plumber(ch); n = len(pl.lines) + len(pl.rects) + len(pl.curves)
        info[nom] = {"m": m, "voix": v, "part": p, "page_m": max(W, H) * m if m else 0, "objets": n}
    except Exception as e:
        info[nom] = {"erreur": str(e)[:80]}
    json.dump(info, open(CACHE, "w", encoding="utf-8"))
    print("  page", nom[:50], info[nom], flush=True)
R = []
for f in sorted(glob.glob(os.path.join(ici, "sorties", "neufs_v3", "*.json"))):
    J = json.load(open(f, encoding="utf-8")); nom = J["page"]; I = info.get(nom, {})
    plusieurs = bool(re.search(r"\bet\b|_et_|-et-", nom, re.I))
    for p in J["detail"]:
        e = (p["mesuree"] / p["ecrite"] - 1) if (p["mesuree"] and p["ecrite"]) else None
        R.append({"sure": p["sure"],
                  "dossier": nom.split("_")[0],
                  "coupee par le bord": "oui" if p["coupee_bord"] else "non",
                  "echelle": "inconnue" if not I.get("m") else "ecrite (garde-fou)" if I.get("voix") == -1 else "faible (<20 voix)" if I.get("voix", 0) < 20 else "solide",
                  "page (m)": "?" if not I.get("page_m") else "<40 m" if I["page_m"] < 40 else "40-90 m" if I["page_m"] < 90 else ">90 m",
                  "niveaux sur la page": "plusieurs" if plusieurs else "un",
                  "densite": "?" if not I.get("objets") else "<20k objets" if I["objets"] < 20000 else "20-80k" if I["objets"] < 80000 else ">80k",
                  "surface ecrite": "<5 m2" if p["ecrite"] < 5 else "5-15" if p["ecrite"] < 15 else "15-40" if p["ecrite"] < 40 else ">40",
                  "nom": "circulation" if re.search(r"circ|d.gag|hall|couloir", (p["nom"] or ""), re.I) else "wc/sanitaire" if re.search(r"wc|sanit|douche", (p["nom"] or ""), re.I) else "bureau" if re.search(r"bureau", (p["nom"] or ""), re.I) else "autre/vide",
                  "mode": "sure" if p["sure"] else "non mesuree" if e is None else "trop grande" if e > 0.01 else "trop petite"})
s = np.mean([r["sure"] for r in R]); print("\n%d pieces | sures %.1f %%\n" % (len(R), 100 * s))
causes = []
for fct in ["dossier", "coupee par le bord", "echelle", "page (m)", "niveaux sur la page", "densite", "surface ecrite", "nom"]:
    g = collections.defaultdict(list)
    for r in R: g[r[fct]].append(r["sure"])
    print(fct.upper())
    for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
        reste = [r["sure"] for r in R if r[fct] != k]; tg, tr = np.mean(v), (np.mean(reste) if reste else 0)
        mark = "  <<< CAUSE PROBABLE" if len(v) >= 30 and tr > 0 and tg <= 0.5 * tr else ""
        if mark: causes.append("%s = %s (%.0f %% sures contre %.0f %% ailleurs, %d pieces)" % (fct, k, 100 * tg, 100 * tr, len(v)))
        print("    %-22s %5d pieces | sures %3.0f %%%s" % (k, len(v), 100 * tg, mark))
print("\nMODES D'ECHEC :", dict(collections.Counter(r["mode"] for r in R)))
print("\nCAUSES PROBABLES :"); [print("  -", c) for c in causes]
