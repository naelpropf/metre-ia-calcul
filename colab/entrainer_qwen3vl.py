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


# 28/11 : SUJETS = entrainement DECOUPE (idee du porteur : des specialistes, puis on fusionne). Chaque fiche donne un
# exercice par sujet : tout (l'ancien, plan + contour), etiquette (ou est-elle), murs (lesquels entourent la piece),
# tri (mur / objet interieur / cote), contour (murs donnes -> fermer le contour). SUJETS=murs,tri = melange de deux.
SUJETS = os.environ.get("SUJETS", "tout").split(",")
FIN = {"tout": "Contour", "etiquette": "ETIQUETTE", "murs": "MURS", "tri": "COTES", "contour": "Contour", "tri_visuel": None}
# 28/11 matin : l'IA ne sait pas ecrire des coordonnees (etiquette 0/16 base, 1/16 entrainee) -> « tri_visuel » : les traits
# sont DESSINES en couleur et numerotes sur l'image (methode « set of marks ») ; l'IA dit seulement MUR / OBJET / COTE.
COULEURS = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (240, 50, 230)]


def marques(f):
    p = f["pensee"]; r = random.Random(f["image"] + "tv")
    def pris(L, k):
        L = [t for t in L if isinstance(t, list) and len(t) >= 4]; r.shuffle(L); return L[:k]
    T = [(t, "MUR") for t in pris(p.get("murs", []), 2)] + [(t, "OBJET") for t in pris(p.get("exclus", []), 2)] + \
        [(t, "COTE") for t in pris(p.get("cotes", []), 2)]
    r.shuffle(T); return T


def dessiner(im, T):
    from PIL import ImageDraw
    im = im.copy(); d = ImageDraw.Draw(im); W, H = im.size
    for i, (t, _) in enumerate(T):
        x0, y0, x1, y1 = t[0] * W / 1000, t[1] * H / 1000, t[2] * W / 1000, t[3] * H / 1000; c = COULEURS[i % 6]
        d.line([x0, y0, x1, y1], fill=c, width=5); mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        # 28/11 : chiffre de 8 px (~5 px apres reduction a 512) = illisible -> specialiste 3/16 ; chiffre de 26 px
        d.rectangle([mx - 17, my - 17, mx + 17, my + 17], fill=c, outline=(0, 0, 0), width=2)
        d.text((mx, my), str(i + 1), fill=(255, 255, 255), font=POLICE, anchor="mm")
    return im


try:
    from PIL import ImageFont
    POLICE = ImageFont.load_default(size=26)
except Exception:
    POLICE = None
NOMS_COULEURS = ["rouge", "vert", "bleu", "orange", "violet", "rose"]


def nom(f):
    m = re.search(r"«\s*(.+?)\s*»", f["question"]); return m.group(1) if m else "?"


def traits_tri(f):
    p = f["pensee"]; T = [(t, "MUR") for t in p["murs"]] + [(t, "OBJET") for t in p["exclus"]] + [(t, "COTE") for t in p["cotes"]]
    random.Random(f["image"]).shuffle(T); return T


def valable(f, s):
    if s == "tout": return True
    p = f.get("pensee") or {}
    if s == "etiquette": return bool(p.get("etiquette"))
    if s == "murs": return bool(p.get("murs")) and bool(p.get("etiquette"))
    if s == "tri": return len(traits_tri(f)) >= 2 if p else False
    if s == "tri_visuel":
        T = marques(f) if p else []; return len(T) >= 2 and any(e != "MUR" for _, e in T)
    if s == "contour": return bool(p.get("murs")) and len(points(f.get("contour") or liste_apres(f["reponse"], "Contour") or [])) >= 3
    return False


