import time
import json
import threading
import os

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

class HardwareBridge:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self.serial_port = None
        self.port_name = None
        self.baud_rate = 9600
        self.is_connected = False
        self.is_running = False
        self.thread = None
        self.io_lock = threading.RLock()
        
        # State received from Arduino
        self.telemetry = {
            "ir_triggered": False,
            "distance_cm": 120.0,
            "proximity_alert": False,
            "last_seen": None,
            "lcd_line1": "SITE SAFETY GATE",
            "lcd_line2": "SYSTEM READY",
            "buzzer_active": False,
            "gate_status": "READY",  # READY, PASS, DENIED, HAZARD
            "hardware_mode": "SIMULATION"  # "PHYSICAL" or "SIMULATION"
        }
        
        # Thresholds
        self.danger_distance_cm = 50.0  # Alert if distance < 50cm
        
        # Auto-connect attempt
        self.connect()

    def find_arduino_port(self):
        """Scans COM ports for Arduino or serial device."""
        if not SERIAL_AVAILABLE:
            return None
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = p.description.lower()
            if "arduino" in desc or "ch340" in desc or "usb-serial" in desc or "com" in p.device.lower():
                return p.device
        return None

    def connect(self, port=None):
        """Attempts to open serial connection with Arduino."""
        if not SERIAL_AVAILABLE:
            print("[HardwareBridge] pyserial not available. Using Simulation mode.")
            self.telemetry["hardware_mode"] = "SIMULATION"
            return False

        target_port = port or self.find_arduino_port()
        if not target_port:
            print("[HardwareBridge] No physical Arduino detected. Operating in Simulation mode.")
            self.telemetry["hardware_mode"] = "SIMULATION"
            self.is_connected = False
            return False

        try:
            self.disconnect()
            self.serial_port = serial.Serial(target_port, self.baud_rate, timeout=1.0)
            self.port_name = target_port
            self.is_connected = True
            self.telemetry["hardware_mode"] = f"PHYSICAL ({target_port})"
            self.is_running = True
            
            # Start background reader thread
            self.thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.thread.start()
            
            # Send initial greeting
            time.sleep(1.8)  # Wait for Arduino reboot on serial open
            self.send_command("RESET", "SITE SAFETY GATE", "READY")
            print(f"[HardwareBridge] Successfully connected to Arduino on {target_port}")
            return True
        except Exception as e:
            print(f"[HardwareBridge] Failed to connect to {target_port}: {e}")
            self.is_connected = False
            self.telemetry["hardware_mode"] = "SIMULATION"
            return False

    def disconnect(self):
        """Closes serial connection safely."""
        self.is_running = False
        if self.serial_port:
            try:
                self.serial_port.close()
            except Exception:
                pass
            self.serial_port = None
        self.is_connected = False

    def _reader_loop(self):
        """Background thread reading telemetry messages from Arduino."""
        while self.is_running and self.serial_port and self.serial_port.is_open:
            try:
                line = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    self._parse_incoming_line(line)
            except Exception as e:
                print(f"[HardwareBridge] Serial read error: {e}")
                time.sleep(0.5)
            time.sleep(0.02)

    def _parse_incoming_line(self, line):
        """Parses lines like:
        JSON: {"ir":1, "dist":42}
        OR key-value: IR:1,DIST:45.2
        """
        try:
            if line.startswith("{") and line.endswith("}"):
                data = json.loads(line)
                with self.io_lock:
                    if "ir" in data:
                        self.telemetry["ir_triggered"] = bool(data["ir"])
                    if "dist" in data:
                        dist = float(data["dist"])
                        self.telemetry["distance_cm"] = dist
                        self.telemetry["proximity_alert"] = (dist > 0 and dist < self.danger_distance_cm)
                    self.telemetry["last_seen"] = time.time()
            elif "IR:" in line or "DIST:" in line:
                parts = line.split(",")
                with self.io_lock:
                    for p in parts:
                        if ":" in p:
                            k, v = p.split(":", 1)
                            k = k.strip().upper()
                            v = v.strip()
                            if k == "IR":
                                self.telemetry["ir_triggered"] = (v in ["1", "HIGH", "TRIGGERED"])
                            elif k == "DIST":
                                dist = float(v)
                                self.telemetry["distance_cm"] = dist
                                self.telemetry["proximity_alert"] = (dist > 0 and dist < self.danger_distance_cm)
                    self.telemetry["last_seen"] = time.time()
        except Exception:
            pass

    def send_command(self, action, line1, line2, buzzer_pattern=0):
        """
        Sends an actuation command to Arduino.
        action: 'ALLOW', 'DENY', 'HAZARD', 'RESET'
        line1: Max 16 chars for LCD Line 1
        line2: Max 16 chars for LCD Line 2
        buzzer_pattern: 0=OFF, 1=BEEP_SHORT, 2=BEEP_ALARM_3X, 3=BEEP_CONTINUOUS
        """
        line1 = str(line1)[:16]
        line2 = str(line2)[:16]

        with self.io_lock:
            self.telemetry["lcd_line1"] = line1
            self.telemetry["lcd_line2"] = line2
            self.telemetry["gate_status"] = action
            self.telemetry["buzzer_active"] = (buzzer_pattern > 0)

        # Build payload
        payload = f"CMD:{action}|{line1}|{line2}|{buzzer_pattern}\n"

        if self.is_connected and self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.write(payload.encode('utf-8'))
                self.serial_port.flush()
            except Exception as e:
                print(f"[HardwareBridge] Failed to write to Arduino: {e}")

    # High-level actions
    def trigger_access_granted(self, worker_label="Worker"):
        """Worker has all required PPE -> Grant Entry."""
        self.send_command(
            action="PASS",
            line1=f"{worker_label[:9]}: PASS",
            line2="PPE OK - ENTER",
            buzzer_pattern=1  # Short pleasant confirmation beep
        )

    def trigger_access_denied(self, missing_text="HELMET/VEST"):
        """Worker violated safety gear -> Deny Entry and Alarm."""
        short_missing = missing_text.replace(" ", "")[:16]
        self.send_command(
            action="DENIED",
            line1="ENTRY DENIED!",
            line2=f"NO: {short_missing}",
            buzzer_pattern=2  # 3-beep warning alarm
        )

    def trigger_hazard_proximity(self, distance_cm):
        """Worker stepped into heavy machinery danger perimeter."""
        self.send_command(
            action="HAZARD",
            line1="!DANGER ZONE!",
            line2=f"PROX: {int(distance_cm)}cm STOP",
            buzzer_pattern=3  # Continuous hazard buzzer
        )

    def reset_gate(self):
        """Resets LCD to ready state."""
        self.send_command(
            action="READY",
            line1="SITE SAFETY GATE",
            line2="SCANNING PPE...",
            buzzer_pattern=0
        )

    def get_telemetry(self):
        """Returns current hardware state for API & UI."""
        with self.io_lock:
            return dict(self.telemetry)

    def simulate_event(self, event_type, value=None):
        """Allows testing hardware behavior directly from the web interface."""
        with self.io_lock:
            if event_type == "ir_toggle":
                self.telemetry["ir_triggered"] = not self.telemetry["ir_triggered"]
            elif event_type == "distance":
                dist = float(value)
                self.telemetry["distance_cm"] = dist
                self.telemetry["proximity_alert"] = (dist < self.danger_distance_cm)
                if dist < self.danger_distance_cm:
                    self.trigger_hazard_proximity(dist)
                else:
                    self.reset_gate()
            elif event_type == "test_alarm":
                self.trigger_access_denied("HELMET/VEST")
            elif event_type == "test_pass":
                self.trigger_access_granted("Worker #1")
            elif event_type == "reset":
                self.reset_gate()
        return self.get_telemetry()
