import sqlite3
import os
import csv
import io
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "safety_monitoring.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        worker_label TEXT,
        missing_ppe TEXT,
        detected_ppe TEXT,
        snapshot_path TEXT,
        confidence REAL,
        severity TEXT DEFAULT 'HIGH',
        status TEXT DEFAULT 'Open'
    )
    """)
    
    cursor.execute("""
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

def log_incident(worker_label, missing_ppe, detected_ppe="", snapshot_path="", confidence=0.0, severity="HIGH"):
    """Logs a single safety violation incident."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    INSERT INTO incidents (timestamp, worker_label, missing_ppe, detected_ppe, snapshot_path, confidence, severity, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'Open')
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        worker_label,
        missing_ppe,
        detected_ppe,
        snapshot_path,
        round(confidence, 2),
        severity
    ))
    
    incident_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return incident_id

def get_recent_incidents(limit=15):
    """Fetches the most recent incidents for the live alert ticker."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT id, timestamp, worker_label, missing_ppe, detected_ppe, snapshot_path, confidence, severity, status
    FROM incidents
    ORDER BY id DESC
    LIMIT ?
    """, (limit,))
    
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_all_incidents(limit=200, status=None):
    """Fetches incidents with optional status filter."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if status:
        cursor.execute("""
        SELECT * FROM incidents WHERE status = ? ORDER BY id DESC LIMIT ?
        """, (status, limit))
    else:
        cursor.execute("""
        SELECT * FROM incidents ORDER BY id DESC LIMIT ?
        """, (limit,))
        
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def update_incident_status(incident_id, new_status):
    """Updates the status of an incident (e.g. 'Reviewed', 'Dismissed')."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE incidents SET status = ? WHERE id = ?", (new_status, incident_id))
    conn.commit()
    conn.close()

def log_compliance_snapshot(total_workers, compliant_workers, violators, safety_rate):
    """Records a periodic snapshot of safety compliance rate."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO compliance_snapshots (timestamp, total_workers, compliant_workers, violators, safety_rate)
    VALUES (?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_workers,
        compliant_workers,
        violators,
        round(safety_rate, 1)
    ))
    conn.commit()
    conn.close()

def get_analytics_summary():
    """Aggregates analytics for the dashboard and charts."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Total incidents count
    cursor.execute("SELECT COUNT(*) as count FROM incidents")
    total_incidents = cursor.fetchone()["count"]
    
    # 2. Today's incidents count
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COUNT(*) as count FROM incidents WHERE timestamp LIKE ?", (f"{today_str}%",))
    today_incidents = cursor.fetchone()["count"]
    
    # 3. Frequency of missing items
    cursor.execute("SELECT missing_ppe FROM incidents")
    rows = cursor.fetchall()
    
    missing_freq = {
        "Helmet": 0,
        "Vest": 0,
        "Gloves": 0,
        "Goggles": 0,
        "Boots": 0
    }
    for r in rows:
        text = r["missing_ppe"] or ""
        for item in missing_freq:
            if item.lower() in text.lower():
                missing_freq[item] += 1
                
    # 4. Hourly breakdown for today
    hourly_counts = {f"{h:02d}:00": 0 for h in range(8, 20)}  # 8am to 8pm
    cursor.execute("""
    SELECT strftime('%H:00', timestamp) as hour_slot, COUNT(*) as count
    FROM incidents
    WHERE timestamp LIKE ?
    GROUP BY hour_slot
    """, (f"{today_str}%",))
    for r in cursor.fetchall():
        slot = r["hour_slot"]
        if slot in hourly_counts:
            hourly_counts[slot] = r["count"]
            
    # 5. Recent compliance trend
    cursor.execute("""
    SELECT timestamp, total_workers, compliant_workers, violators, safety_rate
    FROM compliance_snapshots
    ORDER BY id DESC
    LIMIT 20
    """)
    trend_rows = [dict(row) for row in cursor.fetchall()]
    trend_rows.reverse()
    
    conn.close()
    
    return {
        "total_incidents": total_incidents,
        "today_incidents": today_incidents,
        "missing_freq": missing_freq,
        "hourly_distribution": hourly_counts,
        "compliance_trend": trend_rows
    }

def export_incidents_to_csv_string():
    """Exports all incidents to a CSV string."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, worker_label, missing_ppe, detected_ppe, confidence, severity, status FROM incidents ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Incident ID", "Timestamp", "Worker", "Missing PPE", "Detected PPE", "Confidence", "Severity", "Status"])
    for r in rows:
        writer.writerow([r["id"], r["timestamp"], r["worker_label"], r["missing_ppe"], r["detected_ppe"], r["confidence"], r["severity"], r["status"]])
        
    return output.getvalue()

# Auto-initialize on import
init_db()
