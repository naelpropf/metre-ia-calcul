# Metre IA -- ETAPE 1 de l'apprentissage : Qwen3-VL-2B (apache-2.0) apprend « PLAN puis REPONSE » sur nos fiches v2.
# Methode : carnet officiel unsloth « Qwen3_VL_(8B)-Vision » (Colab T4 gratuit), seul le modele change (2B, 4 bits) + LoRA r=16.
# Entree : fiches.zip (exercices.jsonl + img/) envoye dans /content.  Sortie : /content/sortie/ (adaptateur LoRA + reponses
# du modele sur les fiches d'EXAMEN, au meme format que les fiches -> pensee_dessinee.py les dessine au PC).
# EXAMEN : un dossier entier jamais vu a l'entrainement (DOSSIER_EXAMEN, sinon le dernier par ordre alphabetique).
# Note : on mesure si le contour rendu tombe a 1 % / 3 % de la surface ecrite (echelle tiree de la fiche juste).
#   Colab :  !pip install -q unsloth   puis   !python entrainer_qwen3vl.py
import json, math, os, random, re, sys, time, zipfile

ENTREE = os.environ.get("ENTREE", "/content")
SORTIE = os.environ.get("SORTIE", "/content/sortie")
MODELE = os.environ.get("MODELE", "unsloth/Qwen3-VL-2B-Instruct-unsloth-bnb-4bit")
PAS = int(os.environ.get("PAS", "300"))
LR = float(os.environ.get("LR", "1e-4"))   # 28/11 : 2e-4 -> grad_norm nan au pas 30 (essai) ; plus doux
LONG = int(os.environ.get("LONG", "3072"))   # 28/11 : 2048 risquait de couper la REPONSE (contour) des longues fiches
N_EXA = int(os.environ.get("N_EXA", "16"))
EXAMEN_SEUL = os.environ.get("EXAMEN_SEUL")
SEC = os.environ.get("A_SEC") == "1"   # test sans GPU : lit les fiches, fait le decoupage, n'entraine pas
os.makedirs(SORTIE, exist_ok=True)

# 1) fiches
z = os.path.join(ENTREE, "fiches.zip")
if os.path.exists(z) and not os.path.exists(os.path.join(ENTREE, "fiches")):
    zipfile.ZipFile(z).extractall(os.path.join(ENTREE, "fiches"))
racine = os.path.join(ENTREE, "fiches") if os.path.exists(os.path.join(ENTREE, "fiches")) else ENTREE
FJ = [os.path.join(dp, f) for dp, _, fs in os.walk(racine) for f in fs if f == "exercices.jsonl"][0]
BASE = os.path.dirname(FJ)
fiches = [json.loads(l) for l in open(FJ, encoding="utf-8") if l.strip()]
fiches = [f for f in fiches if f.get("v") == 2]
dossier = lambda f: f["image"].split("/")[-1].split("_")[0]
doss = sorted({dossier(f) for f in fiches})
EXA = os.environ.get("DOSSIER_EXAMEN") or doss[-1]
appr = [f for f in fiches if dossier(f) != EXA]; exa = [f for f in fiches if dossier(f) == EXA]
print("fiches v2 :", len(fiches), "| dossiers :", doss, "| examen :", EXA, "->", len(exa), "fiches | entrainement :", len(appr), flush=True)

CONSIGNE = ("Tu es metreur. Reponds en deux parties. PLAN : le batiment, la piece, ce qu'on s'attend a y trouver, comment "
            "les murs sont dessines, puis les objets que tu utilises (l'etiquette lue, les murs suivis, les portes fermees, "
            "les objets ecartes), en millimes de l'image. REPONSE : le contour de la piece et sa surface.")


def question(f):
    return "%s\n\n%s\n\n%s" % (CONSIGNE, f["legende"], f["question"])


def cible(f):
    return "PLAN : %s\nREPONSE : %s" % (f["plan"], f["reponse"])


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


def surface_ecrite(f):
    return float(re.search(r"surface ecrite ([\d.]+)", f["plan"]).group(1))


if SEC:
    f = appr[0]; print("--- exemple ---\n", question(f)[:400], "\n>>>\n", cible(f)[:600])
    c = f.get("contour") or liste_apres(f["reponse"], "Contour"); print("aire millimes", aire(c), "| ecrite", surface_ecrite(f))
    sys.exit(0)

# 2) modele (methode du carnet unsloth)
from unsloth import FastVisionModel
from PIL import Image
import torch
if EXAMEN_SEUL:
    model, tok = FastVisionModel.from_pretrained(EXAMEN_SEUL, load_in_4bit=True)
else:
    model, tok = FastVisionModel.from_pretrained(MODELE, load_in_4bit=True, use_gradient_checkpointing="unsloth")
    model = FastVisionModel.get_peft_model(model, finetune_vision_layers=True, finetune_language_layers=True,
                                           finetune_attention_modules=True, finetune_mlp_modules=True,
                                           r=16, lora_alpha=16, lora_dropout=0, bias="none", random_state=3407)


def msg(f, avec_reponse=True):
    im = Image.open(os.path.join(BASE, f["image"])).convert("RGB")
    m = [{"role": "user", "content": [{"type": "text", "text": question(f)}, {"type": "image", "image": im}]}]
    if avec_reponse: m.append({"role": "assistant", "content": [{"type": "text", "text": cible(f)}]})
    return {"messages": m}


