#!/usr/bin/env python3
"""
event_queue_tool.py — 离线事件缓存管理工具

Usage: python3 event_queue_tool.py <action> '<args_json>'

Called by gateway_start hook to detect and report offline events.
"""
import sys
import os
import json
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db, db_query, db_exec, ok, err, parse_args, load_config


def _send_to_primary_platform(message: str):
    """Send message to user's primary platform via openclaw."""
    try:
        subprocess.run(
            ["openclaw", "message", "send", "--message", message],
            capture_output=True, text=True
        )
    except FileNotFoundError:
        # Dev mode: print to stdout instead
        print(f"[SEND TO PLATFORM] {message}", file=sys.stderr)


def _build_offline_summary(pending_events: list) -> str:
    if not pending_events:
        return ""

    # Determine offline duration
    earliest = pending_events[0]['scheduled_at']
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    count = len(pending_events)

    # Categorize
    high_priority = []
    others = []
    for evt in pending_events:
        payload = {}
        try:
            payload = json.loads(evt.get('payload') or '{}')
        except Exception:
            pass
        evt_type = evt.get('event_type', '')
        context = payload.get('context', '') or evt.get('payload', '')
        if evt_type == 'timer_heavy':
            high_priority.append(f"· {evt['scheduled_at'][:16]} — {context[:80]}")
        else:
            others.append(f"· {evt['scheduled_at'][:16]} — {context[:80]}")

    lines = [
        f"您好，我在您离线期间（{earliest[:16]} 至 {now}）积压了 {count} 件事项：",
        "",
    ]
    if high_priority:
        lines.append("⚠ 重要：")
        lines.extend(high_priority[:5])
        lines.append("")
    if others:
        lines.append("📋 其余事项：")
        lines.extend(others[:5])
        lines.append("")

    if count > 10:
        lines.append(f"（还有 {count - 10} 件事项未列出）")

    lines.append("建议优先处理：最近的重型提醒任务。")
    lines.append("如需逐项处理，请回复「处理积压事项」。")

    return "\n".join(lines)


def check(args: dict):
    with get_db() as conn:
        pending = db_query(conn,
            "SELECT * FROM event_queue WHERE status='pending' ORDER BY scheduled_at"
        )
        if not pending:
            ok({"pending_count": 0})
            return

        summary = _build_offline_summary(pending)
        _send_to_primary_platform(summary)

        conn.execute(
            "UPDATE event_queue SET status='processed' WHERE status='pending'"
        )
        conn.commit()

    ok({"pending_count": len(pending), "summary_sent": True})


def push(args: dict):
    event_type = args.get('event_type')
    scheduled_at = args.get('scheduled_at')
    if not event_type or not scheduled_at:
        return err("event_type and scheduled_at are required")

    payload = args.get('payload', '{}')
    if isinstance(payload, dict):
        payload = json.dumps(payload, ensure_ascii=False)

    with get_db() as conn:
        event_id = db_exec(conn,
            """INSERT INTO event_queue (event_type, timer_id, scheduled_at, payload, status)
               VALUES (?,?,?,?,?)""",
            event_type, args.get('timer_id'), scheduled_at, payload, 'pending'
        )
    ok({"event_id": event_id})


def main():
    action, args = parse_args()
    dispatch = {
        'check': check,
        'push': push,
    }
    fn = dispatch.get(action)
    if not fn:
        err(f"Unknown action: {action}. Available: {list(dispatch.keys())}")
        sys.exit(1)
    fn(args)


if __name__ == '__main__':
    main()
