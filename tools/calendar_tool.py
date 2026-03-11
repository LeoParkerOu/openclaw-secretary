#!/usr/bin/env python3
"""
calendar_tool.py — 日历工具

Usage: python3 calendar_tool.py <action> '<args_json>'
"""
import sys
import os
import json
import requests
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db, db_query, db_exec, ok, err, parse_args, today_str, load_config


def read_range(args: dict):
    start = args.get('start')
    end = args.get('end')
    if not start or not end:
        return err("start and end are required")
    with get_db() as conn:
        rows = db_query(conn,
            "SELECT * FROM calendar_events WHERE date BETWEEN ? AND ? ORDER BY date, time_start",
            start, end)
    ok(rows)


def add_event(args: dict):
    required = ['date', 'title', 'event_type']
    for f in required:
        if not args.get(f):
            return err(f"Field '{f}' is required")
    with get_db() as conn:
        row_id = db_exec(conn,
            """INSERT INTO calendar_events
               (date, time_start, time_end, title, description, event_type, recurrence,
                recurrence_rule, source, plan_id)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            args['date'],
            args.get('time_start'),
            args.get('time_end'),
            args['title'],
            args.get('description'),
            args['event_type'],
            args.get('recurrence'),
            json.dumps(args['recurrence_rule']) if args.get('recurrence_rule') else None,
            args.get('source', 'user'),
            args.get('plan_id'),
        )
    ok({"id": row_id})


def update_event(args: dict):
    event_id = args.get('id')
    if not event_id:
        return err("id is required")
    fields = {k: v for k, v in args.items() if k != 'id'}
    if not fields:
        return err("No fields to update")
    fields['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    set_clause = ', '.join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [event_id]
    with get_db() as conn:
        conn.execute(f"UPDATE calendar_events SET {set_clause} WHERE id=?", values)
        conn.commit()
    ok({"id": event_id})


def delete_event(args: dict):
    event_id = args.get('id')
    if not event_id:
        return err("id is required")
    with get_db() as conn:
        conn.execute("DELETE FROM calendar_events WHERE id=?", (event_id,))
        conn.commit()
    ok({"deleted_id": event_id})


def add_special_date(args: dict):
    title = args.get('title')
    recurrence = args.get('recurrence')
    recurrence_rule = args.get('recurrence_rule', {})
    if not title:
        return err("title is required")

    # For lunar_yearly, we store the template and let expand_calendar materialize instances
    # For yearly (solar), we store as a recurring event with today's year as base date
    if recurrence == 'lunar_yearly':
        # Store the template; actual solar dates created by expand_calendar
        month = recurrence_rule.get('lunar_month')
        day = recurrence_rule.get('lunar_day')
        if not month or not day:
            return err("lunar_month and lunar_day required for lunar_yearly")
        # Use placeholder date 0001-01-01 for lunar templates
        with get_db() as conn:
            row_id = db_exec(conn,
                """INSERT INTO calendar_events
                   (date, title, event_type, recurrence, recurrence_rule, source)
                   VALUES (?,?,?,?,?,?)""",
                '0001-01-01', title, 'special_date', 'lunar_yearly',
                json.dumps(recurrence_rule), 'user'
            )
        ok({"id": row_id, "note": "Lunar date template saved. Run expand_calendar to materialize."})
    elif recurrence == 'yearly':
        # Solar yearly recurrence — store with actual date
        event_date = args.get('date')
        if not event_date:
            return err("date required for yearly recurrence")
        with get_db() as conn:
            row_id = db_exec(conn,
                """INSERT INTO calendar_events
                   (date, title, event_type, recurrence, recurrence_rule, source)
                   VALUES (?,?,?,?,?,?)""",
                event_date, title, 'special_date', 'yearly',
                json.dumps(recurrence_rule) if recurrence_rule else None, 'user'
            )
        ok({"id": row_id})
    else:
        # One-time special date
        event_date = args.get('date')
        if not event_date:
            return err("date required")
        with get_db() as conn:
            row_id = db_exec(conn,
                """INSERT INTO calendar_events
                   (date, title, event_type, recurrence, source)
                   VALUES (?,?,?,?,?)""",
                event_date, title, 'special_date', recurrence, 'user'
            )
        ok({"id": row_id})


def _fetch_holiday_api(year: int) -> list:
    """Fetch Chinese holidays from timor.tools API."""
    try:
        url = f"https://timor.tools/api/holiday/year/{year}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        holidays = []
        if data.get('code') == 0 and 'holiday' in data:
            for date_str, info in data['holiday'].items():
                if info.get('holiday'):
                    holidays.append({
                        'date': date_str,
                        'name': info.get('name', '节假日'),
                    })
        return holidays
    except Exception as e:
        return []


def _lunar_to_solar(lunar_month: int, lunar_day: int, year: int):
    """Convert lunar date to solar date for given year using lunardate library."""
    try:
        from lunardate import LunarDate
        ld = LunarDate(year, lunar_month, lunar_day, False)
        return ld.toSolarDate()
    except Exception:
        return None


def expand_calendar(args: dict):
    to_date_str = args.get('to_date')
    if not to_date_str:
        return err("to_date is required")
    to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()

    with get_db() as conn:
        # Determine existing max date (excluding lunar templates at 0001-01-01)
        row = conn.execute(
            "SELECT MAX(date) as max_date FROM calendar_events WHERE date > '0001-01-01' AND source='api'"
        ).fetchone()
        existing_max_str = row['max_date'] if row and row['max_date'] else None

        existing_max_year = int(existing_max_str[:4]) if existing_max_str else (datetime.now().year - 1)
        target_year = to_date.year
        years_to_add = range(existing_max_year + 1, target_year + 1)

        added_holidays = 0
        added_lunar = 0

        # 1. Fetch holidays for each new year
        for year in years_to_add:
            holidays = _fetch_holiday_api(year)
            for h in holidays:
                # Check if already exists
                existing = conn.execute(
                    "SELECT id FROM calendar_events WHERE date=? AND title=? AND source='api'",
                    (h['date'], h['name'])
                ).fetchone()
                if not existing:
                    conn.execute(
                        """INSERT INTO calendar_events
                           (date, title, event_type, source, recurrence)
                           VALUES (?,?,?,?,?)""",
                        (h['date'], h['name'], 'special_date', 'api', None)
                    )
                    added_holidays += 1

        # 2. Materialize lunar yearly events
        lunar_templates = db_query(conn,
            "SELECT * FROM calendar_events WHERE recurrence='lunar_yearly'"
        )
        for tmpl in lunar_templates:
            rule = json.loads(tmpl['recurrence_rule']) if tmpl['recurrence_rule'] else {}
            lunar_month = rule.get('lunar_month')
            lunar_day = rule.get('lunar_day')
            if not lunar_month or not lunar_day:
                continue
            for year in range(datetime.now().year, target_year + 1):
                solar = _lunar_to_solar(lunar_month, lunar_day, year)
                if solar:
                    solar_str = solar.strftime('%Y-%m-%d')
                    existing = conn.execute(
                        "SELECT id FROM calendar_events WHERE date=? AND title=? AND recurrence IS NULL",
                        (solar_str, tmpl['title'])
                    ).fetchone()
                    if not existing:
                        conn.execute(
                            """INSERT INTO calendar_events
                               (date, title, event_type, source, plan_id)
                               VALUES (?,?,?,?,?)""",
                            (solar_str, tmpl['title'], 'special_date', 'system', None)
                        )
                        added_lunar += 1

        # 3. Materialize solar yearly events
        yearly_templates = db_query(conn,
            "SELECT * FROM calendar_events WHERE recurrence='yearly'"
        )
        for tmpl in yearly_templates:
            base_date = datetime.strptime(tmpl['date'], '%Y-%m-%d').date()
            for year in range(datetime.now().year, target_year + 1):
                try:
                    solar_str = base_date.replace(year=year).strftime('%Y-%m-%d')
                except ValueError:
                    continue  # Feb 29 in non-leap year
                existing = conn.execute(
                    "SELECT id FROM calendar_events WHERE date=? AND title=? AND source='system'",
                    (solar_str, tmpl['title'])
                ).fetchone()
                if not existing:
                    conn.execute(
                        """INSERT INTO calendar_events
                           (date, title, event_type, source)
                           VALUES (?,?,?,?)""",
                        (solar_str, tmpl['title'], 'special_date', 'system')
                    )
                    added_lunar += 1

        conn.commit()

    ok({"added_holidays": added_holidays, "added_recurrence": added_lunar, "expanded_to": to_date_str})


def get_today_context(args: dict):
    today = today_str()
    with get_db() as conn:
        events = db_query(conn,
            "SELECT * FROM calendar_events WHERE date=? ORDER BY time_start",
            today)
    ok({"date": today, "events": events})


def main():
    action, args = parse_args()
    dispatch = {
        'read_range': read_range,
        'add_event': add_event,
        'update_event': update_event,
        'delete_event': delete_event,
        'add_special_date': add_special_date,
        'expand_calendar': expand_calendar,
        'get_today_context': get_today_context,
    }
    fn = dispatch.get(action)
    if not fn:
        err(f"Unknown action: {action}. Available: {list(dispatch.keys())}")
        sys.exit(1)
    fn(args)


if __name__ == '__main__':
    main()
