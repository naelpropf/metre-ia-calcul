"""ARBITRE APPRIS (27/11) pour les plans SANS surface ecrite : l'IA juge si un contour est JUSTE, a partir des indices
du metreur (etiquettes dedans, porte au coeur, bord meuble, bord en mur/vitre/porte, forme) -- sans la surface ecrite.
Exemples : plans du banc avec surfaces ecrites (juste <= 1 %, faux > 3 % ; entre les deux : ignore).
Test ecrit AVANT (26/11, 03 h) : un dossier laisse de cote a chaque fois (jamais vu a l'entrainement).
  Seuil de proba choisi SUR L'ENTRAINEMENT (precision >= 95 % des « juste »).
  REUSSI si, sur les dossiers laisses de cote, poole : precision des « juste » >= 90 % ET >= 40 % des justes retenus.
  Sinon ECHEC (on ne retouche pas le seuil).
Cache des indices par plan : sorties/cache_arbitre/<plan>.json (le calcul matiere est long, une fois suffit).
Usage : python arbitre.py [codes de plans...]   (defaut : tous les plans_test)
RESULTAT A (27/11, 03 h 30) : ECHEC -- precision 86 % / justes retenus 79 % ; 53 justes seulement pour apprendre.
VERSION B (ecrite AVANT de la lancer, 27/11) : option --b. Plus d'exemples : plans_test + plans_appr (47 pages des MEMES
7 dossiers ; on laisse toujours un DOSSIER ENTIER de cote). Portes lues sur le plan (matiere.portes : milieu de l'ouverture),
plus dans la base d'objets. Indices de bord retires (aucun signal en A). MEMES seuils (>= 90 % precision, >= 40 % retenus)."""
import glob, gzip, json, math, os, sys
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
CACHE = os.path.join(ici, "sorties", "cache_arbitre"); os.makedirs(CACHE, exist_ok=True)
COLS = ["n_etiq", "portes_coeur", "portes_bord", "bord_meuble", "bord_mur", "bord_vide", "aire_m2", "compacite",
        "convexite", "n_sommets", "rect", "allong"]


def portes_plan(f, m):
    import matiere
    from metre import normaliser, lire_textes, page_plumber
    ch = normaliser(f); W, H, _, _ = lire_textes(ch, 0)
    doc = matiere.pdfium.PdfDocument(ch); OX, OY = matiere.origine(doc[0]); doc.close()
    conv = lambda p, dy=H - OY: (p[0] - OX, p[1] - dy)
    return [((c.coords[0][0] + c.coords[-1][0]) / 2, (c.coords[0][1] + c.coords[-1][1]) / 2)
            for c in matiere.portes(page_plumber(ch), m, conv)]


