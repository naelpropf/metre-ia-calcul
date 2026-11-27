"""Lance objets.py sur UNE page (pour par_page_sous_garde.py, qui passe --une <pdf>), avec les reglages de la base
objets_appr_mm_mp_au utilisee par exercices_plans.py (MUR_MATIERE, MOBILIER_PARTOUT, AUTRE).
python par_page_sous_garde.py plans_appr_masse objets_une.py 900"""
import os, subprocess, sys
ici = os.path.dirname(os.path.abspath(__file__))
f = sys.argv[sys.argv.index("--une") + 1]
env = dict(os.environ, SEULEMENT=os.path.basename(f), MUR_MATIERE="1", MOBILIER_PARTOUT="1", AUTRE="1")
sys.exit(subprocess.call([sys.executable, "-u", "objets.py", os.path.basename(os.path.dirname(os.path.abspath(f)))], env=env, cwd=ici))
