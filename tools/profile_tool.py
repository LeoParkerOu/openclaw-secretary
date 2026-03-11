#!/usr/bin/env python3
"""
profile_tool.py — 用户画像管理工具

Usage: python3 profile_tool.py <action> '<args_json>'
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db, db_query, db_exec, ok, err, parse_args, load_config, save_config


ONBOARDING_QUESTIONS = [
    {"key": "occupation",       "category": "hard", "question": "您目前的职业或身份是？（例如：创业者、工程师、学生等）"},
    {"key": "city",             "category": "hard", "question": "您主要生活在哪个城市？"},
    {"key": "family_status",    "category": "hard", "question": "您的家庭状况？（例如：已婚有孩子、单身等，如不方便可跳过）"},
    {"key": "important_people", "category": "hard", "question": "生活中有哪些重要的人需要我记住？（例如：家人、重要合作伙伴等）"},
    {"key": "work_hours",       "category": "soft", "question": "您通常的工作时间是？（例如：9点-18点、弹性等）"},
    {"key": "planning_style",   "category": "soft", "question": "您偏好密集型规划（排满）还是宽松型规划（留余量）？"},
    {"key": "timezone",         "category": "hard", "question": "您所在时区？（默认 Asia/Shanghai，如一致可跳过）"},
]


def read_profile(args: dict):
    category = args.get('category', 'all')
    with get_db() as conn:
        if category == 'all':
            rows = db_query(conn, "SELECT * FROM user_profile ORDER BY category, key")
        else:
            rows = db_query(conn,
                "SELECT * FROM user_profile WHERE category=? ORDER BY key", category)
    ok(rows)


def write_profile(args: dict):
    category = args.get('category')
    key = args.get('key')
    value = args.get('value')
    if not category or not key or value is None:
        return err("category, key, and value are required")
    note = args.get('note', '')
    with get_db() as conn:
        conn.execute(
            """INSERT INTO user_profile (category, key, value, note, updated_at)
               VALUES (?,?,?,?,datetime('now'))
               ON CONFLICT(category, key) DO UPDATE SET value=excluded.value,
               note=excluded.note, updated_at=excluded.updated_at""",
            (category, key, str(value), note)
        )
        conn.commit()
    ok({"category": category, "key": key, "value": value})


def capture_owner_id(args: dict):
    sender_id = args.get('sender_id')
    if not sender_id:
        return err("sender_id is required")
    cfg = load_config()
    if cfg.get('owner_id'):
        # Already captured
        ok({"captured": False, "owner_id": cfg['owner_id']})
        return
    cfg['owner_id'] = sender_id
    save_config(cfg)
    ok({"captured": True, "owner_id": sender_id})


def verify_owner(args: dict):
    sender_id = args.get('sender_id')
    if not sender_id:
        return err("sender_id is required")
    cfg = load_config()
    if not cfg.get('owner_verify', True):
        ok({"verified": True, "reason": "owner_verify=false"})
        return
    owner_id = cfg.get('owner_id')
    if not owner_id:
        # Not yet onboarded — let through so first message can capture
        ok({"verified": True, "reason": "onboarding_pending"})
        return
    verified = (sender_id == owner_id)
    ok({"verified": verified})


def get_onboarding_questions(args: dict):
    ok(ONBOARDING_QUESTIONS)


def main():
    action, args = parse_args()
    dispatch = {
        'read_profile': read_profile,
        'write_profile': write_profile,
        'capture_owner_id': capture_owner_id,
        'verify_owner': verify_owner,
        'get_onboarding_questions': get_onboarding_questions,
    }
    fn = dispatch.get(action)
    if not fn:
        err(f"Unknown action: {action}. Available: {list(dispatch.keys())}")
        sys.exit(1)
    fn(args)


if __name__ == '__main__':
    main()
