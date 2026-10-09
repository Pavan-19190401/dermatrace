# DermaTrace – full stack (mobile PWA + FastAPI + Siamese MobileNetV2)

Clinical decision-support / triage aid. **Not a diagnostic system.**

## 1 Run locally
    ./run.sh                       # http://localhost:8000  (camera works on localhost / HTTPS only)
    cd backend && python test_api.py

## 2 Train the deep model
**Easiest:** open `DermaTrace_Colab_v2.ipynb` in Google Colab (free T4 GPU) and run the cells – it downloads HAM10000, trains, and gives you `weights.zip` to unzip into `backend/weights/`.
**Pipeline check on your own PC first (2 min):** `pip install torch torchvision`, then `cd backend && python tools/make_smoke_data.py smoke && python train.py --meta smoke/HAM10000_metadata.csv --images smoke/images --epochs 1 --steps 64 --bs 8 --workers 0` (delete `backend/weights` afterwards – these are fake images).
**Manual route (GPU machine, ~1-3 h on a T4):**
1. Download HAM10000 images (Harvard Dataverse doi:10.7910/DVN/DBW86T, or Kaggle `kmader/skin-cancer-mnist-ham10000`) → folders `HAM10000_images_part_1`, `_part_2`; keep `HAM10000_metadata.csv`.
2. `pip install torch torchvision numpy pillow`
3. `cd backend && python train.py --meta ../HAM10000_metadata.csv --images ../HAM10000_images_part_1 ../HAM10000_images_part_2 --epochs 12`
4. It writes `backend/weights/siamese.pt`, `calib.json` (thresholds picked on the validation split) and `metrics.json` (test-split results). Restart the server: `GET /api/health` now says `"deep_model": true` and every comparison reports `"engine": "siamese-mobilenetv2"` with a `risk` value.

How labels are made (HAM10000 has no "changed" labels): unchanged = same image re-photographed (rotation/shift/zoom/lighting/blur) or another image of the same `lesion_id`; changed = synthetic growth, border warp and new dark blotch. A 7-class diagnosis head is trained jointly; risk = P(akiec+bcc+mel). Splits are by `lesion_id` (no leakage; verified: 6977 / 1504 / 1534 images from your metadata).

## 3 Deploy with HTTPS
    DOMAIN=derma.example.com DT_SECRET=$(openssl rand -hex 32) docker compose up -d
`DT_SECRET` must be ≥ 32 chars (if unset a random secret is generated and stored in `data/.secret`). Rate limiting, security headers, account deletion (`DELETE /api/account`) and a first-run consent screen are built in.

## 4 Phone app
* **PWA (works now):** open the HTTPS URL on the phone → "Install app" / Add to Home Screen.
* **Native store apps:** `npm i @capacitor/core @capacitor/cli @capacitor/android @capacitor/ios`, edit `capacitor.config.json` (your domain), `npx cap add android && npx cap sync` (add `CAMERA` permission / `NSCameraUsageDescription`).

## Limits you must keep in mind
* HAM10000 is **dermoscopy** from two clinics; phone photos differ. Fine-tune/validate on smartphone data (e.g. PAD-UFES-20) before trusting thresholds.
* Change labels are synthetic; real follow-up validation by dermatologists is required before any clinical claim or store listing (medical-device rules, e.g. CDSCO/FDA/EU MDR).
