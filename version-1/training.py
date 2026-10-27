from ultralytics import YOLO
import torch
import os

print("=" * 70)
print("CONSTRUCTION SITE SAFETY MONITORING")
print("MERGED PPE DATASET - 5 EPOCH QUICK TRAINING")
print("=" * 70)

# ============================================================
# GPU CHECK
# ============================================================

if torch.cuda.is_available():
    device = 0
    print("\nGPU detected:")
    print(torch.cuda.get_device_name(0))
    print("CUDA:", torch.version.cuda)
else:
    device = "cpu"
    print("\nWARNING: NVIDIA GPU not detected!")
    print("Training will use CPU.")

# ============================================================
# MERGED DATASET
# ============================================================

DATASET = "Datasets/merged_ppe/data.yaml"

if not os.path.exists(DATASET):
    print("\nERROR: Dataset not found!")
    print(DATASET)
    exit()

print("\nDataset:")
print(DATASET)

# ============================================================
# EXISTING 30-EPOCH MODEL
# ============================================================

MODEL = r"runs\detect\runs\ppe_final_30epochs\weights\best.pt"

if not os.path.exists(MODEL):
    print("\nERROR: Existing best.pt not found!")
    print(MODEL)
    exit()

print("\nLoading existing model:")
print(MODEL)

model = YOLO(MODEL)

# ============================================================
# QUICK 5-EPOCH TRAINING
# ============================================================

print("\nStarting 5-epoch quick training...")
print("Image size: 512")
print("Batch size: 8")

results = model.train(
    data=DATASET,

    # QUICK TRAINING
    epochs=5,

    # Smaller image = faster training
    imgsz=512,

    # RTX 4050
    batch=8,
    device=device,

    # Windows
    workers=0,

    # Training settings
    optimizer="auto",
    patience=5,
    amp=True,

    # Save results
    plots=True,
    save=True,
    val=True,

    # Separate output folder
    project="runs",
    name="ppe_merged_5epochs",
    exist_ok=True,

    verbose=True
)

# ============================================================
# COMPLETED
# ============================================================

print("\n" + "=" * 70)
print("5-EPOCH TRAINING COMPLETED")
print("=" * 70)

print("\nNew model:")
print(
    r"runs\detect\runs\ppe_merged_5epochs\weights\best.pt"
)

print("\nUse this model for quick webcam testing.")

print("=" * 70)