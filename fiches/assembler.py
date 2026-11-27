"""Rassemble les fiches des parts (outil/sorties/fiches_gh/<page>/) dans un seul dossier : exercices.jsonl + img/ +
bilan.txt (une ligne par page) + journaux (fin seulement).   python fiches/assembler.py <dossier_destination>"""
import glob, os, shutil, sys
src = os.path.join("outil", "sorties", "fiches_gh")
dest = sys.argv[1]
os.makedirs(os.path.join(dest, "img"), exist_ok=True); os.makedirs(os.path.join(dest, "journaux"), exist_ok=True)
nf, lignes = 0, []
with open(os.path.join(dest, "exercices.jsonl"), "w", encoding="utf-8") as s:
    for d in sorted(glob.glob(os.path.join(src, "*"))):
        fj = os.path.join(d, "exercices.jsonl")
        if os.path.exists(fj):
            for l in open(fj, encoding="utf-8"):
                s.write(l); nf += 1
        for p in glob.glob(os.path.join(d, "img", "*.png")):
            shutil.copy2(p, os.path.join(dest, "img"))
        b = os.path.join(d, "bilan.txt")
        lignes.append(open(b, encoding="utf-8").read().strip() if os.path.exists(b) else os.path.basename(d) + " : PAS DE BILAN (part coupee ?)")
        j = os.path.join(d, "journal.txt")
        if os.path.exists(j):
            open(os.path.join(dest, "journaux", os.path.basename(d) + ".txt"), "w", encoding="utf-8").write(
                "".join(open(j, encoding="utf-8", errors="replace").readlines()[-80:]))
lignes.append("TOTAL : %d pages, %d fiches" % (len(lignes), nf))
open(os.path.join(dest, "bilan.txt"), "w", encoding="utf-8").write("\n".join(lignes) + "\n")
print("\n".join(lignes))
