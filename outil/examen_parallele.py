"""Examen des dossiers neufs EN PARALLELE (27/11, pour Colab ou toute machine a plusieurs coeurs).
Meme calcul que `python un_par_un.py test_neufs.py plans_neufs` : une page par programme neuf (memoire rendue),
meme limite de temps par page (TEMPS_MAX, 1500 s par defaut), mais N pages a la fois, les plus longues d'abord.
  python examen_parallele.py N            -> toutes les pages, N a la fois
  python examen_parallele.py N k/n        -> seulement la part k sur n (pour repartir sur plusieurs machines)
Les resultats vont dans sorties/neufs_v3 (un .json par page, avec sa duree) ; a la fin : test_neufs.py --bilan."""
import glob, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 2
TEMPS_MAX = int(os.environ.get("TEMPS_MAX", "1500"))
pages = sorted(glob.glob(os.path.join(ici, "plans_neufs", "*.pdf")))
# les plus longues d'abord (durees de l'examen local du 27/11 si connues) : la derniere page ne bloque pas la fin ;
# le tri se fait AVANT le partage, pour que chaque part recoive un melange de pages longues et courtes
durees = {}
fd = os.path.join(ici, "durees_examen_local.json")
if os.path.exists(fd):
    durees = json.load(open(fd, encoding="utf-8"))
pages.sort(key=lambda f: (-durees.get(os.path.splitext(os.path.basename(f))[0][:80], 0), f))
if len(sys.argv) > 2:
    k, n = (int(x) for x in sys.argv[2].split("/"))
    pages = pages[k - 1::n]
print("%d pages, %d a la fois, limite %d s par page" % (len(pages), N, TEMPS_MAX), flush=True)
debut = time.time()


def une_page(f):
    nom = os.path.splitext(os.path.basename(f))[0]
    t = time.time()
    try:
        r = subprocess.run([sys.executable, "-u", "test_neufs.py", "--page", f], cwd=ici, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=TEMPS_MAX)
    except subprocess.TimeoutExpired:
        return "%-60s TROP LONG (> %d s) : mise de cote" % (nom[:60], TEMPS_MAX)
    if r.returncode:
        err = (r.stderr or "").strip().splitlines()
        return "%-60s PLANTE (%s) | %d s" % (nom[:60], err[-1][:90] if err else "?", time.time() - t)
    sortie = (r.stdout or "").strip().splitlines()
    return sortie[-1] if sortie else "%-60s (rien)" % nom[:60]


with ThreadPoolExecutor(max_workers=N) as ex:
    for i, ligne in enumerate(ex.map(une_page, pages), 1):
        print("[%d/%d | %.1f min] %s" % (i, len(pages), (time.time() - debut) / 60, ligne), flush=True)
print("FINI en %.1f min" % ((time.time() - debut) / 60), flush=True)
