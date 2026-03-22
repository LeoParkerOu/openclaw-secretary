#!/usr/bin/env python3
"""
reflection_tool.py — 每日总结 & 周总结管理工具

每日总结：晚间复盘后由 AI 静默写入，最多保留 7 条。
周总结：每周日晚由重型定时器触发，汇总当周每日总结，发给用户讨论后写入。

Usage: python3 reflection_tool.py <action> '<args_json>'
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from _common import (
    get_db, db_query, db_exec, ok, err, parse_args,
    today_str, now_str, get_week_number
)


MAX_DAILY_REFLECTIONS = 7


def write_daily(args: dict):
    """
    写入每日总结（复盘结束后 AI 自动调用，用户无感知）。
    超过 7 条时删除最旧的。
    """
    date = args.get('date', today_str())
    if date == 'today':
        date = today_str()

    week_number = get_week_number(date)

    with get_db() as conn:
        # UPSERT：同一日期只保留最新版本
        existing = conn.execute(
            "SELECT id FROM daily_reflections WHERE reflection_date=?", (date,)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE daily_reflections SET
                   execution_pattern=?, goal_health=?, user_state=?,
                   planning_quality=?, raw_summary=?, week_number=?
                   WHERE reflection_date=?""",
                (
                    args.get('execution_pattern'),
                    args.get('goal_health'),
                    args.get('user_state'),
                    args.get('planning_quality'),
                    args.get('raw_summary'),
                    week_number,
                    date,
                )
            )
            conn.commit()
            reflection_id = existing[0]
        else:
            reflection_id = db_exec(conn,
                """INSERT INTO daily_reflections
                   (reflection_date, execution_pattern, goal_health, user_state,
                    planning_quality, raw_summary, week_number)
                   VALUES (?,?,?,?,?,?,?)""",
                date,
                args.get('execution_pattern'),
                args.get('goal_health'),
                args.get('user_state'),
                args.get('planning_quality'),
                args.get('raw_summary'),
                week_number,
            )

        # 保持最多 7 条每日总结（删除最旧的）
        count = conn.execute("SELECT COUNT(*) FROM daily_reflections").fetchone()[0]
        if count > MAX_DAILY_REFLECTIONS:
            conn.execute(
                """DELETE FROM daily_reflections WHERE id IN (
                   SELECT id FROM daily_reflections ORDER BY reflection_date ASC
                   LIMIT ?)""",
                (count - MAX_DAILY_REFLECTIONS,)
            )
            conn.commit()

    ok({"id": reflection_id, "date": date, "week_number": week_number})


def run_weekly_summary(args: dict):
    """
    生成周总结所需数据（读取本周所有每日总结，供 AI 生成内容）。
    AI 读取返回数据后，自行生成周总结文本，再调用 write_weekly 写入。
    写入后本工具会删除对应的每日总结。
    """
    week_number = args.get('week_number', get_week_number())

    with get_db() as conn:
        dailies = db_query(conn,
            "SELECT * FROM daily_reflections WHERE week_number=? ORDER BY reflection_date",
            week_number
        )

    if not dailies:
        return ok({
            "week_number": week_number,
            "dailies": [],
            "note": "本周暂无每日总结，无法生成周总结",
            "instruction": "如果本周有复盘但未触发每日总结，请先调用 write_daily 补录"
        })

    # 计算周起止日期
    year, week = week_number.split('-')
    week_start_date = datetime.strptime(f"{year}-W{week}-1", "%Y-W%W-%w")
    week_end_date = week_start_date + timedelta(days=6)

    ok({
        "week_number": week_number,
        "week_start": week_start_date.strftime('%Y-%m-%d'),
        "week_end": week_end_date.strftime('%Y-%m-%d'),
        "dailies": dailies,
        "count": len(dailies),
        "instruction": (
            "请 AI 根据以上每日总结生成本周总结，然后调用 write_weekly 写入。"
            "写入成功后，每日总结将自动删除。"
        )
    })


def write_weekly(args: dict):
    """
    写入周总结（需用户讨论确认后调用）。
    写入成功后删除对应周的每日总结。
    """
    week_number = args.get('week_number')
    week_start = args.get('week_start')
    week_end = args.get('week_end')
    if not week_number or not week_start or not week_end:
        return err("week_number, week_start, week_end are required")

    with get_db() as conn:
        # UPSERT
        existing = conn.execute(
            "SELECT id FROM weekly_reflections WHERE week_number=?", (week_number,)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE weekly_reflections SET
                   week_start=?, week_end=?, execution_patterns=?, goal_progress=?,
                   new_insights=?, next_week_advice=?, raw_summary=?
                   WHERE week_number=?""",
                (
                    week_start, week_end,
                    args.get('execution_patterns'),
                    args.get('goal_progress'),
                    args.get('new_insights'),
                    args.get('next_week_advice'),
                    args.get('raw_summary'),
                    week_number,
                )
            )
            conn.commit()
            weekly_id = existing[0]
        else:
            weekly_id = db_exec(conn,
                """INSERT INTO weekly_reflections
                   (week_number, week_start, week_end, execution_patterns, goal_progress,
                    new_insights, next_week_advice, raw_summary)
                   VALUES (?,?,?,?,?,?,?,?)""",
                week_number, week_start, week_end,
                args.get('execution_patterns'),
                args.get('goal_progress'),
                args.get('new_insights'),
                args.get('next_week_advice'),
                args.get('raw_summary'),
            )

        # 写入成功后删除本周每日总结
        conn.execute(
            "DELETE FROM daily_reflections WHERE week_number=?", (week_number,)
        )
        conn.commit()

    ok({"id": weekly_id, "week_number": week_number, "dailies_cleared": True})


def update_weekly_feedback(args: dict):
    """记录用户对周总结的反馈（讨论后写入）。"""
    week_number = args.get('week_number')
    feedback = args.get('feedback')
    if not week_number or not feedback:
        return err("week_number and feedback are required")

    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM weekly_reflections WHERE week_number=?", (week_number,)
        ).fetchone()
        if not row:
            return err(f"Weekly reflection for {week_number} not found")
        conn.execute(
            "UPDATE weekly_reflections SET user_feedback=? WHERE week_number=?",
            (feedback, week_number)
        )
        conn.commit()
    ok({"week_number": week_number, "feedback_saved": True})


def get_recent_weekly(args: dict):
    """获取最近 N 条周总结（规划模式时调用）。"""
    count = args.get('count', 4)
    with get_db() as conn:
        rows = db_query(conn,
            "SELECT * FROM weekly_reflections ORDER BY week_number DESC LIMIT ?",
            count
        )
    ok({"reflections": rows, "count": len(rows)})


def get_daily_list(args: dict):
    """获取所有当前保留的每日总结。"""
    with get_db() as conn:
        rows = db_query(conn,
            "SELECT * FROM daily_reflections ORDER BY reflection_date DESC"
        )
    ok({"reflections": rows, "count": len(rows)})


ACTIONS = {
    'write_daily': write_daily,
    'run_weekly_summary': run_weekly_summary,
    'write_weekly': write_weekly,
    'update_weekly_feedback': update_weekly_feedback,
    'get_recent_weekly': get_recent_weekly,
    'get_daily_list': get_daily_list,
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
