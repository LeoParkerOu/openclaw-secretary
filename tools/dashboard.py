#!/usr/bin/env python3
"""
dashboard.py — Secretary Dashboard Flask 服务

Usage: python3 dashboard.py
启动后自动在浏览器打开 http://localhost:<port>
"""
import sys
import os
import json
import threading
import time
import webbrowser
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db, db_query, load_config, get_data_dir

try:
    from flask import Flask, jsonify, request, send_from_directory
    from flask_cors import CORS
except ImportError:
    print("Flask not installed. Run: pip3 install flask flask-cors")
    sys.exit(1)

# 项目根目录（tools/ 的上级）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIR = os.path.join(BASE_DIR, 'dashboard')

app = Flask(__name__, static_folder=DASHBOARD_DIR)
CORS(app)

# 浏览器心跳监控（30s 无响应自动关闭）
_last_heartbeat = time.time()
_shutdown_timer = None


def _watchdog():
    global _last_heartbeat
    while True:
        time.sleep(5)
        if time.time() - _last_heartbeat > 30:
            print("Browser disconnected. Dashboard shutting down.")
            os._exit(0)


# ─── Static ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(DASHBOARD_DIR, 'index.html')


# ─── API ──────────────────────────────────────────────────────────────────────

@app.route('/api/calendar')
def api_calendar():
    """查询日历事项（支持日期范围、calendar_type 过滤）。"""
    start = request.args.get('start', datetime.now().strftime('%Y-%m-01'))
    end = request.args.get('end', (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d'))
    calendar_type = request.args.get('calendar_type', 'all')

    with get_db() as conn:
        if calendar_type == 'all':
            rows = db_query(conn,
                "SELECT * FROM calendar_events WHERE date >= ? AND date <= ? ORDER BY date, time_start",
                start, end)
        else:
            rows = db_query(conn,
                "SELECT * FROM calendar_events WHERE date >= ? AND date <= ? AND calendar_type=? ORDER BY date, time_start",
                start, end, calendar_type)

    # 为每个事项补充农历日期
    events = _annotate_lunar(rows)
    return jsonify({"ok": True, "events": events, "count": len(events)})


@app.route('/api/goals')
def api_goals():
    """查询目标列表（按 scope 分组）。"""
    status = request.args.get('status', 'active')

    with get_db() as conn:
        if status == 'all':
            rows = db_query(conn, "SELECT * FROM goals ORDER BY priority, scope, created_at")
        else:
            rows = db_query(conn,
                "SELECT * FROM goals WHERE status=? ORDER BY priority, scope, created_at",
                status)

    # 按 scope 分组（支持预设值和自定义 scope）
    known_scopes = ['day', 'week', 'month', 'quarter', 'year', 'long_term']
    grouped = {s: [] for s in known_scopes}
    grouped['other'] = []

    for row in rows:
        s = row.get('scope', 'other')
        if s not in grouped:
            grouped[s] = []  # 自定义 scope 动态创建分组
        grouped[s].append(row)

    return jsonify({"ok": True, "goals": rows, "grouped": grouped, "total": len(rows)})


@app.route('/api/goal/<int:goal_id>')
def api_goal_detail(goal_id):
    """目标详情（含日志和关联事项）。"""
    with get_db() as conn:
        goal = conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        if not goal:
            return jsonify({"ok": False, "error": "Not found"}), 404
        goal = dict(goal)
        logs = db_query(conn,
            "SELECT * FROM goal_logs WHERE goal_id=? ORDER BY log_date DESC LIMIT 10",
            goal_id)
        events = db_query(conn,
            "SELECT * FROM calendar_events WHERE goal_id=? ORDER BY date",
            goal_id)

    goal['logs'] = logs
    goal['linked_events'] = events
    return jsonify({"ok": True, "goal": goal})


@app.route('/api/today')
def api_today():
    """今日概览（事项、特殊日期、近期定时任务）。"""
    today = datetime.now().strftime('%Y-%m-%d')

    with get_db() as conn:
        events = db_query(conn,
            "SELECT * FROM calendar_events WHERE date=? ORDER BY time_start",
            today)
        specials = db_query(conn,
            "SELECT * FROM calendar_events WHERE date=? AND item_type='special_date'",
            today)
        # 近期活跃定时任务（最多 5 条）
        timers = db_query(conn,
            "SELECT * FROM timers WHERE status='active' ORDER BY created_at DESC LIMIT 5")
        # 活跃目标数量
        goal_count = conn.execute(
            "SELECT COUNT(*) FROM goals WHERE status='active'"
        ).fetchone()[0]

    return jsonify({
        "ok": True,
        "date": today,
        "events": _annotate_lunar(events),
        "special_dates": specials,
        "timers": timers,
        "active_goal_count": goal_count,
    })


@app.route('/api/weekly_reflections')
def api_weekly_reflections():
    """周总结历史列表。"""
    limit = int(request.args.get('limit', 20))
    with get_db() as conn:
        rows = db_query(conn,
            "SELECT * FROM weekly_reflections ORDER BY week_number DESC LIMIT ?",
            limit)
    return jsonify({"ok": True, "reflections": rows, "count": len(rows)})


@app.route('/api/heartbeat')
def api_heartbeat():
    """浏览器心跳，保持服务活跃。"""
    global _last_heartbeat
    _last_heartbeat = time.time()
    return jsonify({"ok": True, "ts": _last_heartbeat})


@app.route('/api/lunar_info')
def api_lunar_info():
    """获取指定日期的农历信息。"""
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    info = _get_lunar_info(date_str)
    return jsonify({"ok": True, "date": date_str, "lunar": info})


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_lunar_info(date_str: str) -> dict:
    """获取公历日期对应的农历信息。"""
    try:
        from lunardate import LunarDate
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
        lunar = LunarDate.fromSolarDate(d.year, d.month, d.day)
        month_names = ['正', '二', '三', '四', '五', '六', '七', '八', '九', '十', '冬', '腊']
        day_names = [
            '', '初一', '初二', '初三', '初四', '初五', '初六', '初七', '初八', '初九', '初十',
            '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十',
            '廿一', '廿二', '廿三', '廿四', '廿五', '廿六', '廿七', '廿八', '廿九', '三十'
        ]
        month_str = ('闰' if lunar.isLeapMonth else '') + month_names[lunar.month - 1] + '月'
        day_str = day_names[lunar.day] if lunar.day < len(day_names) else str(lunar.day)
        return {
            "year": lunar.year,
            "month": lunar.month,
            "day": lunar.day,
            "is_leap_month": lunar.isLeapMonth,
            "display": f"{month_str}{day_str}",
        }
    except Exception:
        return {"display": ""}


def _annotate_lunar(events: list) -> list:
    """为事项列表补充农历日期信息。"""
    result = []
    for event in events:
        e = dict(event)
        if e.get('date'):
            e['lunar'] = _get_lunar_info(e['date'])
        result.append(e)
    return result


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    config = load_config()
    port = config.get('dashboard_port', 5299)

    # 启动心跳监控线程
    t = threading.Thread(target=_watchdog, daemon=True)
    t.start()

    # 延迟打开浏览器
    def open_browser():
        time.sleep(1.2)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=open_browser, daemon=True).start()

    print(f"Secretary Dashboard running at http://localhost:{port}")
    print("Close this terminal or press Ctrl+C to stop.")
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