if not EXAMEN_SEUL:   # 28/11 : EXAMEN_SEUL=<dossier lora> -> pas d'entrainement, examen de l'IA deja entrainee
    data = [msg(f) for f in appr]
    from unsloth.trainer import UnslothVisionDataCollator
    from trl import SFTTrainer, SFTConfig
    FastVisionModel.for_training(model)
    tr = SFTTrainer(model=model, tokenizer=tok, data_collator=UnslothVisionDataCollator(model, tok), train_dataset=data,
                    args=SFTConfig(per_device_train_batch_size=2, gradient_accumulation_steps=4, warmup_steps=5, max_steps=PAS,
                                   learning_rate=LR, logging_steps=5, max_grad_norm=1.0, optim="adamw_8bit", weight_decay=0.01,
                                   lr_scheduler_type="linear", seed=3407, output_dir=os.path.join(SORTIE, "points"),
                                   report_to="none", remove_unused_columns=False, dataset_text_field="",
                                   dataset_kwargs={"skip_prepare_dataset": True}, max_length=LONG))
    t0 = time.time(); st = tr.train()
    print("ENTRAINEMENT FINI | %.0f min | perte finale %.3f" % ((time.time() - t0) / 60, st.training_loss), flush=True)
    # 28/11 : run v2 -> aucune perte par pas dans le journal (unsloth n'imprime pas les logs hors carnet) : on les ecrit
    json.dump(tr.state.log_history, open(os.path.join(SORTIE, "pertes.json"), "w"))
    for h in tr.state.log_history:
        if "loss" in h: print("pas %s | perte %.3f | grad %s" % (h.get("step"), h["loss"], h.get("grad_norm")), flush=True)
    model.save_pretrained(os.path.join(SORTIE, "lora")); tok.save_pretrained(os.path.join(SORTIE, "lora"))

# 3) examen sur le dossier jamais vu : le modele ecrit son PLAN puis sa REPONSE ; on mesure la surface de SON contour
FastVisionModel.for_inference(model)
res = []; n1 = n3 = 0
# 28/11 : l'examen ne note QUE le contour -> on arrete d'ecrire des que la liste du contour est fermee (meme note,
# moins de mots a generer). ARRET_CONTOUR=0 pour garder la reponse entiere.
from transformers import StoppingCriteria, StoppingCriteriaList


class ArretContour(StoppingCriteria):
    def __init__(self, n0): self.n0 = n0
    def __call__(self, ids, scores, **kw):
        t = tok.decode(ids[0][self.n0:], skip_special_tokens=True)
        return "REPONSE" in t and liste_apres(t.split("REPONSE")[-1], "Contour") is not None
g_inc = open(os.path.join(SORTIE, "examen_modele.jsonl"), "w", encoding="utf-8")   # 28/11 : ecrit au fur et a mesure
for f in exa[:N_EXA]:
    im = Image.open(os.path.join(BASE, f["image"])).convert("RGB")
    m = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": question(f)}]}]
    txt = tok.apply_chat_template(m, add_generation_prompt=True)
    x = tok(im, txt, add_special_tokens=False, return_tensors="pt").to("cuda")
    # 28/11 : essai 30 pas -> la REPONSE tournait en boucle (« Le contour est au nu interieur des murs... » x10) ; frein leger
    out = model.generate(**x, max_new_tokens=900, use_cache=True, do_sample=False, repetition_penalty=1.05,
                         no_repeat_ngram_size=12,
                         stopping_criteria=StoppingCriteriaList([ArretContour(x["input_ids"].shape[1])]) if os.environ.get("ARRET_CONTOUR", "1") == "1" else None)
    rep = tok.decode(out[0][x["input_ids"].shape[1]:], skip_special_tokens=True)
    plan = rep.split("REPONSE :")[0].replace("PLAN :", "").strip(); reponse = rep.split("REPONSE :")[-1].strip()
    vrai = f.get("contour") or liste_apres(f["reponse"], "Contour"); S = surface_ecrite(f)
    k2 = S / aire(vrai) if aire(vrai) else 0                     # m2 par millime carre (echelle de CETTE image)
    sien = liste_apres(reponse, "Contour") or []
    Sm = aire(sien) * k2 if len(points(sien)) >= 3 else None
    ok1 = Sm is not None and abs(Sm / S - 1) <= 0.01; ok3 = Sm is not None and abs(Sm / S - 1) <= 0.03
    n1 += ok1; n3 += ok3
    res.append({"image": f["image"], "legende": f["legende"], "question": f["question"], "plan": plan, "reponse": reponse,
                "surface_modele": Sm, "surface_ecrite": S, "juste_1pc": ok1, "juste_3pc": ok3, "v": "modele"})
    g_inc.write(json.dumps(res[-1], ensure_ascii=False) + "\n"); g_inc.flush()
    print("%-50s ecrite %7.2f | modele %s %s" % (f["image"][4:54], S, "%.2f" % Sm if Sm else "-", "OK" if ok1 else ("~3%" if ok3 else "")), flush=True)
    print("   DEBUT REPONSE :", rep[:300].replace("\n", " / "), flush=True)
json.dump(res, open(os.path.join(SORTIE, "examen_modele.json"), "w", encoding="utf-8"), ensure_ascii=False)
g_inc.close()
print("EXAMEN dossier %s : %d fiches | justes a 1 %% : %d | a 3 %% : %d" % (EXA, len(exa), n1, n3), flush=True)
