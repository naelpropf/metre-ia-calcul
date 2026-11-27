"""COMPRENDRE la vision (27/11, demande du porteur : savoir comment elle raisonne, ce qu'elle rate et pourquoi).
Pour un plan : murs de la reference RATES et REUSSIS, chacun en 3 vignettes : le plan | ce qu'elle voit (classes) | sa confiance
« mur » (noir = sure que non, blanc = sure que oui). Sortie : sorties/vision/comprendre_<nom>.png
  python vision_comprendre.py <code plan> [classe=mur]"""
import glob, gzip, json, os, sys, math
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
import vision_murs as V


def probas(f, net):
    """comme V.carte mais renvoie aussi les probabilites (4, H, W) et l'image"""
    import torch, pypdfium2 as pdfium
    from metre import normaliser, echelle_par_cotes
    ch = normaliser(f); m = echelle_par_cotes(ch, 0)[0]
    if not m:
        import metre_v3; m = metre_v3.echelle_par_etiquettes(ch)[0]
    pxm = V.PX / V.CARREAU_M; sc = pxm * m
    im = np.asarray(pdfium.PdfDocument(ch)[0].render(scale=sc, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB"), np.float32) / 255
    H, W = im.shape[:2]; pas = int((V.CARREAU_M - V.CHEV_M) * pxm)
    S = np.zeros((4, H, W), np.float32); N = np.zeros((H, W), np.float32)
    with torch.no_grad():
        for y in range(0, max(H - V.PX, 0) + pas, pas):
            for x in range(0, max(W - V.PX, 0) + pas, pas):
                c = im[y:y + V.PX, x:x + V.PX]
                if c.size == 0 or c.min() > 0.97: continue
                h, w = c.shape[:2]
                pad = np.ones((V.PX, V.PX, 3), np.float32) * V.MEAN.astype(np.float32); pad[:h, :w] = c
                t = torch.from_numpy(((pad - V.MEAN) / V.STD).astype(np.float32).transpose(2, 0, 1))[None]
                S[:, y:y + h, x:x + w] += torch.softmax(net(t)[0], 0).numpy()[:, :h, :w]; N[y:y + h, x:x + w] += 1
    S /= np.maximum(N, 1); S[0][N == 0] = 1
    return S, im, sc, m


if __name__ == "__main__":
    from PIL import Image, ImageDraw
    k = sys.argv[1]; cible = sys.argv[2] if len(sys.argv) > 2 else "mur"
    f = glob.glob(os.path.join(ici, "plans_test", k + "*.pdf"))[0]
    S, im, sc, m = probas(f, V.modele())
    cls = S.argmax(0); H, W = cls.shape
    np.save(os.path.join(V.SORTIE, "proba_mur_" + k + ".npy"), S[1].astype(np.float16))
    L = [json.loads(l) for l in gzip.open(glob.glob(os.path.join(ici, "sorties", "objets_vb", k + "*.jsonl.gz"))[0], "rt", encoding="utf-8")]
    obj = [x for x in L if x.get("classe") == cible and (cible != "mur" or x.get("etiquette") == 1)]
    pal = np.array([[245, 245, 240], [30, 30, 35], [230, 120, 50], [60, 150, 220]], np.uint8)
    rates, vus = [], []
    for x in obj:
        px = int(round((x["_x0"] + x["_x1"]) / 2 / m * sc)); py = int(round((x["_y0"] + x["_y1"]) / 2 / m * sc))
        if not (0 <= px < W and 0 <= py < H): continue
        z = cls[max(0, py - 1):py + 2, max(0, px - 1):px + 2]
        (vus if (z == 1).any() else rates).append((x, px, py))
    print("%s : %d %s | vus mur %d | rates %d" % (k, len(obj), cible, len(vus), len(rates)))
    print("ce qu'elle voit a la place, sous les rates :", {n: int(sum(cls[py, px] == i for _, px, py in rates)) for i, n in enumerate(("sol", "mur", "porte", "fenetre"))})
    print("confiance mur mediane : rates %.2f | vus %.2f" % (np.median([S[1, py, px] for _, px, py in rates]) if rates else 0,
                                                            np.median([S[1, py, px] for _, px, py in vus]) if vus else 0))
    R = int(1.5 * V.PX / V.CARREAU_M)   # 1,5 m autour
    def vignettes(x, px, py, titre):
        b = (max(0, px - R), max(0, py - R), min(W, px + R), min(H, py + R))
        a = Image.fromarray((im[b[1]:b[3], b[0]:b[2]] * 255).astype(np.uint8))
        c = Image.fromarray(pal[cls[b[1]:b[3], b[0]:b[2]]])
        p = Image.fromarray((S[1, b[1]:b[3], b[0]:b[2]] * 255).astype(np.uint8)).convert("RGB")
        out = Image.new("RGB", (3 * 2 * R + 8, 2 * R + 14), (255, 255, 255))
        for n, t in enumerate((a, c, p)):
            out.paste(t, (n * (2 * R + 4), 14))
            ImageDraw.Draw(out).rectangle([n * (2 * R + 4) + px - b[0] - 3, 14 + py - b[1] - 3, n * (2 * R + 4) + px - b[0] + 3, 14 + py - b[1] + 3], outline=(255, 0, 60), width=2)
        ImageDraw.Draw(out).text((2, 1), titre + "  long %.2f m" % x["longueur_m"], fill=(0, 0, 200))
        return out
    rng = np.random.default_rng(0)
    choix = [vignettes(*rates[i], "RATE") for i in rng.permutation(len(rates))[:8]] + [vignettes(*vus[i], "vu") for i in rng.permutation(len(vus))[:4]]
    if choix:
        w, h = choix[0].size
        pl = Image.new("RGB", (2 * w, math.ceil(len(choix) / 2) * h), (255, 255, 255))
        for n, t in enumerate(choix): pl.paste(t, ((n % 2) * w, (n // 2) * h))
        pl.save(os.path.join(V.SORTIE, "comprendre_%s_%s.png" % (cible, k))); print("planche :", os.path.join(V.SORTIE, "comprendre_%s_%s.png" % (cible, k)))
