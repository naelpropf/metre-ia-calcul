"""LIVRE DES PIECES (27/11) -- logique des pieces apprise sur Swiss Dwellings v3 (Zenodo 7788422, CC BY 4.0, Archilyse).
Pour chaque piece : type, surface, perimetre, nb de sommets, rectangularite, nb de portes / fenetres qui la touchent,
types des pieces voisines (qui partagent un mur ou une porte). Lecture en flux, appartement par appartement (memoire).
Sortie : sorties/livre_des_pieces.jsonl.gz (une ligne par piece) + resume.
Attribution : Swiss Dwellings, Archilyse AG / Standfest et al., CC BY 4.0."""
import csv, gzip, json, os, sys, collections, time
from shapely import wkt
from shapely.strtree import STRtree
sys.stdout.reconfigure(encoding="utf-8")
csv.field_size_limit(10 ** 9)
ici = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ici, "..", "donnees_externes", "swiss_dwellings", "swiss-dwellings-v3.0.0", "geometries.csv")
OUT = os.path.join(ici, "sorties", "livre_des_pieces.jsonl.gz")


def traiter(lignes, sortie):
    aires = [r for r in lignes if r["entity_type"] == "area"]
    if not aires: return 0
    G = {}
    for r in lignes:
        try: G[id(r)] = wkt.loads(r["geometry"])
        except Exception: G[id(r)] = None
    A = [(r, G[id(r)]) for r in aires if G[id(r)] is not None and G[id(r)].area > 0]
    portes = [G[id(r)] for r in lignes if r["entity_type"] == "opening" and "DOOR" in r["entity_subtype"] and G[id(r)] is not None]
    fen = [G[id(r)] for r in lignes if r["entity_subtype"] == "WINDOW" and G[id(r)] is not None]
    if not A: return 0
    arbre = STRtree([g for _, g in A])
    tp = STRtree(portes) if portes else None; tf = STRtree(fen) if fen else None
    n = 0
    for i, (r, g) in enumerate(A):
        voisins, par_porte = collections.Counter(), collections.Counter()
        for j in arbre.query(g.buffer(0.45)):   # murs de 10 a 40 cm : les pieces voisines sont a moins de 45 cm
            if j == i: continue
            voisins[A[j][0]["entity_subtype"]] += 1
        np_ = 0
        if tp is not None:
            for k in tp.query(g.buffer(0.05)):
                np_ += 1
                for j in arbre.query(portes[k].buffer(0.05)):
                    if j != i: par_porte[A[j][0]["entity_subtype"]] += 1
        nf = len(tf.query(g.buffer(0.05))) if tf is not None else 0
        mrr = g.minimum_rotated_rectangle
        sortie.write(json.dumps({
            "type": r["entity_subtype"], "usage": r["unit_usage"], "surface": round(g.area, 2), "perimetre": round(g.length, 2),
            "sommets": len(g.exterior.coords) - 1 if g.geom_type == "Polygon" else -1,
            "rect": round(g.area / mrr.area, 3) if mrr.area else 0, "hauteur": float(r["height"] or 0),
            "portes": np_, "fenetres": nf, "voisins": dict(voisins), "par_porte": dict(par_porte)}) + "\n")
        n += 1
    return n


if __name__ == "__main__":
    t0 = time.time(); tot = 0; napp = 0
    with open(SRC, encoding="utf-8", newline="") as f, gzip.open(OUT, "wt", encoding="utf-8") as s:
        cur, lot = None, []
        for r in csv.DictReader(f):
            cle = (r["apartment_id"], r["floor_id"])
            if cle != cur and lot:
                tot += traiter(lot, s); napp += 1; lot = []
                if napp % 2000 == 0: print("  %d logements-etages, %d pieces, %d s" % (napp, tot, time.time() - t0), flush=True)
            cur = cle; lot.append(r)
        if lot: tot += traiter(lot, s); napp += 1
    print("FINI : %d logements-etages, %d pieces -> %s (%d s)" % (napp, tot, OUT, time.time() - t0))
