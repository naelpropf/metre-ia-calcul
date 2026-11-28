# Metre IA -- « REVES FILTRES » (28/11, go du porteur) : l'IA deja entrainee repond PLUSIEURS fois a chaque fiche
# d'ENTRAINEMENT (jamais l'examen), la surface ecrite note chaque reponse, on garde les bonnes, on reentraine dessus.
# (methode connue : rejection sampling / « expert iteration »). Aucune etiquette nouvelle a faire a la main.
#   Colab (apres entrainer_qwen3vl.py) :  LORA=/content/sortie_v2/lora N_FICHES=50 K=4 python reves_filtres.py
# Sortie : /content/reves/reves.jsonl (fiches gardees, format des fiches v2 : plan/reponse = ceux de l'IA) + bilan.
import json, os, random, re, sys, time, zipfile

ENTREE = os.environ.get("ENTREE", "/content")
SORTIE = os.environ.get("SORTIE", "/content/reves")
LORA = os.environ.get("LORA", "/content/sortie_v2/lora")
N_FICHES = int(os.environ.get("N_FICHES", "50"))
K = int(os.environ.get("K", "4"))
TEMP = float(os.environ.get("TEMP", "0.8"))
TOL = float(os.environ.get("TOL", "0.03"))   # reponse gardee si sa surface tombe a 3 % de l'ecrit
os.makedirs(SORTIE, exist_ok=True)

# memes fiches et meme decoupage que entrainer_qwen3vl.py (le dossier d'examen n'est JAMAIS utilise ici)
racine = os.path.join(ENTREE, "fiches") if os.path.exists(os.path.join(ENTREE, "fiches")) else ENTREE
FJ = [os.path.join(dp, f) for dp, _, fs in os.walk(racine) for f in fs if f == "exercices.jsonl"][0]
BASE = os.path.dirname(FJ)
fiches = [json.loads(l) for l in open(FJ, encoding="utf-8") if l.strip()]
fiches = [f for f in fiches if f.get("v") == 2]
dossier = lambda f: f["image"].split("/")[-1].split("_")[0]
doss = sorted({dossier(f) for f in fiches})
EXA = os.environ.get("DOSSIER_EXAMEN") or doss[-1]
appr = [f for f in fiches if dossier(f) != EXA]
random.Random(3407).shuffle(appr)
lot = appr[:N_FICHES]
print("fiches d'entrainement :", len(appr), "| essai sur", len(lot), "| K =", K, "| examen ecarte :", EXA, flush=True)

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "entrainer_qwen3vl.py"), encoding="utf-8").read()
CONSIGNE = re.search(r'CONSIGNE = \((.*?)\)\n', src, re.S).group(1)
CONSIGNE = "".join(eval(x) for x in re.findall(r'"[^"]*"', CONSIGNE))


def question(f): return "%s\n\n%s\n\n%s" % (CONSIGNE, f["legende"], f["question"])


def points(c):
    """28/11 : run v2 plante (TypeError list - int) sur un contour mal forme ecrit par l'IA -> on ne garde que des
    points [x, y] numeriques ; sinon contour illisible (= pas de contour, compte comme faux)."""
    try:
        P = [(float(p[0]), float(p[1])) for p in c if isinstance(p, (list, tuple)) and len(p) >= 2
             and all(isinstance(v, (int, float)) for v in p[:2])]
        return P if len(P) == len(c) else []
    except Exception:
        return []


def aire(c):
    c = points(c or [])
    return abs(sum(c[i][0] * c[i - 1][1] - c[i - 1][0] * c[i][1] for i in range(len(c)))) / 2 if len(c) >= 3 else 0.0


def liste_apres(txt, mot):
    i = txt.find(mot)
    if i < 0: return None
    j = txt.find("[", i); prof = 0
    if j < 0: return None
    for q in range(j, len(txt)):
        prof += {"[": 1, "]": -1}.get(txt[q], 0)
        if prof == 0:
            try: return json.loads(txt[j:q + 1])
            except Exception: return None
    return None


def surface_ecrite(f): return float(re.search(r"surface ecrite ([\d.]+)", f["plan"]).group(1))


from unsloth import FastVisionModel
from PIL import Image
from transformers import StoppingCriteria, StoppingCriteriaList
model, tok = FastVisionModel.from_pretrained(LORA, load_in_4bit=True)
FastVisionModel.for_inference(model)


class ArretContour(StoppingCriteria):   # s'arrete quand TOUTES les reponses du lot ont ferme leur contour
    def __init__(self, n0): self.n0 = n0
    def __call__(self, ids, scores, **kw):
        for r in ids:
            t = tok.decode(r[self.n0:], skip_special_tokens=True)
            if not ("REPONSE" in t and liste_apres(t.split("REPONSE")[-1], "Contour") is not None): return False
        return True


g = open(os.path.join(SORTIE, "reves.jsonl"), "w", encoding="utf-8")
t0 = time.time(); n_rep = n_bonnes = n_fiches_ok = n_sans_contour = 0
for i, f in enumerate(lot):
    im = Image.open(os.path.join(BASE, f["image"])).convert("RGB")
    m = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": question(f)}]}]
    txt = tok.apply_chat_template(m, add_generation_prompt=True)
    x = tok(im, txt, add_special_tokens=False, return_tensors="pt").to("cuda")
    n0 = x["input_ids"].shape[1]
    out = model.generate(**x, max_new_tokens=900, use_cache=True, do_sample=True, temperature=TEMP, top_p=0.95,
                         num_return_sequences=K, repetition_penalty=1.05,
                         stopping_criteria=StoppingCriteriaList([ArretContour(n0)]))
    vrai = f.get("contour") or liste_apres(f["reponse"], "Contour"); S = surface_ecrite(f)
    k2 = S / aire(vrai) if aire(vrai) else 0
    bonnes = []
    for r in out:
        rep = tok.decode(r[n0:], skip_special_tokens=True); n_rep += 1
        c = liste_apres(rep.split("REPONSE")[-1], "Contour") if "REPONSE" in rep else None
        if len(points(c or [])) < 3: n_sans_contour += 1; continue
        Sm = aire(c) * k2
        if abs(Sm / S - 1) <= TOL:
            bonnes.append((abs(Sm / S - 1), rep))
    n_bonnes += len(bonnes); n_fiches_ok += bool(bonnes)
    for ec, rep in sorted(bonnes)[:2]:   # au plus 2 reves gardes par fiche (pas de sur-poids d'une fiche facile)
        plan = rep.split("REPONSE :")[0].replace("PLAN :", "").strip(); reponse = rep.split("REPONSE :")[-1].strip()
        g.write(json.dumps(dict(f, plan=plan, reponse=reponse, v=2, reve=True, ecart=round(ec, 4)), ensure_ascii=False) + "\n")
    g.flush()
    print("%3d/%d %-45s bonnes %d/%d | %.0f s" % (i + 1, len(lot), f["image"][4:49], len(bonnes), K, time.time() - t0), flush=True)
g.close()
print("REVES FINI : %d fiches, %d reponses, %d sans contour, %d bonnes (a %.0f %%), %d fiches avec au moins une bonne | %.0f min"
      % (len(lot), n_rep, n_sans_contour, n_bonnes, 100 * TOL, n_fiches_ok, (time.time() - t0) / 60), flush=True)
