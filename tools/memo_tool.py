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


def write_memo(args: dict):
    """写入重要事件记录（需用户确认后调用）。"""
    title = args.get('title')
    content = args.get('content')
    if not title or not content:
        return err("title and content are required")

    with get_db() as conn:
        memo_id = db_exec(conn,
            "INSERT INTO memos (title, content, tags, event_date) VALUES (?,?,?,?)",
            title,
            content,
            args.get('tags', ''),
            args.get('event_date', today_str()),
        )
    ok({"id": memo_id, "title": title})


def search_memo(args: dict):
    """按关键词检索重要事件记录。"""
    keyword = args.get('keyword', '')
    days = args.get('days', 0)

    with get_db() as conn:
        if days > 0:
            since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            rows = db_query(conn,
                """SELECT * FROM memos
                   WHERE (title LIKE ? OR content LIKE ? OR tags LIKE ?)
                   AND created_at >= ?
                   ORDER BY created_at DESC""",
                f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', since
            )
        else:
            rows = db_query(conn,
                """SELECT * FROM memos
                   WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
                   ORDER BY created_at DESC""",
                f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'
            )
    ok({"keyword": keyword, "results": rows, "count": len(rows)})


def list_recent(args: dict):
    """列出最近 N 天的重要事件记录。"""
    days = args.get('days', 30)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    with get_db() as conn:
        rows = db_query(conn,
            "SELECT * FROM memos WHERE created_at >= ? ORDER BY created_at DESC",
            since
        )
    ok({"days": days, "since": since, "memos": rows, "count": len(rows)})


def delete_memo(args: dict):
    """删除重要事件记录（需用户确认后调用）。"""
    memo_id = args.get('memo_id') or args.get('id')
    if not memo_id:
        return err("memo_id is required")

    with get_db() as conn:
        row = conn.execute("SELECT title FROM memos WHERE id=?", (memo_id,)).fetchone()
        if not row:
            return err(f"Memo {memo_id} not found")
        conn.execute("DELETE FROM memos WHERE id=?", (memo_id,))
        conn.commit()
    ok({"deleted_id": memo_id, "title": dict(row).get('title')})


ACTIONS = {
    'write_memo': write_memo,
    'search_memo': search_memo,
    'list_recent': list_recent,
    'delete_memo': delete_memo,
    # 向后兼容 v1.0 别名
    'search_memos': search_memo,
    'get_recent_memos': list_recent,
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
