"""Validation au PC de la variante « ouvertures de mur » (27/11) : une page, avec et sans.   python valider_ouvertures.py <debut>"""
import glob, os, sys, time
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
import matiere
from metre import normaliser
f = normaliser(glob.glob(os.path.join(ici, "plans_neufs", glob.escape(sys.argv[1]) + "*.pdf"))[0])
for v in (False, True):
    matiere.OUVERTURES = v; t = time.time()
    o = sys.stdout; sys.stdout = open(os.devnull, "w", encoding="utf-8")
    R = matiere.pieces_par_matiere(f, verbeux=False)
    sys.stdout.close(); sys.stdout = o
    ok = [(e, a) for e, a in R if a]; q = np.array([a / e["surface_ecrite"] for e, a in ok]) if ok else np.array([0.0])
    print("%-22s ouvertures %-5s | %4.0f s | mesurees %3d/%3d | surfaces distinctes %3d | a 1 %%: %3d | a 3 %%: %3d | a 10 %%: %3d" % (
        sys.argv[1][:22], v, time.time() - t, len(ok), len(R), len({round(a, 2) for e, a in ok}),
        np.sum(abs(q - 1) <= 0.01), np.sum(abs(q - 1) <= 0.03), np.sum(abs(q - 1) <= 0.10)), flush=True)
