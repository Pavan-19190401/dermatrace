"""Train + calibrate + evaluate the DermaTrace Siamese network on HAM10000.

  python train.py --meta HAM10000_metadata.csv --images HAM10000_images_part_1 HAM10000_images_part_2 --epochs 12

HAM10000 has diagnosis labels and repeat images of the same lesion, but NO 'changed / unchanged' labels, so:
  unchanged (0): the same image re-photographed (rotation, shift, zoom, lighting, blur) or another image of the same lesion_id
  changed   (1): synthetic evolution of that image (growth, border warp, new dark blotch) + re-photograph
Plus a 7-class diagnosis head (multi-task). Splits are by lesion_id so no lesion leaks across train/val/test.
Outputs weights/siamese.pt, weights/calib.json (thresholds chosen on VAL) and weights/metrics.json (reported on TEST)."""
import argparse, collections, csv, json, os, random
import numpy as np, torch, torch.nn.functional as F
from PIL import Image, ImageFilter
import torchvision.transforms.functional as TF
from app.model import build, DX, MALIGNANT, MEAN, STD, SIZE
BIG = SIZE + 64

def read_meta(meta, dirs):
    paths = {os.path.splitext(f)[0]: os.path.join(d, f) for d in dirs for f in os.listdir(d)}
    rows = [r for r in csv.DictReader(open(meta)) if r["image_id"] in paths]
    if not rows: raise SystemExit("No images matched the metadata — check --images folders")
    for r in rows: r["path"], r["y"] = paths[r["image_id"]], DX.index(r["dx"])
    return rows

def split(rows, seed=0):                       # by lesion → no leakage
    ids = sorted({r["lesion_id"] for r in rows}); random.Random(seed).shuffle(ids); n = len(ids)
    which = {i: "train" if k < .7 * n else "val" if k < .85 * n else "test" for k, i in enumerate(ids)}
    out = collections.defaultdict(list)
    for r in rows: out[which[r["lesion_id"]]].append(r)
    return out

def load(p):
    im = Image.open(p).convert("RGB"); w, h = im.size; s = min(w, h)
    return im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((BIG, BIG))

def rephoto(im, r):                            # a new photo session of the same lesion
    im = TF.rotate(im, r.uniform(-25, 25))
    if r.random() < .5: im = TF.hflip(im)
    im = TF.affine(im, 0, [r.randint(-14, 14), r.randint(-14, 14)], r.uniform(.93, 1.07), 0)
    im = TF.adjust_saturation(TF.adjust_contrast(TF.adjust_brightness(im, r.uniform(.8, 1.2)), r.uniform(.85, 1.15)), r.uniform(.85, 1.15))
    if r.random() < .3: im = im.filter(ImageFilter.GaussianBlur(r.uniform(.4, 1.2)))
    return TF.center_crop(im, SIZE)

def evolve(im, r):                             # synthetic lesion evolution (the "E" in ABCDE)
    kinds = r.sample(["grow", "warp", "blotch"], r.randint(1, 3))
    if "grow" in kinds: im = TF.affine(im, 0, [0, 0], r.uniform(1.2, 1.7), 0)
    if "warp" in kinds:
        w = im.size[0]; k = w * .13; sp = [[0, 0], [w, 0], [w, w], [0, w]]
        im = TF.perspective(im, sp, [[x + r.uniform(-k, k), y + r.uniform(-k, k)] for x, y in sp])
    if "blotch" in kinds:
        a = np.asarray(im, dtype=np.float32); h, w, _ = a.shape; yy, xx = np.mgrid[:h, :w]
        cx, cy, rad = w / 2 + r.uniform(-.12, .12) * w, h / 2 + r.uniform(-.12, .12) * h, r.uniform(.07, .18) * w
        m = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * rad ** 2))[..., None]
        tint = np.array([r.uniform(.25, .6), r.uniform(.25, .55), r.uniform(.25, .55)])
        im = Image.fromarray((a * (1 - m * (1 - tint) * r.uniform(.6, 1))).clip(0, 255).astype(np.uint8))
    return im

class Pairs(torch.utils.data.Dataset):
    def __init__(self, rows, n, fixed=None):
        self.rows, self.n, self.fixed = rows, n, fixed
        self.by = collections.defaultdict(list)
        for r in rows: self.by[r["lesion_id"]].append(r)
        c = collections.Counter(r["y"] for r in rows); self.w = [1 / c[r["y"]] ** .5 for r in rows]   # soften class imbalance
    def __len__(self): return self.n
    def __getitem__(self, i):
        r = random.Random(self.fixed * 1_000_003 + i) if self.fixed is not None else random.Random()
        row = self.rows[i % len(self.rows)] if self.fixed is not None else r.choices(self.rows, self.w)[0]
        base, u, others = load(row["path"]), r.random(), [x for x in self.by[row["lesion_id"]] if x is not row]
        if u < .35: a, b, y = rephoto(base, r), rephoto(base, r), 0
        elif u < .5 and others: a, b, y = rephoto(base, r), rephoto(load(r.choice(others)["path"]), r), 0
        elif u < .5: a, b, y = rephoto(base, r), rephoto(base, r), 0
        else: a, b, y = rephoto(base, r), rephoto(evolve(base, r), r), 1
        t = lambda im: TF.normalize(TF.to_tensor(im), MEAN, STD)
        return t(a), t(b), y, row["y"]

