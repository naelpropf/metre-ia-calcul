"""Portes dessinees en POINTILLES (quart de cercle en tirets, chaque tiret = une petite courbe) : combien par page ? (27/11)
On raccroche les petites courbes non remplies dont les bouts sont a < 15 cm, puis meme detection de porte que matiere.portes
(Kasa sur les points reunis, rayon 0,55-1,3 m, ouverture 40-120 deg). Regle ecrite avant (journal) : cause frequente si
>= 50 portes en pointilles ET >= 3 dossiers.     python compter_pointilles.py [dossier_de_pdf]
Fonction reutilisable : arcs_pointilles(pl, m_pt) -> [liste de points (coordonnees pdfplumber)] par porte."""
import glob, math, os, sys, collections
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
from faces import kasa


def arcs_pointilles(pl, m_pt):
    # 27/11 soir : un arc en tirets est trace avec UN SEUL stylo -> on ne regroupe que des tirets de meme couleur et meme
    # epaisseur (3094167 : les tirets gris de l'arc fusionnaient avec les hachures noires du mur voisin -> 0 arc ; gris seuls -> 1)
    stylos = collections.defaultdict(list)
    for o in pl.curves + pl.lines:
        pts = o.get("pts") or []
        if o.get("fill") or len(pts) < 2: continue
        L = sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) * m_pt
        if L <= 0.40: stylos[(str(o.get("stroking_color")), round(o.get("linewidth") or 0, 2))].append(pts)   # un tiret : court
    out = []
    for petits in stylos.values(): out += _arcs_d_un_stylo(petits, m_pt)
    return out


def _arcs_d_un_stylo(petits, m_pt):
    if not petits: return []
    from scipy.spatial import cKDTree
    bouts = np.array([p[0] for p in petits] + [p[-1] for p in petits], float)
    arbre = cKDTree(bouts); n = len(petits); tol = 0.15 / m_pt
    parent = list(range(n))
    def racine(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, j in arbre.query_pairs(tol):
        a, b = racine(i % n), racine(j % n)
        if a != b: parent[a] = b
    groupes = collections.defaultdict(list)
    for i in range(n): groupes[racine(i)].append(i)
    out = []
    for g in groupes.values():
        if len(g) < 3: continue                   # une porte en pointilles = plusieurs tirets
        P = [p for i in g for p in petits[i]]
        k = kasa(P)
        if not k: continue
        cx, cy, r = k
        if not (0.55 <= r * m_pt <= 1.3): continue
        if max(abs(math.dist(p, (cx, cy)) - r) for p in P) * m_pt > 0.05: continue   # les points sont bien SUR le cercle
        ang = sorted(math.atan2(p[1] - cy, p[0] - cx) for p in P)
        trous = [b - a for a, b in zip(ang, ang[1:])] + [ang[0] + 2 * math.pi - ang[-1]]
        bal = 2 * math.pi - max(trous)            # etendue angulaire couverte
        if 0.7 <= bal <= 2.1: out.append(P)
    return out


if __name__ == "__main__":
    from metre import normaliser, page_plumber, echelle_par_cotes
    D = sys.argv[1] if len(sys.argv) > 1 else "plans_neufs"
    tot, dos = 0, collections.Counter()
    for f in sorted(glob.glob(os.path.join(ici, D, "*.pdf"))):
        try:
            ch = normaliser(f)
            old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
            try: m = echelle_par_cotes(ch, 0)[0]
            finally: sys.stdout.close(); sys.stdout = old
            if not m: continue
            n = len(arcs_pointilles(page_plumber(ch), m))
            if n:
                tot += n; dos[os.path.basename(f).split("_")[0]] += n
                print("%-55s portes en pointilles %3d" % (os.path.basename(f)[:55], n), flush=True)
        except Exception as ex:
            print("ERREUR", os.path.basename(f)[:50], str(ex)[:60])
    print("\nTOTAL portes en pointilles %d | dossiers %d %s" % (tot, len(dos), dict(dos)))
    print("REGLE (>= 50 ET >= 3 dossiers) -> %s" % ("CAUSE FREQUENTE" if tot >= 50 and len(dos) >= 3 else "NON"))
