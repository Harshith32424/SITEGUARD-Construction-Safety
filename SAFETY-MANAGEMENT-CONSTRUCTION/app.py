import os
import time
from datetime import datetime
from flask import Flask, render_template, Response, request, jsonify, redirect, url_for, send_file, make_response
from werkzeug.utils import secure_filename
import database
from safety_engine import SafetyMonitorEngine
from hardware_bridge import HardwareBridge

app = Flask(__name__)
app.config['SECRET_KEY'] = 'construction-safety-zero-cost-2026'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB max
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'mp4', 'avi', 'mov'}

engine = SafetyMonitorEngine.get_instance()
hardware = HardwareBridge.get_instance()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# -------------------------------------------------------------
# VIEWS
# -------------------------------------------------------------

@app.route('/')
def index():
    """Main Live Surveillance Dashboard."""
    settings = engine.get_settings()
    hw_status = hardware.get_telemetry()
    return render_template('index.html', settings=settings, hw=hw_status)

@app.route('/upload')
def upload_page():
    """Media Studio: Upload and inspect photos and recorded videos."""
    return render_template('upload.html')

@app.route('/incidents')
def incidents_page():
    """Incident audit log and snapshot gallery."""
    status_filter = request.args.get('status', None)
    all_incidents = database.get_all_incidents(limit=100, status=status_filter)
    return render_template('incidents.html', incidents=all_incidents, current_filter=status_filter)

@app.route('/analytics')
def analytics_page():
    """Compliance trends and safety charts."""
    summary = database.get_analytics_summary()
    return render_template('analytics.html', summary=summary)

@app.route('/settings')
def settings_page():
    """Safety configuration and hardware controls."""
    settings = engine.get_settings()
    hw_status = hardware.get_telemetry()
    return render_template('settings.html', settings=settings, hw=hw_status)

# -------------------------------------------------------------
# VIDEO STREAMING & CAMERA
# -------------------------------------------------------------

@app.route('/video_feed')
def video_feed():
    """MJPEG streaming endpoint for live webcam feed."""
    return Response(
        engine.generate_mjpeg_stream(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/api/camera/start', methods=['POST'])
def start_camera():
    source = request.json.get('source', 0) if request.is_json else 0
    success = engine.start_camera(source)
    return jsonify({"success": success, "source": str(source)})

@app.route('/api/camera/stop', methods=['POST'])
def stop_camera():
    engine.stop_camera()
    return jsonify({"success": True})

# -------------------------------------------------------------
# REST APIS FOR DASHBOARD
# -------------------------------------------------------------

@app.route('/api/stats')
def api_stats():
    """Returns real-time worker count, compliance, and FPS."""
    stats = dict(engine.current_stats)
    stats["hardware"] = hardware.get_telemetry()
    return jsonify(stats)

@app.route('/api/incidents/recent')
def api_recent_incidents():
    """Returns recent incidents for live notification drawer."""
    incidents = database.get_recent_incidents(limit=12)
    return jsonify(incidents)

@app.route('/api/incidents/<int:incident_id>/status', methods=['POST'])
def api_update_incident(incident_id):
    new_status = request.json.get('status', 'Reviewed')
    database.update_incident_status(incident_id, new_status)
    return jsonify({"success": True, "id": incident_id, "status": new_status})

# -------------------------------------------------------------
# HARDWARE APIS (ARDUINO, IR, ULTRASONIC, BUZZER, LCD)
# -------------------------------------------------------------

@app.route('/api/hardware')
def api_hardware_telemetry():
    """Returns real-time hardware status."""
    return jsonify(hardware.get_telemetry())

@app.route('/api/hardware/simulate', methods=['POST'])
def api_hardware_simulate():
    """Simulates hardware events (IR trigger, ultrasonic distance slider, buzzer test)."""
    data = request.json or {}
    event_type = data.get('event')
    value = data.get('value')
    res = hardware.simulate_event(event_type, value)
    return jsonify({"success": True, "telemetry": res})

@app.route('/api/hardware/reconnect', methods=['POST'])
def api_hardware_reconnect():
    port = request.json.get('port') if request.is_json else None
    connected = hardware.connect(port)
    return jsonify({
        "success": connected,
        "mode": hardware.telemetry["hardware_mode"],
        "is_connected": hardware.is_connected
    })

# -------------------------------------------------------------
# SETTINGS & CONFIGURATION APIS
# -------------------------------------------------------------

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'POST':
        data = request.json or {}
        engine.update_settings(
            conf=data.get('conf_threshold'),
            iou=data.get('iou_threshold'),
            required_ppe=data.get('required_ppe'),
            show_boxes=data.get('show_boxes'),
            show_labels=data.get('show_labels'),
            show_hud=data.get('show_hud')
        )
        return jsonify({"success": True, "settings": engine.get_settings()})
    return jsonify(engine.get_settings())

# -------------------------------------------------------------
# MEDIA UPLOAD & INSPECTION
# -------------------------------------------------------------

@app.route('/upload/media', methods=['POST'])
def upload_media():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        input_filename = f"upload_{timestamp}_{filename}"
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
        file.save(input_path)

        ext = filename.rsplit('.', 1)[1].lower()
        if ext in ['jpg', 'jpeg', 'png']:
            output_filename = f"annotated_{input_filename}"
            try:
                out_name, stats = engine.process_static_image(input_path, output_filename)
                return jsonify({
                    "success": True,
                    "type": "image",
                    "original_url": url_for('static', filename=f"uploads/{input_filename}"),
                    "annotated_url": url_for('static', filename=f"uploads/{out_name}"),
                    "stats": stats
                })
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        else:
            # Video file upload
            return jsonify({
                "success": True,
                "type": "video",
                "video_path": input_path,
                "filename": input_filename,
                "message": "Video uploaded successfully. You can stream it in Live Monitor by setting the source."
            })
    return jsonify({"error": "Invalid file format. Allowed: JPG, PNG, MP4, AVI"}), 400

# -------------------------------------------------------------
# AUDIT EXPORT
# -------------------------------------------------------------

@app.route('/export/csv')
def export_csv():
    csv_data = database.export_incidents_to_csv_string()
    response = make_response(csv_data)
    response.headers["Content-Disposition"] = f"attachment; filename=safety_audit_{datetime.now().strftime('%Y%m%d')}.csv"
    response.headers["Content-type"] = "text/csv"
    return response

if __name__ == '__main__':
    print("=" * 70)
    print("CONSTRUCTION SITE SAFETY MONITORING SYSTEM - FLASK WEB PLATFORM")
    print("100% Zero Software Cost | Python, OpenCV, YOLOv8, SQLite, HTML5")
    print("Hardware Gateway: Arduino Uno + IR + Ultrasonic + Buzzer + LCD 16x2")
    print("Server running at: http://127.0.0.1:5000")
    print("=" * 70)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
