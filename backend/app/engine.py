"""Lesion analysis: ABCDE metrics + longitudinal change score + 3-way decision.
Uses the Siamese MobileNetV2 (app/model.py) when weights exist, otherwise a transparent
numpy heuristic. Both feed the same decision rule."""
import base64, io
import numpy as np
from PIL import Image
VERDICTS = ["No Visit Needed", "Visit a Doctor", "Inconclusive"]

def decode(data_url: str) -> Image.Image:
    raw = base64.b64decode(data_url.split(",", 1)[-1])
    return Image.open(io.BytesIO(raw)).convert("RGB")

def square(img, n):
    w, h = img.size; s = min(w, h)
    return np.asarray(img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2)).resize((n, n)), dtype=np.float32)

def metrics(img, sens=.5, fov=40.0):
    n = 64; d = square(img, n); L = d @ np.array([.3, .59, .11], dtype=np.float32)
    edge = np.concatenate([L[:6].ravel(), L[-6:].ravel(), L[:, :6].ravel(), L[:, -6:].ravel()])
    k = 14 + (1 - sens) * 22; M = L < edge.mean() - k; area = int(M.sum())
    lap = 4 * L[1:-1, 1:-1] - L[:-2, 1:-1] - L[2:, 1:-1] - L[1:-1, :-2] - L[1:-1, 2:]
    q = float(min(1, min((lap ** 2).mean() / 25, 1) * .6 + (.4 if 55 < L.mean() < 225 else .1)))
    if area < 20: return dict(A=0, B=0, C=0, D=0, q=min(q, .2), area=area)
    ys, xs = np.nonzero(M); x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    P = np.pad(M, 1); inner = P[1:-1, :-2] & P[1:-1, 2:] & P[:-2, 1:-1] & P[2:, 1:-1]
    per = int((M & ~inner).sum())
    sub = M[y0:y1 + 1, x0:x1 + 1]
    mis = int((sub != sub[:, ::-1]).sum() + (sub != sub[::-1, :]).sum()) / 2
    A = min(1, mis / area * 1.1)
    B = min(1, max(0, (per ** 2 / (4 * np.pi * area) - 1.1) / 2.2))
    C = min(1, float(np.sqrt(((d[M] - d[M].mean(0)) ** 2).mean())) / 45)
    return dict(A=float(A), B=float(B), C=float(C), D=round(float((x1 - x0 + 1) / n * fov), 1), q=q, area=area)

def pixel_change(a, b, n=48):
    return float(min(1, np.abs(square(a, n) - square(b, n)).mean() / 255 * 4))

def decide(score, q, thr, risk=None, risk_thr=None):
    """3-way outcome from change score, image quality and (deep model only) single-image malignancy risk."""
    hi = risk is not None and risk >= max(risk_thr, .7)
    if q < .45: v, r = 2, "Image quality too low (blur or lighting). Retake under even light."
    elif hi: v, r = 1, "The lesion's appearance pattern was flagged as high-risk — see a dermatologist."
    elif score >= thr + 8 or (risk is not None and risk >= risk_thr and score >= thr - 8):
        v, r = 1, "Significant evolution across visits — book a dermatologist review."
    elif score < thr - 8: v, r = 0, "Lesion looks stable between visits. Keep monitoring."
    else: v, r = 2, "Borderline change — the model is not confident. Retake and compare again."
    return v, r, round(min(1, .45 + abs(score - thr) / max(thr, 1) * .6) * q * 100)

def compare(ia, ib, sens=.5, fov=40.0, mode="Auto", w=None):
    w = {**dict(A=1, B=1, C=1, D=1, E=1), **(w or {})}
    n = {"Fast": 32, "Slow": 72}.get(mode, 48)
    ma, mb = metrics(ia, sens, fov), metrics(ib, sens, fov); q = min(ma["q"], mb["q"])
    p = pixel_change(ia, ib, n)
    dl = dict(A=mb["A"] - ma["A"], B=mb["B"] - ma["B"], C=mb["C"] - ma["C"], D=mb["D"] - ma["D"], E=p)
    deep = None
    try:
        from . import model
        deep = model.analyze(ia, ib)
    except Exception as e: print("deep model unavailable:", e)
    if deep:                                   # trained Siamese MobileNetV2 + calibrated thresholds
        dl["E"] = deep["change"]; score = int(round(deep["change"] * 100)); thr = 50 - (sens - .5) * 30
        v, r, conf = decide(score, q, thr, deep["risk"], deep["risk_thr"] * 1.0)
        return dict(score=score, dl=dl, v=v, verdict=VERDICTS[v], r=r, conf=conf, engine="siamese-mobilenetv2",
                    risk=round(deep["risk"], 3), dx=deep["dx"], a=ma, b=mb)
    t = [w["A"] * abs(dl["A"]) * 160, w["B"] * abs(dl["B"]) * 140, w["C"] * abs(dl["C"]) * 140,
         w["D"] * min(1, abs(dl["D"]) / 3) * 100, w["E"] * p * 100]
    score = int(min(100, round(.6 * sum(t) / (sum(w.values()) or 1) + .4 * max(t))))   # mean + strongest single change
    v, r, conf = decide(score, q, 48 - sens * 26)
    return dict(score=score, dl=dl, v=v, verdict=VERDICTS[v], r=r, conf=conf, engine="heuristic", risk=None, a=ma, b=mb)
