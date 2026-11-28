"""Moteur de metre v0 (lot peinture) -- lit un plan d'etage PDF vectoriel et sort, piece par piece :
surface, perimetre, murs bruts (perimetre x hauteur), plafond ; + Excel facon DPGF + image coloriee.

Methode v0 :
1. lire les surfaces ecrites (« 16,98 m2 ») et le nom de la piece au-dessus ;
2. dessiner le plan en image, epaissir les traits (ferme les petits trous), reperer les zones blanches fermees ;
3. pour chaque etiquette, la zone blanche qui l'entoure = la piece (trous du mobilier rebouches) ;
4. echelle : celle ecrite sur le plan (1/50...) si elle colle aux etiquettes, sinon calee sur les etiquettes ;
5. murs = perimetre x hauteur (ouvertures PAS encore deduites en v0) ; plafond = surface.
Usage : python -I metre.py plan.pdf [--hauteur 2.50] [--sortie dossier] [--page 1]"""
import argparse, json, math, os, re, statistics, sys
import numpy as np

import pypdfium2 as pdfium
from scipy import ndimage
from PIL import Image, ImageDraw

RX_SURF = re.compile(r"(\d{1,4}[,.]\d{1,2})\s?m[2²]")
RX_ECH = re.compile(r"\b1\s?[/:]\s?(20|25|50|75|100|125|200|250|500)\b")
def normaliser(chemin, num_page=0):
    """Une page TOURNEE (90/180/270) : on travaille sur une copie remise a plat (rotation 0), pour que l'image et les
    positions des textes et des traits parlent le meme langage. Rend le chemin a utiliser."""
    doc = pdfium.PdfDocument(chemin)
    rot = doc[num_page].get_rotation()
    if not rot:
        doc.close(); return chemin
    dossier = os.path.join(os.path.dirname(os.path.abspath(chemin)), "_a_plat")
    os.makedirs(dossier, exist_ok=True)
    sortie = os.path.join(dossier, os.path.basename(chemin))
    if not os.path.exists(sortie):
        neuf = pdfium.PdfDocument.new()
        neuf.import_pages(doc, [num_page])
        neuf[0].set_rotation(0)
        neuf.save(sortie)
    doc.close()
    return sortie


import functools as _ft


_CHAMPS = ("object_type", "pts", "linewidth", "fill", "stroke", "stroking_color", "non_stroking_color", "calque")   # 28/11 : calque du dessin (calques.py)


@_ft.lru_cache(maxsize=2)
def _page_plumber(chemin_abs, num_page, mtime):
    """LECTURE UNE FOIS POUR TOUTES (27/11) : lire un PDF coute ~22 s (Briffaut) a CHAQUE seance ; on garde sur disque
    les 3 listes d'objets (traits, rectangles, courbes) avec les 7 champs utilises par l'outil -> ~1 s ensuite.
    Fichier de cache invalide si le PDF change (date de modification dans le nom)."""
    import pickle, types, hashlib
    dossier = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sorties", "cache_pdf")
    os.makedirs(dossier, exist_ok=True)
    cle = hashlib.md5(("%s|%d|%d|calques" % (chemin_abs, num_page, int(mtime))).encode()).hexdigest()[:16]   # 28/11 : + calque
    fc = os.path.join(dossier, os.path.basename(chemin_abs)[:60] + "__" + cle + ".pkl")
    if os.path.exists(fc):
        with open(fc, "rb") as h:          # fichier ecrit par nous-memes (pas une source externe)
            d = pickle.load(h)
    else:
        import pdfplumber
        with pdfplumber.open(chemin_abs) as pdf:
            pg = pdf.pages[num_page]
            import calques; calques.preparer(pg)   # 28/11 : nom du calque de chaque trait
            d = {k: [{c: o.get(c) for c in _CHAMPS} for o in getattr(pg, k)] for k in ("lines", "rects", "curves")}
        with open(fc, "wb") as h:
            pickle.dump(d, h, protocol=pickle.HIGHEST_PROTOCOL)
    return types.SimpleNamespace(**d)


COTES_TXT = {}      # {plan: [(x, y, valeur m)]} tous les nombres-cotes ecrits (27/11)
COTES_VAL = {}      # {plan: [((x0,y0,x1,y1), valeur en m)]} (27/11 : arbitre des plans sans surface ecrite)
LIGNES_COTES = {}   # {plan: [(x0, y0, x1, y1)]} lignes de cote reconnues par le calcul d'echelle (27/11)
ZONE = None   # polygone (coordonnees de travail) : si defini, les methodes ne regardent QUE les objets qui le touchent


