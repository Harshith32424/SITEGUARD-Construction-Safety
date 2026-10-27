from pathlib import Path
import shutil

# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).parent

DATASET1 = BASE / "Datasets" / "dataset_1"
DATASET2 = BASE / "Datasets" / "dataset_2"

OUTPUT = BASE / "Datasets" / "merged_ppe"

# ============================================================
# FINAL 11 CLASSES
# ============================================================

CLASSES = [
    "Helmet",
    "Gloves",
    "Vest",
    "Boots",
    "Goggles",
    "none",
    "Person",
    "No_Helmet",
    "No_Goggles",
    "No_Gloves",
    "No_Boots"
]

# SH17 -> OUR CLASS IDs
SH17_MAPPING = {
    0: 6,    # Person -> Person
    9: 1,    # Gloves -> Gloves
    10: 0,   # Helmet -> Helmet
    14: 3,   # Shoes -> Boots
    16: 2    # Safety-vest -> Vest
}

# ============================================================
# CREATE OUTPUT
# ============================================================

for split in ["train", "val"]:
    (OUTPUT / split / "images").mkdir(parents=True, exist_ok=True)
    (OUTPUT / split / "labels").mkdir(parents=True, exist_ok=True)

print("=" * 70)
print("CONSTRUCTION SAFETY - DATASET MERGING")
print("=" * 70)

# ============================================================
# DATASET 1
# ============================================================

print("\n[1/2] COPYING DATASET 1...")

for split in ["train", "val"]:

    src_images = DATASET1 / "images" / split
    src_labels = DATASET1 / "labels" / split

    dst_images = OUTPUT / split / "images"
    dst_labels = OUTPUT / split / "labels"

    if not src_images.exists():
        print("ERROR: Missing:", src_images)
        continue

    count = 0

    for image in src_images.iterdir():

        if not image.is_file():
            continue

        label = src_labels / f"{image.stem}.txt"

        new_image = f"dataset1_{image.name}"
        new_label = f"dataset1_{image.stem}.txt"

        shutil.copy2(
            image,
            dst_images / new_image
        )

        if label.exists():
            shutil.copy2(
                label,
                dst_labels / new_label
            )

        count += 1

    print(f"{split}: {count} Dataset-1 images copied")

# ============================================================
# DATASET 2 - SH17
# ============================================================

print("\n[2/2] PROCESSING SH17 DATASET...")

for split in ["train", "val"]:

    split_file = DATASET2 / f"{split}_files.txt"

    if not split_file.exists():
        print("ERROR: Missing:", split_file)
        continue

    image_names = split_file.read_text(
        encoding="utf-8",
        errors="ignore"
    ).splitlines()

    copied = 0
    skipped = 0

    for filename in image_names:

        filename = filename.strip()

        if not filename:
            continue

        image_path = DATASET2 / "images" / filename

        if not image_path.exists():
            skipped += 1
            continue

        # Find corresponding label
        label_path = DATASET2 / "labels" / Path(filename).stem

        if not label_path.exists():
            label_path = DATASET2 / "labels" / f"{Path(filename).stem}.txt"

        if not label_path.exists():
            skipped += 1
            continue

        new_labels = []

        with open(
            label_path,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:

            for line in f:

                parts = line.strip().split()

                if len(parts) != 5:
                    continue

                old_class = int(parts[0])

                # Keep only useful PPE classes
                if old_class not in SH17_MAPPING:
                    continue

                new_class = SH17_MAPPING[old_class]

                new_labels.append(
                    f"{new_class} "
                    f"{parts[1]} "
                    f"{parts[2]} "
                    f"{parts[3]} "
                    f"{parts[4]}"
                )

        # Skip images that contain none of our selected classes
        if not new_labels:
            skipped += 1
            continue

        new_image_name = f"sh17_{image_path.name}"
        new_label_name = f"sh17_{image_path.stem}.txt"

        shutil.copy2(
            image_path,
            OUTPUT / split / "images" / new_image_name
        )

        with open(
            OUTPUT / split / "labels" / new_label_name,
            "w",
            encoding="utf-8"
        ) as f:
            f.write("\n".join(new_labels))

        copied += 1

    print(
        f"{split}: {copied} SH17 images added | "
        f"{skipped} skipped"
    )

# ============================================================
# DATA.YAML
# ============================================================

yaml_text = f"""path: {OUTPUT.as_posix()}
train: train/images
val: val/images

nc: 11

names:
"""

for i, name in enumerate(CLASSES):
    yaml_text += f"  {i}: {name}\n"

with open(
    OUTPUT / "data.yaml",
    "w",
    encoding="utf-8"
) as f:
    f.write(yaml_text)

# ============================================================
# FINISHED
# ============================================================

print("\n" + "=" * 70)
print("MERGING COMPLETED")
print("=" * 70)

print("\nOUTPUT:")
print(OUTPUT)

print("\nDATA YAML:")
print(OUTPUT / "data.yaml")

print("\nFINAL CLASSES:")

for i, name in enumerate(CLASSES):
    print(f"{i}: {name}")

print("\nDONE!")