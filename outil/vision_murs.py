"""VISION (27/11) : le plan vu comme une IMAGE par un modele de murs (Yytsi/floorplan-to-3d-walls, MIT, entraine sur CubiCasa5K).
Classes par pixel : 0 sol, 1 mur, 2 porte, 3 fenetre. Pages decoupees en carreaux de 12 m (512 px), chevauchement 2 m.
  python vision_murs.py --page <pdf>          -> sorties/vision/<nom>.npz (carte des classes) + apercu .png
  python vision_murs.py --test                -> test declare (coffre « Vision - modele murs CubiCasa »)"""
import glob, gzip, json, os, sys, time
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
MOD = os.path.join(ici, "..", "donnees_externes", "modele_murs_cubicasa")
SORTIE = os.path.join(ici, "sorties", os.environ.get("VISION_SORTIE", "vision")); os.makedirs(SORTIE, exist_ok=True)
CARREAU_M, CHEV_M, PX = float(os.environ.get("VISION_CARREAU", "12")), 2.0, 512
MEAN, STD = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])


def modele():
    import torch, segmentation_models_pytorch as smp
    from safetensors.torch import load_file
    torch.set_num_threads(2)
    net = smp.Unet(encoder_name="resnet34", encoder_weights=None, in_channels=3, classes=4)
    net.load_state_dict(load_file(os.environ.get("VISION_POIDS") or os.path.join(MOD, "best.safetensors")))   # 27/11 : poids re-entraines
    return net.eval()


def carte(f, net):
    import torch, pypdfium2 as pdfium
    from metre import normaliser, echelle_par_cotes
    ch = normaliser(f)
    m = echelle_par_cotes(ch, 0)[0]
    if not m:
        import metre_v3; m = metre_v3.echelle_par_etiquettes(ch)[0]
    pxm = PX / CARREAU_M                       # pixels par metre
    sc = pxm * m                               # pixels par point PDF
    im = np.asarray(pdfium.PdfDocument(ch)[0].render(scale=sc, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB"),
                    np.float32) / 255.0
    H, W = im.shape[:2]
    pas = int((CARREAU_M - CHEV_M) * pxm)
    score = np.zeros((4, H, W), np.float32); nb = np.zeros((H, W), np.float32)
    with torch.no_grad():
        for y in range(0, max(H - PX, 0) + pas, pas):
            for x in range(0, max(W - PX, 0) + pas, pas):
                c = im[y:y + PX, x:x + PX]
                if c.size == 0 or c.min() > 0.97: continue        # carreau blanc : sol
                h, w = c.shape[:2]
                pad = np.ones((PX, PX, 3), np.float32) * MEAN.astype(np.float32); pad[:h, :w] = c
                t = torch.from_numpy(((pad - MEAN) / STD).astype(np.float32).transpose(2, 0, 1))[None]
                p = torch.softmax(net(t)[0], 0).numpy()[:, :h, :w]
                score[:, y:y + h, x:x + w] += p; nb[y:y + h, x:x + w] += 1
    cls = np.where(nb > 0, score.argmax(0), 0).astype(np.uint8)
    return cls, sc, m


def nom_de(f):
    return os.path.splitext(os.path.basename(f))[0][:60]


if __name__ == "__main__" and sys.argv[1] == "--page":
    f = sys.argv[2]; t = time.time()
    cls, sc, m = carte(f, modele())
    np.savez_compressed(os.path.join(SORTIE, nom_de(f) + ".npz"), cls=cls, sc=sc, m=m)
    from PIL import Image
    pal = np.array([[245, 245, 240], [30, 30, 35], [230, 120, 50], [60, 150, 220]], np.uint8)
    ap = Image.fromarray(pal[cls]); ap.thumbnail((2400, 2400)); ap.save(os.path.join(SORTIE, nom_de(f) + ".png"))
    print("%-60s %dx%d px | mur %.1f %% porte %.2f %% fenetre %.2f %% | %d s" % (nom_de(f), cls.shape[1], cls.shape[0],
          100 * (cls == 1).mean(), 100 * (cls == 2).mean(), 100 * (cls == 3).mean(), time.time() - t), flush=True)

elif __name__ == "__main__" and sys.argv[1] == "--test":
    from scipy.ndimage import maximum_filter
    from collections import Counter
    tot = Counter()
    for fz in sorted(glob.glob(os.path.join(SORTIE, "*.npz"))):
        nom = os.path.basename(fz)[:-4]
        fo = glob.glob(os.path.join(ici, "sorties", "objets_vb", glob.escape(nom) + "*.jsonl.gz"))
        if not fo: continue
        z = np.load(fz, allow_pickle=False); cls = z["cls"]; sc = float(z["sc"]); m = float(z["m"])
        H, W = cls.shape
        vois = {k: maximum_filter((cls == k).astype(np.uint8), size=3) for k in (1, 2, 3)}
        c = Counter()
        for l in gzip.open(fo[0], "rt", encoding="utf-8"):
            x = json.loads(l); k = x.get("classe")
            groupe = "mur" if (k == "mur" and x.get("etiquette") == 1) else k if k in ("vitre", "porte", "lettre", "cote", "mobilier") else None
            if not groupe: continue
            px = int(round((x["_x0"] + x["_x1"]) / 2 / m * sc)); py = int(round((x["_y0"] + x["_y1"]) / 2 / m * sc))
            if not (0 <= px < W and 0 <= py < H): continue
            vu_mur = bool(vois[1][py, px]); c[groupe, "n"] += 1; c[groupe, "mur"] += vu_mur
            c[groupe, "porte"] += bool(vois[2][py, px]); c[groupe, "fen"] += bool(vois[3][py, px])
        print("%-45s murs %d/%d | fausses alarmes %d/%d | vitres vues fen/mur %d/%d | portes vues porte %d/%d" % (
            nom[:45], c["mur", "mur"], c["mur", "n"], sum(c[g, "mur"] for g in ("lettre", "cote", "mobilier")),
            sum(c[g, "n"] for g in ("lettre", "cote", "mobilier")), c["vitre", "fen"] + c["vitre", "mur"] - 0, c["vitre", "n"],
            c["porte", "porte"], c["porte", "n"]), flush=True)
        tot.update(c)
    rm = tot["mur", "mur"] / max(tot["mur", "n"], 1)
    fa = sum(tot[g, "mur"] for g in ("lettre", "cote", "mobilier")) / max(sum(tot[g, "n"] for g in ("lettre", "cote", "mobilier")), 1)
    print("TOTAL murs vus mur %.0f %% (seuil >= 70) | fausses alarmes %.0f %% (seuil <= 20) -> %s" % (
        100 * rm, 100 * fa, "REUSSI" if rm >= 0.70 and fa <= 0.20 else "ECHEC"))
    # 27/11 : seuils de la declaration « Vision re-entrainee sur nos plans » (murs >= 80, FA <= 15, portes >= 50)
    for g in ("lettre", "cote", "mobilier"):   # 27/11 : d'ou viennent les fausses alarmes
        print("  fausses alarmes %-9s %5d / %5d (%.0f %%)" % (g, tot[g, "mur"], tot[g, "n"], 100 * tot[g, "mur"] / max(tot[g, "n"], 1)))
    rp = tot["porte", "porte"] / max(tot["porte", "n"], 1)
    print("DECLARATION re-entrainement : murs %.0f %% (>= 80) | fausses alarmes %.0f %% (<= 15) | portes %.0f %% (>= 50) -> %s" % (
        100 * rm, 100 * fa, 100 * rp, "REUSSI" if rm >= 0.80 and fa <= 0.15 and rp >= 0.50 else "ECHEC"))
