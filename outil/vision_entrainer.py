"""APPRENDRE notre dessin a la vision (declaration au coffre « Vision re-entrainee sur nos plans », 27/11).
  python un_par_un.py vision_entrainer.py plans_appr     -> exercices : sorties/vision_appr/<nom>.npz (image + reponse)
  python vision_entrainer.py --entrainer [minutes]       -> affine le UNet (poids CubiCasa au depart) -> sorties/vision_nos_plans.safetensors
Reponse par pixel : 0 sol, 1 mur, 2 porte, 3 fenetre, 255 inconnu (pas note)."""
import glob, gzip, json, os, sys, time
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ici)
import vision_murs as V
EX = os.path.join(ici, "sorties", "vision_appr"); os.makedirs(EX, exist_ok=True)
POIDS = os.path.join(ici, "sorties", "vision_nos_plans.safetensors")
CL = {"mur": 1, "porte": 2, "vitre": 3, "lettre": 0, "cote": 0, "mobilier": 0, "autre": 0, "fond": 0}


def exercice(f, base="objets_appr_mm_mp_au"):
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw
    from metre import normaliser, echelle_par_cotes, lire_textes, origine, page_plumber
    ch = normaliser(f); nom = os.path.splitext(os.path.basename(f))[0][:60]
    fo = glob.glob(os.path.join(ici, "sorties", base, glob.escape(nom) + "*.jsonl.gz"))
    if not fo: return None, "pas de base"
    L = [json.loads(l) for l in gzip.open(fo[0], "rt", encoding="utf-8")]
    m = echelle_par_cotes(ch, 0)[0]
    if not m: return None, "pas d'echelle"
    sc = V.PX / V.CARREAU_M * m
    doc = pdfium.PdfDocument(ch); OX, OY = origine(doc[0])
    img = doc[0].render(scale=sc, fill_color=(255, 255, 255, 255)).to_pil().convert("RGB"); doc.close()
    W, H = img.size
    if min(W, H) < 600: return None, "echelle douteuse (page de %dx%d px = %.1f x %.1f m)" % (W, H, W / V.PX * V.CARREAU_M, H / V.PX * V.CARREAU_M)
    _, Hp, _, _ = lire_textes(ch, 0); dy = Hp - OY
    pl = page_plumber(ch)
    objs = [o for o in pl.lines + pl.rects + pl.curves if len(o.get("pts") or []) >= 2]
    if len(objs) != len(L): return None, "alignement %d/%d" % (len(objs), len(L))
    rep = Image.new("L", (W, H), 0)          # sol par defaut (fond blanc)
    d = ImageDraw.Draw(rep)
    # 1) tout objet dessine = inconnu ; 2) puis les objets notes, sol d'abord, mur/fenetre/porte par-dessus
    ordre = [(i, 255) for i in range(len(objs))] + \
            [(i, CL[L[i]["classe"]]) for i in range(len(objs)) if CL.get(L[i].get("classe")) == 0] + \
            [(i, CL[L[i]["classe"]]) for k in (1, 3, 2) for i in range(len(objs)) if CL.get(L[i].get("classe")) == k]
    for i, v in ordre:
        o = objs[i]
        pts = [((p[0] - OX) * sc, (p[1] - dy) * sc) for p in o["pts"]]
        if o.get("object_type") == "rect" and len(pts) >= 4: pts = pts + [pts[0]]
        lw = max(2, int(round((o.get("linewidth") or 0) * sc)) + 1)
        if o.get("fill") and len(pts) >= 3: d.polygon(pts, fill=v)
        d.line(pts, fill=v, width=lw)
    return (np.asarray(img, np.uint8), nettoyer(np.asarray(rep, np.uint8).copy())), "ok"


def nettoyer(rep):
    """27/11, cause mesuree : 34 % des pixels « mur » etaient des PLAQUES de plus de 50 cm (formes remplies etiquetees mur,
    jusqu'a 267 m2 ; plan de carrelage a 62 % « mur »). Un mur est mince : ce qui survit a une ouverture de 50 cm -> inconnu."""
    from scipy.ndimage import binary_opening
    k = int(0.5 * V.PX / V.CARREAU_M)
    epais = binary_opening(rep == 1, structure=np.ones((k, k), bool))
    rep[epais] = 255
    return rep


