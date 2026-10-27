import os
import sys
import numpy as np

print("=" * 60)
print("TESTING CONSTRUCTION SITE SAFETY SYSTEM")
print("=" * 60)

print("\n[1] Testing Database...")
import database
inc_id = database.log_incident("Worker #1 (Test)", "Helmet, Vest", "Gloves", "", 0.92, "HIGH")
print(f"-> Logged test incident #{inc_id}")
recent = database.get_recent_incidents(5)
assert len(recent) > 0, "Recent incidents should not be empty"
print(f"-> Retrieved {len(recent)} recent incidents successfully.")

print("\n[2] Testing Hardware Bridge...")
from hardware_bridge import HardwareBridge
hw = HardwareBridge.get_instance()
telem = hw.get_telemetry()
print("-> Initial Hardware Mode:", telem["hardware_mode"])
hw.simulate_event("distance", 35.0)
telem2 = hw.get_telemetry()
assert telem2["proximity_alert"] is True, "Proximity alert should trigger at 35cm"
print(f"-> Proximity hazard triggered correctly: LCD shows '{telem2['lcd_line1']}' | '{telem2['lcd_line2']}'")
hw.simulate_event("reset")
print("-> Reset gate passed.")

print("\n[3] Testing Safety Engine & Model Loading...")
from safety_engine import SafetyMonitorEngine
engine = SafetyMonitorEngine.get_instance()
print("-> Engine model loaded:", engine.model_path)
dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
ann_frame, stats = engine.process_frame(dummy_frame, is_live=False)
print(f"-> Processed frame successfully: {stats['total_workers']} workers, {stats['safety_rate']}% compliance.")

print("\n[4] Testing Flask Web Server Routes...")
import app
client = app.app.test_client()

r1 = client.get('/')
assert r1.status_code == 200, f"GET / returned {r1.status_code}"
print("-> GET / (Dashboard): 200 OK")

r2 = client.get('/api/stats')
assert r2.status_code == 200, f"GET /api/stats returned {r2.status_code}"
print(f"-> GET /api/stats: 200 OK (safety_rate: {r2.json['safety_rate']}%)")

r3 = client.get('/api/hardware')
assert r3.status_code == 200
print(f"-> GET /api/hardware: 200 OK (mode: {r3.json['hardware_mode']})")

r4 = client.get('/incidents')
assert r4.status_code == 200
print("-> GET /incidents: 200 OK")

r5 = client.get('/analytics')
assert r5.status_code == 200
print("-> GET /analytics: 200 OK")

r6 = client.get('/settings')
assert r6.status_code == 200
print("-> GET /settings: 200 OK")

r7 = client.get('/upload')
assert r7.status_code == 200
print("-> GET /upload: 200 OK")

r8 = client.get('/export/csv')
assert r8.status_code == 200
print(f"-> GET /export/csv: 200 OK ({len(r8.data)} bytes exported)")

print("\n" + "=" * 60)
print("ALL SYSTEM TESTS PASSED SUCCESSFULLY!")
print("=" * 60)
