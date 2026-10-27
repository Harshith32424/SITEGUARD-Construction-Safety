import os
import sys
import subprocess

print("=" * 70)
print("CONSTRUCTION SITE SAFETY MONITORING PLATFORM (AI + HARDWARE IoT)")
print("100% Zero Software Cost | Real-Time YOLOv8 PPE Compliance")
print("Hardware Gateway: Arduino Uno + IR + Ultrasonic + Buzzer + LCD 16x2")
print("=" * 70)

print("\nSystem Components:")
print(" [✓] YOLOv8n PPE Inference Engine (Trained weights loaded)")
print(" [✓] Live Browser Surveillance Stream (Webcam / CCTV / Media)")
print(" [✓] Worker-Level PPE Spatial Matching & Compliance Auditing")
print(" [✓] SQLite Incident Store & CSV Safety Audit Reporting")
print(" [✓] Real-Time Alert Ticker & Browser Audio Siren")
print(" [✓] Hardware Serial Bridge (Arduino Uno Auto-Detect + Simulation Mode)")

print("\nLaunching Web Server on http://127.0.0.1:5000 ...")
print("Press Ctrl+C to stop.\n")

import app
app.app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)