def exemple(f, s):
    """(question, cible) de la fiche f pour le sujet s."""
    if s == "tout": return question(f), cible(f)
    p = f["pensee"]; S = surface_ecrite(f); tete = "%s\n\n" % f["legende"]
    if s == "etiquette":
        return (tete + "Trouve sur cet extrait de plan l'etiquette de la piece « %s » (%.2f m2 ecrits). Reponds : "
                "ETIQUETTE : [x, y] en millimes de l'image." % (nom(f), S), "ETIQUETTE : %s" % json.dumps(p["etiquette"]))
    if s == "murs":
        return (tete + "La piece « %s » (%.2f m2 ecrits) a son etiquette en %s. Donne les traits de MUR qui l'entourent, "
                "(x0, y0, x1, y1) en millimes de l'image. Reponds : MURS : [[x0, y0, x1, y1], ...]"
                % (nom(f), S, json.dumps(p["etiquette"])), "MURS : %s" % json.dumps(p["murs"]))
    if s == "tri":
        T = traits_tri(f)
        q = (tete + "Autour de la piece « %s », voici des traits (x0, y0, x1, y1) en millimes de l'image : %s. Pour chacun, "
             "dis si c'est un MUR, un OBJET a l'interieur (mobilier, equipement) ou une ligne de COTE. Reponds : "
             "MURS : [numeros] ; OBJETS : [numeros] ; COTES : [numeros]"
             % (nom(f), " ; ".join("%d : %s" % (i, json.dumps(t)) for i, (t, _) in enumerate(T))))
        c = " ; ".join("%sS : %s" % (k, json.dumps([i for i, (_, e) in enumerate(T) if e == k])) for k in ("MUR", "OBJET", "COTE"))
        return q, c
    if s == "tri_visuel":
        T = marques(f)
        return (tete + "Sur l'image, %d traits sont surlignes en couleur et numerotes (1 a %d) ; la piece « %s » est autour. "
                "Les traits : %s. Pour chaque trait numerote, dis si c'est un MUR, un OBJET a l'interieur (mobilier, "
                "equipement) ou une ligne de COTE. Reponds : 1 : MUR ; 2 : OBJET ; ..."
                % (len(T), len(T), nom(f), ", ".join("%d = %s" % (i + 1, NOMS_COULEURS[i % 6]) for i in range(len(T)))),
                " ; ".join("%d : %s" % (i + 1, e) for i, (_, e) in enumerate(T)))
    if s == "contour":
        c = points(f.get("contour") or liste_apres(f["reponse"], "Contour"))
        return (tete + "La piece « %s » (%.2f m2 ecrits), etiquette en %s. Ses murs (x0, y0, x1, y1) : %s ; portes a fermer "
                "au droit du mur : %s. Donne son contour au nu interieur des murs. Reponds : Contour de la piece (millimes "
                "de l'image, x puis y) : [[x, y], ...]" % (nom(f), S, json.dumps(p["etiquette"]), json.dumps(p["murs"]),
                                                          json.dumps(p.get("portes") or [])),
                "Contour de la piece (millimes de l'image, x puis y) : %s" % json.dumps([[round(x), round(y)] for x, y in c]))


def meme_trait(a, b, tol=15):
    try:
        a, b = [float(v) for v in a[:4]], [float(v) for v in b[:4]]
    except Exception:
        return False
    d = lambda u, v: max(abs(u[0] - v[0]), abs(u[1] - v[1]), abs(u[2] - v[2]), abs(u[3] - v[3]))
    return min(d(a, b), d(a, b[2:] + b[:2])) <= tol


