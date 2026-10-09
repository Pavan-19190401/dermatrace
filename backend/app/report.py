"""One-page PDF report (Pillow only)."""
import io
from PIL import Image, ImageDraw, ImageFont
def font(n, bold=False):
    for f in (["DejaVuSans-Bold.ttf"] if bold else ["DejaVuSans.ttf"]):
        try: return ImageFont.truetype(f, n)
        except OSError: pass
    return ImageFont.load_default()
def make_pdf(name, site, ia, ib, ta, tb, res):
    W, H = 1240, 1754; pg = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(pg)
    d.text((80, 80), "DermaTrace - lesion monitoring report", font=font(44, True), fill=(30, 30, 40))
    d.text((80, 150), f"Lesion: {name}   Site: {site or '-'}", font=font(28), fill=(80, 80, 90))
    for k, (im, t) in enumerate(((ia, ta), (ib, tb))):
        pg.paste(im.resize((500, 500)), (80 + k * 540, 230)); d.text((80 + k * 540, 745), f"Visit {t}", font=font(26), fill=(60, 60, 70))
    col = [(46, 158, 106), (214, 75, 75), (217, 151, 43)][res["v"]]
    d.rounded_rectangle((80, 830, 1160, 960), 24, fill=col)
    d.text((120, 855), f"{res['verdict']}", font=font(46, True), fill="white")
    d.text((120, 915), f"Change score {res['score']}/100   confidence {res['conf']}%   engine: {res['engine']}", font=font(24), fill="white")
    y = 1000; d.text((80, y), res["r"], font=font(26), fill=(40, 40, 50)); y += 70
    names = dict(A="Asymmetry", B="Border", C="Colour", D="Diameter (mm)", E="Evolution")
    for k, n in names.items():
        b = res["b"]; val = b["D"] if k == "D" else (res["dl"]["E"] if k == "E" else b[k])
        d.text((80, y), f"{k} - {n}", font=font(26), fill=(40, 40, 50)); d.rectangle((520, y + 6, 1000, y + 28), fill=(235, 235, 240))
        d.rectangle((520, y + 6, 520 + int(480 * min(1, val / (20 if k == "D" else 1))), y + 28), fill=(47, 107, 255))
        d.text((1020, y), f"{val:.2f}", font=font(24), fill=(80, 80, 90)); y += 55
    if res.get("risk") is not None: d.text((80, y + 10), f"Single-image high-risk pattern probability: {res['risk']*100:.0f}%", font=font(26), fill=(40, 40, 50))
    d.text((80, H - 160), "Clinical decision-support / triage aid only - NOT a diagnosis. Show this report to a dermatologist.", font=font(22), fill=(150, 60, 60))
    out = io.BytesIO(); pg.save(out, "PDF", resolution=150); return out.getvalue()
