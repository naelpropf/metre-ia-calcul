"""S1 -- mesure de developpement sur les 7 plans d'essai (seuil ecrit avant dans le coffre, note S1) :
>= 5 plans sur 7 ou >= 80 % des pieces lues sont a +/- 3 % de la surface ecrite."""
import gc, glob, json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
from metre import mesurer
version = sys.argv[1] if len(sys.argv) > 1 else "v0"
options = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}  # ex. '{"fermer_portes": 1.1}'
lignes, ok_plans = [], 0
for f in sorted(glob.glob(os.path.join(ici, "plans_test", "*.pdf"))):
    t = time.time()
    try:
        r = mesurer(f, sortie=os.path.join(ici, "sorties", version), **options)
    except Exception as e:
        print("ERREUR", os.path.basename(f), e, flush=True); continue
    p = r["pieces"]; n = len(p)
    e3 = sum(1 for e in p if e.get("ecart_pct") is not None and abs(e["ecart_pct"]) <= 3)
    e10 = sum(1 for e in p if e.get("ecart_pct") is not None and abs(e["ecart_pct"]) <= 10)
    passe = n > 0 and e3 >= 0.8 * n
    ok_plans += passe
    l = {"plan": os.path.basename(f)[:60], "pieces": n, "a_3pct": e3, "a_10pct": e10, "echelle": r["echelle_source"],
         "passe": passe, "secondes": round(time.time() - t)}
    lignes.append(l)
    print("%-60s pieces %3d | a 3 %% : %3d (%3.0f %%) | a 10 %% : %3d (%3.0f %%) | %s | %d s" % (
        l["plan"], n, e3, 100 * e3 / max(1, n), e10, 100 * e10 / max(1, n), r["echelle_source"][:22], l["secondes"]), flush=True)
    del r; gc.collect()
print("\nPLANS QUI PASSENT (>= 80 %% des pieces a 3 %%) : %d sur %d -> %s" % (ok_plans, len(lignes), "SEUIL PASSE" if ok_plans >= 5 else "SEUIL PAS ENCORE ATTEINT"))
json.dump(lignes, open(os.path.join(ici, "sorties", version, "s1_mesure.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
