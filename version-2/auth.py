"""
SITEGUARD V2 — Authentication Module
Flask session-based auth with role-based access control decorators.
"""
import functools
from flask import session, redirect, url_for, flash, request, jsonify
import database_v2 as db

SESSION_TIMEOUT_HOURS = 8

def login_user_session(user):
    """Stores user info in Flask session."""
    session.permanent = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    session['full_name'] = user.get('full_name') or user['username']
    db.update_last_login(user['id'])

def logout_user_session():
    """Clears the session."""
    session.clear()

def get_current_user():
    """Returns current user dict from DB, or None if not logged in."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.get_user_by_id(user_id)

def is_authenticated():
    return 'user_id' in session

def is_supervisor():
    return session.get('role') == 'supervisor'

def is_worker():
    return session.get('role') == 'worker'

# ─────────────────────────────────────────────
# Access Decorators
# ─────────────────────────────────────────────

def login_required(f):
    """Redirects unauthenticated users to login page."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            flash('Please sign in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def supervisor_required(f):
    """Allows only supervisors. Redirects workers to their dashboard."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            flash('Please sign in to continue.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'supervisor':
            flash('Access denied. Supervisor privileges required.', 'danger')
            return redirect(url_for('worker_dashboard'))
        return f(*args, **kwargs)
    return decorated

def worker_required(f):
    """Allows workers AND supervisors (supervisors can preview worker views)."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            flash('Please sign in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def api_supervisor_required(f):
    """Returns JSON 403 for non-supervisor API calls."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            return jsonify({"error": "Authentication required"}), 401
        if session.get('role') != 'supervisor':
            return jsonify({"error": "Supervisor access required"}), 403
        return f(*args, **kwargs)
    return decorated

def api_login_required(f):
    """Returns JSON 401 for unauthenticated API calls."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated
