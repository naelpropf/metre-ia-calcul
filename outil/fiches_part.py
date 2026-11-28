"""FICHES SUR GITHUB (28/11) : une part des plans d'entrainement -> triage des objets (objets.py) puis fiches
(exercices_plans.py --une), 2 pages a la fois, chaque page dans son propre dossier sorties/fiches_gh/<page>/.
Plans : plans_appr/ et plans_appr_masse/ (JAMAIS plans_neufs = l'examen).
Filtre : variable FILTRE (debut du nom de page ; vide = toutes).   python fiches_part.py 3/12"""
import glob, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
k, n = map(int, sys.argv[1].split("/"))
LIMITE = int(os.environ.get("LIMITE_PAGE", "2400"))   # s par etape et par page (une page bloquee ne bloque pas la part)
filtre = os.environ.get("FILTRE", "").strip()
pages = [f for d in ("plans_appr", "plans_appr_masse") for f in glob.glob(os.path.join(ici, d, "*.pdf"))
         if os.path.basename(f).startswith(tuple(filtre.split(",")))]   # 28/11 : plusieurs debuts de nom, separes par des virgules
pages.sort(key=lambda f: (-os.path.getsize(f), os.path.basename(f)))   # les plus lourdes d'abord, reparties a tour de role
mes = pages[k - 1::n]
print("part %d/%d : %d pages sur %d" % (k, n, len(mes), len(pages)), flush=True)


def etape(cmd, env, journal):
    t = time.time()
    try:
        r = subprocess.run(cmd, env=env, cwd=ici, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=LIMITE)
        code = r.returncode; sortie = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        code = "COUPEE"; sortie = ""
    open(journal, "a", encoding="utf-8").write(sortie)
    return code, round(time.time() - t)


def une(f):
    nom = os.path.splitext(os.path.basename(f))[0]
    dos = os.path.join(ici, "sorties", "fiches_gh", nom[:90]); os.makedirs(dos, exist_ok=True)
    journal = os.path.join(dos, "journal.txt")
    env = dict(os.environ, SEULEMENT=os.path.basename(f), MUR_MATIERE="1", MOBILIER_PARTOUT="1", AUTRE="1",
               PYTHONIOENCODING="utf-8")
    c1, t1 = etape([sys.executable, "-u", "objets.py", os.path.basename(os.path.dirname(f))], env, journal)
    env["SORTIE_FICHES"] = dos
    c2, t2 = etape([sys.executable, "-u", "exercices_plans.py", "--une", f], env, journal)
    fj = os.path.join(dos, "exercices.jsonl")
    nf = sum(1 for _ in open(fj, encoding="utf-8")) if os.path.exists(fj) else 0
    ligne = "%-60s objets %s (%d s) | fiches %s (%d s) : %d" % (nom[:60], c1, t1, c2, t2, nf)
    open(os.path.join(dos, "bilan.txt"), "w", encoding="utf-8").write(ligne + "\n")
    print(ligne, flush=True)


with ThreadPoolExecutor(int(os.environ.get("A_LA_FOIS", "2"))) as ex:
    list(ex.map(une, mes))
print("FIN part %d/%d" % (k, n), flush=True)
