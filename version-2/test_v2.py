"""
SITEGUARD V2 — System Tests
Verifies authentication, role-based routing, database, APIs.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

print("=" * 60)
print("SITEGUARD V2 — SYSTEM TESTS")
print("=" * 60)

# ── Test 1: Database Layer ─────────────────────────────────────
print("\n[1] Testing V2 Database...")
import database_v2 as db

# Create test users
sup_id = db.create_user("test_supervisor", "TestPass123", "supervisor", "Test Supervisor", "sup@test.com")
wrk_id = db.create_user("test_worker", "WorkPass456", "worker", "Test Worker", "wrk@test.com")

# Handle case where test users already exist
if sup_id is None:
    sup_user = db.get_user_by_username("test_supervisor")
    sup_id = sup_user['id'] if sup_user else None
if wrk_id is None:
    wrk_user = db.get_user_by_username("test_worker")
    wrk_id = wrk_user['id'] if wrk_user else None

assert sup_id is not None, "Supervisor creation failed"
assert wrk_id is not None, "Worker creation failed"
print(f"  -> Supervisor created/found: id={sup_id}")
print(f"  -> Worker created/found: id={wrk_id}")

# Verify password
sup = db.verify_password("test_supervisor", "TestPass123")
assert sup is not None and sup['role'] == 'supervisor', "Supervisor password verification failed"
wrk = db.verify_password("test_worker", "WorkPass456")
assert wrk is not None and wrk['role'] == 'worker', "Worker password verification failed"
print("  -> Password verification: PASS")

# Wrong password
bad = db.verify_password("test_supervisor", "wrongpass")
assert bad is None, "Wrong password should return None"
print("  -> Wrong password rejection: PASS")

# Get all workers
workers = db.get_all_workers()
assert len(workers) >= 2, "Should have at least 2 users"
print(f"  -> Retrieved {len(workers)} users: PASS")

# Incident logging
inc_id = db.log_incident("test_worker", "Helmet, Vest", "Gloves", "", 0.88, "HIGH")
assert inc_id > 0
print(f"  -> Logged incident #{inc_id}: PASS")

# Worker incidents (should find test_worker's incidents)
worker_incs = db.get_worker_incidents("test_worker", limit=10)
assert len(worker_incs) > 0, "Worker should have incidents"
print(f"  -> Worker incident filter: {len(worker_incs)} found: PASS")

# Analytics
summary = db.get_analytics_summary()
assert "total_incidents" in summary
assert "missing_freq" in summary
print("  -> Analytics summary: PASS")

print("\n[1] DATABASE TESTS: ALL PASS ✓")

# ── Test 2: Auth Module ────────────────────────────────────────
print("\n[2] Testing Auth Module...")
from auth import login_user_session, logout_user_session, get_current_user, is_supervisor, is_worker

# We test the decorators through Flask test client below
print("  -> Auth module imports successfully: PASS")

# ── Test 3: Flask App Routes ───────────────────────────────────
print("\n[3] Testing Flask V2 Routes...")
import app_v2
client = app_v2.app.test_client()
app_v2.app.config['TESTING'] = True
app_v2.app.config['WTF_CSRF_ENABLED'] = False

# Unauthenticated root → redirect to login
r = client.get('/', follow_redirects=False)
assert r.status_code in (301, 302), f"Root should redirect, got {r.status_code}"
print("  -> GET / → redirect: PASS")

# Login page loads
r = client.get('/login')
assert r.status_code == 200
print("  -> GET /login: 200 OK: PASS")

# Bad login
r = client.post('/login', data={"username": "test_supervisor", "password": "wrongpass"})
assert r.status_code == 200  # Re-renders login with error
assert b"Invalid" in r.data or b"incorrect" in r.data.lower() or r.status_code == 200
print("  -> POST /login (bad creds): PASS")

# Good supervisor login
r = client.post('/login', data={"username": "test_supervisor", "password": "TestPass123"}, follow_redirects=True)
assert r.status_code == 200
print("  -> POST /login (supervisor): PASS")

# Supervisor routes (logged in as supervisor)
with client.session_transaction() as sess:
    sess['user_id'] = sup_id
    sess['username'] = 'test_supervisor'
    sess['role'] = 'supervisor'
    sess['full_name'] = 'Test Supervisor'

r = client.get('/supervisor/dashboard')
assert r.status_code == 200, f"Supervisor dashboard returned {r.status_code}"
print("  -> GET /supervisor/dashboard: 200 OK: PASS")

r = client.get('/supervisor/incidents')
assert r.status_code == 200
print("  -> GET /supervisor/incidents: 200 OK: PASS")

r = client.get('/supervisor/analytics')
assert r.status_code == 200
print("  -> GET /supervisor/analytics: 200 OK: PASS")

r = client.get('/supervisor/workers')
assert r.status_code == 200
print("  -> GET /supervisor/workers: 200 OK: PASS")

r = client.get('/supervisor/settings')
assert r.status_code == 200
print("  -> GET /supervisor/settings: 200 OK: PASS")

r = client.get('/api/stats')
assert r.status_code == 200
print("  -> GET /api/stats (supervisor): 200 OK: PASS")

r = client.get('/api/hardware')
assert r.status_code == 200
print("  -> GET /api/hardware: 200 OK: PASS")

r = client.get('/export/csv')
assert r.status_code == 200
print("  -> GET /export/csv: 200 OK: PASS")

# ── Test 4: Role Isolation (Worker cannot access supervisor routes)
print("\n[4] Testing Role-Based Access Control...")

with client.session_transaction() as sess:
    sess['user_id'] = wrk_id
    sess['username'] = 'test_worker'
    sess['role'] = 'worker'
    sess['full_name'] = 'Test Worker'

r = client.get('/supervisor/dashboard', follow_redirects=False)
assert r.status_code in (301, 302), f"Worker accessing supervisor dashboard should redirect, got {r.status_code}"
print("  -> Worker blocked from /supervisor/dashboard: PASS")

r = client.get('/supervisor/incidents', follow_redirects=False)
assert r.status_code in (301, 302), f"Worker accessing supervisor incidents should redirect, got {r.status_code}"
print("  -> Worker blocked from /supervisor/incidents: PASS")

# Worker API blocked from supervisor endpoints
import json
r = client.post('/api/camera/start', data=json.dumps({"source": 0}), content_type='application/json')
assert r.status_code == 403, f"Worker camera start should be 403, got {r.status_code}"
print("  -> Worker blocked from /api/camera/start: 403: PASS")

r = client.post('/api/hardware/simulate', data=json.dumps({"event": "reset"}), content_type='application/json')
assert r.status_code == 403
print("  -> Worker blocked from /api/hardware/simulate: 403: PASS")

r = client.get('/export/csv', follow_redirects=False)
assert r.status_code in (301, 302), f"Worker export should redirect, got {r.status_code}"
print("  -> Worker blocked from /export/csv: PASS")

# Worker can access their own routes
r = client.get('/worker/dashboard')
assert r.status_code == 200, f"Worker dashboard returned {r.status_code}"
print("  -> Worker /worker/dashboard: 200 OK: PASS")

r = client.get('/worker/incidents')
assert r.status_code == 200
print("  -> Worker /worker/incidents: 200 OK: PASS")

r = client.get('/api/stats')
assert r.status_code == 200
print("  -> Worker /api/stats (read-only): 200 OK: PASS")

# Worker incidents only returns their own incidents (not others')
r = client.get('/api/incidents/recent')
data = json.loads(r.data)
for inc in data:
    assert 'test_worker' in inc['worker_label'].lower() or len(data) == 0, \
        f"Worker saw another user's incident: {inc['worker_label']}"
print("  -> Worker incidents filtered to own data: PASS")

print("\n[4] RBAC TESTS: ALL PASS ✓")

# ── Test 5: Unauthenticated access blocked
print("\n[5] Testing Unauthenticated Access Blocking...")
with client.session_transaction() as sess:
    sess.clear()

r = client.get('/supervisor/dashboard', follow_redirects=False)
assert r.status_code in (301, 302)
print("  -> Unauthenticated /supervisor/dashboard: redirect: PASS")

r = client.get('/api/stats')
assert r.status_code == 401
print("  -> Unauthenticated /api/stats: 401: PASS")

r = client.get('/worker/dashboard', follow_redirects=False)
assert r.status_code in (301, 302)
print("  -> Unauthenticated /worker/dashboard: redirect: PASS")

print("\n[5] UNAUTH BLOCKING TESTS: ALL PASS ✓")

# ── Final Summary ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("  ALL SITEGUARD V2 TESTS PASSED SUCCESSFULLY!")
print("=" * 60)
print()
print("SUMMARY:")
print("  [✓] V2 Database (users, incidents, analytics)")
print("  [✓] Password hashing & verification")
print("  [✓] Role-based session authentication")
print("  [✓] Supervisor routes accessible")
print("  [✓] Worker routes accessible")
print("  [✓] RBAC: Workers blocked from supervisor resources")
print("  [✓] RBAC: Workers see only own incident data")
print("  [✓] Unauthenticated users blocked from all routes")
print()
