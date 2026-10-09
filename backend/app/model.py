"""Siamese MobileNetV2: shared-weight branches -> L2-normalised 128-d embedding.
 * change  = embedding distance, calibrated to 0..1 (0.5 = optimal threshold on validation data)
 * risk    = P(akiec|bcc|mel) from the 7-class HAM10000 head on the newest image
Weights/calibration come from train.py (weights/siamese.pt + weights/calib.json).
Without them analyze() returns None and the server falls back to the heuristic engine."""
import json, math, os
BASE = os.path.join(os.path.dirname(__file__), "..", "weights")
WEIGHTS, CALIB = os.path.join(BASE, "siamese.pt"), os.path.join(BASE, "calib.json")
DX = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]
MALIGNANT = [0, 1, 4]                      # actinic keratosis/Bowen, basal cell carcinoma, melanoma
SIZE, MEAN, STD = 224, [.485, .456, .406], [.229, .224, .225]
_state = {}

def build(pretrained=False):
    import torch.nn as nn, torch.nn.functional as F
    from torchvision.models import mobilenet_v2, MobileNet_V2_Weights
    try: body = mobilenet_v2(weights=MobileNet_V2_Weights.IMAGENET1K_V1 if pretrained else None).features
    except Exception as e: print("pretrained weights unavailable, training from scratch:", e); body = mobilenet_v2(weights=None).features
    class Siamese(nn.Module):
        def __init__(s, dim=128):
            super().__init__(); s.body = body
            s.embed = nn.Sequential(nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Dropout(.2), nn.Linear(1280, dim))
            s.cls = nn.Sequential(nn.Linear(dim, 64), nn.ReLU(), nn.Linear(64, len(DX)))
        def enc(s, x): return F.normalize(s.embed(s.body(x)), dim=1)
        def forward(s, a, b):                                  # shared weights on both branches
            ea, eb = s.enc(a), s.enc(b)
            return (ea - eb).pow(2).sum(1).add(1e-8).sqrt(), s.cls(ea)
    return Siamese()

def _prep(im):
    import numpy as np, torch
    w, h = im.size; s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((SIZE + 32,) * 2)
    o = (SIZE + 32 - SIZE) // 2; im = im.crop((o, o, o + SIZE, o + SIZE))
    x = (np.asarray(im, dtype=np.float32) / 255 - MEAN) / STD
    return torch.tensor(x, dtype=torch.float32).permute(2, 0, 1)[None]

def available(): return os.path.exists(WEIGHTS) and os.path.exists(CALIB)

def analyze(ia, ib):
    if not available(): return None
    import torch
    if not _state:
        net = build(); net.load_state_dict(torch.load(WEIGHTS, map_location="cpu")); net.eval()
        _state.update(net=net, cal=json.load(open(CALIB)))
    net, cal = _state["net"], _state["cal"]
    with torch.no_grad():
        ea, eb = net.enc(_prep(ia)), net.enc(_prep(ib))
        dist = float((ea - eb).pow(2).sum().sqrt())
        pr = torch.softmax(net.cls(eb), 1)[0]
    change = 1 / (1 + math.exp(-(dist - cal["thr"]) / cal["scale"]))
    return dict(change=change, risk=float(sum(pr[i] for i in MALIGNANT)), risk_thr=cal["risk_thr"],
                dx={d: round(float(pr[i]), 3) for i, d in enumerate(DX)})
