"""
SITEGUARD V2 — Main Flask Application
Premium Metallic Chic redesign with role-based authentication.
Runs on port 5001. V1 remains untouched on port 5000.
"""
import os
import sys
import time
from datetime import datetime, timedelta
from flask import (Flask, render_template, Response, request, jsonify,
                   redirect, url_for, send_file, make_response, session, flash)
from werkzeug.utils import secure_filename

# Add parent path so safety_engine and hardware_bridge can be imported
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import database_v2 as db
from auth import (login_required, supervisor_required, worker_required,
                  api_supervisor_required, api_login_required,
                  login_user_session, logout_user_session, get_current_user,
                  is_supervisor, is_authenticated)
from safety_engine import SafetyMonitorEngine
from hardware_bridge import HardwareBridge

app = Flask(__name__)
app.secret_key = os.environ.get('V2_SECRET_KEY', 'siteguard-v2-metallic-chic-2026-secret')
app.permanent_session_lifetime = timedelta(hours=8)

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'mp4', 'avi', 'mov'}
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

engine = SafetyMonitorEngine.get_instance()
hardware = HardwareBridge.get_instance()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ─────────────────────────────────────────────────────────────
# Context processor — inject user info into all templates
# ─────────────────────────────────────────────────────────────
@app.context_processor
def inject_user():
    return {
        'current_user': get_current_user(),
        'is_supervisor': is_supervisor(),
        'is_authenticated': is_authenticated()
    }

# ─────────────────────────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────────────────────────

