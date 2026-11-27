"""POURQUOI la vision rate des murs (27/11, consigne du porteur : chercher le probleme AVANT toute solution).
Regle ecrite AVANT de mesurer : un facteur est une CAUSE PROBABLE si, dans l'un de ses groupes (>= 20 murs), le taux de ratés
est >= 2 fois le taux moyen. Murs = objets « mur » au bord d'une piece juste (reference corrigee sorties/objets_vb).
Lit les cartes deja calculees (sorties/vision/*.npz). Aucun reglage du modele.
  python vision_pourquoi.py"""
import glob, gzip, json, os, sys, math, collections
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
import vision_murs as V

lignes = []
for fz in sorted(glob.glob(os.path.join(V.SORTIE, "*.npz"))):
    nom = os.path.basename(fz)[:-4]
    fo = glob.glob(os.path.join(ici, "sorties", "objets_vb", glob.escape(nom) + "*.jsonl.gz"))
    if not fo: continue
    z = np.load(fz, allow_pickle=False); cls = z["cls"]; sc = float(z["sc"]); m = float(z["m"]); H, W = cls.shape
    L = [json.loads(l) for l in gzip.open(fo[0], "rt", encoding="utf-8")]
    # 27/11 : mesurer SUR le trait (points le long de l'objet), pas au centre de sa boite (faux pour les murs longs ou en L)
    from metre import normaliser, page_plumber, lire_textes, origine
    import pypdfium2 as pdfium
    ch = normaliser(glob.glob(os.path.join(ici, "plans_test", nom[:7] + "*.pdf"))[0])
    _, Hp, _, _ = lire_textes(ch, 0); dd = pdfium.PdfDocument(ch); OX, OY = origine(dd[0]); dd.close()
    objs = [o for o in (lambda p: p.lines + p.rects + p.curves)(page_plumber(ch)) if len(o.get("pts") or []) >= 2]
    if len(objs) != len(L): print("alignement impossible", nom); continue
    mur_px = (cls == 1)
    from scipy.ndimage import maximum_filter
    mur_px = maximum_filter(mur_px.astype(np.uint8), size=3).astype(bool)
    def part_vue(i):
        P = np.array([((q[0] - OX) * sc, (q[1] - (Hp - OY)) * sc) for q in objs[i]["pts"]])
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1); tot = seg.sum()
        if tot <= 0: return 0.0
        t = np.linspace(0, tot, 11)[:-1] + tot / 20; cum = np.r_[0, np.cumsum(seg)]
        pts = []
        for u in t:
            k = min(np.searchsorted(cum, u, side="right") - 1, len(seg) - 1); a_ = (u - cum[k]) / max(seg[k], 1e-9)
            pts.append(P[k] + a_ * (P[k + 1] - P[k]))
        pts = np.round(pts).astype(int)
        ok = (pts[:, 0] >= 0) & (pts[:, 0] < W) & (pts[:, 1] >= 0) & (pts[:, 1] < H)
        return float(mur_px[pts[ok, 1], pts[ok, 0]].mean()) if ok.any() else 0.0
    def pix(x): return int(round((x["_x0"] + x["_x1"]) / 2 / m * sc)), int(round((x["_y0"] + x["_y1"]) / 2 / m * sc))
    ouv = np.array([pix(x) for x in L if x.get("classe") in ("vitre", "porte")] or [(-9999, -9999)], float)
    enc = np.array([pix(x) for x in L if x.get("classe") in ("lettre", "hachure", "mobilier", "cote")] or [(-9999, -9999)], float)
    from scipy.spatial import cKDTree
    t_ouv, t_enc = cKDTree(ouv), cKDTree(enc)
    pas = int((V.CARREAU_M - V.CHEV_M) * V.PX / V.CARREAU_M)
    for i, x in enumerate(L):
        if not (x.get("classe") == "mur" and x.get("etiquette") == 1): continue
        px, py = pix(x)
        if not (0 <= px < W and 0 <= py < H): continue
        pv = part_vue(i); vu = pv >= 0.5   # vu si au moins la moitie du trait est vue « mur »
        lum_trait = (x.get("trait_r", 0) + x.get("trait_g", 0) + x.get("trait_b", 0)) / 3
        lum_rempli = (x.get("rempli_r", 0) + x.get("rempli_g", 0) + x.get("rempli_b", 0)) / 3
        lum = lum_rempli if x.get("rempli") else lum_trait
        sat = (max(x.get("rempli_r", 0), x.get("rempli_g", 0), x.get("rempli_b", 0)) - min(x.get("rempli_r", 0), x.get("rempli_g", 0), x.get("rempli_b", 0))) if x.get("rempli") else \
              (max(x.get("trait_r", 0), x.get("trait_g", 0), x.get("trait_b", 0)) - min(x.get("trait_r", 0), x.get("trait_g", 0), x.get("trait_b", 0)))
        bord = min(px % pas, pas - px % pas, py % pas, pas - py % pas) / (V.PX / V.CARREAU_M)
        lignes.append({
            "plan": nom[:7], "vu": vu,
            "style": "bande pleine" if x.get("rempli") else ("rect/polyligne" if x.get("type") in (1, 3) else "trait"),
            "couleur": ("couleur" if sat > 0.15 else "noir" if lum < 0.25 else "gris fonce" if lum < 0.55 else "gris clair" if lum < 0.85 else "tres pale"),
            "epaisseur": "<5 cm" if x.get("ep_bande_m", 0) < 0.05 else "5-15 cm" if x["ep_bande_m"] < 0.15 else "15-30 cm" if x["ep_bande_m"] < 0.30 else ">30 cm",
            "stylo": "fin <0,3 pt" if x.get("stylo_pt", 0) < 0.3 else "moyen" if x["stylo_pt"] < 0.8 else "epais",
            "orientation": "droit" if x.get("angle_mod90", 0) < 3 or x.get("angle_mod90", 0) > 87 else "en biais",
            "longueur": "<0,5 m" if x["longueur_m"] < 0.5 else "0,5-2 m" if x["longueur_m"] < 2 else ">2 m",
            "ouverture <1 m": "oui" if t_ouv.query([px, py])[0] < 1.0 * V.PX / V.CARREAU_M else "non",
            "encombrement 50 cm": str(min(len(t_enc.query_ball_point([px, py], 0.5 * V.PX / V.CARREAU_M)), 5)) + ("+" if len(t_enc.query_ball_point([px, py], 0.5 * V.PX / V.CARREAU_M)) >= 5 else ""),
            "bord de carreau": "<1 m" if bord < 1 else "1-3 m" if bord < 3 else ">3 m",
        })

n = len(lignes); r_moy = 1 - np.mean([l["vu"] for l in lignes]) if n else 0
print("murs de reference : %d | rates : %.0f %% (moyenne)\n" % (n, 100 * r_moy))
causes = []
for f in ["plan", "style", "couleur", "epaisseur", "stylo", "orientation", "longueur", "ouverture <1 m", "encombrement 50 cm", "bord de carreau"]:
    g = collections.defaultdict(list)
    for l in lignes: g[l[f]].append(l["vu"])
    txt = []
    for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
        r = 1 - np.mean(v); marque = " <<< CAUSE PROBABLE" if len(v) >= 20 and r >= 2 * r_moy else ""
        if marque: causes.append("%s = %s (%.0f %% rates sur %d)" % (f, k, 100 * r, len(v)))
        txt.append("    %-16s %5d murs | rates %3.0f %%%s" % (k, len(v), 100 * r, marque))
    print(f.upper()); print("\n".join(txt))
print("\nCAUSES PROBABLES :" if causes else "\nAucun facteur ne double le taux de rates.")
for c in causes: print("  -", c)