def indices_plan(f, b=False):
    import matiere
    from shapely.geometry import Point
    from shapely import prepared
    nom = os.path.basename(f)[:-4]
    fc = os.path.join(CACHE + ("_b" if b else ""), nom[:80] + ".json"); os.makedirs(os.path.dirname(fc), exist_ok=True)
    if os.path.exists(fc) and os.path.getmtime(fc) >= os.path.getmtime(f): return json.load(open(fc, encoding="utf-8"))
    res = matiere.pieces_par_matiere(f, verbeux=False, rendre=True)
    m = matiere.DERNIERE_MATIERE[1]
    etiq = [Point(e["x"], e["y"]) for e, a, h in res]
    fo = glob.glob(os.path.join(ici, "sorties", "objets", nom[:40] + "*.jsonl.gz"))
    obj = []
    if fo:
        for l in gzip.open(fo[0], "rt", encoding="utf-8"):
            x = json.loads(l)
            if x.get("classe") in ("porte", "mur", "vitre", "mobilier"):
                obj.append(((x["_x0"] + x["_x1"]) / 2 / m, (x["_y0"] + x["_y1"]) / 2 / m, x["classe"]))
    P = np.array([(x, y) for x, y, c in obj]) if obj else np.zeros((0, 2)); C = np.array([c for x, y, c in obj])
    portes = (np.array(portes_plan(f, m)).reshape(-1, 2) if b else (P[C == "porte"] if len(P) else P))
    out = []
    for e, a, h in res:
        if not a: continue
        ec = abs(a / e["surface_ecrite"] - 1)
        if 0.01 < ec <= 0.03: continue
        hp = prepared.prep(h)
        coeur = h.buffer(-0.40 / m)
        pc = sum(1 for x, y in portes if not coeur.is_empty and coeur.contains(Point(x, y)))
        pb = sum(1 for x, y in portes if h.exterior.distance(Point(x, y)) * m < 0.40)
        n = max(int(h.exterior.length * m / 0.10), 8); cnt = {"mobilier": 0, "mur": 0, "vitre": 0, "porte": 0, "": 0}
        for i in range(n):
            q = h.exterior.interpolate(i / n, normalized=True)
            if not len(P): cnt[""] += 1; continue
            d = np.hypot(P[:, 0] - q.x, P[:, 1] - q.y); j = d.argmin()
            cnt[C[j] if d[j] * m < 0.15 else ""] += 1
        r = h.minimum_rotated_rectangle; c = list(r.exterior.coords)
        d1, d2 = sorted([math.dist(c[0], c[1]), math.dist(c[1], c[2])])
        out.append({"juste": int(ec <= 0.01), "n_etiq": sum(hp.contains(p) for p in etiq), "portes_coeur": pc, "portes_bord": pb,
                    "bord_meuble": cnt["mobilier"] / n, "bord_mur": (cnt["mur"] + cnt["vitre"] + cnt["porte"]) / n, "bord_vide": cnt[""] / n,
                    "aire_m2": a, "compacite": 4 * math.pi * h.area / h.length ** 2, "convexite": h.area / h.convex_hull.area,
                    "n_sommets": len(h.exterior.coords), "rect": h.area / r.area if r.area else 0, "allong": d2 / d1 if d1 else 0})
    json.dump(out, open(fc, "w", encoding="utf-8"))
    return out


if __name__ == "__main__":
    from sklearn.ensemble import HistGradientBoostingClassifier
    B = "--b" in sys.argv
    if B: COLS = [c for c in COLS if not c.startswith("bord_")]
    dossiers = ["plans_test", "plans_appr"] if B else ["plans_test"]
    codes = [a for a in sys.argv[1:] if not a.startswith("--")] or sorted({os.path.basename(f)[:7] for f in glob.glob(os.path.join(ici, "plans_test", "*.pdf"))})
    data = {}
    for k in codes:
        for f in sorted(f for d in dossiers for f in glob.glob(os.path.join(ici, d, k + "*.pdf"))):
            try: L = indices_plan(f, B)
            except Exception as e: print("  ", os.path.basename(f)[:50], "ERREUR", e); continue
            data.setdefault(k, []).extend(L)
            print("  %s %-50s %3d justes %3d faux" % (k, os.path.basename(f)[:50], sum(x["juste"] for x in L),
                                                    sum(1 - x["juste"] for x in L)), flush=True)
    vp = fp = tot_j = 0
    for k in data:
        tr = [x for kk, L in data.items() if kk != k for x in L]; te = data[k]
        if not te or len({x["juste"] for x in tr}) < 2: continue
        Xtr = np.array([[x[c] for c in COLS] for x in tr]); ytr = np.array([x["juste"] for x in tr])
        mdl = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_depth=4, random_state=0).fit(Xtr, ytr)
        ptr = mdl.predict_proba(Xtr)[:, 1]; s = 0.99
        for s_ in np.arange(0.50, 0.995, 0.01):   # plus petit seuil donnant >= 95 % de precision a l'entrainement
            sel = ptr >= s_
            if sel.sum() and ytr[sel].mean() >= 0.95: s = s_; break
        Xte = np.array([[x[c] for c in COLS] for x in te]); yte = np.array([x["juste"] for x in te])
        sel = mdl.predict_proba(Xte)[:, 1] >= s
        vp += int((yte[sel] == 1).sum()); fp += int((yte[sel] == 0).sum()); tot_j += int(yte.sum())
        print("%s laisse de cote : seuil %.2f | retenus %d (dont faux %d) | justes retenus %d / %d" % (
            k, s, sel.sum(), (yte[sel] == 0).sum(), (yte[sel] == 1).sum(), yte.sum()), flush=True)
    prec = vp / max(vp + fp, 1); rap = vp / max(tot_j, 1)
    print("POOLE : precision %.0f %% | justes retenus %.0f %% -> %s" % (100 * prec, 100 * rap,
          "REUSSI" if prec >= 0.90 and rap >= 0.40 else "ECHEC"))