def auc(s, y):
    o = np.argsort(s); rk = np.empty(len(s)); rk[o] = np.arange(1, len(s) + 1); p = y == 1
    return float((rk[p].sum() - p.sum() * (p.sum() + 1) / 2) / (p.sum() * (~p).sum()))

@torch.no_grad()
def predict(net, dl, dev):
    net.eval(); D, Y, P, C = [], [], [], []
    for xa, xb, y, c in dl:
        d, la = net(xa.to(dev), xb.to(dev)); D += d.cpu().tolist(); Y += y.tolist(); C += c.tolist(); P += F.softmax(la, 1).cpu().tolist()
    return np.array(D), np.array(Y), np.array(P), np.array(C)

def balanced_acc(P, C): return float(np.mean([(P[C == k].argmax(1) == k).mean() for k in range(len(DX)) if (C == k).any()]))

def calibrate(D, Y, P, C):
    ts = np.quantile(D, np.linspace(.01, .99, 99)); J = [((D[Y == 1] > t).mean() - (D[Y == 0] > t).mean()) for t in ts]
    thr = float(ts[int(np.argmax(J))]); scale = max(1e-3, float((D[Y == 1].mean() - D[Y == 0].mean()) / 4))
    risk, mal = P[:, MALIGNANT].sum(1), np.isin(C, MALIGNANT)
    ok = [t for t in np.linspace(.05, .95, 91) if (risk[mal] >= t).mean() >= .90]     # keep ≥90 % malignant sensitivity
    return dict(thr=thr, scale=scale, risk_thr=float(max(ok) if ok else .2))

def report(D, Y, P, C, cal):
    risk, mal = P[:, MALIGNANT].sum(1), np.isin(C, MALIGNANT)
    pred_change = D > cal["thr"]
    true_change = Y == 1
    tp = int(((pred_change == 1) & (true_change == 1)).sum())
    fp = int(((pred_change == 1) & (true_change == 0)).sum())
    fn = int(((pred_change == 0) & (true_change == 1)).sum())
    tn = int(((pred_change == 0) & (true_change == 0)).sum())
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-6)
    return dict(
        change_auc=auc(D, Y),
        change_acc=float(((pred_change) == (true_change)).mean()),
        precision=float(prec),
        recall=float(rec),
        f1_score=float(f1),
        confusion_matrix=dict(TP=tp, FP=fp, FN=fn, TN=tn),
        dx_balanced_acc=balanced_acc(P, C),
        malignant_sensitivity=float((risk[mal] >= cal["risk_thr"]).mean()),
        malignant_specificity=float((risk[~mal] < cal["risk_thr"]).mean())
    )

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--meta", required=True); ap.add_argument("--images", nargs="+", required=True)
    ap.add_argument("--epochs", type=int, default=12); ap.add_argument("--steps", type=int, default=3000, help="pairs per epoch")
    ap.add_argument("--bs", type=int, default=32); ap.add_argument("--workers", type=int, default=4); ap.add_argument("--margin", type=float, default=1.0)
    ap.add_argument("--val-steps", type=int, default=1500, help="validation pairs")
    ap.add_argument("--test-steps", type=int, default=2000, help="testing pairs")
    a = ap.parse_args(); dev = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    sp = split(read_meta(a.meta, a.images)); print({k: len(v) for k, v in sp.items()}, "device", dev)
    mk = lambda rows, n, fixed=None, sh=False: torch.utils.data.DataLoader(Pairs(rows, n, fixed), a.bs, shuffle=sh, num_workers=a.workers, persistent_workers=a.workers > 0)
    tr, va, te = mk(sp["train"], a.steps, None), mk(sp["val"], a.val_steps, 1), mk(sp["test"], a.test_steps, 2)
    c = collections.Counter(r["y"] for r in sp["train"]); cw = torch.tensor([len(sp["train"]) / (len(DX) * max(c[k], 1)) for k in range(len(DX))]).float().clamp(max=8).sqrt().to(dev)
    net = build(pretrained=True).to(dev); opt = torch.optim.AdamW(net.parameters(), 2e-4, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 6e-4, total_steps=a.epochs * len(tr)); best = -1; os.makedirs("weights", exist_ok=True)
    for ep in range(a.epochs):
        net.train(); tot = 0
        for xa, xb, y, c_ in tr:
            xa, xb, y, c_ = xa.to(dev), xb.to(dev), y.to(dev).float(), c_.to(dev)
            d, la = net(xa, xb)
            loss = ((1 - y) * d.pow(2) + y * F.relu(a.margin - d).pow(2)).mean() + .5 * F.cross_entropy(la, c_, weight=cw, label_smoothing=.05)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step(); tot += loss.item()
        D, Y, P, C = predict(net, va, dev); score = .5 * auc(D, Y) + .5 * balanced_acc(P, C)
        print(f"epoch {ep+1}/{a.epochs} loss {tot/len(tr):.4f}  val change-AUC {auc(D, Y):.3f}  val dx-balAcc {balanced_acc(P, C):.3f}")
        if score > best: best = score; torch.save(net.state_dict(), "weights/siamese.pt")
    net.load_state_dict(torch.load("weights/siamese.pt", map_location=dev))
    cal = calibrate(*predict(net, va, dev)); cal.update(margin=a.margin, data="HAM10000 + synthetic evolution", labels=DX)
    json.dump(cal, open("weights/calib.json", "w"), indent=1)
    m = report(*predict(net, te, dev), cal); json.dump(m, open("weights/metrics.json", "w"), indent=1)
    print("TEST (thresholds frozen from val):", json.dumps(m, indent=1))
if __name__ == "__main__": main()
