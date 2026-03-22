#!/usr/bin/env python3
"""
working_memory_tool.py — 工作记忆管理工具

工作记忆存储用户对 AI 行为方式的偏好和要求，按场景动态加载。
展示行程时加载 'display_schedule'，规划时加载 'planning'，通用加载 'general'。

Usage: python3 working_memory_tool.py <action> '<args_json>'
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db, db_query, db_exec, ok, err, parse_args, now_str


def read_by_scene(args: dict):
    """按场景读取工作记忆（加载启用状态的规则）。"""
    scene = args.get('scene', 'general')

    with get_db() as conn:
        # 加载指定场景 + general 场景（通用规则始终加载）
        if scene == 'general':
            rows = db_query(conn,
                "SELECT * FROM working_memory WHERE active=1 AND scene='general' ORDER BY created_at",
            )
        else:
            rows = db_query(conn,
                "SELECT * FROM working_memory WHERE active=1 AND scene IN (?,?) ORDER BY scene, created_at",
                scene, 'general'
            )

    ok({"scene": scene, "rules": rows, "count": len(rows)})


def write_rule(args: dict):
    """写入工作记忆规则（需用户确认：「这个要作为我以后的习惯吗？」）。"""
    scene = args.get('scene')
    rule = args.get('rule')
    if not scene or not rule:
        return err("scene and rule are required")

    valid_scenes = ('display_schedule', 'planning', 'reminder', 'general', 'review', 'memo')
    if scene not in valid_scenes:
        # 接受未知场景，不报错
        pass

    with get_db() as conn:
        rule_id = db_exec(conn,
            """INSERT INTO working_memory (scene, rule, source, active)
               VALUES (?,?,?,?)""",
            scene, rule, args.get('source', ''), 1
        )
    ok({"id": rule_id, "scene": scene, "rule": rule})


def list_all(args: dict):
    """列出所有工作记忆（含停用的）。"""
    with get_db() as conn:
        rows = db_query(conn,
            "SELECT * FROM working_memory ORDER BY scene, active DESC, created_at"
        )
    ok({"rules": rows, "total": len(rows)})


def disable_rule(args: dict):
    """停用某条规则（需用户确认）。"""
    rule_id = args.get('id')
    if not rule_id:
        return err("id is required")

    with get_db() as conn:
        row = conn.execute("SELECT * FROM working_memory WHERE id=?", (rule_id,)).fetchone()
        if not row:
            return err(f"Rule {rule_id} not found")
        conn.execute(
            "UPDATE working_memory SET active=0, updated_at=? WHERE id=?",
            (now_str(), rule_id)
        )
        conn.commit()
    ok({"id": rule_id, "status": "disabled"})


def enable_rule(args: dict):
    """重新启用某条规则。"""
    rule_id = args.get('id')
    if not rule_id:
        return err("id is required")

    with get_db() as conn:
        conn.execute(
            "UPDATE working_memory SET active=1, updated_at=? WHERE id=?",
            (now_str(), rule_id)
        )
        conn.commit()
    ok({"id": rule_id, "status": "enabled"})


ACTIONS = {
    'read_by_scene': read_by_scene,
    'write_rule': write_rule,
    'list_all': list_all,
    'disable_rule': disable_rule,
    'enable_rule': enable_rule,
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
