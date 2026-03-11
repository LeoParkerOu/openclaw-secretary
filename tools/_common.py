"""
Shared utilities for OpenClaw Secretary tools.
"""
import os
import sys
import json
import sqlite3
from datetime import datetime


def get_workspace() -> str:
    ws = os.environ.get('OPENCLAW_WORKSPACE')
    if ws:
        return ws
    return os.path.expanduser('~/.openclaw')


def get_data_dir() -> str:
    return os.path.join(get_workspace(), 'secretary')


def get_db_path() -> str:
    return os.path.join(get_data_dir(), 'secretary.db')


def get_config_path() -> str:
    return os.path.join(get_data_dir(), 'config.json')


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def db_query(conn: sqlite3.Connection, sql: str, *params) -> list:
    cur = conn.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def db_exec(conn: sqlite3.Connection, sql: str, *params) -> int:
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid


def load_config() -> dict:
    path = get_config_path()
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_config(cfg: dict):
    path = get_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def ok(data=None):
    print(json.dumps({"ok": True, "data": data}, ensure_ascii=False, default=str))


def err(msg: str):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))


def parse_args():
    if len(sys.argv) < 2:
        err("No action specified")
        sys.exit(1)
    action = sys.argv[1]
    args = {}
    if len(sys.argv) >= 3:
        try:
            args = json.loads(sys.argv[2])
        except json.JSONDecodeError as e:
            err(f"Invalid JSON args: {e}")
            sys.exit(1)
    return action, args


def today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def now_str() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
