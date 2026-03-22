#!/usr/bin/env python3
"""
event_queue_tool.py — 离线事件缓存工具

OpenClaw 离线期间积压的事件，恢复后合并成一条摘要汇报，不逐条回放。
在 gateway_start 钩子和每次进入秘书模式时调用 check。

Usage: python3 event_queue_tool.py <action> '<args_json>'
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db, db_query, db_exec, ok, err, parse_args, now_str


def check(args: dict):
    """
    检查并处理离线事件队列。
    返回 pending 事件的摘要，AI 应在回复用户前先汇报积压情况。
    """
    with get_db() as conn:
        pending = db_query(conn,
            "SELECT * FROM event_queue WHERE status='pending' ORDER BY scheduled_at",
        )

        if not pending:
            return ok({"has_pending": False, "count": 0})

        # 合并摘要
        count = len(pending)
        types = {}
        for event in pending:
            t = event.get('event_type', 'unknown')
            types[t] = types.get(t, 0) + 1

        # 标记为已处理
        ids = [e['id'] for e in pending]
        placeholders = ','.join('?' * len(ids))
        conn.execute(
            f"UPDATE event_queue SET status='processed' WHERE id IN ({placeholders})",
            ids
        )
        conn.commit()

    summary_parts = []
    for t, n in types.items():
        if t == 'timer_heavy':
            summary_parts.append(f"{n} 个重型定时器触发")
        elif t == 'timer_light':
            summary_parts.append(f"{n} 条轻型提醒")
        else:
            summary_parts.append(f"{n} 个系统事件")

    ok({
        "has_pending": True,
        "count": count,
        "summary": "离线期间积压了：" + "、".join(summary_parts),
        "events": pending,
    })


def enqueue(args: dict):
    """入队离线事件（离线期间由系统调用）。"""
    event_type = args.get('event_type')
    scheduled_at = args.get('scheduled_at', now_str())
    if not event_type:
        return err("event_type is required")

    import json as _json
    payload = args.get('payload')
    if isinstance(payload, dict):
        payload = _json.dumps(payload, ensure_ascii=False)

    with get_db() as conn:
        event_id = db_exec(conn,
            """INSERT INTO event_queue (event_type, timer_id, scheduled_at, payload, status)
               VALUES (?,?,?,?,?)""",
            event_type,
            args.get('timer_id'),
            scheduled_at,
            payload,
            'pending',
        )
    ok({"event_id": event_id, "event_type": event_type})


def clear_processed(args: dict):
    """清理已处理的历史事件（保持队列整洁）。"""
    with get_db() as conn:
        conn.execute("DELETE FROM event_queue WHERE status='processed'")
        conn.commit()
    ok({"cleared": True})


ACTIONS = {
    'check': check,
    'enqueue': enqueue,
    'push': enqueue,  # 向后兼容别名
    'clear_processed': clear_processed,
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
