"""v3 -- pieces = TROUS de la « matiere » du plan (structure changee le 25/11).
Racine trouvee : la methode « faces » (faces.py) suppose que les murs sont des TRAITS ; sur une partie des plans,
les murs ne sont que des SURFACES remplies (bandes grises, sans trait). Structurel -> on change la representation :
  matiere = bandes remplies (murs, seuils, fenetres : 2 a EP_MAX cm d'epaisseur, toutes couleurs)
          + traits epais (stylo >= seuil), elargis a leur epaisseur reelle
          + cordes de portes (gond -> deux bouts de l'arc, cf. faces.py)
  piece   = le trou de la matiere qui contient l'etiquette (geometrie exacte, pas de pixels).
Usage : python matiere.py plan.pdf"""
import math, sys
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
import pdfplumber, pypdfium2 as pdfium
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from metre import lire_textes, etiquettes, echelle_par_cotes, normaliser, origine, page_plumber, dans_zone
from faces import kasa


PORTES_POINTILLES = False   # 27/11 : variante v3 « portes en pointilles » (arcs en tirets reconstitues, compter_pointilles.py)
PORTE_ANGLE_MIN = 0.7   # rad : ouverture mini d'un arc de porte (27/11 : 36 % des arcs des neufs sont ENTROUVERTS 10-40 deg ;
                        # variante v3 « portes entrouvertes » = 10 deg)


def portes(pl, m_pt, conv):
    """cordes gond -> bouts, pour chaque arc de porte (voir faces.py : Kasa si >= 5 points, sinon angle droit)."""
    from scipy.spatial import cKDTree
    tous = [p for o in pl.lines + pl.rects + pl.curves for p in (o.get("pts") or [])]
    arbre = cKDTree(np.asarray(tous, float)) if tous else None
    out = []
    for c in pl.curves:
        pts = c.get("pts") or []
        if len(pts) < 2 or c.get("fill"): continue
        g = None
        if len(pts) >= 5:
            k = kasa(pts)
            if k:
                cx, cy, r = k
                a1 = math.atan2(pts[0][1] - cy, pts[0][0] - cx); a2 = math.atan2(pts[-1][1] - cy, pts[-1][0] - cx)
                bal = abs((a2 - a1 + math.pi) % (2 * math.pi) - math.pi)
                if 0.55 <= r * m_pt <= 1.3 and PORTE_ANGLE_MIN <= bal <= 2.1: g = (cx, cy)
        if g is None and len(pts) <= 8:
            (ax, ay), (bx, by) = pts[0], pts[-1]
            cl = math.hypot(bx - ax, by - ay)
            if cl and 0.55 <= cl / math.sqrt(2) * m_pt <= 1.3 and arbre is not None:
                mx, my = (ax + bx) / 2, (ay + by) / 2
                nx, ny = -(by - ay) / cl, (bx - ax) / cl
                cands = [(mx + nx * cl / 2, my + ny * cl / 2), (mx - nx * cl / 2, my - ny * cl / 2)]
                v = [len(arbre.query_ball_point(q, 0.10 / m_pt)) for q in cands]
                if v[0] != v[1]: g = cands[0] if v[0] > v[1] else cands[1]
        if g is None: continue
        for e in (pts[0], pts[-1]):
            L = math.hypot(e[0] - g[0], e[1] - g[1])
            if not L: continue
            ux, uy = (e[0] - g[0]) / L, (e[1] - g[1]) / L; pr = 0.05 / m_pt
            out.append(LineString([conv((g[0] - ux * pr, g[1] - uy * pr)), conv((e[0] + ux * pr, e[1] + uy * pr))]))
    if PORTES_POINTILLES:   # 27/11 (3068854 : quarts de cercle en TIRETS, chaque tiret = une courbe) : arcs reconstitues
        from compter_pointilles import arcs_pointilles
        for P in arcs_pointilles(pl, m_pt):
            cx, cy, r = kasa(P)
            ang = sorted(math.atan2(p[1] - cy, p[0] - cx) for p in P)
            trous = [(b - a, i) for i, (a, b) in enumerate(zip(ang, ang[1:]))] + [(ang[0] + 2 * math.pi - ang[-1], len(ang) - 1)]
            _, i = max(trous)                     # le plus grand trou angulaire = hors de l'arc ; les bouts l'encadrent
            a_deb, a_fin = ang[(i + 1) % len(ang)], ang[i]
            for a in (a_deb, a_fin):
                e = (cx + r * math.cos(a), cy + r * math.sin(a))
                ux, uy = math.cos(a), math.sin(a); pr = 0.05 / m_pt
                out.append(LineString([conv((cx - ux * pr, cy - uy * pr)), conv((e[0] + ux * pr, e[1] + uy * pr))]))
    return out