def dans_zone(pl, conv):
    """NE RECALCULER QUE LA OU IL RESTE DU TRAVAIL (27/11) : les variantes du moteur v3 ne servent qu'aux pieces encore
    douteuses ; on ne garde que les objets qui touchent la ZONE autour d'elles. Retirer des objets ne peut jamais CREER
    une piece fermee (seulement en ouvrir) et l'ecrit arbitre a 1 % -> aucune fausse piece possible."""
    if ZONE is None: return pl
    import types
    from shapely.geometry import box as _box
    from shapely.prepared import prep
    z = prep(ZONE)
    def garde(o):
        pts = o.get("pts") or []
        if not pts: return False
        c = [conv(p) for p in pts]
        xs = [p[0] for p in c]; ys = [p[1] for p in c]
        return z.intersects(_box(min(xs), min(ys), max(xs), max(ys)))
    return types.SimpleNamespace(lines=[o for o in pl.lines if garde(o)], rects=[o for o in pl.rects if garde(o)],
                                 curves=[o for o in pl.curves if garde(o)])


def page_plumber(chemin, num_page=0):
    """LECTURE UNIQUE (26/11, racine de la lenteur : le meme PDF etait relu 19 fois par plan = 61 % du temps).
    Rend la page pdfplumber, gardee en memoire pour les 2 derniers plans ; ses objets ne doivent PAS etre modifies."""
    a = os.path.abspath(chemin)
    return _page_plumber(a, num_page, os.path.getmtime(a))


def origine(page):
    """Coin haut-gauche de la page en coordonnees PDF : certaines pages ont leur origine au CENTRE (Briffaut :
    -595 ; -421). Toutes les positions de texte sont ramenees a ce coin."""
    l, b, r, t = page.get_cropbox()
    return l, t


RX_COTE = re.compile(r"(?<![\d,.])(\d{1,2}[,.]\d{2}|\d{2,4})(?![\d,.]|\s?m[2²])")


def echelle_par_cotes(chemin, num_page=0):
    """meme resultat que _echelle_par_cotes, calcule UNE fois par plan (avant : 10 fois x 24 s sur Briffaut)"""
    a = os.path.abspath(chemin)
    return _echelle_memo(a, num_page, os.path.getmtime(a))


@_ft.lru_cache(maxsize=16)
def _echelle_memo(chemin_abs, num_page, mtime):
    r = _echelle_par_cotes(chemin_abs, num_page)
    return garde_fou_echelle(chemin_abs, num_page, r)


ECHELLES_PLAUSIBLES = (20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500)


def echelle_ecrite(chemin, num_page=0):
    """28/11 -- echelle ECRITE sur la page (« 1/100 » ou « 1:100 »), la plus frequente parmi les plausibles ; None sinon.
    Cause mesuree : 3068854 demolition R-3, cotes = 3 voix -> 0,0251 m/pt alors que la page dit « Echelle : 1:100 »
    (0,0353) : toutes les pieces a la MOITIE de l'ecrit. Le garde-fou ne lisait que « 1/N »."""
    import re
    from collections import Counter
    try:
        doc = pdfium.PdfDocument(normaliser(chemin, num_page)); p = doc[0 if "_a_plat" in normaliser(chemin, num_page) else num_page]
        txt = p.get_textpage().get_text_range(); doc.close()
    except Exception:
        return None
    N = [int(n) for n in re.findall(r"(?<![\d,.])1\s*[/:]\s*(\d{2,3})(?![\d,.])", txt) if int(n) in ECHELLES_PLAUSIBLES]
    return Counter(N).most_common(1)[0][0] * 0.0254 / 72.0 if N else None


def garde_fou_echelle(chemin, num_page, r):
    """27/11 -- bug trouve en entrainant la vision : sur 8 pages, l'echelle « par les cotes » tenait sur un paquet de 2 a 12 voix
    (5-12 % des voix) et donnait une page de 0,1 a 16 m de large, alors que le cartouche dit 1/200. Le metreur controle avec
    l'echelle ECRITE. Regle : page de moins de 25 m de grand cote = impossible -> echelle ecrite (1/N le plus frequent),
    sinon inconnue (le secours par les etiquettes de metre_v3 prend le relais)."""
    import re, math
    m, voix, part = r
    if not m: return r
    try:
        doc = pdfium.PdfDocument(normaliser(chemin, num_page)); p = doc[0 if "_a_plat" in normaliser(chemin, num_page) else num_page]
        W, H = p.get_size(); txt = p.get_textpage().get_text_range(); doc.close()
    except Exception:
        return r
    if max(W, H) * m >= 25.0: return r
    N = [int(n) for n in re.findall(r"(?<![\d,.])1\s*/\s*(\d{2,3})(?![\d,.])", txt) if int(n) in ECHELLES_PLAUSIBLES]
    if N:
        from collections import Counter
        n = Counter(N).most_common(1)[0][0]
        m2 = n * 0.0254 / 72.0
        print("  ECHELLE corrigee (garde-fou) : cotes -> page de %.1f m, ecrit 1/%d -> %.1f m" % (max(W, H) * m, n, max(W, H) * m2))
        return m2, -1, 0
    print("  ECHELLE rejetee (garde-fou) : page de %.1f m et pas d'echelle ecrite" % (max(W, H) * m))
    return None, voix, 0


