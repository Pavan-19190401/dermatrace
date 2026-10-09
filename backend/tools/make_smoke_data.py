"""Generates a tiny fake HAM10000-style dataset (images + metadata CSV) to test the training pipeline in ~2 minutes.
Results are meaningless medically; it only proves that train.py / calibration / the server work on your machine.
  python tools/make_smoke_data.py smoke
  python train.py --meta smoke/HAM10000_metadata.csv --images smoke/images --epochs 2 --steps 64 --bs 8 --workers 0"""
import csv, math, os, random, sys
from PIL import Image, ImageDraw, ImageFilter
out = sys.argv[1] if len(sys.argv) > 1 else "smoke"; os.makedirs(out + "/images", exist_ok=True)
DX = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]; r = random.Random(1); rows = []
def lesion(rad, irr, col):
    im = Image.new("RGB", (450, 450), (r.randint(200, 235), r.randint(160, 190), r.randint(135, 165))); d = ImageDraw.Draw(im)
    d.polygon([(225 + rad * (1 + irr * .35 * math.sin(5 * a / 10)) * math.cos(a / 10), 225 + rad * (1 + irr * .35 * math.sin(5 * a / 10)) * math.sin(a / 10)) for a in range(63)], fill=col)
    return im.filter(ImageFilter.GaussianBlur(2))
for k in range(210):                                  # 210 lesions, 30 per class, some with 2 images
    dx = DX[k % 7]; n = 2 if k % 3 == 0 else 1
    for j in range(n):
        iid = f"ISIC_{k:04d}{j}"; lesion(r.randint(60, 140), r.random() * (1 if dx in ("mel", "bcc", "akiec") else .3), (r.randint(20, 90), r.randint(10, 50), r.randint(10, 40))).save(f"{out}/images/{iid}.jpg")
        rows.append(dict(lesion_id=f"HAM_{k:04d}", image_id=iid, dx=dx, dx_type="histo", age=50, sex="male", localization="back"))
with open(f"{out}/HAM10000_metadata.csv", "w", newline="") as f:
    w = csv.DictWriter(f, rows[0].keys()); w.writeheader(); w.writerows(rows)
print(len(rows), "images written to", out)
