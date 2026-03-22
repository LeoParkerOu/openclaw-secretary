#!/usr/bin/env python3
"""
calendar_tool.py — 日历读写工具（核心工具）

Usage: python3 calendar_tool.py <action> '<args_json>'

所有日程相关回答必须先调用此工具，禁止凭记忆作答。
"""
import sys
import os
import json
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db, db_query, db_exec, ok, err, parse_args, today_str, now_str


def read_range(args: dict):
    """查询日期范围内所有事项。"""
    start = args.get('start')
    end = args.get('end')
    calendar_type = args.get('calendar_type', 'all')
    if not start or not end:
        return err("start and end are required")

    with get_db() as conn:
        if calendar_type == 'all':
            rows = db_query(conn,
                "SELECT * FROM calendar_events WHERE date >= ? AND date <= ? ORDER BY date, time_start",
                start, end)
        else:
            rows = db_query(conn,
                "SELECT * FROM calendar_events WHERE date >= ? AND date <= ? AND calendar_type=? ORDER BY date, time_start",
                start, end, calendar_type)
    ok(rows)


def read_today(args: dict):
    """查询今日所有事项 + 特殊日期。"""
    today = today_str()
    with get_db() as conn:
        events = db_query(conn,
            "SELECT * FROM calendar_events WHERE date=? ORDER BY time_start",
            today)
        special = db_query(conn,
            "SELECT * FROM calendar_events WHERE date=? AND item_type='special_date'",
            today)
    ok({"date": today, "events": events, "special_dates": special, "count": len(events)})