if __name__ == "__main__" and sys.argv[1] == "--page":
    f = sys.argv[2]; nom = os.path.splitext(os.path.basename(f))[0][:60]
    sortie = os.path.join(EX, nom + ".npz")
    if os.path.exists(sortie): print("%-60s deja fait" % nom); sys.exit(0)
    t = time.time(); r, msg = exercice(f)
    if r is None: print("%-60s ignore (%s)" % (nom, msg)); sys.exit(0)
    im, rep = r
    np.savez_compressed(sortie, im=im, rep=rep)
    n = rep.size
    print("%-60s %dx%d | mur %.2f %% fen %.2f %% porte %.2f %% inconnu %.1f %% | %d s" % (nom, im.shape[1], im.shape[0],
          100 * (rep == 1).sum() / n, 100 * (rep == 3).sum() / n, 100 * (rep == 2).sum() / n, 100 * (rep == 255).sum() / n, time.time() - t), flush=True)

elif __name__ == "__main__" and sys.argv[1] == "--entrainer":
    import torch
    from safetensors.torch import save_file
    minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 60
    torch.set_num_threads(2); rng = np.random.default_rng(0)
    net = V.modele().train()
    if os.path.exists(POIDS) and "--depuis-zero" not in sys.argv:
        from safetensors.torch import load_file; net.load_state_dict(load_file(POIDS)); print("reprise de", POIDS)
    opt = torch.optim.AdamW(net.parameters(), lr=1e-4, weight_decay=1e-4)
    poids_cl = torch.tensor([1.0, 3.0, 5.0, 5.0])   # sol tres majoritaire
    pages = sorted(glob.glob(os.path.join(EX, "*.npz")))
    print(len(pages), "pages d'exercices", flush=True)
    t0 = time.time(); it = 0; pertes = []
    while time.time() - t0 < minutes * 60:
        ip = rng.integers(len(pages)); z = np.load(pages[ip], allow_pickle=False); im, rep = z["im"], z["rep"]; coords = []
        H, W = rep.shape; lots_x, lots_y = [], []
        for _ in range(int(os.environ.get("LOT", "2"))):   # 27/11 : 4 -> 2 (memoire)
            for essai in range(20):   # carreaux qui contiennent des murs / fenetres / portes de preference
                y = rng.integers(0, max(H - V.PX, 1)); x = rng.integers(0, max(W - V.PX, 1))
                r = rep[y:y + V.PX, x:x + V.PX]
                if ((r >= 1) & (r <= 3)).mean() > 0.002 or essai == 19: break
            coords.append((int(x), int(y)))
            c = np.ones((V.PX, V.PX, 3), np.float32) * V.MEAN.astype(np.float32); rr = np.full((V.PX, V.PX), 255, np.uint8)
            cc = im[y:y + V.PX, x:x + V.PX].astype(np.float32) / 255; c[:cc.shape[0], :cc.shape[1]] = cc; rr[:r.shape[0], :r.shape[1]] = r
            if rng.random() < 0.5: c = c[:, ::-1]; rr = rr[:, ::-1]
            if rng.random() < 0.5: c = c[::-1]; rr = rr[::-1]
            lots_x.append(((c - V.MEAN) / V.STD).transpose(2, 0, 1).copy()); lots_y.append(rr.copy())
        X = torch.from_numpy(np.stack(lots_x).astype(np.float32)); Y = torch.from_numpy(np.stack(lots_y).astype(np.int64))
        perte = torch.nn.functional.cross_entropy(net(X), Y, weight=poids_cl, ignore_index=255)
        opt.zero_grad(); perte.backward(); opt.step(); it += 1; pertes.append(float(perte.detach()))
        if pertes[-1] > 3:   # 27/11 : garder les carreaux a grosse erreur pour les regarder (chercher pourquoi)
            with open(os.path.join(ici, "sorties", "vision_carreaux_difficiles.txt"), "a", encoding="utf-8") as fd:
                fd.write("%d | %.2f | %s | %s\n" % (it, pertes[-1], os.path.basename(pages[ip]), coords))
        if it % 25 == 0:
            print("  pas %d | perte %.3f | %d min" % (it, np.mean(pertes[-25:]), (time.time() - t0) / 60), flush=True)
            save_file({k: v.contiguous() for k, v in net.state_dict().items()}, POIDS)
    save_file({k: v.contiguous() for k, v in net.state_dict().items()}, POIDS)
    print("FINI : %d pas, perte finale %.3f -> %s" % (it, np.mean(pertes[-25:]) if pertes else 0, POIDS))
