"""LIRE LA LEGENDE d'un plan (27/11) -- outil pour Claude / l'operateur qui ecrit la fiche de conventions du dossier.
Pour chaque echantillon DESSINE dans le cadre de la legende : sa couleur exacte (remplissage / trait) et le texte ecrit a
sa droite. Le metreur fait pareil : il lit la legende avant de lire le plan.
Usage : python lire_legende.py plan.pdf x0 y0 x1 y1     (cadre de la legende en FRACTIONS de la page, origine en haut a gauche)"""
import sys
import pdfplumber
sys.stdout.reconfigure(encoding="utf-8")


def c(v):
    return tuple(round(x, 2) for x in v) if isinstance(v, (list, tuple)) else v


def lire(chemin, fx0, fy0, fx1, fy1):
    with pdfplumber.open(chemin) as pdf:
        p = pdf.pages[0]; W, H = p.width, p.height
        box = (fx0 * W, fy0 * H, fx1 * W, fy1 * H)
        z = p.within_bbox(box)
        mots = z.extract_words(keep_blank_chars=False, use_text_flow=True)
        vus = {}
        # 27/11 : objets qui TOUCHENT le cadre (within_bbox ratait les carres de couleur a cheval sur le bord)
        objs = [o for o in p.rects + p.curves + p.lines
                if o["x1"] >= box[0] and o["x0"] <= box[2] and o["bottom"] >= box[1] and o["top"] <= box[3]
                and (o["x1"] - o["x0"]) < 0.2 * W]
        for o in objs:
            coul = (("rempli", c(o.get("non_stroking_color"))) if o.get("fill") else ("trait", c(o.get("stroking_color"))))
            x1, ym = o["x1"], (o["top"] + o["bottom"]) / 2
            # texte : mots a droite de l'echantillon, sur la meme bande verticale (+- 12 pt), a moins de 120 pt
            txt = [w for w in mots if 0 <= w["x0"] - x1 <= 120 and abs((w["top"] + w["bottom"]) / 2 - ym) <= 14]
            txt.sort(key=lambda w: (round(w["top"] / 4), w["x0"]))
            t = " ".join(w["text"] for w in txt)[:70]
            k = (coul, round(o.get("linewidth") or 0, 2))
            if k not in vus or len(t) > len(vus[k]): vus[k] = t
        for (coul, lw), t in sorted(vus.items(), key=lambda kv: kv[1]):
            if t: print("%-7s %-22s ep %.2f | %s" % (coul[0], coul[1], lw, t))


if __name__ == "__main__":
    lire(sys.argv[1], *map(float, sys.argv[2:6]))