TOL_BAIE = 0.03   # distance max (m) entre le bout d une vitre et un mur parallele
DERNIERS_MURS_REELS = []   # [union des vrais murs] du dernier appel
DERNIERE_MATIERE = []   # [matiere fermee, m_pt] du dernier appel (diagnostic des fuites)
DERNIERES_VITRES = []   # vitres retenues au dernier appel (pour compter les fenetres : quantites.py)
DEMI_TRAIT = 0.001  # m : demi-largeur donnee a un trait epais (avant : son epaisseur reelle -> biais -1 %)
SANS_BLANC = False      # ecarter les bandes remplies en BLANC pur (masques, fonds) -- essai 26/11 (Briffaut : 6,1 m2 dans les vrais contours)
EXCLURE_SIG = set()     # conventions de dessin a NE PAS prendre pour des murs (candidat v3 « conventions du plan », 26/11)
DERNIERS_MORCEAUX = []  # [(geometrie, signature)] des vrais murs du dernier appel


def signature(o, ep=None):
    """convention de dessin d'un objet : bande (couleur de remplissage, fine ou non) ou trait (epaisseur, couleur)"""
    def c(v): return tuple(round(x, 2) for x in v) if isinstance(v, (list, tuple)) else v
    if ep is not None: return ("bande", c(o.get("non_stroking_color")), ep < 0.05)
    return ("trait", round(o.get("linewidth") or 0, 2), c(o.get("stroking_color")))


BAIES_PAQUET = False # fenetres = paquet de traits fins paralleles touchant le tableau du mur (candidat v3, 26/11)
ETIQ_PROCHE = False  # 27/11 : etiquette posee sur la matiere -> piece la plus proche (candidat v3)
IA_MURS = False      # 27/11 : candidat v3 « matiere + murs IA » (ia_sens.py)
PAS_MUR = set()      # 27/11 : couleurs que la LEGENDE du dossier dit « pas un mur » (conventions/<dossier>.json, lue par Claude)
NEUTRES = False      # 27/11 (diag 3102902 : objets interieurs pris pour murs = bandes beiges, traits magenta/bleu/orange) :
                     # le metreur sait que la COULEUR = annotation de lot ; murs = noir/gris. Candidat v3 : matiere neutre seule


def _vive(c):
    return isinstance(c, (list, tuple)) and len(c) == 3 and max(c) - min(c) > 0.12


def _pas_mur(c):
    return bool(PAS_MUR) and isinstance(c, (list, tuple)) and tuple(round(x, 2) for x in c) in PAS_MUR


DOUBLE_TRAIT = False # murs dessines en deux traits fins paralleles (convention CAO classique ; plan Scanner)
SANS_COTES = False    # 27/11 (548666 : chaines de cotes = courbes epaisses prises pour des murs) : variante v3 qui retire
                      # de la matiere les traits/courbes qui PORTENT un chiffre de cote (diag_cotes.ids_objets_de_cote)
CALCUL_DOUTES = True  # 27/11 : les variantes v3 ne gardent que la surface -> elles sautent la mesure « part inventee » (34 s/passe)

# 27/11 (profil 947775 : fusions des murs 41 s + 93 s par passe, refaites a chaque variante) : une fusion deja faite DANS CE
# programme est reprise si les morceaux sont EXACTEMENT les memes (empreinte des coordonnees binaires, dans l'ordre).
# Cas typique : une variante sans effet sur la page (pas de fond blanc, pas de couleur vive...). Resultat identique par construction.
_MEMO = {}


def _empreinte(geoms, *extra):
    import hashlib, shapely
    h = hashlib.sha1(repr(extra).encode())
    for b in shapely.to_wkb(np.array(list(geoms), dtype=object)): h.update(b)
    return h.hexdigest()