@app.route('/')
def root():
    if is_authenticated():
        if is_supervisor():
            return redirect(url_for('supervisor_dashboard'))
        return redirect(url_for('worker_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_authenticated():
        return redirect(url_for('root'))
    
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            error = 'Please enter both username and password.'
        else:
            user = db.verify_password(username, password)
            if user:
                login_user_session(user)
                next_url = request.args.get('next')
                if next_url:
                    return redirect(next_url)
                if user['role'] == 'supervisor':
                    return redirect(url_for('supervisor_dashboard'))
                return redirect(url_for('worker_dashboard'))
            else:
                error = 'Invalid username or password. Please try again.'
    
    return render_template('v2_login.html', error=error)

@app.route('/logout')
def logout():
    logout_user_session()
    flash('You have been signed out successfully.', 'success')
    return redirect(url_for('login'))

# ─────────────────────────────────────────────────────────────
# SUPERVISOR ROUTES
# ─────────────────────────────────────────────────────────────

@app.route('/supervisor/dashboard')
@supervisor_required
def supervisor_dashboard():
    summary = db.get_analytics_summary()
    hw_status = hardware.get_telemetry()
    stats = dict(engine.current_stats)
    recent_incidents = db.get_recent_incidents(limit=5)
    return render_template('supervisor/dashboard.html',
                           summary=summary, hw=hw_status,
                           stats=stats, recent_incidents=recent_incidents)

@app.route('/supervisor/live')
@supervisor_required
def supervisor_live():
    settings = engine.get_settings()
    hw_status = hardware.get_telemetry()
    return render_template('supervisor/live_monitor.html', settings=settings, hw=hw_status)

@app.route('/supervisor/incidents')
@supervisor_required
def supervisor_incidents():
    status_filter = request.args.get('status', None)
    all_incidents = db.get_all_incidents(limit=200, status=status_filter)
    return render_template('supervisor/incidents.html',
                           incidents=all_incidents, current_filter=status_filter)

@app.route('/supervisor/analytics')
@supervisor_required
def supervisor_analytics():
    summary = db.get_analytics_summary()
    return render_template('supervisor/analytics.html', summary=summary)

@app.route('/supervisor/workers')
@supervisor_required
def supervisor_workers():
    workers = db.get_all_workers()
    return render_template('supervisor/workers.html', workers=workers)

@app.route('/supervisor/settings')
@supervisor_required
def supervisor_settings():
    settings = engine.get_settings()
    hw_status = hardware.get_telemetry()
    return render_template('supervisor/settings.html', settings=settings, hw=hw_status)

# ─────────────────────────────────────────────────────────────
# WORKER ROUTES
# ─────────────────────────────────────────────────────────────

@app.route('/worker/dashboard')
@worker_required
def worker_dashboard():
    user = get_current_user()
    # Workers see only their own incidents
    my_incidents = db.get_worker_incidents(user['username'], limit=10)
    stats = dict(engine.current_stats)
    return render_template('worker/dashboard.html',
                           my_incidents=my_incidents, stats=stats)

@app.route('/worker/incidents')
@worker_required
def worker_incidents():
    user = get_current_user()
    # Workers can only see their own incidents
    my_incidents = db.get_worker_incidents(user['username'], limit=100)
    return render_template('worker/my_incidents.html', incidents=my_incidents)

@app.route('/worker/profile', methods=['GET', 'POST'])
@worker_required
def worker_profile():
    user = get_current_user()
    error = None
    success = None
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_profile':
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            db.update_user_profile(user['id'], full_name, email)
            success = 'Profile updated successfully.'
        elif action == 'change_password':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            if not db.verify_password(user['username'], current_pw):
                error = 'Current password is incorrect.'
            elif len(new_pw) < 6:
                error = 'New password must be at least 6 characters.'
            elif new_pw != confirm_pw:
                error = 'New passwords do not match.'
            else:
                db.update_user_password(user['id'], new_pw)
                success = 'Password changed successfully.'
        user = get_current_user()  # Refresh
    
    return render_template('worker/profile.html', user=user, error=error, success=success)

# ─────────────────────────────────────────────────────────────
# VIDEO STREAMING
# ─────────────────────────────────────────────────────────────

@app.route('/video_feed')
@login_required
def video_feed():
    return Response(engine.generate_mjpeg_stream(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/camera/start', methods=['POST'])
@api_supervisor_required
def start_camera():
    source = request.json.get('source', 0) if request.is_json else 0
    success = engine.start_camera(source)
    return jsonify({"success": success, "source": str(source)})

@app.route('/api/camera/stop', methods=['POST'])
@api_supervisor_required
def stop_camera():
    engine.stop_camera()
    return jsonify({"success": True})

# ─────────────────────────────────────────────────────────────
# STATS & HARDWARE APIs (authenticated)
# ─────────────────────────────────────────────────────────────

@app.route('/api/stats')
@api_login_required
def api_stats():
    stats = dict(engine.current_stats)
    stats["hardware"] = hardware.get_telemetry()
    return jsonify(stats)

@app.route('/api/incidents/recent')
@api_login_required
def api_recent_incidents():
    user = get_current_user()
    if user['role'] == 'supervisor':
        incidents = db.get_recent_incidents(limit=12)
    else:
        incidents = db.get_worker_incidents(user['username'], limit=12)
    return jsonify(incidents)

@app.route('/api/incidents/<int:incident_id>/status', methods=['POST'])
@api_supervisor_required
def api_update_incident(incident_id):
    new_status = request.json.get('status', 'Reviewed')
    user = get_current_user()
    db.update_incident_status(incident_id, new_status, reviewed_by=user['username'])
    return jsonify({"success": True, "id": incident_id, "status": new_status})

@app.route('/api/hardware')
@api_login_required
def api_hardware_telemetry():
    return jsonify(hardware.get_telemetry())

@app.route('/api/hardware/simulate', methods=['POST'])
@api_supervisor_required
def api_hardware_simulate():
    data = request.json or {}
    event_type = data.get('event')
    value = data.get('value')
    res = hardware.simulate_event(event_type, value)
    return jsonify({"success": True, "telemetry": res})

@app.route('/api/hardware/reconnect', methods=['POST'])
@api_supervisor_required
def api_hardware_reconnect():
    port = request.json.get('port') if request.is_json else None
    connected = hardware.connect(port)
    return jsonify({
        "success": connected,
        "mode": hardware.telemetry["hardware_mode"],
        "is_connected": hardware.is_connected
    })

@app.route('/api/settings', methods=['GET', 'POST'])
@api_supervisor_required
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

# ─────────────────────────────────────────────────────────────
# WORKER MANAGEMENT APIs (supervisor only)
# ─────────────────────────────────────────────────────────────

@app.route('/api/workers', methods=['GET'])
@api_supervisor_required
def api_get_workers():
    return jsonify(db.get_all_workers())

@app.route('/api/workers/register', methods=['POST'])
@api_supervisor_required
def api_register_worker():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip()
    role = data.get('role', 'worker')
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if role not in ('supervisor', 'worker'):
        return jsonify({"error": "Role must be supervisor or worker"}), 400
    
    user_id = db.create_user(username, password, role, full_name, email)
    if user_id is None:
        return jsonify({"error": f"Username '{username}' already exists"}), 409
    return jsonify({"success": True, "user_id": user_id})

@app.route('/api/workers/<int:user_id>/toggle', methods=['POST'])
@api_supervisor_required
def api_toggle_worker(user_id):
    data = request.json or {}
    active = data.get('active', True)
    # Prevent supervisor from deactivating themselves
    if user_id == session.get('user_id'):
        return jsonify({"error": "Cannot deactivate your own account"}), 400
    db.toggle_user_active(user_id, active)
    return jsonify({"success": True})

# ─────────────────────────────────────────────────────────────
# MEDIA UPLOAD (supervisor only)
# ─────────────────────────────────────────────────────────────

@app.route('/supervisor/upload', methods=['GET'])
@supervisor_required
def upload_page():
    return render_template('supervisor/upload.html')

@app.route('/upload/media', methods=['POST'])
@api_supervisor_required
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
        input_path = os.path.join(UPLOAD_FOLDER, input_filename)
        file.save(input_path)
        ext = filename.rsplit('.', 1)[1].lower()
        if ext in ['jpg', 'jpeg', 'png']:
            output_filename = f"annotated_{input_filename}"
            try:
                out_name, stats = engine.process_static_image(input_path, output_filename)
                return jsonify({
                    "success": True, "type": "image",
                    "original_url": url_for('static', filename=f"uploads/{input_filename}"),
                    "annotated_url": url_for('static', filename=f"uploads/{out_name}"),
                    "stats": stats
                })
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        else:
            return jsonify({
                "success": True, "type": "video",
                "video_path": input_path, "filename": input_filename,
                "message": "Video uploaded. Set the source in Live Monitor."
            })
    return jsonify({"error": "Invalid file format"}), 400

# ─────────────────────────────────────────────────────────────
# AUDIT EXPORT (supervisor only)
# ─────────────────────────────────────────────────────────────

@app.route('/export/csv')
@supervisor_required
def export_csv():
    csv_data = db.export_incidents_to_csv_string()
    response = make_response(csv_data)
    response.headers["Content-Disposition"] = f"attachment; filename=v2_safety_audit_{datetime.now().strftime('%Y%m%d')}.csv"
    response.headers["Content-type"] = "text/csv"
    return response

# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 70)
    print("SITEGUARD V2 — METALLIC CHIC PREMIUM EDITION")
    print("Role-Based Auth | Supervisor + Worker Dashboards")
    print("Server: http://127.0.0.1:5001")
    print("Default admin: run  python create_supervisor.py  first")
    print("=" * 70)
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