def _echelle_par_cotes(chemin, num_page=0):
    """v1 -- l'echelle lue sur les COTES, comme un metreur qui verifie « sur une cote connue ».
    Une cote = un nombre ecrit le long d'une ligne de cote. Pour chaque nombre, on cherche la ligne droite parallele
    juste a cote, qui l'englobe ; metres / longueur de la ligne = une « voix » pour l'echelle. Les mauvaises paires
    s'eparpillent, les bonnes tombent toutes au meme endroit : on garde le paquet le plus gros.
    Nombres a virgule (3,23) = metres ; nombres entiers (513) = centimetres (usage francais).
    Rend (metres par point PDF, nombre de voix du paquet, part du paquet) ou (None, 0, 0)."""
    import math, pdfplumber
    chemin = normaliser(chemin, num_page); num_page = 0 if chemin.find("_a_plat") >= 0 else num_page
    doc = pdfium.PdfDocument(chemin); p = doc[num_page]; W, H = p.get_size(); OX, OY = origine(p)
    tp = p.get_textpage(); txt = tp.get_text_range()
    cotes = []
    for m in RX_COTE.finditer(txt):
        try:
            bx = [tp.get_charbox(i) for i in range(m.start(1), m.end(1))]
        except Exception:
            continue
        bx = [b for b in bx if b[2] > b[0]]
        if not bx: continue
        l = min(b[0] for b in bx); b_ = min(b[1] for b in bx); r = max(b[2] for b in bx); t = max(b[3] for b in bx)
        s = m.group(1)
        val = float(s.replace(",", ".")) if ("," in s or "." in s) else int(s) / 100.0
        if val <= 0.05: continue
        cotes.append({"val": val, "x0": l - OX, "x1": r - OX, "y0": OY - t, "y1": OY - b_, "horiz": (r - l) >= (t - b_)})
    tp.close(); p.close(); doc.close()
    COTES_TXT[os.path.abspath(chemin)] = [((c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2, c["val"]) for c in cotes]   # nombres ecrits (27/11)
    if not cotes:
        return None, 0, 0
    # comme pour les etiquettes : on ecarte les textes beaucoup plus petits (plan de situation, cartouche)
    hs = sorted(min(c["x1"] - c["x0"], c["y1"] - c["y0"]) for c in cotes)
    p90 = hs[int(0.9 * (len(hs) - 1))]
    cotes = [c for c in cotes if min(c["x1"] - c["x0"], c["y1"] - c["y0"]) >= 0.5 * p90]
    lignes = page_plumber(chemin, num_page).lines
    # lignes de TOUS angles (un plan peut etre legerement tourne : 2 pt sur 1 117 sur Pithiviers ; 8 degres en Guyane)
    P = np.array([[l["pts"][0][0], l["pts"][0][1], l["pts"][-1][0], l["pts"][-1][1]] for l in lignes if l.get("pts")], float)
    if not len(P):
        return None, 0, 0
    # pdfplumber : x brut, y compte depuis le haut de la boite MEDIA -> on ramene au meme coin que les textes
    P[:, [0, 2]] -= OX
    P[:, [1, 3]] -= (H - OY)
    D = P[:, 2:] - P[:, :2]
    long_ = np.hypot(D[:, 0], D[:, 1])
    ok = long_ > 1
    P, D, long_ = P[ok], D[ok], long_[ok]
    U = D / long_[:, None]
    votes = []
    k_votes = []   # indice de la ligne de cote de chaque voix (27/11 : etiquettes « cote » pour l'IA)
    for c in cotes:
        cx, cy = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
        h = min(c["x1"] - c["x0"], c["y1"] - c["y0"]); w = max(c["x1"] - c["x0"], c["y1"] - c["y0"])
        vx, vy = cx - P[:, 0], cy - P[:, 1]
        proj = vx * U[:, 0] + vy * U[:, 1]                      # position du nombre le long de la ligne
        dist = np.abs(vx * U[:, 1] - vy * U[:, 0])              # distance du nombre a la ligne
        m = (proj >= 0) & (proj <= long_) & (dist <= 2.5 * max(h, 1)) & (long_ >= 1.5 * w)
        if m.any():
            k = np.flatnonzero(m)[np.argmin(dist[m])]
            votes.append(c["val"] / long_[k]); k_votes.append(k)
    if len(votes) < 5:
        return None, len(votes), 0
    # paquet le plus gros, a +/- 1,5 % pres (en echelle logarithmique)
    lv = sorted(math.log(v) for v in votes)
    best, bi = 0, 0
    j = 0
    for i in range(len(lv)):
        while lv[i] - lv[j] > 0.03: j += 1
        if i - j + 1 > best: best, bi = i - j + 1, i
    paquet = lv[bi - best + 1: bi + 1]
    m_par_pt = math.exp(statistics.median(paquet))
    # les VRAIES lignes de cote = celles dont la voix tombe dans le paquet retenu (memorisees pour l'IA, cassure 2)
    lo, hi = paquet[0], paquet[-1]
    LIGNES_COTES[os.path.abspath(chemin)] = [tuple(P[k]) for v, k in zip(votes, k_votes) if lo <= math.log(v) <= hi]
    COTES_VAL[os.path.abspath(chemin)] = [(tuple(P[k]), v * long_[k]) for v, k in zip(votes, k_votes) if lo <= math.log(v) <= hi]   # (ligne, valeur m)
    return m_par_pt, best, best / len(votes)


def lire_textes(chemin, num_page):
    """Texte de la page avec pdfium (pdfplumber decoupe mal les textes de ces plans). Coordonnees : origine en haut a gauche."""
    doc = pdfium.PdfDocument(chemin)
    p = doc[num_page]
    W, H = p.get_size(); OX, OY = origine(p)
    tp = p.get_textpage()
    txt = tp.get_text_range()
    etq = []
    for m in RX_SURF.finditer(txt):
        # « 1500 Kg/5,7m² » = une CHARGE au m2 (fiche d'equipement), pas une piece (racine 26/11, Pithiviers).
        # Mesure : 4 cas sur tout le banc + 47 pages d'apprentissage, tous des equipements.
        if txt[max(0, m.start() - 12):m.start()].rstrip().endswith("/"): continue
        try:
            bx = [tp.get_charbox(i) for i in range(m.start(1), m.end(1))]
        except Exception:
            continue
        bx = [b for b in bx if b[2] > b[0]]
        if not bx: continue
        l = min(b[0] for b in bx); bas = min(b[1] for b in bx); r = max(b[2] for b in bx); haut = max(b[3] for b in bx)
        t = haut - bas
        etq.append({"surface_ecrite": float(m.group(1).replace(",", ".")), "x": (l + r) / 2 - OX, "y": OY - (bas + haut) / 2,
                    "taille": t, "x0": l - OX, "x1": r - OX, "top": OY - haut, "_bas_pdf": bas, "_haut_pdf": haut,
                    "_x0_pdf": l, "_x1_pdf": r, "_monte": bx[-1][1] > bx[0][1] + 0.5})
    # nom de la piece : MOTS ENTIERS au-dessus de la surface (27/11 : la boite coupait les lettres qui depassaient
    # -> « ocal ménage », « alle de réunion » ; un mot qui TOUCHE la boite est maintenant garde en entier)
    mots = []
    if etq:
        for mo in re.finditer(r"\S+", txt):
            try:
                bb = [tp.get_charbox(i) for i in range(mo.start(), mo.end())]
            except Exception:
                continue
            bb = [b for b in bb if b[2] > b[0]]
            if bb: mots.append((mo.group(0), min(b[0] for b in bb), min(b[1] for b in bb), max(b[2] for b in bb), max(b[3] for b in bb)))
    for e in etq:
        larg, haut_ = e["_x1_pdf"] - e["_x0_pdf"], e["_haut_pdf"] - e["_bas_pdf"]
        if haut_ > 1.5 * larg:
            # TEXTE VERTICAL (Scanner, 27/11) : le nom n'est pas au-dessus mais A COTE (lignes precedentes a droite)
            s = max(larg, 1)
            if e.get("_monte"):
                # 27/11 soir (3091292, 10 etiquettes sur 10) : texte lu de BAS EN HAUT -> le nom est A GAUCHE ;
                # a droite il n'y avait que les codes de revetement (« SOL / MU / RS03 »)
                gx0, gx1 = e["_x0_pdf"] - 4 * s, e["_x0_pdf"] - 0.2 * s
            else:
                gx0, gx1 = e["_x1_pdf"] + 0.2 * s, e["_x1_pdf"] + 4 * s
            # dans le sens de lecture, un nom est plus long que la surface (« Atelier de prelevement ») : 10 lignes de marge
            gy0, gy1 = e["_bas_pdf"] - 10 * s, e["_haut_pdf"] + 10 * s
        else:
            s = max(e["taille"], 1)
            gx0, gx1, gy0, gy1 = e["_x0_pdf"] - 4 * s, e["_x1_pdf"] + 4 * s, e["_haut_pdf"] + 0.2 * s, e["_haut_pdf"] + 4 * s
        brut = tp.get_text_bounded(left=gx0, bottom=gy0, right=gx1, top=gy1)
        lignes = [x.strip() for x in re.split(r"[\r\n]+", brut) if x.strip()]
        # COMPLETER les mots coupes au bord de la boite : le 1er (fin de mot) et le dernier (debut de mot) de chaque ligne
        # sont remplaces par le mot ENTIER du texte qui touche la boite (plans tournes : Guyane 8 deg)
        proches = [w for w in mots if w[3] > gx0 - 8 * s and w[1] < gx1 + 8 * s and w[4] > gy0 - s and w[2] < gy1 + s]
        def complete(tok, fin):
            if len(tok) < 2: return tok
            if re.search(r"[\d=]", tok): return tok
            c = [w[0] for w in proches if len(w[0]) > len(tok) and not re.search(r"[\d=]", w[0])
                 and (w[0].endswith(tok) if fin else w[0].startswith(tok))]
            return min(c, key=len) if c else tok
        for i, ln in enumerate(lignes):
            t = ln.split(" ")
            t[0] = complete(t[0], True)
            t[-1] = complete(t[-1], False)   # aussi quand la ligne n'a qu'UN mot (« Sani » -> « Sanitaire »)
            lignes[i] = " ".join(t)
        lignes = [x for x in lignes if not RX_SURF.search(x) and not re.fullmatch(r"[\d\s,.:+=-]*(m[2²])?", x) and len(x) >= 3]
        e["_lignes"] = lignes
    ech = sorted({int(m.group(1)) for m in RX_ECH.finditer(txt)})
    tp.close(); p.close(); doc.close()
    return W, H, etq, ech


def etiquettes(etq):
    """Ecarte les petits textes (plan de reperage, cartouche) et choisit le nom de la piece."""
    if not etq:
        return etq
    tailles = sorted(e["taille"] for e in etq)
    p95 = tailles[int(0.95 * (len(tailles) - 1))]
    etq = [e for e in etq if e["taille"] >= 0.5 * p95]  # le plan de reperage est ecrit beaucoup plus petit
    # les lignes qui reviennent partout (nom du service, « Existant »...) ne sont pas des noms de pieces
    from collections import Counter
    freq = Counter(l for e in etq for l in set(e["_lignes"]))
    for e in etq:
        noms = [l for l in e["_lignes"] if freq[l] < 5]
        nom = noms[0] if noms else ""
        # 27/11 soir : nom sur 2 lignes (« Atelier de / prelevement », « Infirmier / ») -> on recolle la 2e ligne
        if len(noms) > 1 and re.search(r"(\b(de|du|des|d'|et|la|le|les|a|en)|[/&+-])$", nom, re.I): nom += " " + noms[1]
        e["nom"] = nom[:50]
    return etq


def mesurer(chemin, hauteur=2.50, sortie=None, num_page=0, cote_px=7000, epaissir=1, seuil_gris=235, refermer=2, fermer_portes=0, fermer_arcs=1):
    chemin_orig = chemin
    chemin = normaliser(chemin, num_page)
    if chemin != chemin_orig: num_page = 0
    W, H, etq, ech_ecr = lire_textes(chemin, num_page)
    etq = etiquettes(etq)
    s = cote_px / max(W, H)  # pixels par point
    doc = pdfium.PdfDocument(chemin)
    page = doc[num_page]
    img = page.render(scale=s, grayscale=True).to_pil().convert("L")
    # on efface TOUS les textes (noms, cotes, surfaces) : sinon ils deviennent des petits murs
    tp = page.get_textpage(); OX, OY = origine(page)
    g = np.array(img)
    Hpx, Wpx = g.shape
    for i in range(tp.count_chars()):
        try:
            l, b, r, t_ = tp.get_charbox(i)
        except Exception:
            continue
        if r <= l: continue
        x0, x1 = max(0, int((l - OX) * s) - 2), min(Wpx, int((r - OX) * s) + 3)
        y0, y1 = max(0, int((OY - t_) * s) - 2), min(Hpx, int((OY - b) * s) + 3)
        g[y0:y1, x0:x1] = 255
    tp.close(); page.close(); doc.close()
    encre = g < seuil_gris
    # on referme les petits trous des cloisons (hachures, pointilles) avant d'effacer les traits fins
    encre = ndimage.binary_closing(encre, structure=np.ones((3, 3), bool), iterations=refermer)
    # les MURS sont des traits epais ou remplis : une « ouverture » efface les traits fins (texte, cotes, axes, mobilier)
    murs = ndimage.binary_opening(encre, structure=np.ones((3, 3), bool), iterations=epaissir)
    # v1 : un mur fait au plus ~70 cm d'epaisseur. Ce qui est plus epais est un APLAT de couleur (piece grisee,
    # zone hachuree pleine) : ce n'est pas un mur, on l'enleve. On a besoin de l'echelle AVANT -> lue sur les cotes.
    m_pt_c, voix_c, part_c = echelle_par_cotes(chemin, num_page)
    ech_sure, ech_src = None, None
    if m_pt_c and voix_c >= 15 and part_c >= 0.10:
        ech_sure, ech_src = m_pt_c, "cotes (%d voix" % voix_c
        for d in ech_ecr:  # tombe sur une echelle ecrite a 3 % pres -> valeur exacte
            if abs(m_pt_c / (0.0254 / 72 * d) - 1) < 0.03:
                ech_sure = 0.0254 / 72 * d
    elif m_pt_c and voix_c >= 5:
        # deux indices faibles mais INDEPENDANTS qui concordent : echelle ecrite + cotes a 3 % pres
        for d in ech_ecr:
            if abs(m_pt_c / (0.0254 / 72 * d) - 1) < 0.03:
                ech_sure, ech_src = 0.0254 / 72 * d, "ecrite confirmee par les cotes (%d voix" % voix_c
    if ech_sure:
        ech_src += ", 1/%d)" % round(ech_sure / (0.0254 / 72))
    defaut = (0.0254 / 72 * (ech_ecr[0] if len(ech_ecr) == 1 else 50))
    m_px = (ech_sure or defaut) / s
    T = max(4, int(0.35 / m_px))  # demi-epaisseur max d'un mur, en pixels
    d_mur = ndimage.distance_transform_edt(murs)
    coeur = d_mur > T
    if coeur.any():
        aplats = ndimage.distance_transform_edt(~coeur) <= T + 1
        murs = murs & ~aplats
    if fermer_arcs:
        # PORTES : chaque porte est dessinee avec un arc (le debattement). Centre de l'arc = le gond ; les deux rayons
        # (gond -> bouts de l'arc) = le battant ouvert et la position fermee, c.-a-d. l'OUVERTURE du mur.
        # On dessine ces deux rayons comme des murs : la porte est fermee, la ou il y a vraiment une porte.
        import pdfplumber
        from skimage.draw import line as tracer
        with pdfplumber.open(chemin) as pdf:
            courbes = pdf.pages[num_page].curves
        n_portes = 0
        traits = np.zeros_like(murs)
        for c in courbes:
            pts = c.get("pts") or []
            if len(pts) < 3: continue
            (x1, y1), (x2, y2), (x3, y3) = pts[0], pts[len(pts) // 2], pts[-1]
            dd = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
            if abs(dd) < 1e-6: continue
            ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / dd
            uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / dd
            rayon_m = math.hypot(x1 - ux, y1 - uy) * s * m_px
            a = math.degrees(math.atan2(y1 - uy, x1 - ux) - math.atan2(y3 - uy, x3 - ux)) % 360
            balayage = min(a, 360 - a)
            if not (0.55 <= rayon_m <= 1.25 and 70 <= balayage <= 110): continue
            dy = H - OY  # meme recalage que pour les cotes
            for (px_, py_) in ((x1, y1), (x3, y3)):
                rr, cc = tracer(int((uy - dy) * s), int((ux - OX) * s), int((py_ - dy) * s), int((px_ - OX) * s))
                ok = (rr >= 0) & (rr < murs.shape[0]) & (cc >= 0) & (cc < murs.shape[1])
                traits[rr[ok], cc[ok]] = True
            n_portes += 1
        if n_portes:  # on epaissit SEULEMENT les traits de porte ajoutes (pas les murs existants)
            murs = murs | ndimage.binary_dilation(traits, iterations=1)
    if fermer_portes:
        # on referme les trous ALIGNES dans un mur (horizontaux puis verticaux) plus petits que ~1,1 m (une porte)
        L = max(3, int(fermer_portes / m_px))
        h = ndimage.binary_closing(murs, structure=np.ones((1, L), bool))
        v = ndimage.binary_closing(murs, structure=np.ones((L, 1), bool))
        murs = murs | h | v
    libre = ~murs
    # chaque etiquette = une graine ; l'exterieur (bords de l'image) = une graine ; on « inonde » depuis les graines :
    # les inondations se rencontrent aux passages etroits (portes) -> une zone par piece
    dist = ndimage.distance_transform_edt(libre)
    graines = np.zeros(g.shape, np.int32)
    R = max(10, int(1.2 / m_px))  # on cherche le « centre » de la piece dans un rayon de ~1,2 m autour de l'etiquette
    for i, e in enumerate(etq, 1):
        cx, cy = int(e["x"] * s), int(e["y"] * s)
        y0, y1, x0, x1 = max(0, cy - R), min(g.shape[0], cy + R), max(0, cx - R), min(g.shape[1], cx + R)
        fen = dist[y0:y1, x0:x1]
        e["zone"] = i
        if fen.size == 0:  # etiquette hors de l'image (bord de page)
            continue
        # point le plus eloigne des murs = fond de la « cuvette » de la piece : l'inondation doit partir de la
        k = np.unravel_index(np.argmax(fen), fen.shape)
        py, px = y0 + k[0], x0 + k[1]
        r = max(2, int(0.15 / m_px))
        yy0, yy1, xx0, xx1 = max(0, py - r), py + r, max(0, px - r), px + r
        bloc = graines[yy0:yy1, xx0:xx1]
        bloc[libre[yy0:yy1, xx0:xx1] & (bloc == 0)] = i
        e["zone"] = i
    ext = len(etq) + 1
    for bordure in (graines[0], graines[-1], graines[:, 0], graines[:, -1]):
        bordure[bordure == 0] = ext
    from skimage.segmentation import watershed
    lab = watershed(-dist, graines, mask=libre)
    # une zone qui touche le bord de l'image n'est pas une piece fermee
    bord = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) | {ext}
    objs = ndimage.find_objects(lab)
    for e in etq:
        z = e["zone"]
        if z > len(objs) or objs[z - 1] is None or z in bord:
            e["px_aire"] = e["px_perim"] = None; continue
        m = np.pad(lab[objs[z - 1]] == z, 1)
        e["px_perim"] = int(np.count_nonzero(m[:, 1:] != m[:, :-1]) + np.count_nonzero(m[1:, :] != m[:-1, :]))
        # le flou autour des traits (seuil de gris) mange ~2 px de bordure : mesure le 25/11 sur 2 plans d'echelles
        # differentes (2,1 et 2,8 px) -> on rend 2 px sur tout le pourtour. A CONFIRMER sur des dossiers neufs.
        e["px_aire"] = int(m.sum()) + 2 * e["px_perim"]
        # CONTOUR PROPRE (lecon d'OpenTakeoff) : le bord de la zone devient un polygone simplifie (a ~3 cm pres),
        # en points PDF depuis le coin haut-gauche de la page -> c'est ce que l'ecran de validation affichera.
        try:
            from skimage.measure import find_contours
            from shapely.geometry import Polygon
            cs = find_contours(m.astype(np.uint8), 0.5)
            if cs:
                c = max(cs, key=len)
                sl = objs[z - 1]
                pts = [((cc + sl[1].start - 1) / s, (rr + sl[0].start - 1) / s) for rr, cc in c]
                # meme correction que la surface : on rend la bande de 2 px mangee par le flou des traits
                poly = Polygon(pts).buffer(2 / s, join_style=2).simplify(0.03 / (m_px * s), preserve_topology=True)
                if poly.is_valid and not poly.is_empty and poly.geom_type == "Polygon":
                    e["contour_pt"] = [[round(x, 1), round(y, 1)] for x, y in poly.exterior.coords]
        except Exception as ex:
            e["contour_erreur"] = str(ex)[:80]
    # echelle
    # 1) on essaie chaque echelle ECRITE sur le plan : celle qui fait coller le plus d'etiquettes (a 5 %) gagne,
    #    si elle en fait coller au moins 20 % ; 2) sinon, mediane des etiquettes (en le signalant).
    ratios = [e["surface_ecrite"] / e["px_aire"] for e in etq if e.get("px_aire") and e["surface_ecrite"] > 0]
    choix, source, meilleur = None, None, 0
    # v1 : d'abord l'echelle sure (cotes, ou ecrite confirmee par les cotes), calculee plus haut, une seule fois
    if ech_sure:
        choix, source = (ech_sure / s) ** 2, ech_src
        meilleur = len(ratios) + 1  # pour ne pas repasser par les autres methodes
    for d in ech_ecr:
        c_d = (0.0254 / 72 * d / s) ** 2
        k = sum(1 for r in ratios if abs(c_d / r - 1) < 0.05)
        if k > meilleur:
            choix, source, meilleur = c_d, "ecrite 1/%d" % d, k
    if not ech_sure and (not ratios or meilleur < 0.2 * len(ratios)):
        choix = statistics.median(ratios) if ratios else None
        source = "calee sur les etiquettes (pas d'echelle ecrite fiable)"
    zones_vues = {}
    for e in etq:
        if e.get("px_aire") and choix:
            e["surface_calc"] = round(e["px_aire"] * choix, 2)
            e["perimetre"] = round(e["px_perim"] * choix ** 0.5, 2)
            e["ecart_pct"] = round(100 * (e["surface_calc"] / e["surface_ecrite"] - 1), 1) if e["surface_ecrite"] else None
            e["murs_bruts"] = round(e["perimetre"] * hauteur, 2)
            e["plafond"] = e["surface_calc"]
        zones_vues.setdefault(e["zone"], []).append(e)
    for e in etq:
        doute = []
        if not e.get("surface_calc"): doute.append("piece non fermee")
        elif abs(e["ecart_pct"]) > 3: doute.append("ecart %+.1f %%" % e["ecart_pct"])
        if e["zone"] and len(zones_vues.get(e["zone"], [])) > 1: doute.append("zone partagee")
        e["statut"] = "ok" if not doute else "a verifier : " + ", ".join(doute)
        # PROVENANCE (lecon d'OpenTakeoff) : comment ce chiffre a ete obtenu ; « revue » passe a vrai quand un humain valide
        e["provenance"] = {"methode": "inondation_v1", "echelle": source, "revue": False}
    res = {"plan": os.path.basename(chemin), "echelle_source": source, "echelles_ecrites": ech_ecr,
           "m_par_px": round(choix ** 0.5, 5) if choix else None, "hauteur": hauteur, "pieces": etq}
    if sortie:
        os.makedirs(sortie, exist_ok=True)
        base = os.path.join(sortie, os.path.splitext(os.path.basename(chemin))[0])
        ecrire_image(img, lab, etq, s, base + "_controle.png")
        ecrire_excel(res, base + "_metre.xlsx")
        json.dump({k: v for k, v in res.items()}, open(base + "_metre.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1, default=str)
    return res


def ecrire_image(img, lab, etq, s, chemin, cote=2400):
    rgb = np.stack([np.asarray(img)] * 3, axis=-1).copy()
    for e in etq:
        if not e.get("zone"): continue
        ok = e.get("ecart_pct") is not None and abs(e["ecart_pct"]) <= 3
        coul = (120, 210, 120) if ok else ((250, 180, 80) if e.get("ecart_pct") is not None and abs(e["ecart_pct"]) <= 10 else (240, 110, 110))
        m = lab == e["zone"]
        rgb[m] = (0.5 * rgb[m] + 0.5 * np.array(coul)).astype(np.uint8)
    im = Image.fromarray(rgb)
    k = cote / max(im.size)
    im = im.resize((int(im.size[0] * k), int(im.size[1] * k)))
    d = ImageDraw.Draw(im)
    for e in etq:
        if e.get("ecart_pct") is not None:
            d.text((e["x"] * s * k, e["y"] * s * k + 8), "%+.0f%%" % e["ecart_pct"], fill=(0, 0, 0))
    im.save(chemin)


def ecrire_excel(res, chemin):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Pieces"
    ent = ["Piece", "Surface ecrite (m2)", "Surface calculee (m2)", "Ecart %", "Perimetre (m)", "Hauteur (m)",
           "Murs bruts (m2)", "Plafond (m2)", "Statut"]
    ws.append(ent)
    for c in ws[1]: c.font = Font(bold=True)
    for e in res["pieces"]:
        ws.append([e.get("nom"), e["surface_ecrite"], e.get("surface_calc"), e.get("ecart_pct"), e.get("perimetre"),
                   res["hauteur"], e.get("murs_bruts"), e.get("plafond"), e["statut"]])
        if e["statut"] != "ok":
            ws.cell(ws.max_row, 9).fill = PatternFill("solid", fgColor="FFE0B0")
    for col, l in zip("ABCDEFGHI", (34, 14, 14, 9, 12, 10, 14, 12, 40)):
        ws.column_dimensions[col].width = l
    r = wb.create_sheet("Recap lot peinture")
    ok = [e for e in res["pieces"] if e.get("surface_calc")]
    r.append(["Plan", res["plan"]]); r.append(["Echelle", res["echelle_source"]])
    r.append(["Hauteur sous plafond retenue (m)", res["hauteur"]])
    r.append([]); r.append(["Poste", "Quantite", "Unite", "Remarque"])
    r.append(["Peinture murs (brut, ouvertures non deduites)", round(sum(e["murs_bruts"] for e in ok), 2), "m2", "v0 : ouvertures a deduire"])
    r.append(["Peinture plafonds", round(sum(e["plafond"] for e in ok), 2), "m2", ""])
    r.append(["Pieces mesurees / pieces lues", "%d / %d" % (len(ok), len(res["pieces"])), "", ""])
    r.append(["Pieces a verifier", sum(1 for e in res["pieces"] if e["statut"] != "ok"), "", ""])
    r.column_dimensions["A"].width = 48
    wb.save(chemin)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = argparse.ArgumentParser()
    a.add_argument("pdf"); a.add_argument("--hauteur", type=float, default=2.50)
    a.add_argument("--sortie", default=None); a.add_argument("--page", type=int, default=1)
    o = a.parse_args()
    res = mesurer(o.pdf, o.hauteur, o.sortie, o.page - 1)
    p = res["pieces"]
    me = [e for e in p if e.get("ecart_pct") is not None]
    bon = [e for e in me if abs(e["ecart_pct"]) <= 3]
    print("%s | echelle %s | pieces lues %d | mesurees %d | a +/-3 %% : %d (%.0f %% des pieces lues)" % (
        res["plan"], res["echelle_source"], len(p), len(me), len(bon), 100 * len(bon) / max(1, len(p))))
