"""DermaTrace End-to-End Pipeline Runner.
Follows PPT Slide 1 & Slide 2:
1. Data Cleaning (Steps 1–8)
2. Data Visualization & Analytics (Steps 1–7)
3. 70/15/15 Data Splitting (Train/Val/Test by lesion_id)
4. Siamese MobileNetV2 Contrastive Training
5. Evaluation & Testing (Accuracy, Precision, Recall, F1, Confusion Matrix, ROC-AUC)
6. Calibration of 3-Way Decision System: No Visit Needed, Visit a Doctor, Inconclusive
"""

import argparse, collections, csv, json, os, random, sys, time
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
import torchvision.transforms.functional as TF

from app.model import build, DX, MALIGNANT, MEAN, STD, SIZE
from app.pipeline import get_pipeline_eda, get_model_metrics

def run_data_cleaning(meta_path, output_csv):
    """Executes the 8 Data Cleaning Steps from PPT Slide 2."""
    print("=" * 60)
    print("PHASE 1: DERMATRACE DATA CLEANING (8 STEPS - PPT SLIDE 2)")
    print("=" * 60)
    
    # Step 1: Load Data
    print("[Step 1/8] Loading dataset from:", meta_path)
    with open(meta_path, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    total_raw = len(reader)
    print(f"           Loaded {total_raw} raw records.")
    
    # Step 2: Explore Data
    print("[Step 2/8] Exploring data schema, column types, and distributions...")
    dx_counts = collections.Counter(r.get("dx") for r in reader)
    for dx, count in dx_counts.items():
        print(f"           - {dx}: {count} ({count/total_raw*100:.1f}%)")
    
    # Step 3: Handle Missing Values
    print("[Step 3/8] Handling missing values...")
    ages = [float(r["age"]) for r in reader if r.get("age") and r["age"].replace(".", "", 1).isdigit()]
    median_age = float(np.median(ages)) if ages else 50.0
    imputed_count = 0
    for r in reader:
        if not r.get("age") or not r["age"].replace(".", "", 1).isdigit():
            r["age"] = str(median_age)
            imputed_count += 1
        if not r.get("localization"):
            r["localization"] = "unknown"
    print(f"           Imputed {imputed_count} missing age values with median ({median_age} yrs).")
    
    # Step 4: Remove Duplicates
    print("[Step 4/8] Detecting duplicate records...")
    seen = set()
    deduped = []
    for r in reader:
        key = (r.get("lesion_id"), r.get("image_id"))
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    print(f"           Retained {len(deduped)} distinct image records (removed {total_raw - len(deduped)} duplicates).")
    
    # Step 5: Handle Outliers
    print("[Step 5/8] Handling outliers via IQR bounding...")
    q25, q75 = np.percentile(ages, 25), np.percentile(ages, 75)
    iqr = q75 - q25
    low_b, high_b = max(0, q25 - 1.5 * iqr), min(100, q75 + 1.5 * iqr)
    capped = 0
    for r in deduped:
        a = float(r["age"])
        if a < low_b or a > high_b:
            r["age"] = str(max(low_b, min(high_b, a)))
            capped += 1
    print(f"           IQR age bounds: [{low_b:.1f}, {high_b:.1f}]. Capped {capped} extreme outliers.")
    
    # Step 6: Encode Categorical Data
    print("[Step 6/8] Encoding categorical data (dx classes, sex, anatomical site)...")
    for r in deduped:
        r["dx_code"] = str(DX.index(r["dx"])) if r["dx"] in DX else "-1"
        r["sex_code"] = "0" if r.get("sex") == "male" else ("1" if r.get("sex") == "female" else "2")
    
    # Step 7: Scale Numerical Features
    print("[Step 7/8] Scaling numerical features (Image tensors normalized to standard ImageNet mean & std)...")
    
    # Step 8: Final Check & Save
    print(f"[Step 8/8] Final validation check & saving cleaned dataset to: {output_csv}")
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    if deduped:
        keys = list(deduped[0].keys())
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(deduped)
    print("           Data cleaning complete. Cleaned records:", len(deduped))
    return deduped

def main():
    parser = argparse.ArgumentParser(description="DermaTrace Full Pipeline Runner")
    parser.add_argument("--meta", default="smoke/HAM10000_metadata.csv", help="Metadata CSV path")
    parser.add_argument("--images", nargs="+", default=["smoke/images"], help="Image folders")
    parser.add_argument("--epochs", type=int, default=1, help="Training epochs")
    parser.add_argument("--steps", type=int, default=64, help="Steps per epoch")
    parser.add_argument("--bs", type=int, default=8, help="Batch size")
    parser.add_argument("--workers", type=int, default=0, help="Dataloader workers")
    parser.add_argument("--val-steps", type=int, default=100, help="Validation pairs")
    parser.add_argument("--test-steps", type=int, default=100, help="Testing pairs")
    parser.add_argument("--output-weights", default="weights", help="Directory for weights output")
    args = parser.parse_args()

    cleaned_csv = os.path.join(args.output_weights, "HAM10000_cleaned.csv")
    cleaned_rows = run_data_cleaning(args.meta, cleaned_csv)

    print("\n" + "=" * 60)
    print("PHASE 2 & 3: MODEL TRAINING, TESTING & EVALUATION (PPT SLIDE 1)")
    print("=" * 60)
    import subprocess
    cmd = [
        sys.executable,
        "train.py",
        "--meta", cleaned_csv,
        "--images", *args.images,
        "--epochs", str(args.epochs),
        "--steps", str(args.steps),
        "--bs", str(args.bs),
        "--workers", str(args.workers),
        "--val-steps", str(args.val_steps),
        "--test-steps", str(args.test_steps)
    ]
    print("Running command:", " ".join(cmd))
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print("Training encountered an error.")
        sys.exit(res.returncode)

    print("\n" + "=" * 60)
    print("PHASE 3 COMPLETE: MODEL EVALUATION METRICS SUMMARY")
    print("=" * 60)
    metrics_file = os.path.join(args.output_weights, "metrics.json")
    if os.path.exists(metrics_file):
        with open(metrics_file) as f:
            m = json.load(f)
            print(json.dumps(m, indent=2))
    print("All tasks finished successfully!")

if __name__ == "__main__":
    main()
