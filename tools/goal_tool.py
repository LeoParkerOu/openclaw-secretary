#!/usr/bin/env python3
"""
goal_tool.py — 目标/计划管理工具 v1.2

Usage: python3 goal_tool.py <action> '<args_json>'

v1.2 新增：
- search_goals: 关键词模糊搜索目标（解决语义识别问题）
"""
import sys
import os
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db, db_query, db_exec, ok, err, parse_args, today_str, now_str


def search_goals(args: dict):
    """关键词模糊搜索目标（v1.2 新增）。
    支持在 title 和 description 中做 LIKE 搜索，解决语义识别问题。
    AI 收到用户描述的任务名称时，优先用此接口查找，而非依赖字面匹配。
    """
    keyword = args.get('keyword', '')
    status = args.get('status', 'active')

    with get_db() as conn:
        pattern = f"%{keyword}%"
        if status == 'all':
            rows = db_query(conn,
                """SELECT * FROM goals
                   WHERE (title LIKE ? OR description LIKE ?)
                   ORDER BY priority, created_at""",
                pattern, pattern)
        else:
            rows = db_query(conn,
                """SELECT * FROM goals
                   WHERE status=? AND (title LIKE ? OR description LIKE ?)
                   ORDER BY priority, created_at""",
                status, pattern, pattern)
    ok({"goals": rows, "count": len(rows), "keyword": keyword})


def list_goals(args: dict):
    """返回指定范围和状态的目标列表。"""
    status = args.get('status', 'active')
    scope = args.get('scope')

    with get_db() as conn:
        if scope:
            rows = db_query(conn,
                "SELECT * FROM goals WHERE status=? AND scope=? ORDER BY priority, created_at",
                status, scope)
        elif status == 'all':
            rows = db_query(conn,
                "SELECT * FROM goals ORDER BY status, priority, created_at")
        else:
            rows = db_query(conn,
                "SELECT * FROM goals WHERE status=? ORDER BY priority, created_at",
                status)
    ok(rows)


def get_goal(args: dict):
    """返回目标详情，含日志和修订历史。"""
    goal_id = args.get('goal_id')
    if not goal_id:
        return err("goal_id is required")

    with get_db() as conn:
        goal = conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        if not goal:
            return err(f"Goal {goal_id} not found")
        goal = dict(goal)
        logs = db_query(conn,
            "SELECT * FROM goal_logs WHERE goal_id=? ORDER BY log_date DESC LIMIT 10",
            goal_id)
        revisions = db_query(conn,
            "SELECT * FROM goal_revisions WHERE goal_id=? ORDER BY revised_at DESC",
            goal_id)
        events = db_query(conn,
            "SELECT id, date, title, time_start, item_type FROM calendar_events WHERE goal_id=? ORDER BY date",
            goal_id)

    goal['logs'] = logs
    goal['revisions'] = revisions
    goal['linked_events'] = events
    ok(goal)


def get_active_summary(args: dict):
    """返回所有活跃目标摘要，进入秘书模式时调用。"""
    today = today_str()

    with get_db() as conn:
        goals = db_query(conn,
            """SELECT id, title, scope, status, priority, start_date, end_date, progress_pct
               FROM goals WHERE status='active' ORDER BY priority, scope""")
        # 今日关联事项数量
        for goal in goals:
            count = conn.execute(
                "SELECT COUNT(*) FROM calendar_events WHERE goal_id=? AND date=?",
                (goal['id'], today)
            ).fetchone()[0]
            goal['today_items'] = count

    ok({"goals": goals, "total": len(goals), "date": today})


def create_goal(args: dict):
    """创建目标（需用户确认后调用）。
    scope 支持预设值（day/week/month/quarter/year/long_term）或任意自定义字符串。
    """
    title = args.get('title')
    scope = args.get('scope')
    if not title or not scope:
        return err("title and scope are required")

    with get_db() as conn:
        goal_id = db_exec(conn,
            """INSERT INTO goals (title, description, scope, status, priority, start_date, end_date)
               VALUES (?,?,?,?,?,?,?)""",
            title,
            args.get('description', ''),
            scope,
            'active',
            args.get('priority', 2),
            args.get('start_date'),
            args.get('end_date'),
        )
        # 记录创建修订
        db_exec(conn,
            """INSERT INTO goal_revisions (goal_id, change_summary, change_reason, revised_by)
               VALUES (?,?,?,?)""",
            goal_id, f"目标创建：{title}", args.get('description', ''), 'user'
        )
    ok({"goal_id": goal_id, "title": title, "scope": scope})


def update_goal(args: dict):
    """修改目标（需用户确认后调用）。"""
    goal_id = args.get('goal_id')
    if not goal_id:
        return err("goal_id is required")

    fields = {k: v for k, v in args.items() if k not in ('goal_id', 'change_reason')}
    if not fields:
        return err("No fields to update")

    fields['updated_at'] = now_str()
    set_clause = ', '.join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [goal_id]

    with get_db() as conn:
        conn.execute(f"UPDATE goals SET {set_clause} WHERE id=?", values)
        # 记录修订
        db_exec(conn,
            """INSERT INTO goal_revisions (goal_id, change_summary, change_reason, revised_by)
               VALUES (?,?,?,?)""",
            goal_id,
            f"目标更新：{', '.join(fields.keys())}",
            args.get('change_reason', ''),
            'user'
        )
    ok({"goal_id": goal_id, "updated_fields": list(fields.keys())})


