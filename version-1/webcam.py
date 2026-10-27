from ultralytics import YOLO
import cv2
import torch
import os
import math

# ============================================================
# CONSTRUCTION SITE SAFETY MONITORING
# PERSON-LEVEL PPE COMPLIANCE
# ============================================================

print("=" * 65)
print("CONSTRUCTION SITE SAFETY MONITORING")
print("=" * 65)

# ============================================================
# 1. MODEL
# ============================================================

model_path = r"runs\detect\runs\ppe_merged_5epochs\weights\best.pt"

if not os.path.exists(model_path):
    print("\nERROR: best.pt not found!")
    print(os.path.abspath(model_path))
    exit()

print("\nLoading trained YOLOv8n model...")
model = YOLO(model_path)
print("Model loaded successfully.")

# ============================================================
# 2. GPU
# ============================================================

if torch.cuda.is_available():
    device = 0
    print("GPU:", torch.cuda.get_device_name(0))
else:
    device = "cpu"
    print("GPU not available. Using CPU.")

# ============================================================
# 3. CLASS NAMES
# ============================================================

# These match your dataset
PERSON = "Person"

PPE_CLASSES = {
    "Helmet",
    "Gloves",
    "Vest",
    "Boots",
    "Goggles"
}

NEGATIVE_CLASSES = {
    "No_Helmet",
    "No_Goggles",
    "No_Gloves",
    "No_Boots"
}

# PPE required for a worker to be considered FOLLOWING
REQUIRED_PPE = [
    "Helmet",
    "Vest",
    "Gloves",
    "Goggles",
    "Boots"
]

# ============================================================
# 4. CAMERA
# ============================================================

print("\nSearching for camera...")

cap = None

for index in [0, 1, 2]:

    print("Trying camera index:", index)

    test_cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)

    if test_cap.isOpened():

        ret, frame = test_cap.read()

        if ret and frame is not None:
            cap = test_cap
            print("Camera found at index:", index)
            break

        test_cap.release()

    else:
        test_cap.release()

if cap is None:
    print("\nERROR: No working camera found.")
    exit()

# Camera resolution
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

print("\nStarting live safety monitoring...")
print("Press Q to stop.")

# ============================================================
# 5. HELPER FUNCTIONS
# ============================================================

def center_of_box(box):
    x1, y1, x2, y2 = box
    return (
        (x1 + x2) / 2,
        (y1 + y2) / 2
    )


def point_inside_box(point, box):
    px, py = point
    x1, y1, x2, y2 = box

    return (
        x1 <= px <= x2
        and
        y1 <= py <= y2
    )


def distance_between(p1, p2):
    return math.sqrt(
        (p1[0] - p2[0]) ** 2 +
        (p1[1] - p2[1]) ** 2
    )


# ============================================================
# 6. LIVE LOOP
# ============================================================

