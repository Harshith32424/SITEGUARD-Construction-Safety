"""
SITEGUARD V2 — Database Layer
Extends V1 database with user authentication and role management.
Uses a separate DB file (v2_safety.db) to avoid conflicts with V1.
"""
import sqlite3
import os
import csv
import io
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v2_safety.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes all V2 database tables."""
    conn = get_connection()
    c = conn.cursor()

    # Users table (Supervisor + Worker roles)
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'worker',
        full_name TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_login DATETIME,
        is_active INTEGER DEFAULT 1
    )
    """)

    # Incidents table (same structure as V1, separate DB)
    c.execute("""
    CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        worker_label TEXT,
        missing_ppe TEXT,
        detected_ppe TEXT,
        snapshot_path TEXT,
        confidence REAL,
        severity TEXT DEFAULT 'HIGH',
        status TEXT DEFAULT 'Open',
        reviewed_by TEXT
    )
    """)

    # Compliance snapshots
    c.execute("""
    CREATE TABLE IF NOT EXISTS compliance_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        total_workers INTEGER,
        compliant_workers INTEGER,
        violators INTEGER,
        safety_rate REAL
    )
    """)

    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
# USER MANAGEMENT
# ─────────────────────────────────────────────

def create_user(username, password, role='worker', full_name='', email=''):
    """Creates a new user with hashed password. Returns user id or None if exists."""
    conn = get_connection()
    c = conn.cursor()
    try:
        pw_hash = generate_password_hash(password)
        c.execute("""
            INSERT INTO users (username, email, password_hash, role, full_name)
            VALUES (?, ?, ?, ?, ?)
        """, (username.strip().lower(), email.strip(), pw_hash, role, full_name.strip()))
        user_id = c.lastrowid
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        return None  # Username already exists
    finally:
        conn.close()

def get_user_by_username(username):
    """Fetches user by username."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username.strip().lower(),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id):
    """Fetches user by ID."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def verify_password(username, password):
    """Verifies credentials. Returns user dict or None."""
    user = get_user_by_username(username)
    if user and check_password_hash(user['password_hash'], password):
        return user
    return None

def update_last_login(user_id):
    """Updates last_login timestamp."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET last_login = ? WHERE id = ?",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()

def update_user_profile(user_id, full_name, email):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET full_name = ?, email = ? WHERE id = ?",
              (full_name.strip(), email.strip(), user_id))
    conn.commit()
    conn.close()

def update_user_password(user_id, new_password):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET password_hash = ? WHERE id = ?",
              (generate_password_hash(new_password), user_id))
    conn.commit()
    conn.close()

def get_all_workers():
    """Returns all worker accounts (supervisor use only)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, username, full_name, email, role, created_at, last_login, is_active FROM users ORDER BY created_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def toggle_user_active(user_id, active_state):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if active_state else 0, user_id))
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
# INCIDENTS
# ─────────────────────────────────────────────

def log_incident(worker_label, missing_ppe, detected_ppe="", snapshot_path="", confidence=0.0, severity="HIGH"):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO incidents (timestamp, worker_label, missing_ppe, detected_ppe, snapshot_path, confidence, severity, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Open')
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        worker_label, missing_ppe, detected_ppe,
        snapshot_path, round(confidence, 2), severity
    ))
    incident_id = c.lastrowid
    conn.commit()
    conn.close()
    return incident_id

def get_recent_incidents(limit=15):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, timestamp, worker_label, missing_ppe, detected_ppe, snapshot_path, confidence, severity, status
        FROM incidents ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_all_incidents(limit=200, status=None):
    conn = get_connection()
    c = conn.cursor()
    if status:
        c.execute("SELECT * FROM incidents WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit))
    else:
        c.execute("SELECT * FROM incidents ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_worker_incidents(worker_label_fragment, limit=100):
    """Fetches incidents where worker_label contains the fragment (for worker self-view)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM incidents WHERE worker_label LIKE ?
        ORDER BY id DESC LIMIT ?
    """, (f"%{worker_label_fragment}%", limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def update_incident_status(incident_id, new_status, reviewed_by=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE incidents SET status = ?, reviewed_by = ? WHERE id = ?",
              (new_status, reviewed_by, incident_id))
    conn.commit()
    conn.close()

def get_analytics_summary():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as count FROM incidents")
    total_incidents = c.fetchone()["count"]

    today_str = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT COUNT(*) as count FROM incidents WHERE timestamp LIKE ?", (f"{today_str}%",))
    today_incidents = c.fetchone()["count"]

    c.execute("SELECT missing_ppe FROM incidents")
    rows = c.fetchall()
    missing_freq = {"Helmet": 0, "Vest": 0, "Gloves": 0, "Goggles": 0, "Boots": 0}
    for r in rows:
        text = r["missing_ppe"] or ""
        for item in missing_freq:
            if item.lower() in text.lower():
                missing_freq[item] += 1

    hourly_counts = {f"{h:02d}:00": 0 for h in range(8, 20)}
    c.execute("""
        SELECT strftime('%H:00', timestamp) as hour_slot, COUNT(*) as count
        FROM incidents WHERE timestamp LIKE ? GROUP BY hour_slot
    """, (f"{today_str}%",))
    for r in c.fetchall():
        slot = r["hour_slot"]
        if slot in hourly_counts:
            hourly_counts[slot] = r["count"]

    c.execute("""
        SELECT timestamp, total_workers, compliant_workers, violators, safety_rate
        FROM compliance_snapshots ORDER BY id DESC LIMIT 20
    """)
    trend_rows = [dict(r) for r in c.fetchall()]
    trend_rows.reverse()
    conn.close()

    return {
        "total_incidents": total_incidents,
        "today_incidents": today_incidents,
        "missing_freq": missing_freq,
        "hourly_distribution": hourly_counts,
        "compliance_trend": trend_rows
    }

def log_compliance_snapshot(total_workers, compliant_workers, violators, safety_rate):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO compliance_snapshots (timestamp, total_workers, compliant_workers, violators, safety_rate)
        VALUES (?, ?, ?, ?, ?)
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total_workers, compliant_workers, violators, round(safety_rate, 1)))
    conn.commit()
    conn.close()

def export_incidents_to_csv_string():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, timestamp, worker_label, missing_ppe, detected_ppe, confidence, severity, status FROM incidents ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Incident ID", "Timestamp", "Worker", "Missing PPE", "Detected PPE", "Confidence", "Severity", "Status"])
    for r in rows:
        writer.writerow([r["id"], r["timestamp"], r["worker_label"], r["missing_ppe"], r["detected_ppe"], r["confidence"], r["severity"], r["status"]])
    return output.getvalue()

# Auto-initialize on import
init_db()