def noter(f, s, rep):
    """note de 0 a 1 et juste (bool) de la reponse rep de l'IA, pour le sujet s (tout / contour : surface a 1 %)."""
    p = f.get("pensee") or {}
    if s in ("tout", "contour"):
        vrai = f.get("contour") or liste_apres(f["reponse"], "Contour"); S = surface_ecrite(f)
        k2 = S / aire(vrai) if aire(vrai) else 0
        sien = liste_apres(rep.split("REPONSE :")[-1], "Contour") or []
        Sm = aire(sien) * k2 if len(points(sien)) >= 3 else None
        e = abs(Sm / S - 1) if Sm else 1.0
        return max(0.0, 1 - e / 0.1), e <= 0.01
    if s == "etiquette":
        e = liste_apres(rep, "ETIQUETTE")
        try: d = math.dist([float(v) for v in e[:2]], p["etiquette"])
        except Exception: d = 999
        return max(0.0, 1 - d / 60), d <= 20
    if s == "murs":
        sien = liste_apres(rep, "MURS") or []; sien = [t for t in sien if isinstance(t, list) and len(t) >= 4]
        if not sien: return 0.0, False
        r = sum(any(meme_trait(t, u) for u in sien) for t in p["murs"]) / len(p["murs"])
        q = sum(any(meme_trait(u, t) for t in p["murs"]) for u in sien) / len(sien)
        F1 = 2 * r * q / (r + q) if r + q else 0.0
        return F1, F1 >= 0.8
    if s == "tri_visuel":
        T = marques(f); dit = {}
        for i, e in re.findall(r"(\d+)\s*:\s*(MUR|OBJET|COTE)", rep): dit.setdefault(int(i) - 1, e)
        bon = sum(dit.get(i) == e for i, (_, e) in enumerate(T)) / len(T)
        return bon, bon == 1.0
    if s == "tri":
        T = traits_tri(f); dit = {}
        for k in ("MUR", "OBJET", "COTE"):
            for i in (liste_apres(rep, k + "S") or []):
                if isinstance(i, int): dit.setdefault(i, k)
        bon = sum(dit.get(i) == e for i, (_, e) in enumerate(T)) / len(T)
        return bon, bon == 1.0


if SEC:
    for s in SUJETS:
        ok = [f for f in appr if valable(f, s)]; f = ok[0]; q, c = exemple(f, s)
        print("=== sujet %s : %d fiches d'entrainement, %d d'examen ===\n%s\n>>> %s\n(note de la cible juste : %s)"
              % (s, len(ok), sum(valable(g, s) for g in exa), q[-500:], c[:400], noter(f, s, c)))
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


def msg(f, s="tout", avec_reponse=True):
    im = Image.open(os.path.join(BASE, f["image"])).convert("RGB"); q, c = exemple(f, s)
    if s == "tri_visuel": im = dessiner(im, marques(f))
    m = [{"role": "user", "content": [{"type": "text", "text": q}, {"type": "image", "image": im}]}]
    if avec_reponse: m.append({"role": "assistant", "content": [{"type": "text", "text": c}]})
    return {"messages": m}


