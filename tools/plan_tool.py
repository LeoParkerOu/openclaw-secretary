#!/usr/bin/env python3
"""
plan_tool.py — 计划管理工具

Usage: python3 plan_tool.py <action> '<args_json>'
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db, db_query, db_exec, ok, err, parse_args, today_str


def list_plans(args: dict):
    status = args.get('status', 'active')
    with get_db() as conn:
        if status == 'all':
            rows = db_query(conn, "SELECT * FROM plans ORDER BY priority, updated_at DESC")
        else:
            rows = db_query(conn,
                "SELECT * FROM plans WHERE status=? ORDER BY priority, updated_at DESC", status)
    ok(rows)


def get_plan_summary(args: dict):
    plan_id = args.get('plan_id')
    if not plan_id:
        return err("plan_id is required")
    today = today_str()
    with get_db() as conn:
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            return err(f"Plan {plan_id} not found")
        plan = dict(plan)
        logs = db_query(conn,
            "SELECT * FROM plan_logs WHERE plan_id=? AND log_date=?", plan_id, today)
        tasks_today = db_query(conn,
            "SELECT * FROM plan_tasks WHERE plan_id=? AND date=? ORDER BY sort_order", plan_id, today)
    ok({"plan": plan, "today_logs": logs, "today_tasks": tasks_today})


def get_plan_detail(args: dict):
    plan_id = args.get('plan_id')
    if not plan_id:
        return err("plan_id is required")
    with get_db() as conn:
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            return err(f"Plan {plan_id} not found")
        plan = dict(plan)
        tasks = db_query(conn,
            "SELECT * FROM plan_tasks WHERE plan_id=? ORDER BY date, sort_order", plan_id)
        logs = db_query(conn,
            "SELECT * FROM plan_logs WHERE plan_id=? ORDER BY log_date DESC", plan_id)
        revisions = db_query(conn,
            "SELECT * FROM plan_revisions WHERE plan_id=? ORDER BY revised_at DESC", plan_id)
    ok({"plan": plan, "tasks": tasks, "logs": logs, "revisions": revisions})


def get_active_with_today(args: dict):
    today = today_str()
    with get_db() as conn:
        plans = db_query(conn,
            "SELECT * FROM plans WHERE status='active' ORDER BY priority, updated_at DESC")
        result = []
        for plan in plans:
            pid = plan['id']
            today_tasks = db_query(conn,
                "SELECT * FROM plan_tasks WHERE plan_id=? AND date=? ORDER BY sort_order", pid, today)
            today_log = db_query(conn,
                "SELECT * FROM plan_logs WHERE plan_id=? AND log_date=?", pid, today)
            result.append({
                "plan": plan,
                "today_tasks": today_tasks,
                "today_log": today_log[0] if today_log else None,
            })
    ok(result)


def create_plan(args: dict):
    title = args.get('title')
    if not title:
        return err("title is required")
    with get_db() as conn:
        plan_id = db_exec(conn,
            """INSERT INTO plans (title, goal, start_date, end_date, granularity, priority, status)
               VALUES (?,?,?,?,?,?,?)""",
            title,
            args.get('goal'),
            args.get('start_date'),
            args.get('end_date'),
            args.get('granularity', 'day'),
            args.get('priority', 2),
            'active',
        )
        # Insert tasks if provided
        tasks = args.get('tasks', [])
        for i, task in enumerate(tasks):
            conn.execute(
                """INSERT INTO plan_tasks (plan_id, date, time_slot, title, status, sort_order)
                   VALUES (?,?,?,?,?,?)""",
                (plan_id, task.get('date'), task.get('time_slot'),
                 task['title'], task.get('status', 'pending'), i)
            )
        conn.commit()
    ok({"plan_id": plan_id, "tasks_created": len(tasks)})


def update_plan(args: dict):
    plan_id = args.get('plan_id')
    if not plan_id:
        return err("plan_id is required")
    fields = {k: v for k, v in args.items() if k not in ('plan_id',)}
    if not fields:
        return err("No fields to update")
    fields['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    set_clause = ', '.join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [plan_id]
    with get_db() as conn:
        # Record revision
        change_summary = "Updated: " + ", ".join(f"{k}={v}" for k, v in args.items() if k != 'plan_id')
        conn.execute(
            "INSERT INTO plan_revisions (plan_id, change_summary, change_reason, revised_by) VALUES (?,?,?,?)",
            (plan_id, change_summary, args.get('reason'), 'user')
        )
        conn.execute(f"UPDATE plans SET {set_clause} WHERE id=?", values)
        conn.commit()
    ok({"plan_id": plan_id})


def add_task(args: dict):
    plan_id = args.get('plan_id')
    title = args.get('title')
    if not plan_id or not title:
        return err("plan_id and title are required")
    with get_db() as conn:
        # Get max sort_order for this plan
        row = conn.execute("SELECT MAX(sort_order) as mx FROM plan_tasks WHERE plan_id=?", (plan_id,)).fetchone()
        sort_order = (row['mx'] or 0) + 1
        task_id = db_exec(conn,
            """INSERT INTO plan_tasks (plan_id, date, time_slot, title, status, note, sort_order)
               VALUES (?,?,?,?,?,?,?)""",
            plan_id, args.get('date'), args.get('time_slot'),
            title, args.get('status', 'pending'), args.get('note'), sort_order
        )
    ok({"task_id": task_id})


def update_task(args: dict):
    task_id = args.get('task_id')
    if not task_id:
        return err("task_id is required")
    fields = {k: v for k, v in args.items() if k != 'task_id'}
    if not fields:
        return err("No fields to update")
    set_clause = ', '.join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [task_id]
    with get_db() as conn:
        conn.execute(f"UPDATE plan_tasks SET {set_clause} WHERE id=?", values)
        conn.commit()
        # Get plan_id for progress recalc
        task = conn.execute("SELECT plan_id FROM plan_tasks WHERE id=?", (task_id,)).fetchone()
    if task:
        _recalc_progress_internal(task['plan_id'])
    ok({"task_id": task_id})


def delete_task(args: dict):
    task_id = args.get('task_id')
    if not task_id:
        return err("task_id is required")
    with get_db() as conn:
        task = conn.execute("SELECT plan_id FROM plan_tasks WHERE id=?", (task_id,)).fetchone()
        plan_id = task['plan_id'] if task else None
        conn.execute("DELETE FROM plan_tasks WHERE id=?", (task_id,))
        conn.commit()
    if plan_id:
        _recalc_progress_internal(plan_id)
    ok({"deleted_task_id": task_id})


def write_log(args: dict):
    plan_id = args.get('plan_id')
    log_date = args.get('log_date', today_str())
    if not plan_id:
        return err("plan_id is required")
    with get_db() as conn:
        # Upsert log
        existing = conn.execute(
            "SELECT id FROM plan_logs WHERE plan_id=? AND log_date=?", (plan_id, log_date)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE plan_logs SET completed=?, not_done=?, reason=?, ai_note=?
                   WHERE plan_id=? AND log_date=?""",
                (args.get('completed'), args.get('not_done'), args.get('reason'),
                 args.get('ai_note'), plan_id, log_date)
            )
        else:
            conn.execute(
                """INSERT INTO plan_logs (plan_id, log_date, completed, not_done, reason, ai_note)
                   VALUES (?,?,?,?,?,?)""",
                (plan_id, log_date, args.get('completed'), args.get('not_done'),
                 args.get('reason'), args.get('ai_note'))
            )
        conn.commit()
    ok({"plan_id": plan_id, "log_date": log_date})