def _memo(cle, calcul):
    if cle not in _MEMO:
        if len(_MEMO) >= 4: _MEMO.clear()
        _MEMO[cle] = calcul()
    return _MEMO[cle]


def pieces_par_matiere(chemin, seuil=0.45, ep_max=0.35, couleurs="toutes", verbeux=True, rendre=False, baies=True, m_force=None):
    chemin = normaliser(chemin)
    W, H, etq, _ = lire_textes(chemin, 0)
    etq = etiquettes(etq)
    m_pt = m_force or echelle_par_cotes(chemin, 0)[0]
    if not m_pt: return []
    doc = pdfium.PdfDocument(chemin); OX, OY = origine(doc[0]); doc.close()
    pl = page_plumber(chemin)   # lecture unique (26/11)
    dy = H - OY
    conv = lambda p: (p[0] - OX, p[1] - dy)
    pl = dans_zone(pl, conv)   # 27/11 : seulement la ou il reste du travail (si metre.ZONE est defini)
    morceaux = []
    a_epaissir = []   # indices des traits epais (epaissis ensemble apres la boucle)
    sigs = []     # signature de chaque morceau « vrai mur » (convention de dessin) -- meme ordre que morceaux
    n_bandes = n_traits = 0
    ids_cotes = set()
    if SANS_COTES:
        from diag_cotes import ids_objets_de_cote
        ids_cotes = ids_objets_de_cote(chemin)
    for o in pl.lines + pl.rects + pl.curves:
        if ids_cotes and id(o) in ids_cotes: continue
        pts = o.get("pts") or []
        if len(pts) < 2: continue
        lw = o.get("linewidth") or 0
        if o.get("fill") and len(pts) >= 3:
            c = o.get("non_stroking_color")
            if couleurs == "foncees":
                if not (isinstance(c, (list, tuple)) and len(c) in (1, 3) and sum(c) / len(c) <= 0.75): c = None
            if c is not None:
                try:
                    P = Polygon([conv(p) for p in pts]).buffer(0)
                except Exception:
                    P = None
                if P is not None and not P.is_empty and P.length:
                    ep = 2 * P.area / P.length * m_pt
                    # LETTRES VECTORISEES (racine mesuree 26/11, Scanner : 33 etiquettes sur 38 posees sur le nom de la
                    # piece dessine en contours) : > 40 points ET < 4 cm d'epaisseur. Mesure sur le banc : 646 objets sur
                    # Scanner, TOUS sur du texte ; 0 sur Guyane, Briffaut, CPAM -> aucun vrai mur ecarte.
                    if len(pts) > 40 and ep < 0.04: continue
                    if SANS_BLANC and isinstance(c, (list, tuple)) and len(c) in (1, 3) and min(c) >= 0.98: continue
                    if NEUTRES and _vive(c): continue
                    if _pas_mur(c): continue
                    if 0.02 <= ep <= ep_max:
                        sg = signature(o, ep)
                        if sg not in EXCLURE_SIG:
                            morceaux.append(P); n_bandes += 1; sigs.append(sg)
                            continue
        if lw >= seuil:
            if NEUTRES and _vive(o.get("stroking_color")): continue
            if _pas_mur(o.get("stroking_color")): continue
            sg = signature(o)
            if sg in EXCLURE_SIG: continue
            ln = LineString([conv(p) for p in pts])
            # un trait de contour = la LIMITE elle-meme (l architecte mesure au milieu du trait : faces.py tombait a 0,0 %)
            # -> on ne l elargit que de 1 mm (racine du biais -1 % du 25/11)
            a_epaissir.append(len(morceaux)); morceaux.append(ln); n_traits += 1; sigs.append(sg)
    # epaissir TOUS les traits d'un coup (27/11 : 14 000 appels un par un = 2,2 s par appel de la methode)
    if a_epaissir:
        import shapely
        ep = shapely.buffer(np.array([morceaux[i] for i in a_epaissir], dtype=object), DEMI_TRAIT / m_pt,
                            cap_style="flat", join_style="mitre")
        for i, g in zip(a_epaissir, ep): morceaux[i] = g
    n_double = 0
    if DOUBLE_TRAIT:
        # MURS EN DOUBLE TRAIT (racine du plan Scanner, 26/11) : deux traits FINS paralleles, espaces de 5 a 40 cm,
        # qui se font face sur >= 50 % de la longueur du plus court = les deux faces d'une cloison.
        from shapely.strtree import STRtree as _ST
        fins = []
        for o in pl.lines:
            pts = o.get("pts") or []
            if len(pts) != 2 or (o.get("linewidth") or 0) >= seuil: continue
            a, b = conv(pts[0]), conv(pts[1])
            if math.dist(a, b) * m_pt >= 0.30: fins.append(LineString([a, b]))
        if fins:
            arbre_f = _ST(fins)
            garde = set()
            for i, l in enumerate(fins):
                (x1, y1), (x2, y2) = l.coords; L = l.length
                ux, uy = (x2 - x1) / L, (y2 - y1) / L
                for j in arbre_f.query(l.buffer(0.40 / m_pt)):
                    if j <= i: continue
                    l2 = fins[j]; (x3, y3), (x4, y4) = l2.coords
                    v = ((x4 - x3) / l2.length, (y4 - y3) / l2.length)
                    if abs(ux * v[1] - uy * v[0]) > 0.035: continue          # pas parallele (~2 degres)
                    d = abs((x3 - x1) * uy - (y3 - y1) * ux) * m_pt           # ecart perpendiculaire
                    if not (0.05 <= d <= 0.40): continue
                    p3, p4 = (x3 - x1) * ux + (y3 - y1) * uy, (x4 - x1) * ux + (y4 - y1) * uy
                    recouvre = min(L, max(p3, p4)) - max(0, min(p3, p4))
                    if recouvre >= 0.5 * min(L, l2.length): garde.update((i, j))
            for i in garde:
                morceaux.append(fins[i].buffer(DEMI_TRAIT / m_pt, cap_style=2)); n_double += 1
    DERNIERS_MORCEAUX[:] = list(zip(morceaux[:len(sigs)], sigs))   # bandes + traits epais (avant double trait)
    n_reels = len(morceaux)   # jusqu'ici : VRAIS murs (bandes, traits epais) ; apres : vitres et portes = fermetures « inventees »
    n_baies = 0
    DERNIERES_VITRES.clear()
    if baies:
        # FENETRES (racine trouvee 25/11 sur Forestier bio) : la vitre = traits FINS dans l'ouverture du mur.
        # Une vitre prolonge un mur PARALLELE a elle a ses deux bouts ; une ligne de cote touche des murs PERPENDICULAIRES.
        from shapely.strtree import STRtree
        def direction(g):
            r = g.minimum_rotated_rectangle
            if r.geom_type != "Polygon" or len(r.exterior.coords) < 4: return None
            c = list(r.exterior.coords)
            l1 = math.hypot(c[1][0] - c[0][0], c[1][1] - c[0][1]); l2 = math.hypot(c[2][0] - c[1][0], c[2][1] - c[1][1])
            if min(l1, l2) == 0 or max(l1, l2) / min(l1, l2) < 2: return None   # pas allonge
            a, b = (c[0], c[1]) if l1 >= l2 else (c[1], c[2])
            return math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
        def cote_parallele(g, p, ang):
            for poly in getattr(g, "geoms", [g]):
                if poly.geom_type != "Polygon": continue
                c = list(poly.exterior.coords)
                for (x1, y1), (x2, y2) in zip(c, c[1:]):
                    if math.hypot(x2 - x1, y2 - y1) * m_pt < 0.30: continue
                    a2 = math.atan2(y2 - y1, x2 - x1) % math.pi
                    if min(abs(a2 - ang), math.pi - abs(a2 - ang)) >= math.radians(10): continue
                    if LineString([(x1, y1), (x2, y2)]).distance(p) * m_pt <= 0.20: return True
            return False
        murs = [g for g in morceaux]
        dirs = [direction(g) for g in murs]
        arbre = STRtree(murs)
        tol = TOL_BAIE / m_pt
        cotes_fins = []
        for o in pl.lines + pl.curves + pl.rects:
            pts = o.get("pts") or []
            if len(pts) < 2 or (o.get("linewidth") or 0) >= seuil or o.get("fill"): continue
            # un contour fin (cadre de fenetre = petit rectangle) est decoupe en ses cotes
            if o.get("object_type") == "rect" and len(pts) >= 4: pts = list(pts) + [pts[0]]
            cotes_fins += list(zip(pts, pts[1:]))
        jumeaux = None
        if BAIES_PAQUET:
            # FENETRE EN PAQUET (racine mesuree 26/11, Guyane : 4 pieces sur 8 ratees) : la vitre touche le TABLEAU
            # du mur (face perpendiculaire de 14 cm) -> pas de cote parallele de 30 cm ; mais une fenetre = 3-4 traits
            # fins PARALLELES de meme longueur (cadre + vitrage), une cote = un trait seul.
            segs_f = [LineString([conv(pa), conv(pb)]) for pa, pb in cotes_fins]
            arbre_s = STRtree(segs_f) if segs_f else None
            def jumeaux(i):
                s = segs_f[i]; (x1, y1), (x2, y2) = s.coords; L = s.length
                if not L: return False
                ux, uy = (x2 - x1) / L, (y2 - y1) / L
                for j in arbre_s.query(s.buffer(0.35 / m_pt)):
                    if j == i: continue
                    t = segs_f[j]; (x3, y3), (x4, y4) = t.coords; L2 = t.length
                    if not L2 or abs(L2 - L) > 0.2 * L: continue
                    if abs(ux * (y4 - y3) / L2 - uy * (x4 - x3) / L2) > 0.035: continue
                    d = abs((x3 - x1) * uy - (y3 - y1) * ux) * m_pt
                    if not (0.01 <= d <= 0.35): continue
                    p3, p4 = (x3 - x1) * ux + (y3 - y1) * uy, (x4 - x1) * ux + (y4 - y1) * uy
                    if min(L, max(p3, p4)) - max(0, min(p3, p4)) >= 0.8 * L: return True
                return False
        for idx, (pa, pb) in enumerate(cotes_fins):
            a, b = conv(pa), conv(pb)
            L = math.hypot(b[0] - a[0], b[1] - a[1]) * m_pt
            if not (0.3 <= L <= 4): continue
            ang = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
            ok = True
            for bout in (a, b):
                p = Point(bout)
                proches = [i for i in arbre.query(p.buffer(tol)) if murs[i].distance(p) <= tol]
                # direction LOCALE (racine 25/11 : un mur d'angle en L n'a pas de direction globale) :
                # le morceau doit avoir, a moins de 20 cm du bout, un cote >= 30 cm parallele a la vitre
                if not any(cote_parallele(murs[i], p, ang) for i in proches):
                    ok = False; break
            if not ok and jumeaux is not None and L <= 3.0:
                # regle « paquet » : un mur a <= 3 cm de CHAQUE bout (toute orientation) + un jumeau parallele
                ok = all(any(murs[i].distance(Point(bt)) <= tol for i in arbre.query(Point(bt).buffer(tol))) for bt in (a, b)) \
                     and jumeaux(idx)
            if ok:
                morceaux.append(LineString([a, b]).buffer(DEMI_TRAIT / m_pt, cap_style=2)); n_baies += 1
                DERNIERES_VITRES.append(LineString([a, b]))
    cordes = portes(pl, m_pt, conv)
    reels_u = _memo(_empreinte(morceaux[:n_reels], "reels"), lambda: unary_union(morceaux[:n_reels]))   # fusion des VRAIS murs calculee UNE fois
    DERNIERS_MURS_REELS[:] = [reels_u]   # vrais murs seuls (pour trier vitres / contours)
    morceaux += [c.buffer(DEMI_TRAIT / m_pt, cap_style=2) for c in cordes]
    if IA_MURS:   # 27/11 : l'IA « sens » (apprise sur les autres pages du dossier) ajoute les murs qu'elle reconnait
        from ia_sens import murs_ia
        morceaux += murs_ia(chemin, pl, conv, m_pt, unary_union(morceaux))
    # micro-ecarts du dessin (ex. Repro, 25/11) : on referme les fentes < 2 cm
    mat = _memo(_empreinte(morceaux, "mat", m_pt, n_reels),
                lambda: unary_union([reels_u] + morceaux[n_reels:]).buffer(0.01 / m_pt, join_style=2))
    DERNIERE_MATIERE[:] = [mat, m_pt]   # pour diag_fuites.py (ou fuit chaque piece, et pourquoi)
    trous = [Polygon(a) for g in getattr(mat, "geoms", [mat]) for a in g.interiors]
    res, reels = [], None
    for e in etq:
        p = Point(e["x"], e["y"])
        t = [h for h in trous if h.contains(p)]
        if not t and ETIQ_PROCHE and mat.contains(p):
            # 27/11 (diag 3102902 : 8 etiquettes posees SUR un aplat) : le metreur prend la piece juste a cote du texte
            import collections as _c
            vois = _c.Counter()
            for r_ in (0.15, 0.30, 0.50):
                for i_ in range(12):
                    q = Point(p.x + r_ / m_pt * math.cos(i_ * math.pi / 6), p.y + r_ / m_pt * math.sin(i_ * math.pi / 6))
                    for j_, h_ in enumerate(trous):
                        if h_.contains(q): vois[j_] += 1; break
                if vois: break
            if vois: t = [trous[vois.most_common(1)[0][0]]]
        if not t: res.append((e, None, None)); continue
        h = min(t, key=lambda h: h.area)
        # on rend la bande de 1 cm retiree par la fermeture des fentes
        h = h.buffer(0.01 / m_pt, join_style=2)   # on rend exactement le cm retire par la fermeture des fentes
        a = h.area * m_pt * m_pt
        # CONFIANCE (ordre de verification, idee d'OpenTakeoff confidence.ts + notre atout la surface ecrite) :
        # 27/11 (profil CALIGNAC p5 : 52 s sur 92 dans UN buffer de tous les murs du plan) : on n'epaissit que les murs
        # PROCHES de la piece. Exact : un point du bord est a moins de r d'un mur ssi il l'est d'un mur de la boite
        # elargie de r ; marge 2r pour que les coupes de la boite restent loin du bord.
        if CALCUL_DOUTES:
            r_ = 0.03 / m_pt
            x0, y0, x1, y1 = h.bounds
            reels = reels_u.intersection(box(x0 - 2 * r_, y0 - 2 * r_, x1 + 2 * r_, y1 + 2 * r_)).buffer(r_)
            bord = h.exterior
            e["part_inventee"] = round(1 - bord.intersection(reels).length / max(bord.length, 1e-9), 3)
        e["ecart_ecrit_pct"] = round(100 * (a / e["surface_ecrite"] - 1), 2) if e.get("surface_ecrite") else None
        doutes = []
        if e["ecart_ecrit_pct"] is not None and abs(e["ecart_ecrit_pct"]) > 1: doutes.append("écart %+.1f %% avec la surface écrite" % e["ecart_ecrit_pct"])
        if (e.get("part_inventee") or 0) > 0.25: doutes.append("%d %% du contour fermé artificiellement (porte, fenêtre)" % (100 * e["part_inventee"]))
        if not (0.5 <= a <= 400): doutes.append("taille peu plausible (%.1f m²)" % a)
        e["doutes"] = doutes
        res.append((e, a, h))
    if verbeux:
        ok = [(e, a) for e, a, _ in res if a]
        n3 = sum(1 for e, a in ok if abs(a / e["surface_ecrite"] - 1) <= 0.03)
        n10 = sum(1 for e, a in ok if abs(a / e["surface_ecrite"] - 1) <= 0.10)
        print("double trait %d | baies %d | bandes %d | traits %d | portes %d | trous %d | pieces %d | trouvees %d | a 3%% : %d | a 10%% : %d" % (
            n_double, n_baies, n_bandes, n_traits, len(cordes) // 2, len(trous), len(res), len(ok), n3, n10))
    return res if rendre else [(e, a) for e, a, _ in res]


if __name__ == "__main__":
    for e, a in pieces_par_matiere(sys.argv[1], couleurs=sys.argv[2] if len(sys.argv) > 2 else "toutes",
                                   ep_max=float(sys.argv[3]) if len(sys.argv) > 3 else 0.35):
        print("  %-28s ecrite %7.2f | calculee %s" % ((e.get("nom") or "")[:28], e["surface_ecrite"],
              "%7.2f (%+.1f %%)" % (a, 100 * (a / e["surface_ecrite"] - 1)) if a else "   -- non fermee"))
