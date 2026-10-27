import os
import cv2
import time
import math
import threading
import numpy as np
from datetime import datetime
import torch
from ultralytics import YOLO
import database_v2 as database
from hardware_bridge import HardwareBridge

# Directory setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
VIOLATIONS_DIR = os.path.join(STATIC_DIR, "violations")
UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads")
os.makedirs(VIOLATIONS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Helper geometry functions
def center_of_box(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

def point_inside_box(point, box):
    px, py = point
    x1, y1, x2, y2 = box
    return (x1 <= px <= x2) and (y1 <= py <= y2)

class SafetyMonitorEngine:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        # Determine best available weights
        candidate_weights = [
            os.path.join(BASE_DIR, "runs", "detect", "runs", "ppe_final_30epochs", "weights", "best.pt"),
            os.path.join(BASE_DIR, "weights", "best.pt"),
            os.path.join(BASE_DIR, "runs", "detect", "runs", "ppe_merged_5epochs", "weights", "best.pt"),
            os.path.join(BASE_DIR, "yolov8n.pt")
        ]
        
        self.model_path = candidate_weights[-1]
        for w in candidate_weights:
            if os.path.exists(w):
                self.model_path = w
                break
                
        print(f"[SafetyEngine] Loading model from: {self.model_path}")
        self.device = 0 if torch.cuda.is_available() else "cpu"
        print(f"[SafetyEngine] Inference device: {self.device}")
        self.model = YOLO(self.model_path)
        
        # Classes
        self.PERSON = "Person"
        self.PPE_CLASSES = {"Helmet", "Gloves", "Vest", "Boots", "Goggles"}
        self.NEGATIVE_CLASSES = {"No_Helmet", "No_Goggles", "No_Gloves", "No_Boots"}
        
        # Adjustable configuration
        self.conf_threshold = 0.30
        self.iou_threshold = 0.45
        self.required_ppe = ["Helmet", "Vest"]  # Core mandatory gear
        self.optional_ppe = ["Gloves", "Goggles", "Boots"]
        self.show_boxes = True
        self.show_labels = True
        self.show_hud = True
        self.violation_cooldown = 4.0  # seconds between logging incidents
        self.last_violation_time = 0.0
        
        # Live Stats
        self.current_stats = {
            "total_workers": 0,
            "compliant_workers": 0,
            "violators": 0,
            "safety_rate": 100.0,
            "active_source": "None",
            "fps": 0.0,
            "model_name": os.path.basename(self.model_path),
            "is_camera_active": False
        }
        
        # Video Capture State
        self.cap = None
        self.is_running = False
        self.capture_thread = None
        self.frame_lock = threading.Lock()
        self.latest_jpeg = None
        self.current_source = None
        self.last_snapshot_time = 0
        self.last_db_log_time = time.time()
        
        # Hardware Integration
        self.hardware = HardwareBridge.get_instance()
        
    def update_settings(self, conf=None, iou=None, required_ppe=None, show_boxes=None, show_labels=None, show_hud=None):
        if conf is not None:
            self.conf_threshold = max(0.1, min(0.95, float(conf)))
        if iou is not None:
            self.iou_threshold = max(0.1, min(0.95, float(iou)))
        if required_ppe is not None and isinstance(required_ppe, list):
            self.required_ppe = [p for p in required_ppe if p in self.PPE_CLASSES]
        if show_boxes is not None:
            self.show_boxes = bool(show_boxes)
        if show_labels is not None:
            self.show_labels = bool(show_labels)
        if show_hud is not None:
            self.show_hud = bool(show_hud)
            
    def get_settings(self):
        return {
            "conf_threshold": self.conf_threshold,
            "iou_threshold": self.iou_threshold,
            "required_ppe": self.required_ppe,
            "all_ppe": list(self.PPE_CLASSES),
            "show_boxes": self.show_boxes,
            "show_labels": self.show_labels,
            "show_hud": self.show_hud,
            "model_path": self.model_path
        }

    def start_camera(self, source=0):
        """Starts video capture on specified source in background thread."""
        self.stop_camera()
        
        self.current_source = source
        self.is_running = True
        self.capture_thread = threading.Thread(target=self._capture_loop, args=(source,), daemon=True)
        self.capture_thread.start()
        return True

    def stop_camera(self):
        """Stops video capture."""
        self.is_running = False
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1.5)
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        self.current_stats["is_camera_active"] = False

    def _open_capture(self, source):
        # If source is an integer or string integer
        try:
            cam_idx = int(source)
            cap = cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW)
            if cap.isOpened():
                return cap
            # Fallback without CAP_DSHOW
            cap = cv2.VideoCapture(cam_idx)
            if cap.isOpened():
                return cap
        except ValueError:
            # File path or URL
            cap = cv2.VideoCapture(source)
            if cap.isOpened():
                return cap
        return None

    def _capture_loop(self, source):
        print(f"[SafetyEngine] Starting capture loop for source: {source}")
        self.cap = self._open_capture(source)
        
        if not self.cap or not self.cap.isOpened():
            # If camera 0 failed, try other common indices (1, 2)
            if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
                for fallback_idx in [1, 2, 0]:
                    print(f"[SafetyEngine] Trying fallback camera index: {fallback_idx}")
                    self.cap = self._open_capture(fallback_idx)
                    if self.cap and self.cap.isOpened():
                        break

        if not self.cap or not self.cap.isOpened():
            print(f"[SafetyEngine] Failed to open video source: {source}")
            self.current_stats["is_camera_active"] = False
            self.is_running = False
            return

        self.current_stats["is_camera_active"] = True
        self.current_stats["active_source"] = str(source)
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        prev_time = time.time()
        fps_counter = 0
        fps_timer = time.time()
        fps_val = 0.0

        while self.is_running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret or frame is None:
                # If video file, loop back to start
                if isinstance(source, str) and os.path.exists(source):
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    time.sleep(0.05)
                    continue
                else:
                    time.sleep(0.1)
                    continue

            # Run safety inference
            annotated_frame, stats = self.process_frame(frame, is_live=True)
            
            # FPS calculation
            fps_counter += 1
            if time.time() - fps_timer >= 1.0:
                fps_val = round(fps_counter / (time.time() - fps_timer), 1)
                fps_counter = 0
                fps_timer = time.time()
            stats["fps"] = fps_val

            # Encode frame to JPEG
            ret, buffer = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret:
                with self.frame_lock:
                    self.latest_jpeg = buffer.tobytes()
                    self.current_stats.update(stats)
                    self.current_stats["is_camera_active"] = True

            # Periodic snapshot to database (every 10s)
            if time.time() - self.last_db_log_time > 10.0:
                try:
                    database.log_compliance_snapshot(
                        stats["total_workers"],
                        stats["compliant_workers"],
                        stats["violators"],
                        stats["safety_rate"]
                    )
                except Exception as e:
                    print(f"[SafetyEngine] DB Log error: {e}")
                self.last_db_log_time = time.time()

            # Slight delay to prevent CPU overload
            time.sleep(0.01)

        if self.cap:
            self.cap.release()
        self.current_stats["is_camera_active"] = False
        print("[SafetyEngine] Capture loop stopped.")

    def process_frame(self, frame, is_live=False):
        """Core detection & compliance evaluation on a single OpenCV frame."""
        h, w = frame.shape[:2]
        
        # YOLO inference
        results = self.model.predict(
            source=frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False
        )
        
        result = results[0]
        persons = []
        ppe_detections = []

        if result.boxes is not None:
            for box in result.boxes:
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                class_name = self.model.names.get(class_id, "")
                
                coords = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = map(int, coords)
                
                det = {
                    "name": class_name,
                    "confidence": confidence,
                    "box": (x1, y1, x2, y2)
                }
                
                if class_name == self.PERSON:
                    persons.append(det)
                elif class_name in self.PPE_CLASSES or class_name in self.NEGATIVE_CLASSES:
                    ppe_detections.append(det)

        following_count = 0
        not_following_count = 0
        person_results = []
        now = time.time()

        for idx, person in enumerate(persons):
            person_box = person["box"]
            assigned_ppe = {}

            # Associate PPE items whose center lies inside person box
            for ppe in ppe_detections:
                center = center_of_box(ppe["box"])
                if point_inside_box(center, person_box):
                    name = ppe["name"]
                    if name in self.PPE_CLASSES or name in self.NEGATIVE_CLASSES:
                        if name not in assigned_ppe or ppe["confidence"] > assigned_ppe[name]["confidence"]:
                            assigned_ppe[name] = ppe

            # Check required PPE items
            safety_status = {}
            missing_items = []
            detected_items = []

            for req in self.required_ppe:
                neg_name = f"No_{req}"
                has_pos = req in assigned_ppe
                has_neg = neg_name in assigned_ppe

                if has_pos:
                    safety_status[req] = True
                    detected_items.append(req)
                elif has_neg:
                    safety_status[req] = False
                    missing_items.append(req)
                else:
                    safety_status[req] = False
                    missing_items.append(req)

            # Optional PPE checks (informational)
            for opt in self.optional_ppe:
                if opt in assigned_ppe:
                    safety_status[opt] = True
                    detected_items.append(opt)

            compliant = (len(missing_items) == 0)
            worker_label = f"Worker #{idx + 1}"

            if compliant:
                following_count += 1
                status_text = "COMPLIANT"
                color = (46, 204, 113)  # Bright green (BGR)
            else:
                not_following_count += 1
                status_text = "VIOLATION"
                color = (46, 46, 235)  # Bright red (BGR)

                # Log incident if cooldown passed
                if is_live and (now - self.last_violation_time > self.violation_cooldown):
                    self.last_violation_time = now
                    try:
                        # Save violation snapshot
                        snap_filename = f"viol_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx+1}.jpg"
                        snap_path = os.path.join(VIOLATIONS_DIR, snap_filename)
                        
                        # Crop worker region with margin
                        pad_x = int((person_box[2] - person_box[0]) * 0.15)
                        pad_y = int((person_box[3] - person_box[1]) * 0.15)
                        crop_x1 = max(0, person_box[0] - pad_x)
                        crop_y1 = max(0, person_box[1] - pad_y)
                        crop_x2 = min(w, person_box[2] + pad_x)
                        crop_y2 = min(h, person_box[3] + pad_y)
                        
                        cropped = frame[crop_y1:crop_y2, crop_x1:crop_x2]
                        if cropped.size > 0:
                            cv2.imwrite(snap_path, cropped)
                            
                        database.log_incident(
                            worker_label=worker_label,
                            missing_ppe=", ".join(missing_items),
                            detected_ppe=", ".join(detected_items),
                            snapshot_path=f"violations/{snap_filename}",
                            confidence=person["confidence"],
                            severity="HIGH" if ("Helmet" in missing_items or "Vest" in missing_items) else "MEDIUM"
                        )
                    except Exception as err:
                        print(f"[SafetyEngine] Error logging violation: {err}")

            person_results.append({
                "worker_id": idx + 1,
                "label": worker_label,
                "box": person_box,
                "status": status_text,
                "compliant": compliant,
                "color": color,
                "safety_status": safety_status,
                "missing_items": missing_items,
                "confidence": person["confidence"]
            })

        total_workers = len(person_results)
        safety_rate = (following_count / total_workers * 100.0) if total_workers > 0 else 100.0

        # Hardware Actuation (Arduino Gate & Buzzer)
        if is_live:
            hw_telem = self.hardware.get_telemetry()
            if hw_telem.get("proximity_alert", False):
                pass  # Proximity hazard is already sounding continuous buzzer
            elif not_following_count > 0:
                all_missing = []
                for p in person_results:
                    if not p["compliant"]:
                        all_missing.extend(p["missing_items"])
                miss_str = "/".join(sorted(list(set(all_missing)))) or "NO PPE"
                self.hardware.trigger_access_denied(miss_str)
            elif following_count > 0:
                first_worker = person_results[0]["label"]
                self.hardware.trigger_access_granted(first_worker)
            elif total_workers == 0 and not hw_telem.get("ir_triggered", False):
                self.hardware.reset_gate()

        # Annotate frame
        annotated = frame.copy()

        if self.show_boxes:
            for p in person_results:
                x1, y1, x2, y2 = p["box"]
                c = p["color"]
                
                # Bounding box
                cv2.rectangle(annotated, (x1, y1), (x2, y2), c, 3)

                # Header Tag
                tag = f"{p['label']} | {p['status']}"
                (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_DUPLEX, 0.6, 2)
                tag_y = max(th + 10, y1)
                
                # Tag background
                cv2.rectangle(annotated, (x1, tag_y - th - 8), (x1 + tw + 14, tag_y + 4), c, -1)
                cv2.putText(annotated, tag, (x1 + 7, tag_y - 2), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 2)

                if self.show_labels:
                    # Render gear checkmark list inside bounding box
                    row_y = y1 + 30
                    for req in self.required_ppe:
                        is_ok = p["safety_status"].get(req, False)
                        txt = f"{req}: {'OK' if is_ok else 'MISSING'}"
                        txt_color = (46, 204, 113) if is_ok else (46, 46, 235)
                        cv2.putText(annotated, txt, (x1 + 8, row_y), cv2.FONT_HERSHEY_SIMPLEX, 0.52, txt_color, 2)
                        row_y += 22

        if self.show_hud:
            # Stylish Top HUD overlay
            cv2.rectangle(annotated, (15, 15), (380, 140), (20, 24, 33), -1)
            cv2.rectangle(annotated, (15, 15), (380, 140), (60, 70, 90), 2)
            
            # Title
            cv2.putText(annotated, "SITE SAFETY MONITOR", (30, 42), cv2.FONT_HERSHEY_DUPLEX, 0.62, (0, 215, 255), 2)
            
            # Metrics
            cv2.putText(annotated, f"PERSONNEL:  {total_workers}", (30, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (240, 240, 240), 2)
            cv2.putText(annotated, f"COMPLIANT:  {following_count}", (30, 98), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (46, 204, 113), 2)
            cv2.putText(annotated, f"VIOLATIONS: {not_following_count}", (30, 124), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (46, 46, 235), 2)

            # Safety Score Gauge badge
            rate_color = (46, 204, 113) if safety_rate >= 80 else ((0, 165, 255) if safety_rate >= 50 else (46, 46, 235))
            cv2.rectangle(annotated, (255, 60), (365, 128), (30, 36, 50), -1)
            cv2.putText(annotated, "RATE", (285, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
            cv2.putText(annotated, f"{int(safety_rate)}%", (270, 116), cv2.FONT_HERSHEY_DUPLEX, 0.78, rate_color, 2)

        # Proximity Hazard Banner if Ultrasonic distance is dangerously low
        hw_status = self.hardware.get_telemetry()
        if hw_status.get("proximity_alert", False):
            d_val = hw_status.get("distance_cm", 0.0)
            cv2.rectangle(annotated, (0, h - 48), (w, h), (30, 30, 220), -1)
            alert_msg = f"! DANGER: MACHINERY PROXIMITY ALERT ! DIST: {int(d_val)}cm - KEEP BACK"
            cv2.putText(annotated, alert_msg, (max(20, (w // 2) - 290), h - 16), cv2.FONT_HERSHEY_DUPLEX, 0.65, (255, 255, 255), 2)

        stats = {
            "total_workers": total_workers,
            "compliant_workers": following_count,
            "violators": not_following_count,
            "safety_rate": round(safety_rate, 1),
            "persons": person_results
        }

        return annotated, stats

    def get_latest_frame_bytes(self):
        """Returns the latest JPEG frame, or a standby canvas if camera offline."""
        with self.frame_lock:
            if self.latest_jpeg is not None and self.is_running:
                return self.latest_jpeg

        # Standby frame
        canvas = np.zeros((480, 640, 3), dtype=np.uint8)
        canvas[:] = (24, 28, 38)  # Deep industrial dark background
        
        cv2.putText(canvas, "SAFETY SURVEILLANCE STANDBY", (110, 220), cv2.FONT_HERSHEY_DUPLEX, 0.72, (0, 215, 255), 2)
        cv2.putText(canvas, "Click 'START CAMERA' or Upload Media", (140, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (160, 170, 185), 1)
        
        ret, buf = cv2.imencode('.jpg', canvas, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ret else b''

    def generate_mjpeg_stream(self):
        """Yields multipart MJPEG chunks for browser <img> streaming."""
        while True:
            frame_data = self.get_latest_frame_bytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
            time.sleep(0.04)  # ~25 FPS

    def process_static_image(self, input_path, output_filename):
        """Analyzes a user-uploaded image and saves annotated result."""
        frame = cv2.imread(input_path)
        if frame is None:
            raise ValueError("Could not read uploaded image file.")

        annotated_frame, stats = self.process_frame(frame, is_live=False)
        output_path = os.path.join(UPLOADS_DIR, output_filename)
        cv2.imwrite(output_path, annotated_frame)
        
        # Log any violations found in the image
        for p in stats["persons"]:
            if not p["compliant"]:
                database.log_incident(
                    worker_label=f"Uploaded Image ({p['label']})",
                    missing_ppe=", ".join(p["missing_items"]),
                    confidence=p["confidence"],
                    severity="HIGH" if ("Helmet" in p["missing_items"] or "Vest" in p["missing_items"]) else "MEDIUM"
                )

        return output_filename, stats
