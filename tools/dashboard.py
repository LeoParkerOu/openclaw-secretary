#!/usr/bin/env python3
"""
dashboard.py — Secretary Dashboard Flask 服务

Usage: python3 dashboard.py
Starts local web server and opens browser at http://localhost:5299
"""
import os
import sys
import sqlite3
import threading
import webbrowser
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db_path, load_config

try:
    from flask import Flask, jsonify, request, send_file
    from flask_cors import CORS
except ImportError:
    print("Flask not installed. Run: pip3 install flask flask-cors")
    sys.exit(1)

app = Flask(__name__)
CORS(app)

# Heartbeat tracking — browser pings every 10s; server stops after 30s silence
_last_heartbeat = time.time()
_shutdown_event = threading.Event()


def db_query(sql: str, *params) -> list:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


# ─── API endpoints ───────────────────────────────────────────────────────────

@app.route('/api/calendar')
def calendar():
    start = request.args.get('start', datetime.now().strftime('%Y-%m-01'))
    end = request.args.get('end', datetime.now().strftime('%Y-%m-31'))
    rows = db_query(
        "SELECT * FROM calendar_events WHERE date BETWEEN ? AND ? ORDER BY date, time_start",
        start, end
    )
    return jsonify(rows)


@app.route('/api/plans')
def plans():
    rows = db_query("SELECT * FROM plans WHERE status='active' ORDER BY priority, updated_at DESC")
    return jsonify(rows)


@app.route('/api/plan/<int:plan_id>')
def plan_detail(plan_id):
    plan = db_query("SELECT * FROM plans WHERE id=?", plan_id)
    tasks = db_query(
        "SELECT * FROM plan_tasks WHERE plan_id=? ORDER BY date, sort_order", plan_id
    )
    logs = db_query(
        "SELECT * FROM plan_logs WHERE plan_id=? ORDER BY log_date DESC LIMIT 7", plan_id
    )
    if not plan:
        return jsonify({"error": "Plan not found"}), 404
    return jsonify({"plan": plan[0], "tasks": tasks, "logs": logs})


@app.route('/api/today')
def today():
    today_str = datetime.now().strftime('%Y-%m-%d')
    events = db_query(
        "SELECT * FROM calendar_events WHERE date=? ORDER BY time_start", today_str
    )
    tasks = db_query(
        """SELECT pt.*, p.title as plan_title FROM plan_tasks pt
           JOIN plans p ON pt.plan_id = p.id
           WHERE pt.date=? AND p.status='active' ORDER BY pt.sort_order""",
        today_str
    )
    timers = db_query(
        "SELECT * FROM timers WHERE status='active' ORDER BY created_at DESC LIMIT 10"
    )
    return jsonify({"date": today_str, "events": events, "tasks": tasks, "timers": timers})


@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    global _last_heartbeat
    _last_heartbeat = time.time()
    return jsonify({"ok": True})


@app.route('/')
def index():
    html_path = os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'index.html')
    html_path = os.path.abspath(html_path)
    if os.path.exists(html_path):
        return send_file(html_path)
    return "<h1>Dashboard HTML not found</h1>", 404


# ─── Heartbeat watchdog ───────────────────────────────────────────────────────

def _watchdog():
    """Shut down Flask if no heartbeat received for 30 seconds."""
    while not _shutdown_event.is_set():
        time.sleep(5)
        if time.time() - _last_heartbeat > 30:
            print("\n[Secretary] Browser disconnected. Shutting down dashboard.")
            os._exit(0)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    cfg = load_config()
    port = cfg.get('dashboard_port', 5299)

    watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
    watchdog_thread.start()

    url = f'http://localhost:{port}'
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    print(f"[Secretary Dashboard] Starting at {url}")
    print("[Secretary Dashboard] Close the browser tab to stop the server.")
    app.run(port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
