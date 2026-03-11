#!/usr/bin/env python3
"""
memo_tool.py — 重要事件记录工具

Usage: python3 memo_tool.py <action> '<args_json>'
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db, db_query, db_exec, ok, err, parse_args, today_str


def search_memos(args: dict):
    query = args.get('query', '')
    tags = args.get('tags', '')
    with get_db() as conn:
        if query and tags:
            rows = db_query(conn,
                """SELECT * FROM memos
                   WHERE (title LIKE ? OR content LIKE ?) AND tags LIKE ?
                   ORDER BY created_at DESC""",
                f'%{query}%', f'%{query}%', f'%{tags}%'
            )
        elif query:
            rows = db_query(conn,
                """SELECT * FROM memos
                   WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
                   ORDER BY created_at DESC""",
                f'%{query}%', f'%{query}%', f'%{query}%'
            )
        elif tags:
            rows = db_query(conn,
                "SELECT * FROM memos WHERE tags LIKE ? ORDER BY created_at DESC",
                f'%{tags}%'
            )
        else:
            rows = db_query(conn, "SELECT * FROM memos ORDER BY created_at DESC LIMIT 20")
    ok(rows)


def get_recent_memos(args: dict):
    days = args.get('days', 30)
    cutoff = (datetime.now() - timedelta(days=int(days))).strftime('%Y-%m-%d')
    with get_db() as conn:
        rows = db_query(conn,
            "SELECT * FROM memos WHERE created_at >= ? ORDER BY created_at DESC",
            cutoff
        )
    ok(rows)


def write_memo(args: dict):
    title = args.get('title')
    content = args.get('content')
    if not title or not content:
        return err("title and content are required")
    with get_db() as conn:
        memo_id = db_exec(conn,
            "INSERT INTO memos (title, content, tags, event_date) VALUES (?,?,?,?)",
            title, content, args.get('tags', ''), args.get('event_date')
        )
    ok({"memo_id": memo_id, "title": title})


def delete_memo(args: dict):
    memo_id = args.get('memo_id')
    if not memo_id:
        return err("memo_id is required")
    with get_db() as conn:
        conn.execute("DELETE FROM memos WHERE id=?", (memo_id,))
        conn.commit()
    ok({"deleted_memo_id": memo_id})


def main():
    action, args = parse_args()
    dispatch = {
        'search_memos': search_memos,
        'get_recent_memos': get_recent_memos,
        'write_memo': write_memo,
        'delete_memo': delete_memo,
    }
    fn = dispatch.get(action)
    if not fn:
        err(f"Unknown action: {action}. Available: {list(dispatch.keys())}")
        sys.exit(1)
    fn(args)


if __name__ == '__main__':
    main()