while True:

    ret, frame = cap.read()

    if not ret:
        print("ERROR: Could not read camera.")
        break

    # --------------------------------------------------------
    # YOLO DETECTION
    # --------------------------------------------------------

    results = model.predict(
        source=frame,
        conf=0.30,
        iou=0.45,
        device=device,
        verbose=False
    )

    result = results[0]

    # --------------------------------------------------------
    # STORE DETECTIONS
    # --------------------------------------------------------

    persons = []
    ppe_detections = []

    if result.boxes is not None:

        for box in result.boxes:

            confidence = float(box.conf[0])
            class_id = int(box.cls[0])

            class_name = model.names[class_id]

            coordinates = box.xyxy[0].cpu().numpy()

            x1, y1, x2, y2 = map(int, coordinates)

            detection = {
                "name": class_name,
                "confidence": confidence,
                "box": (x1, y1, x2, y2)
            }

            if class_name == PERSON:

                persons.append(detection)

            elif (
                class_name in PPE_CLASSES
                or
                class_name in NEGATIVE_CLASSES
            ):

                ppe_detections.append(detection)

    # --------------------------------------------------------
    # PERSON SAFETY ANALYSIS
    # --------------------------------------------------------

    following_count = 0
    not_following_count = 0

    person_results = []

    for person_index, person in enumerate(persons):

        person_box = person["box"]

        # PPE belonging to this person
        assigned_ppe = {}

        # Find PPE whose center lies inside this person's box
        for ppe in ppe_detections:

            ppe_center = center_of_box(ppe["box"])

            if point_inside_box(ppe_center, person_box):

                name = ppe["name"]

                # Positive PPE
                if name in PPE_CLASSES:

                    if (
                        name not in assigned_ppe
                        or
                        ppe["confidence"]
                        > assigned_ppe[name]["confidence"]
                    ):

                        assigned_ppe[name] = ppe

                # Negative PPE
                elif name in NEGATIVE_CLASSES:

                    if (
                        name not in assigned_ppe
                        or
                        ppe["confidence"]
                        > assigned_ppe[name]["confidence"]
                    ):

                        assigned_ppe[name] = ppe

        # ----------------------------------------------------
        # CHECK EACH REQUIRED PPE
        # ----------------------------------------------------

        safety_status = {}

        for required in REQUIRED_PPE:

            negative_name = None

            if required == "Helmet":
                negative_name = "No_Helmet"

            elif required == "Gloves":
                negative_name = "No_Gloves"

            elif required == "Goggles":
                negative_name = "No_Goggles"

            elif required == "Boots":
                negative_name = "No_Boots"

            # Positive detection
            positive_detection = assigned_ppe.get(required)

            # Explicit negative detection
            negative_detection = assigned_ppe.get(negative_name)

            if positive_detection is not None:

                # Positive PPE detected
                safety_status[required] = True

            elif negative_detection is not None:

                # Explicitly detected as missing
                safety_status[required] = False

            else:

                # No PPE detected
                safety_status[required] = False

        # ----------------------------------------------------
        # FINAL PERSON STATUS
        # ----------------------------------------------------

        compliant = all(
            safety_status[ppe]
            for ppe in REQUIRED_PPE
        )

        if compliant:

            following_count += 1
            status_text = "FOLLOWING"
            box_color = (0, 255, 0)

        else:

            not_following_count += 1
            status_text = "NOT FOLLOWING"
            box_color = (0, 0, 255)

        person_results.append({
            "box": person_box,
            "status": status_text,
            "color": box_color,
            "ppe": safety_status
        })

    # ========================================================
    # 7. DRAW PERSON BOXES ONLY
    # ========================================================

    for index, person in enumerate(person_results):

        x1, y1, x2, y2 = person["box"]

        color = person["color"]

        # Person bounding box
        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            color,
            4
        )

        # Person number
        person_label = f"PERSON {index + 1}"

        cv2.putText(
            frame,
            person_label,
            (x1, max(30, y1 - 35)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            color,
            2
        )

        # Status
        cv2.putText(
            frame,
            person["status"],
            (x1, max(55, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            color,
            2
        )

        # ----------------------------------------------------
        # PPE STATUS INSIDE PERSON BOX
        # ----------------------------------------------------

        ppe_status = person["ppe"]

        y_text = y1 + 25

        short_names = {
            "Helmet": "Helmet",
            "Vest": "Vest",
            "Gloves": "Gloves",
            "Goggles": "Goggles",
            "Boots": "Boots"
        }

        for ppe_name in REQUIRED_PPE:

            present = ppe_status[ppe_name]

            if present:

                text = short_names[ppe_name] + " OK"
                text_color = (0, 255, 0)

            else:

                text = short_names[ppe_name] + " MISSING"
                text_color = (0, 0, 255)

            cv2.putText(
                frame,
                text,
                (x1 + 5, y_text),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                text_color,
                2
            )

            y_text += 20

    # ========================================================
    # 8. DASHBOARD / COUNTERS
    # ========================================================

    total_persons = len(person_results)

    # Background panel
    cv2.rectangle(
        frame,
        (10, 10),
        (390, 150),
        (20, 20, 20),
        -1
    )

    # Title
    cv2.putText(
        frame,
        "CONSTRUCTION SITE SAFETY",
        (20, 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 255),
        2
    )

    # Person count
    cv2.putText(
        frame,
        f"PERSONS: {total_persons}",
        (20, 68),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2
    )

    # Following
    cv2.putText(
        frame,
        f"FOLLOWING: {following_count}",
        (20, 98),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 0),
        2
    )

    # Not following
    cv2.putText(
        frame,
        f"NOT FOLLOWING: {not_following_count}",
        (20, 128),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 0, 255),
        2
    )

    # ========================================================
    # 9. DISPLAY
    # ========================================================

    cv2.imshow(
        "YOLOv8n - PPE Safety Monitoring",
        frame
    )

    # Q = quit
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break


# ============================================================
# 10. CLOSE
# ============================================================

cap.release()
cv2.destroyAllWindows()

print("\nCamera stopped.")
print("Program finished.")