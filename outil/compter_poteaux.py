"""POTEAUX dessines en rectangle a trait fin (3068854 : symbole « I » le long de la facade ; les cloisons s'y arretent, mais le
rectangle n'est pas dans la matiere -> les pieces communiquent autour). Combien par page ? (27/11)
Poteau = rectangle (pl.rects, ou trait ferme a 4-5 points) NON rempli, cotes 0,15-0,60 m, a < 5 cm de la matiere des murs.
Regle ecrite avant (journal) : frequent si >= 100 poteaux ET >= 3 dossiers.   python compter_poteaux.py [dossier]
Fonction reutilisable : poteaux(pl, m_pt) -> [liste de 4 points (coordonnees pdfplumber)]"""
import glob, math, os, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)


def poteaux(pl, m_pt):
    out = []
    for o in pl.rects + pl.curves + pl.lines:
        pts = o.get("pts") or []
        if o.get("fill") or len(pts) not in (4, 5): continue
        if len(pts) == 5 and math.dist(pts[0], pts[-1]) * m_pt > 0.01: continue   # trait ferme : 1er = dernier point
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        w, h = (max(xs) - min(xs)) * m_pt, (max(ys) - min(ys)) * m_pt
        if 0.15 <= w <= 0.60 and 0.15 <= h <= 0.60:
            out.append([(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))])
    return out


if __name__ == "__main__":
    import matiere
    from metre import normaliser, page_plumber, lire_textes, origine
    from shapely.geometry import Polygon
    import pypdfium2 as pdfium
    D = sys.argv[1] if len(sys.argv) > 1 else "plans_neufs"
    tot, dos = 0, collections.Counter()
    for f in sorted(glob.glob(os.path.join(ici, D, "*.pdf"))):
        try:
            ch = normaliser(f)
            old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
            try: matiere.pieces_par_matiere(ch, verbeux=False)
            finally: sys.stdout.close(); sys.stdout = old
            if not matiere.DERNIERE_MATIERE: continue
            MAT, m = matiere.DERNIERE_MATIERE
            W, H, _, _ = lire_textes(ch, 0); d = pdfium.PdfDocument(ch); OX, OY = origine(d[0]); d.close(); dy = H - OY
            n = 0
            for P in poteaux(page_plumber(ch), m):
                g = Polygon([(p[0] - OX, p[1] - dy) for p in P])
                if g.distance(MAT) * m <= 0.05 and not MAT.contains(g): n += 1
            if n:
                tot += n; dos[os.path.basename(f).split("_")[0]] += n
                print("%-55s poteaux a trait fin %3d" % (os.path.basename(f)[:55], n), flush=True)
        except Exception as ex:
            print("ERREUR", os.path.basename(f)[:50], str(ex)[:60])
    print("\nTOTAL poteaux %d | dossiers %d %s" % (tot, len(dos), dict(dos)))
    print("REGLE (>= 100 ET >= 3 dossiers) -> %s" % ("FREQUENT" if tot >= 100 and len(dos) >= 3 else "NON"))