def archive_plan(args: dict):
    plan_id = args.get('plan_id')
    if not plan_id:
        return err("plan_id is required")
    with get_db() as conn:
        conn.execute(
            "UPDATE plans SET status='archived', updated_at=datetime('now') WHERE id=?",
            (plan_id,)
        )
        conn.execute(
            "INSERT INTO plan_revisions (plan_id, change_summary, revised_by) VALUES (?,?,?)",
            (plan_id, "Plan archived", 'user')
        )
        conn.commit()
    ok({"plan_id": plan_id, "status": "archived"})


def delete_plan(args: dict):
    plan_id = args.get('plan_id')
    if not plan_id:
        return err("plan_id is required")
    with get_db() as conn:
        conn.execute(
            "UPDATE plans SET status='deleted', updated_at=datetime('now') WHERE id=?",
            (plan_id,)
        )
        conn.execute(
            "INSERT INTO plan_revisions (plan_id, change_summary, revised_by) VALUES (?,?,?)",
            (plan_id, "Plan deleted (soft delete)", 'user')
        )
        conn.commit()
    ok({"plan_id": plan_id, "status": "deleted"})


def _recalc_progress_internal(plan_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done "
            "FROM plan_tasks WHERE plan_id=?", (plan_id,)
        ).fetchone()
        total = row['total'] or 0
        done = row['done'] or 0
        pct = int(done * 100 / total) if total > 0 else 0
        conn.execute(
            "UPDATE plans SET progress_pct=?, updated_at=datetime('now') WHERE id=?",
            (pct, plan_id)
        )
        conn.commit()
    return pct


def recalc_progress(args: dict):
    plan_id = args.get('plan_id')
    if not plan_id:
        return err("plan_id is required")
    pct = _recalc_progress_internal(plan_id)
    ok({"plan_id": plan_id, "progress_pct": pct})


def main():
    action, args = parse_args()
    dispatch = {
        'list_plans': list_plans,
        'get_plan_summary': get_plan_summary,
        'get_plan_detail': get_plan_detail,
        'get_active_with_today': get_active_with_today,
        'create_plan': create_plan,
        'update_plan': update_plan,
        'add_task': add_task,
        'update_task': update_task,
        'delete_task': delete_task,
        'write_log': write_log,
        'archive_plan': archive_plan,
        'delete_plan': delete_plan,
        'recalc_progress': recalc_progress,
    }
    fn = dispatch.get(action)
    if not fn:
        err(f"Unknown action: {action}. Available: {list(dispatch.keys())}")
        sys.exit(1)
    fn(args)


if __name__ == '__main__':
    main()
