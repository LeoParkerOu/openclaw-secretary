#!/usr/bin/env python3
"""
profile_tool.py — 用户画像 + 身份验证工具

Usage: python3 profile_tool.py <action> '<args_json>'
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from _common import (
    get_db, db_query, db_exec, ok, err, parse_args, now_str,
    load_config, save_config
)


def check_access(args: dict):
    """
    综合验证：身份验证 + 私聊保护。
    这是最高优先级的安全检查，每次进入秘书模式前必须调用。

    返回：
    - {"ok": true, "data": {"pass": true}} — 验证通过
    - {"ok": false, "error": "group_chat"} — 群聊中的数据库操作请求
    - {"ok": false, "error": "unauthorized"} — 非 owner 发送者
    - {"ok": true, "data": {"pass": true, "reason": "onboarding_pending"}} — 首次使用，需 onboarding
    """
    sender_id = args.get('sender_id', '')
    is_group = args.get('is_group', False)

    config = load_config()

    # ── 第一优先级：私聊保护 ──────────────────────────────────────────────
    # 群聊中任何秘书数据库操作一律拒绝
    if is_group:
        return err("group_chat")

    # ── 第二优先级：身份验证 ──────────────────────────────────────────────
    owner_verify = config.get('owner_verify', True)

    if not owner_verify:
        # 单用户私聊场景，跳过验证
        return ok({"pass": True, "note": "owner_verify disabled"})

    owner_id = config.get('owner_id')

    if not owner_id:
        # 尚未完成 onboarding，允许通过但标记需要 onboarding
        return ok({"pass": True, "reason": "onboarding_pending"})

    if sender_id and sender_id != owner_id:
        return err("unauthorized")

    ok({"pass": True})


def verify_private_chat(args: dict):
    """单独检查是否为私聊（不验证身份）。"""
    is_group = args.get('is_group', False)
    if is_group:
        return err("group_chat")
    ok({"is_private": True})


def read_profile(args: dict):
    """读取用户画像。"""
    category = args.get('category', 'all')
    with get_db() as conn:
        if category == 'all':
            rows = db_query(conn,
                "SELECT * FROM user_profile ORDER BY category, key")
        else:
            rows = db_query(conn,
                "SELECT * FROM user_profile WHERE category=? ORDER BY key",
                category)
    # 转为易读的 dict 格式
    result = {'hard': {}, 'soft': {}}
    for row in rows:
        result[row['category']][row['key']] = {
            'value': row['value'],
            'note': row.get('note'),
            'updated_at': row.get('updated_at'),
        }
    ok(result)


def write_profile(args: dict):
    """写入用户画像（需用户确认后调用）。"""
    category = args.get('category')
    key = args.get('key')
    value = args.get('value')
    if not category or not key or value is None:
        return err("category, key, value are required")
    if category not in ('hard', 'soft'):
        return err("category must be 'hard' or 'soft'")

    with get_db() as conn:
        db_exec(conn,
            """INSERT INTO user_profile (category, key, value, note, updated_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(category, key) DO UPDATE SET
                 value=excluded.value,
                 note=excluded.note,
                 updated_at=excluded.updated_at""",
            category, key, str(value), args.get('note', ''), now_str()
        )
    ok({"category": category, "key": key, "value": value})


def capture_owner_id(args: dict):
    """Onboarding 时捕获并写入 owner_id（只执行一次）。"""
    sender_id = args.get('sender_id')
    if not sender_id:
        return err("sender_id is required")

    config = load_config()
    if config.get('owner_id'):
        return ok({"already_set": True, "owner_id": config['owner_id']})

    config['owner_id'] = sender_id
    save_config(config)
    ok({"owner_id": sender_id, "captured": True})


def set_config(args: dict):
    """更新 config.json 中的某个字段。"""
    key = args.get('key')
    value = args.get('value')
    if not key:
        return err("key is required")

    config = load_config()
    config[key] = value
    save_config(config)
    ok({"key": key, "value": value})


def get_config(args: dict):
    """读取 config.json。"""
    config = load_config()
    # 不返回敏感信息
    safe_config = {k: v for k, v in config.items() if k not in ('owner_id',)}
    safe_config['owner_configured'] = bool(config.get('owner_id'))
    ok(safe_config)


ACTIONS = {
    'check_access': check_access,
    'verify_private_chat': verify_private_chat,
    'read_profile': read_profile,
    'write_profile': write_profile,
    'capture_owner_id': capture_owner_id,
    'set_config': set_config,
    'get_config': get_config,
    # 向后兼容 v1.0 别名
    'verify_owner': check_access,
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
