#!/usr/bin/env python3
"""
timer_tool.py — 定时任务管理工具

Usage: python3 timer_tool.py <action> '<args_json>'

重型定时器：到点唤醒 AI，注入上下文，触发主动对话。
轻型定时器：到点直接发固定消息，零 Token 消耗。
"""
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db, db_query, db_exec, ok, err, parse_args, now_str


def _register_openclaw_cron(name: str, cron_expr: str, message: str) -> bool:
    """注册周期性 cron 任务到 openclaw。"""
    try:
        result = subprocess.run(
            ["openclaw", "cron", "add",
             "--name", name,
             "--cron", cron_expr,
             "--session", "main",
             "--system-event", message],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        # openclaw 未在 PATH 中 — 开发模式，跳过注册
        return True


def _register_openclaw_cron_once(name: str, trigger_at: str, message: str) -> bool:
    """注册单次 cron 任务到 openclaw。"""
    try:
        result = subprocess.run(
            ["openclaw", "cron", "add",
             "--name", name,
             "--at", trigger_at,
             "--session", "main",
             "--system-event", message,
             "--delete-after-run"],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return True


def _remove_openclaw_cron(name: str):
    """从 openclaw 移除 cron 任务。"""
    try:
        subprocess.run(
            ["openclaw", "cron", "rm", "--name", name],
            capture_output=True
        )
    except FileNotFoundError:
        pass


def add_heavy(args: dict):
    """注册周期性重型定时器（到点唤醒 AI）。"""
    name = args.get('name')
    cron_expr = args.get('cron_expr')
    context = args.get('context', '')
    if not name or not cron_expr:
        return err("name and cron_expr are required")

    message = f"[SECRETARY_TIMER] {context}"
    with get_db() as conn:
        timer_id = db_exec(conn,
            """INSERT INTO timers (name, timer_type, trigger_mode, cron_expr, context, platform, status)
               VALUES (?,?,?,?,?,?,?)""",
            name, 'heavy', 'recurring', cron_expr, context, args.get('platform'), 'active'
        )
    success = _register_openclaw_cron(name, cron_expr, message)
    ok({"timer_id": timer_id, "registered": success, "type": "heavy", "cron": cron_expr})


def add_light(args: dict):
    """注册周期性轻型定时器（到点直发消息，零 Token）。"""
    name = args.get('name')
    cron_expr = args.get('cron_expr')
    message = args.get('message', '')
    if not name or not cron_expr:
        return err("name and cron_expr are required")

    with get_db() as conn:
        timer_id = db_exec(conn,
            """INSERT INTO timers (name, timer_type, trigger_mode, cron_expr, message, platform, status)
               VALUES (?,?,?,?,?,?,?)""",
            name, 'light', 'recurring', cron_expr, message, args.get('platform'), 'active'
        )
    success = _register_openclaw_cron(name, cron_expr, message)
    ok({"timer_id": timer_id, "registered": success, "type": "light", "cron": cron_expr})


def add_once_heavy(args: dict):
    """注册单次重型定时器。"""
    name = args.get('name')
    trigger_at = args.get('trigger_at')
    context = args.get('context', '')
    if not name or not trigger_at:
        return err("name and trigger_at are required")

    message = f"[SECRETARY_TIMER] {context}"
    with get_db() as conn:
        timer_id = db_exec(conn,
            """INSERT INTO timers (name, timer_type, trigger_mode, trigger_at, context, platform, status)
               VALUES (?,?,?,?,?,?,?)""",
            name, 'heavy', 'once', trigger_at, context, args.get('platform'), 'active'
        )
    success = _register_openclaw_cron_once(name, trigger_at, message)
    ok({"timer_id": timer_id, "registered": success, "type": "heavy_once", "trigger_at": trigger_at})


def add_once_light(args: dict):
    """注册单次轻型定时器。"""
    name = args.get('name')
    trigger_at = args.get('trigger_at')
    message = args.get('message', '')
    if not name or not trigger_at:
        return err("name and trigger_at are required")

    with get_db() as conn:
        timer_id = db_exec(conn,
            """INSERT INTO timers (name, timer_type, trigger_mode, trigger_at, message, platform, status)
               VALUES (?,?,?,?,?,?,?)""",
            name, 'light', 'once', trigger_at, message, args.get('platform'), 'active'
        )
    success = _register_openclaw_cron_once(name, trigger_at, message)
    ok({"timer_id": timer_id, "registered": success, "type": "light_once", "trigger_at": trigger_at})


def list_timers(args: dict):
    """列出定时任务。"""
    status = args.get('status', 'active')
    with get_db() as conn:
        if status == 'all':
            rows = db_query(conn, "SELECT * FROM timers ORDER BY created_at DESC")
        else:
            rows = db_query(conn, "SELECT * FROM timers WHERE status=? ORDER BY created_at DESC", status)
    ok(rows)


def update_timer(args: dict):
    """修改定时任务（需用户确认后调用）。"""
    timer_id = args.get('timer_id')
    if not timer_id:
        return err("timer_id is required")

    fields = {k: v for k, v in args.items() if k != 'timer_id'}
    if not fields:
        return err("No fields to update")

    set_clause = ', '.join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [timer_id]

    with get_db() as conn:
        conn.execute(f"UPDATE timers SET {set_clause} WHERE id=?", values)
        conn.commit()
        timer = dict(conn.execute("SELECT * FROM timers WHERE id=?", (timer_id,)).fetchone())

    # 若 cron_expr 变化，重新注册
    if 'cron_expr' in fields and timer.get('trigger_mode') == 'recurring':
        context = timer.get('context', '')
        message_text = (
            timer.get('message') or
            (f"[SECRETARY_TIMER] {context}" if timer.get('timer_type') == 'heavy' else '')
        )
        _remove_openclaw_cron(timer['name'])
        _register_openclaw_cron(timer['name'], fields['cron_expr'], message_text)

    ok({"timer_id": timer_id, "updated_fields": list(fields.keys())})


def cancel_timer(args: dict):
    """取消定时任务（需用户确认后调用）。"""
    timer_id = args.get('timer_id')
    if not timer_id:
        return err("timer_id is required")

    with get_db() as conn:
        timer = conn.execute("SELECT * FROM timers WHERE id=?", (timer_id,)).fetchone()
        if not timer:
            return err(f"Timer {timer_id} not found")
        timer = dict(timer)
        conn.execute("UPDATE timers SET status='done' WHERE id=?", (timer_id,))
        conn.commit()

    _remove_openclaw_cron(timer['name'])
    ok({"timer_id": timer_id, "status": "cancelled", "name": timer['name']})


ACTIONS = {
    'add_heavy': add_heavy,
    'add_light': add_light,
    'add_once_heavy': add_once_heavy,
    'add_once_light': add_once_light,
    'list_timers': list_timers,
    'update_timer': update_timer,
    'cancel_timer': cancel_timer,
}


def main():
    action, args = parse_args()
    fn = ACTIONS.get(action)
    if not fn:
        err(f"Unknown action: {action}. Available: {list(ACTIONS.keys())}")
        sys.exit(1)
    fn(args)


if __name__ == '__main__':
    main()
