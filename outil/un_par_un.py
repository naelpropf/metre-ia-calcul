"""Idee du porteur (27/11) : remettre la memoire a zero. Chaque page est traitee par un programme NEUF ; a sa fin, Windows
reprend toute sa memoire. Une page qui plante ne fait plus tomber les suivantes.
Usage : python un_par_un.py <script.py> <dossier> [<dossier> ...]   (les variables d'environnement sont transmises)
Le script doit accepter SEULEMENT=<nom de page> (objets.py) ou un chemin de PDF en argument (langue_cache.py --page)."""
import glob, os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
script, dossiers = sys.argv[1], sys.argv[2:]
TEMPS_MAX = int(os.environ.get("TEMPS_MAX", "1500"))   # 27/11 : une page geante (EFS, 3 h) bloquait toute la file


def lancer(cmd, env):
    try:
        return subprocess.run(cmd, cwd=ici, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TEMPS_MAX)
    except subprocess.TimeoutExpired:
        return None
for D in dossiers:
    for f in sorted(glob.glob(os.path.join(ici, D, "*.pdf"))):
        nom = os.path.splitext(os.path.basename(f))[0]
        t = time.time()
        if script == "objets.py":
            env = dict(os.environ, SEULEMENT=nom, PART="1/1")
            r = lancer([sys.executable, "-u", script, D], env)
        else:
            r = lancer([sys.executable, "-u", script, "--page", f], None)
        if r is None:
            print("%-60s TROP LONG (> %d s) : mise de cote" % (nom[:60], TEMPS_MAX), flush=True); continue
        sortie = (r.stdout or "").strip().splitlines()
        if r.returncode:
            err = (r.stderr or "").strip().splitlines()
            print("%-60s PLANTE (%s) | %d s" % (nom[:60], err[-1][:90] if err else "?", time.time() - t), flush=True)
        elif sortie:
            print(sortie[-1], flush=True)