if not EXAMEN_SEUL:   # 28/11 : EXAMEN_SEUL=<dossier lora> -> pas d'entrainement, examen de l'IA deja entrainee
    data = [msg(f, s) for s in SUJETS for f in appr if valable(f, s)]
    random.Random(3407).shuffle(data)
    print("exercices d'entrainement :", len(data), "| sujets :", SUJETS, flush=True)
    from unsloth.trainer import UnslothVisionDataCollator
    from trl import SFTTrainer, SFTConfig
    FastVisionModel.for_training(model)
    tr = SFTTrainer(model=model, tokenizer=tok, data_collator=UnslothVisionDataCollator(model, tok, resize=os.environ.get("RESIZE", "max")), train_dataset=data,
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

# 28/11 matin : CAUSE TROUVEE -- unsloth reduisait les images a 512 px de large a l'ENTRAINEMENT (resize="min" par defaut)
# alors que l'examen les passe ENTIERES (jusqu'a 768 px) -> echelle differente entre apprentissage et examen, depuis la v1.
# Desormais RESIZE=max (aucune reduction) : meme image a l'entrainement et a l'examen.
# 3) examen sur le dossier jamais vu, SUJET PAR SUJET (28/11) : tout / contour = surface du contour de l'IA a 1 % de
# l'ecrit ; etiquette = a 20 millimes ; murs = F1 >= 0,8 (trait retrouve a 15 millimes) ; tri = tous les traits bien ranges.
# EXAMEN_SUJETS=etiquette,murs,tri,contour pour noter un specialiste aussi sur les autres sujets (defaut : ses SUJETS).
FastVisionModel.for_inference(model)
from transformers import StoppingCriteria, StoppingCriteriaList


class ArretListe(StoppingCriteria):
    """arrete d'ecrire des que la liste qui suit le dernier mot attendu est fermee (meme note, moins de mots)."""
    def __init__(self, n0, mot, apres=None): self.n0, self.mot, self.apres = n0, mot, apres
    def __call__(self, ids, scores, **kw):
        t = tok.decode(ids[0][self.n0:], skip_special_tokens=True)
        if self.apres:
            if self.apres not in t: return False
            t = t.split(self.apres)[-1]
        return liste_apres(t, self.mot) is not None


g_inc = open(os.path.join(SORTIE, "examen_modele.jsonl"), "w", encoding="utf-8")   # ecrit au fur et a mesure
res = []; bilan = {}
# 28/11 : EXAMEN_APPR=1 -> note aussi 16 fiches D'ENTRAINEMENT (« appr:<sujet> ») : appris par coeur ou rien appris ?
EXS = [(s, s, exa) for s in os.environ.get("EXAMEN_SUJETS", ",".join(SUJETS)).split(",")]
if os.environ.get("EXAMEN_APPR") == "1": EXS += [("appr:" + s, s, appr) for s, _, _ in EXS]
for cle, s, lot in EXS:
    n_ok = 0; notes = []
    for f in [g for g in lot if valable(g, s)][:N_EXA]:
        im = Image.open(os.path.join(BASE, f["image"])).convert("RGB"); q, _ = exemple(f, s)
        if s == "tri_visuel": im = dessiner(im, marques(f))
        # 28/11 : MEME ORDRE qu'a l'entrainement (texte puis image) ; avant : image puis texte (carnet unsloth) = decalage
        m = [{"role": "user", "content": [{"type": "text", "text": q}, {"type": "image"}]}]
        txt = tok.apply_chat_template(m, add_generation_prompt=True)
        x = tok(im, txt, add_special_tokens=False, return_tensors="pt").to("cuda")
        arret = ArretListe(x["input_ids"].shape[1], FIN[s], "REPONSE" if s == "tout" else None)
        out = model.generate(**x, max_new_tokens=900 if s in ("tout", "contour") else (80 if s == "tri_visuel" else 400), use_cache=True, do_sample=False,
                             repetition_penalty=1.05, no_repeat_ngram_size=12,
                             stopping_criteria=StoppingCriteriaList([arret]) if FIN[s] and os.environ.get("ARRET_CONTOUR", "1") == "1" else None)
        rep = tok.decode(out[0][x["input_ids"].shape[1]:], skip_special_tokens=True)
        note, juste = noter(f, s, rep); n_ok += juste; notes.append(note)
        res.append({"sujet": cle, "image": f["image"], "legende": f["legende"], "question": q, "reponse": rep,
                    "note": note, "juste": juste, "surface_ecrite": surface_ecrite(f), "v": "modele",
                    "plan": rep.split("REPONSE :")[0].replace("PLAN :", "").strip() if s == "tout" else "",
                    "juste_1pc": juste if s in ("tout", "contour") else None})
        g_inc.write(json.dumps(res[-1], ensure_ascii=False) + "\n"); g_inc.flush()
        print("%-9s %-46s note %.2f %s | %s" % (cle, f["image"][4:50], note, "JUSTE" if juste else "", rep[:160].replace("\n", " / ")), flush=True)
    bilan[cle] = {"fiches": len(notes), "justes": n_ok, "note_moyenne": round(sum(notes) / len(notes), 3) if notes else None}
    print("EXAMEN %s dossier %s : %d fiches | justes : %d | note moyenne %s" % (cle, EXA, len(notes), n_ok, bilan[cle]["note_moyenne"]), flush=True)
json.dump(res, open(os.path.join(SORTIE, "examen_modele.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump(bilan, open(os.path.join(SORTIE, "bilan_sujets.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
g_inc.close()
print("BILAN PAR SUJET :", json.dumps(bilan, ensure_ascii=False), flush=True)
