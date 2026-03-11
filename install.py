#!/usr/bin/env python3
"""
install.py — OpenClaw Secretary 一键安装脚本

执行时机: openclaw install github:LovLLM/openclaw-secretary
脚本必须幂等，重复执行不破坏已有数据。
"""
import os
import sys
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path


# ─── Path helpers ─────────────────────────────────────────────────────────────

def get_base_dir() -> Path:
    """Skill 文件所在目录（仓库根目录）。"""
    return Path(__file__).parent.resolve()


def get_workspace() -> Path:
    """OpenClaw 工作目录。"""
    ws = os.environ.get('OPENCLAW_WORKSPACE')
    if ws:
        return Path(ws)
    return Path.home() / '.openclaw'


def get_data_dir() -> Path:
    return get_workspace() / 'secretary'


def get_db_path() -> Path:
    return get_data_dir() / 'secretary.db'


def get_config_path() -> Path:
    return get_data_dir() / 'config.json'


def get_version_path() -> Path:
    return get_data_dir() / 'schema_version.txt'


# ─── Schema version ───────────────────────────────────────────────────────────

TARGET_SCHEMA_VERSION = 1


def get_schema_version() -> int:
    """Return current DB schema version (0 if not installed yet)."""
    version_file = get_version_path()
    if version_file.exists():
        try:
            return int(version_file.read_text().strip())
        except ValueError:
            pass
    # Also check meta table
    db_path = get_db_path()
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            conn.close()
            if row:
                return int(row[0])
        except Exception:
            pass
    return 0


def set_schema_version(version: int):
    version_file = get_version_path()
    version_file.write_text(str(version))
    # Also update meta table
    db_path = get_db_path()
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(version),)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass


# ─── Database init & migration ────────────────────────────────────────────────

def run_sql_file(sql_path: Path, db_path: Path):
    """Execute a SQL file against the database."""
    sql = sql_path.read_text(encoding='utf-8')
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()


def backup_db(db_path: Path):
    bak = db_path.with_suffix('.db.bak')
    shutil.copy2(db_path, bak)
    print(f"  Backup created: {bak}")


def run_migrations(current_version: int, target_version: int, db_path: Path):
    migrations_dir = get_base_dir() / 'db' / 'migrations'
    for v in range(current_version + 1, target_version + 1):
        migration_file = migrations_dir / f'v{v}.sql'
        if migration_file.exists():
            print(f"  Running migration: v{v}.sql")
            try:
                backup_db(db_path)
                run_sql_file(migration_file, db_path)
                print(f"  Migration v{v} applied.")
            except Exception as e:
                print(f"  ERROR: Migration v{v} failed: {e}")
                print(f"  Your data is backed up at {db_path.with_suffix('.db.bak')}")
                sys.exit(1)
        else:
            print(f"  No migration file for v{v}, skipping.")


def init_or_migrate_db():
    db_path = get_db_path()
    current_version = get_schema_version()

    if current_version == 0:
        # Fresh install
        print("  Initializing database...")
        schema_file = get_base_dir() / 'db' / 'schema.sql'
        run_sql_file(schema_file, db_path)
        print("  Database initialized with schema v1.")
    elif current_version < TARGET_SCHEMA_VERSION:
        print(f"  Migrating database from v{current_version} to v{TARGET_SCHEMA_VERSION}...")
        run_migrations(current_version, TARGET_SCHEMA_VERSION, db_path)
    else:
        print(f"  Database schema already at v{current_version}, no migration needed.")

    set_schema_version(TARGET_SCHEMA_VERSION)


# ─── Config ───────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "primary_platform": None,
    "timezone": "Asia/Shanghai",
    "onboarding_done": False,
    "owner_id": None,
    "owner_verify": True,
    "holiday_region": "CN",
    "dashboard_port": 5299,
    "activation_message": "您好，秘书小C为您服务。",
}


def init_config():
    config_path = get_config_path()
    if config_path.exists():
        print("  config.json already exists, skipping.")
        return
    config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False), encoding='utf-8')
    print("  config.json created with defaults.")


# ─── Dependencies ─────────────────────────────────────────────────────────────

def install_dependencies():
    print("  Installing Python dependencies...")
    subprocess.run(
        [sys.executable, '-m', 'pip', 'install',
         'flask', 'flask-cors', 'lunardate', 'requests', '--quiet'],
        check=True
    )
    print("  Dependencies installed.")


# ─── OpenClaw command & hook registration ────────────────────────────────────

def register_openclaw_command(base_dir: Path):
    """Register `openclaw secretary` command to launch dashboard."""
    try:
        subprocess.run([
            'openclaw', 'command', 'add',
            '--name', 'secretary',
            '--exec', f'python3 {base_dir}/tools/dashboard.py',
            '--description', 'Open Secretary Dashboard',
        ], capture_output=True)
        print("  Registered: openclaw secretary (Dashboard)")
    except FileNotFoundError:
        print("  [WARN] openclaw CLI not found — skipping command registration.")


def register_openclaw_hook(base_dir: Path):
    """Register gateway_start hook for offline event detection."""
    try:
        subprocess.run([
            'openclaw', 'hook', 'add',
            '--event', 'gateway_start',
            '--exec', f'python3 {base_dir}/tools/event_queue_tool.py check \'{{}}\'',
        ], capture_output=True)
        print("  Registered: gateway_start hook (offline event detection)")
    except FileNotFoundError:
        print("  [WARN] openclaw CLI not found — skipping hook registration.")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("OpenClaw Secretary — Installing...")
    print("=" * 50)

    base_dir = get_base_dir()
    data_dir = get_data_dir()

    # 1. Install Python dependencies
    print("\n[1/5] Installing Python dependencies...")
    install_dependencies()

    # 2. Create data directory
    print("\n[2/5] Creating data directory...")
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Data directory: {data_dir}")

    # 3. Initialize or migrate database
    print("\n[3/5] Initializing database...")
    init_or_migrate_db()

    # 4. Generate default config.json
    print("\n[4/5] Setting up config.json...")
    init_config()

    # 5. Register openclaw command and hook
    print("\n[5/5] Registering openclaw integrations...")
    register_openclaw_command(base_dir)
    register_openclaw_hook(base_dir)

    print("\n" + "=" * 50)
    print("✅  Secretary installed successfully.")
    print("💬  Start a conversation to complete setup.")
    print("📊  Run `openclaw secretary` to open the Dashboard.")
    print("=" * 50)


if __name__ == '__main__':
    main()