def add_item(args: dict):
    """写入新事项（需用户确认后调用）。"""
    date = args.get('date')
    title = args.get('title')
    if not date or not title:
        return err("date and title are required")

    item_type = args.get('item_type', 'event')
    with get_db() as conn:
        # event_type 保留向后兼容（v1 schema 该字段为 NOT NULL）
        item_id = db_exec(conn,
            """INSERT INTO calendar_events
               (date, time_start, time_end, title, description, item_type, event_type,
                calendar_type, recurrence, recurrence_rule, source, goal_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            date,
            args.get('time_start'),
            args.get('time_end'),
            title,
            args.get('description'),
            item_type,
            item_type,          # event_type = item_type，向后兼容
            args.get('calendar_type', 'solar'),
            args.get('recurrence'),
            json.dumps(args['recurrence_rule']) if args.get('recurrence_rule') else None,
            args.get('source', 'user'),
            args.get('goal_id'),
        )
    ok({"id": item_id, "date": date, "title": title})


def update_item(args: dict):
    """更新事项字段（需用户确认后调用）。"""
    item_id = args.get('id')
    if not item_id:
        return err("id is required")
    fields = {k: v for k, v in args.items() if k != 'id'}
    if not fields:
        return err("No fields to update")

    # recurrence_rule 序列化
    if 'recurrence_rule' in fields and isinstance(fields['recurrence_rule'], dict):
        fields['recurrence_rule'] = json.dumps(fields['recurrence_rule'])

    fields['updated_at'] = now_str()
    set_clause = ', '.join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [item_id]

    with get_db() as conn:
        conn.execute(f"UPDATE calendar_events SET {set_clause} WHERE id=?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM calendar_events WHERE id=?", (item_id,)).fetchone()
    ok(dict(row) if row else {"id": item_id})


def delete_item(args: dict):
    """删除事项（需用户二次确认后调用）。"""
    item_id = args.get('id')
    if not item_id:
        return err("id is required")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM calendar_events WHERE id=?", (item_id,)).fetchone()
        if not row:
            return err(f"Item {item_id} not found")
        conn.execute("DELETE FROM calendar_events WHERE id=?", (item_id,))
        conn.commit()
    ok({"deleted_id": item_id, "title": dict(row).get('title')})


def add_special_date(args: dict):
    """录入特殊日期（生日、纪念日等，支持农历循环）。"""
    title = args.get('title')
    recurrence = args.get('recurrence', 'yearly')
    if not title:
        return err("title is required")

    # 解析日期
    event_date = args.get('date', today_str())
    calendar_type = 'solar'
    recurrence_rule = args.get('recurrence_rule')

    if recurrence == 'lunar_yearly':
        calendar_type = 'lunar'

    with get_db() as conn:
        item_id = db_exec(conn,
            """INSERT INTO calendar_events
               (date, title, description, item_type, calendar_type, recurrence, recurrence_rule, source)
               VALUES (?,?,?,?,?,?,?,?)""",
            event_date,
            title,
            args.get('description', ''),
            'special_date',
            calendar_type,
            recurrence,
            json.dumps(recurrence_rule) if recurrence_rule else None,
            'user',
        )
    ok({"id": item_id, "title": title, "recurrence": recurrence, "calendar_type": calendar_type})


def import_ics(args: dict):
    """导入 ics 文件（农历/节假日）。"""
    path = args.get('path')
    if not path:
        return err("path is required")
    if not os.path.exists(path):
        return err(f"File not found: {path}")

    try:
        from icalendar import Calendar
    except ImportError:
        return err("icalendar package not installed. Run: pip3 install icalendar")

    imported = 0
    skipped = 0

    with open(path, 'rb') as f:
        cal = Calendar.from_ical(f.read())

    with get_db() as conn:
        for component in cal.walk():
            if component.name != 'VEVENT':
                continue
            try:
                dtstart = component.get('DTSTART').dt
                if hasattr(dtstart, 'date'):
                    event_date = dtstart.date().isoformat()
                else:
                    event_date = dtstart.isoformat()

                summary = str(component.get('SUMMARY', ''))
                if not summary:
                    skipped += 1
                    continue

                # 检查是否已存在（按日期+标题去重）
                existing = conn.execute(
                    "SELECT id FROM calendar_events WHERE date=? AND title=? AND source='ics'",
                    (event_date, summary)
                ).fetchone()
                if existing:
                    skipped += 1
                    continue

                db_exec(conn,
                    """INSERT INTO calendar_events (date, title, item_type, calendar_type, source)
                       VALUES (?,?,?,?,?)""",
                    event_date, summary, 'special_date', 'solar', 'ics'
                )
                imported += 1
            except Exception:
                skipped += 1
                continue

    ok({"imported": imported, "skipped": skipped})


def expand_calendar(args: dict):
    """扩展日历窗口，拉取节假日 API，展开农历周期事件。"""
    to_date = args.get('to_date')
    if not to_date:
        return err("to_date is required")

    from _common import load_config
    config = load_config()
    region = config.get('holiday_region', 'CN')

    results = {"holiday_api": 0, "lunar_expanded": 0, "errors": []}

    # 1. 拉取节假日 API
    try:
        import requests
        today = datetime.now()
        target = datetime.strptime(to_date, '%Y-%m-%d')
        years = list(range(today.year, target.year + 1))

        with get_db() as conn:
            for year in years:
                try:
                    url = f"https://timor.tech/api/holiday/year/{year}/"
                    resp = requests.get(url, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        holidays = data.get('holiday', {})
                        for date_str, info in holidays.items():
                            full_date = f"{year}-{date_str}"
                            existing = conn.execute(
                                "SELECT id FROM calendar_events WHERE date=? AND source='api' AND title=?",
                                (full_date, info.get('name', ''))
                            ).fetchone()
                            if not existing:
                                db_exec(conn,
                                    """INSERT INTO calendar_events
                                       (date, title, item_type, calendar_type, source)
                                       VALUES (?,?,?,?,?)""",
                                    full_date,
                                    info.get('name', '节假日'),
                                    'special_date',
                                    'solar',
                                    'api'
                                )
                                results['holiday_api'] += 1
                except Exception as e:
                    results['errors'].append(f"Holiday API year {year}: {str(e)}")
    except ImportError:
        results['errors'].append("requests package not available")

    # 2. 展开农历周期事件
    try:
        from lunardate import LunarDate
        today = datetime.now()
        target = datetime.strptime(to_date, '%Y-%m-%d')
        years = list(range(today.year, target.year + 1))

        with get_db() as conn:
            lunar_events = db_query(conn,
                "SELECT * FROM calendar_events WHERE recurrence='lunar_yearly' AND calendar_type='lunar'"
            )
            for event in lunar_events:
                rule = json.loads(event['recurrence_rule']) if event.get('recurrence_rule') else {}
                lunar_month = rule.get('lunar_month')
                lunar_day = rule.get('lunar_day')
                if not lunar_month or not lunar_day:
                    continue
                for year in years:
                    try:
                        lunar = LunarDate(year, lunar_month, lunar_day)
                        solar = lunar.toSolarDate()
                        solar_str = solar.strftime('%Y-%m-%d') if hasattr(solar, 'strftime') else str(solar)
                        existing = conn.execute(
                            "SELECT id FROM calendar_events WHERE date=? AND title=? AND source='system'",
                            (solar_str, event['title'])
                        ).fetchone()
                        if not existing:
                            db_exec(conn,
                                """INSERT INTO calendar_events
                                   (date, title, description, item_type, calendar_type, source, goal_id)
                                   VALUES (?,?,?,?,?,?,?)""",
                                solar_str,
                                event['title'],
                                event.get('description', ''),
                                'special_date',
                                'solar',
                                'system',
                                event.get('goal_id'),
                            )
                            results['lunar_expanded'] += 1
                    except Exception:
                        continue
    except ImportError:
        results['errors'].append("lunardate package not available")

    ok(results)


def get_context(args: dict):
    """获取指定日期的完整上下文（事项+特殊日期+关联目标）。"""
    target_date = args.get('date', today_str())

    with get_db() as conn:
        events = db_query(conn,
            "SELECT * FROM calendar_events WHERE date=? ORDER BY time_start",
            target_date)
        # 关联目标信息
        goal_ids = list({e['goal_id'] for e in events if e.get('goal_id')})
        goals = []
        if goal_ids:
            placeholders = ','.join('?' * len(goal_ids))
            goals = db_query(conn,
                f"SELECT id, title, scope, status, progress_pct FROM goals WHERE id IN ({placeholders})",
                *goal_ids)

    ok({
        "date": target_date,
        "events": events,
        "related_goals": goals,
        "total": len(events),
    })


ACTIONS = {
    'read_range': read_range,
    'read_today': read_today,
    'add_item': add_item,
    'update_item': update_item,
    'delete_item': delete_item,
    'add_special_date': add_special_date,
    'import_ics': import_ics,
    'expand_calendar': expand_calendar,
    'get_context': get_context,
    # 向后兼容 v1.0 别名
    'get_today_context': read_today,
    'add_event': add_item,
    'update_event': update_item,
    'delete_event': delete_item,
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