def write_log(args: dict):
    """写入进展日志（需用户确认后调用）。"""
    goal_id = args.get('goal_id')
    log_date = args.get('log_date', today_str())
    if not goal_id:
        return err("goal_id is required")

    with get_db() as conn:
        # UPSERT：同一目标同一天只保留最新一条
        existing = conn.execute(
            "SELECT id FROM goal_logs WHERE goal_id=? AND log_date=?",
            (goal_id, log_date)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE goal_logs SET completed=?, not_done=?, reason=?, ai_note=?
                   WHERE goal_id=? AND log_date=?""",
                (args.get('completed'), args.get('not_done'), args.get('reason'),
                 args.get('ai_note'), goal_id, log_date)
            )
            conn.commit()
            log_id = existing[0]
        else:
            log_id = db_exec(conn,
                """INSERT INTO goal_logs (goal_id, log_date, completed, not_done, reason, ai_note)
                   VALUES (?,?,?,?,?,?)""",
                goal_id, log_date,
                args.get('completed'), args.get('not_done'),
                args.get('reason'), args.get('ai_note')
            )
    ok({"log_id": log_id, "goal_id": goal_id, "log_date": log_date})


def archive_goal(args: dict):
    """归档目标（需用户二次确认后调用）。"""
    goal_id = args.get('goal_id')
    if not goal_id:
        return err("goal_id is required")

    with get_db() as conn:
        conn.execute(
            "UPDATE goals SET status='archived', updated_at=? WHERE id=?",
            (now_str(), goal_id)
        )
        db_exec(conn,
            """INSERT INTO goal_revisions (goal_id, change_summary, change_reason, revised_by)
               VALUES (?,?,?,?)""",
            goal_id, "目标归档", args.get('reason', ''), 'user'
        )
    ok({"goal_id": goal_id, "status": "archived"})


def delete_goal(args: dict):
    """软删除目标（需用户二次确认后调用）。"""
    goal_id = args.get('goal_id')
    if not goal_id:
        return err("goal_id is required")

    with get_db() as conn:
        conn.execute(
            "UPDATE goals SET status='deleted', updated_at=? WHERE id=?",
            (now_str(), goal_id)
        )
        conn.commit()
    ok({"goal_id": goal_id, "status": "deleted"})


def recalc_progress(args: dict):
    """重新计算目标完成度（基于关联日历事项）。"""
    goal_id = args.get('goal_id')
    if not goal_id:
        return err("goal_id is required")

    with get_db() as conn:
        goal = conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        if not goal:
            return err(f"Goal {goal_id} not found")

        # 获取关联日志，判断完成比例
        logs = db_query(conn,
            "SELECT * FROM goal_logs WHERE goal_id=? ORDER BY log_date DESC",
            goal_id)

        if not logs:
            ok({"goal_id": goal_id, "progress_pct": dict(goal)['progress_pct'], "note": "no logs"})
            return

        # 简单估算：有 completed 内容的日志 / 总日志
        total = len(logs)
        done = sum(1 for l in logs if l.get('completed') and str(l['completed']).strip())
        pct = min(100, int(done / total * 100)) if total > 0 else 0

        conn.execute(
            "UPDATE goals SET progress_pct=?, updated_at=? WHERE id=?",
            (pct, now_str(), goal_id)
        )
        conn.commit()
    ok({"goal_id": goal_id, "progress_pct": pct, "done_logs": done, "total_logs": total})


def suggest_breakdown(args: dict):
    """建议将目标拆解到具体日期，返回建议方案供用户确认。"""
    goal_id = args.get('goal_id')
    week_start = args.get('week_start')
    week_end = args.get('week_end')
    if not goal_id:
        return err("goal_id is required")

    with get_db() as conn:
        goal = conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        if not goal:
            return err(f"Goal {goal_id} not found")
        goal = dict(goal)

    # 生成建议（AI 应在用户确认后再写入日历）
    # 此工具仅返回结构化建议，AI 负责与用户讨论后调用 calendar_tool add_item 写入
    if not week_start:
        today = datetime.now()
        # 本周一
        week_start = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
        week_end = (today - timedelta(days=today.weekday()) + timedelta(days=6)).strftime('%Y-%m-%d')

    ok({
        "goal": goal,
        "week_start": week_start,
        "week_end": week_end,
        "suggestion": "请 AI 根据目标内容向用户建议每天的具体安排，用户确认后调用 calendar_tool add_item 写入",
        "note": "目标拆解必须经用户确认，不得自动写入"
    })


ACTIONS = {
    'search_goals': search_goals,
    'list_goals': list_goals,
    'get_goal': get_goal,
    'get_active_summary': get_active_summary,
    'create_goal': create_goal,
    'update_goal': update_goal,
    'write_log': write_log,
    'archive_goal': archive_goal,
    'delete_goal': delete_goal,
    'recalc_progress': recalc_progress,
    'suggest_breakdown': suggest_breakdown,
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
