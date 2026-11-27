"""Detecteur de LIGNES DE COTE pour le diagnostic (27/11). metre.LIGNES_COTES ne garde que les traits dont la longueur colle
au chiffre (ceux de l'echelle) : il rate les chaines de cotes dessinees en UN seul long trait (CAVE 11 de 548666 : 0,00 m).
Ici : une ligne de cote = un trait qui PORTE un chiffre de cote : texte dans le sens du trait, colle (<= 1,5 x hauteur du texte),
entre ses deux bouts. Coordonnees = celles des pieces (origine en haut a gauche, comme matiere / metre.LIGNES_COTES).
  lignes_de_cote(chemin) -> [(x0, y0, x1, y1)]"""
import math
import numpy as np
import pypdfium2 as pdfium
from metre import normaliser, origine, page_plumber, RX_COTE


_IDS = {}


def ids_objets_de_cote(chemin, num_page=0):
    """27/11 : identifiants (id python) des objets pdfplumber (traits ou courbes) dont AU MOINS un segment porte un chiffre de
    cote. Sert a la variante matiere.SANS_COTES. Les objets de page_plumber sont gardes en memoire : id stable."""
    cle = (normaliser(chemin, num_page), num_page)
    if cle not in _IDS:
        _IDS.clear()
        _IDS[cle] = _calcul(chemin, num_page, objets=True)
    return _IDS[cle]


def lignes_de_cote(chemin, num_page=0):
    return _calcul(chemin, num_page, objets=False)


def _calcul(chemin, num_page=0, objets=False):
    chemin = normaliser(chemin, num_page); num_page = 0 if "_a_plat" in chemin else num_page
    doc = pdfium.PdfDocument(chemin); p = doc[num_page]; W, H = p.get_size(); OX, OY = origine(p)
    tp = p.get_textpage(); txt = tp.get_text_range()
    T = []
    for m in RX_COTE.finditer(txt):
        try:
            bx = [tp.get_charbox(i) for i in range(m.start(1), m.end(1))]
        except Exception:
            continue
        bx = [b for b in bx if b[2] > b[0]]
        if not bx: continue
        l = min(b[0] for b in bx); b_ = min(b[1] for b in bx); r = max(b[2] for b in bx); t = max(b[3] for b in bx)
        T.append(((l + r) / 2 - OX, OY - (t + b_) / 2, min(r - l, t - b_), (r - l) >= (t - b_)))
    tp.close(); p.close(); doc.close()
    if not T: return set() if objets else []
    # 27/11 : une chaine de cotes peut etre UNE courbe de 22 points (548666 : segments + tirets, trait 0,51) -> on decoupe
    # traits ET courbes en segments (points consecutifs)
    pl = page_plumber(chemin, num_page)
    segs, proprio = [], []
    for o in pl.lines + pl.curves:
        pts = o.get("pts") or []
        for a, b in zip(pts, pts[1:]):
            segs.append([a[0], a[1], b[0], b[1]]); proprio.append(id(o))
    if not segs: return set() if objets else []
    P = np.array(segs, float); proprio = np.array(proprio, dtype=object)
    P[:, [0, 2]] -= OX; P[:, [1, 3]] -= (H - OY)
    D = P[:, 2:] - P[:, :2]; L = np.hypot(D[:, 0], D[:, 1]); ok = L > 1
    P, D, L, proprio = P[ok], D[ok], L[ok], proprio[ok]; U = D / L[:, None]
    horiz_l = np.abs(U[:, 0]) >= math.cos(math.radians(10))
    vert_l = np.abs(U[:, 1]) >= math.cos(math.radians(10))
    garde = np.zeros(len(P), bool)
    for cx, cy, h, horiz in T:
        vx, vy = cx - P[:, 0], cy - P[:, 1]
        proj = vx * U[:, 0] + vy * U[:, 1]
        dist = np.abs(vx * U[:, 1] - vy * U[:, 0])
        sens = horiz_l if horiz else vert_l
        garde |= sens & (proj >= 0) & (proj <= L) & (dist <= 1.5 * max(h, 1))
    if objets: return set(proprio[garde].tolist())
    return [tuple(x) for x in P[garde]]
