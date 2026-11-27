"""Test 3 de la declaration « Test IA dossiers neufs » (ecrite le 26/11, avant la recolte) : l'outil v3 sur les pages NEUVES.
Mesure : part des pieces « sures » (< 1 % de la surface ecrite), comparee au banc (125/224 = 56 %).
Si les neufs sont a plus de 15 points sous le banc -> on a sur-appris le banc.
  python un_par_un.py test_neufs.py plans_neufs      (une page par programme : memoire rendue a chaque page)
  python test_neufs.py --bilan
Rien n'est regle ici : on mesure seulement."""
import glob, json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
SORTIE = os.path.join(ici, "sorties", "neufs_v3"); os.makedirs(SORTIE, exist_ok=True)
BANC = 125 / 224

if sys.argv[1] == "--page":
    f = sys.argv[2]
    nom = os.path.splitext(os.path.basename(f))[0][:80]
    js = os.path.join(SORTIE, nom + ".json")
    if os.path.exists(js): print("%-60s deja fait" % nom[:60]); sys.exit(0)
    t = time.time()
    import metre_v3
    metre_v3.PARALLELE = 1
    old = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
    try:
        R = metre_v3.pieces_v3(f)
    finally:
        sys.stdout.close(); sys.stdout = old
    n, s = len(R), sum(1 for r in R if r["sure"])
    cb = sum(1 for r in R if r["e"].get("coupee_bord"))
    det = [{"nom": r["e"].get("nom", ""), "ecrite": r["e"].get("surface_ecrite"), "mesuree": r.get("a"), "sure": bool(r["sure"]),
            "coupee_bord": bool(r["e"].get("coupee_bord"))} for r in R]   # detail par piece (pour le livre des pieces, mesure seule)
    json.dump({"page": nom, "pieces": n, "sures": s, "coupees_bord": cb, "secondes": round(time.time() - t), "detail": det},
              open(js, "w", encoding="utf-8"), ensure_ascii=False)
    print("%-60s pieces %4d | sures %4d | coupees bord %3d | %d s" % (nom[:60], n, s, cb, time.time() - t), flush=True)

elif sys.argv[1] == "--bilan":
    L = [json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob(os.path.join(SORTIE, "*.json")))]
    N = sum(x["pieces"] for x in L); S = sum(x["sures"] for x in L)
    par_dossier = {}
    for x in L:
        d = par_dossier.setdefault(x["page"].split("_")[0], [0, 0]); d[0] += x["pieces"]; d[1] += x["sures"]
    for k, (n, s) in sorted(par_dossier.items()):
        print("%-10s %4d pieces | %4d sures (%3.0f %%)" % (k, n, s, 100 * s / max(n, 1)))
    part = S / max(N, 1)
    print("TOTAL %d pages | %d pieces | %d sures = %.0f %% | banc %.0f %% | ecart %+.0f pts -> %s" % (
        len(L), N, S, 100 * part, 100 * BANC, 100 * (part - BANC),
        "SUR-APPRIS LE BANC (> 15 pts sous)" if part < BANC - 0.15 else "pas de sur-apprentissage"))
