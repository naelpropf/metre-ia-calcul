"""Ou part le temps sur UNE page ? (27/11, pour accelerer l'examen) -- mesure seulement, rien n'est regle.
  python profiler_page.py <pdf> [sortie.txt]
Ecrit les 40 fonctions qui prennent le plus de temps (cumule et propre) dans sorties/profil_<page>.txt."""
import cProfile, io, os, pstats, sys, time
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
f = sys.argv[1]
nom = os.path.splitext(os.path.basename(f))[0][:60]
dest = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ici, "sorties", "profil_" + nom + ".txt")
import metre_v3
metre_v3.PARALLELE = 1          # comme l'examen : tout dans un seul programme, pour que le profil voie tout
t = time.time()
pr = cProfile.Profile(); pr.enable()
R = metre_v3.pieces_v3(f)
pr.disable()
s = io.StringIO()
st = pstats.Stats(pr, stream=s)
s.write("PAGE %s | %d pieces | %.0f s\n\n=== TRIE PAR TEMPS CUMULE ===\n" % (nom, len(R), time.time() - t))
st.sort_stats("cumulative").print_stats(40)
s.write("\n=== TRIE PAR TEMPS PROPRE ===\n")
st.sort_stats("tottime").print_stats(40)
open(dest, "w", encoding="utf-8").write(s.getvalue())
print("FINI %s | %.0f s | profil : %s" % (nom, time.time() - t, dest), flush=True)
