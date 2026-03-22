#!/usr/bin/env python3
"""
resource_tool.py — 个人资源收纳工具（预留接口）

用于快速收纳用户随手记录的想法、灵感、链接等非结构化内容。
当前为预留实现，未来对接独立的个人资源管理库。

Usage: python3 resource_tool.py <action> '<args_json>'
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db, db_query, db_exec, ok, err, parse_args


def collect(args: dict):
    """收纳用户资源（想法、笔记、链接等）。"""
    content = args.get('content')
    if not content:
        return err("content is required")

    resource_type = args.get('type', 'idea')
    valid_types = ('idea', 'note', 'link', 'other')
    if resource_type not in valid_types:
        resource_type = 'other'

    with get_db() as conn:
        resource_id = db_exec(conn,
            "INSERT INTO resources (content, type, tags) VALUES (?,?,?)",
            content, resource_type, args.get('tags', '')
        )
    ok({
        "id": resource_id,
        "type": resource_type,
        "note": "已收纳。未来此接口将对接独立的个人资源管理库。"
    })


def list_resources(args: dict):
    """列出资源。"""
    resource_type = args.get('type')
    limit = args.get('limit', 50)

    with get_db() as conn:
        if resource_type:
            rows = db_query(conn,
                "SELECT * FROM resources WHERE type=? ORDER BY created_at DESC LIMIT ?",
                resource_type, limit
            )
        else:
            rows = db_query(conn,
                "SELECT * FROM resources ORDER BY created_at DESC LIMIT ?",
                limit
            )
    ok({"resources": rows, "count": len(rows)})


ACTIONS = {
    'collect': collect,
    'list_resources': list_resources,
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
