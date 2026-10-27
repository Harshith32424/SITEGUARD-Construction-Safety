from ultralytics import YOLO
from pathlib import Path


# ============================================================
# TEST / EVALUATION
# ============================================================

MODEL_PATH = Path("runs/detect/runs/ppe_training/weights/best.pt")
DATASET_YAML = Path("Datasets/dataset_1/data.yaml")


print("=" * 60)
print("PPE MODEL EVALUATION")
print("=" * 60)


# ------------------------------------------------------------
# Check files
# ------------------------------------------------------------

if not MODEL_PATH.exists():
    raise FileNotFoundError(
        f"\nModel not found:\n{MODEL_PATH}\n\n"
        "Run training.py first."
    )

if not DATASET_YAML.exists():
    raise FileNotFoundError(
        f"\nDataset YAML not found:\n{DATASET_YAML}"
    )


# ------------------------------------------------------------
# Load trained model
# ------------------------------------------------------------

print("\nLoading trained model...")

model = YOLO(str(MODEL_PATH))

print("Model loaded.")


# ------------------------------------------------------------
# Evaluate on TEST dataset
# ------------------------------------------------------------

print("\nEvaluating on TEST dataset...")

metrics = model.val(
    data=str(DATASET_YAML),
    split="test",
    imgsz=640,
    batch=8,
    plots=True
)


# ------------------------------------------------------------
# Display results
# ------------------------------------------------------------

print("\n")
print("=" * 60)
print("TEST EVALUATION COMPLETED")
print("=" * 60)

print(f"\nmAP50:     {metrics.box.map50:.4f}")
print(f"mAP50-95:  {metrics.box.map:.4f}")

print("\nModel:")
print(MODEL_PATH)

print("=" * 60)