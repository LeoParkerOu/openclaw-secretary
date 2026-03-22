#!/usr/bin/env python3
"""
install.py — OpenClaw Secretary v1.1 一键安装脚本

执行时机: openclaw install github:LovLLM/openclaw-secretary
脚本必须幂等：重复执行不破坏已有数据。
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
    """OpenClaw 工作目录，优先读取环境变量。"""
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

TARGET_SCHEMA_VERSION = 2


def get_schema_version() -> int:
    """返回当前 DB schema 版本（0 表示未安装）。"""
    version_file = get_version_path()
    if version_file.exists():
        try:
            return int(version_file.read_text().strip())
        except ValueError:
            pass
    # 检查 meta 表
    db_path = get_db_path()
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            row = conn.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()
            conn.close()
            if row:
                return int(row[0])
        except Exception:
            pass
    return 0


def set_schema_version(version: int):
    version_file = get_version_path()
    version_file.write_text(str(version))
    db_path = get_db_path()
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(version),)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass


# ─── Database ─────────────────────────────────────────────────────────────────

def run_sql_file(sql_path: Path, db_path: Path):
    """执行 SQL 文件。"""
    sql = sql_path.read_text(encoding='utf-8')
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()


def backup_db(db_path: Path):
    bak = db_path.with_suffix('.db.bak')
    shutil.copy2(str(db_path), str(bak))
    print(f"  备份已创建: {bak}")


def run_migrations(current_version: int, target_version: int, db_path: Path):
    migrations_dir = get_base_dir() / 'db' / 'migrations'
    for v in range(current_version + 1, target_version + 1):
        migration_file = migrations_dir / f'v{v}.sql'
        if migration_file.exists():
            print(f"  执行迁移: v{v}.sql")
            try:
                backup_db(db_path)
                run_sql_file(migration_file, db_path)
                print(f"  迁移 v{v} 完成。")
            except Exception as e:
                print(f"  错误：迁移 v{v} 失败：{e}")
                print(f"  数据已备份至 {db_path.with_suffix('.db.bak')}")
                sys.exit(1)
        else:
            print(f"  未找到迁移文件 v{v}.sql，跳过。")


def init_or_migrate_db():
    db_path = get_db_path()
    current_version = get_schema_version()

    if current_version == 0:
        print("  初始化数据库（全新安装）...")
        schema_file = get_base_dir() / 'db' / 'schema.sql'
        run_sql_file(schema_file, db_path)
        print(f"  数据库初始化完成（schema v{TARGET_SCHEMA_VERSION}，共 13 张表）。")
    elif current_version < TARGET_SCHEMA_VERSION:
        print(f"  数据库从 v{current_version} 迁移到 v{TARGET_SCHEMA_VERSION}...")
        run_migrations(current_version, TARGET_SCHEMA_VERSION, db_path)
    else:
        print(f"  数据库已是最新版本 v{current_version}，无需迁移。")

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
}


def init_config():
    config_path = get_config_path()
    if config_path.exists():
        print("  config.json 已存在，跳过。")
        return
    config_path.write_text(
        json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    print("  config.json 已创建（默认配置）。")


# ─── Dependencies ─────────────────────────────────────────────────────────────

def install_dependencies():
    packages = ['flask', 'flask-cors', 'lunardate', 'requests', 'icalendar']
    print(f"  安装依赖：{', '.join(packages)}")
    subprocess.run(
        [sys.executable, '-m', 'pip', 'install'] + packages + ['--quiet'],
        check=True
    )
    print("  依赖安装完成。")


# ─── Lunar ICS ────────────────────────────────────────────────────────────────

def download_lunar_ics():
    """
    下载农历/中国节假日 ics 资源文件。
    失败时仅警告，不中断安装。
    """
    assets_dir = get_base_dir() / 'assets'
    assets_dir.mkdir(exist_ok=True)
    ics_path = assets_dir / 'lunar_calendar.ics'

    if ics_path.exists():
        print("  农历 ics 文件已存在，跳过下载。")
        return

    # 尝试多个来源
    urls = [
        "https://calendars.icloud.com/holidays/cn_zh.ics",
        "https://www.officeholidays.com/ics-all/china",
    ]

    try:
        import requests
        for url in urls:
            try:
                resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
                if resp.status_code == 200 and len(resp.content) > 500:
                    ics_path.write_bytes(resp.content)
                    print(f"  农历 ics 下载成功（{len(resp.content)} bytes）。")
                    return
            except Exception:
                continue
        print("  [WARN] 农历 ics 下载失败，将在首次使用 expand_calendar 时重试。")
        print("         已有数据不受影响，可手动将 ics 文件放入 assets/lunar_calendar.ics。")
    except ImportError:
        print("  [WARN] requests 未安装，跳过农历 ics 下载。")


# ─── OpenClaw integrations ────────────────────────────────────────────────────

def register_openclaw_command(base_dir: Path):
    """
    提示用户 Dashboard 启动方式。
    OpenClaw 没有 CLI 级别的自定义子命令注册，直接运行 Python 脚本或使用 shell alias。
    """
    print(f"  Dashboard 启动命令：python3 {base_dir}/tools/dashboard.py")
    print(f"  建议在 shell 配置中添加别名：")
    print(f"    alias secretary='python3 {base_dir}/tools/dashboard.py'")


def register_openclaw_hook(base_dir: Path):
    """
    离线事件检测：在 OpenClaw 工作区的 BOOT.md 中追加一行调用指令。
    boot-md 钩子会在 gateway 启动时执行 BOOT.md 中的指令。
    """
    workspace = get_workspace()
    boot_md = workspace / 'BOOT.md'

    check_cmd = f"python3 {base_dir}/tools/event_queue_tool.py check '{{}}'"
    marker = "secretary_event_queue_check"

    try:
        existing_content = boot_md.read_text(encoding='utf-8') if boot_md.exists() else ""
        if marker in existing_content:
            print("  离线事件检测指令已存在于 BOOT.md，跳过。")
            return

        append_text = f"\n\n<!-- {marker} -->\n<!-- Secretary: 检查离线事件队列 -->\n```\n{check_cmd}\n```\n"
        with open(boot_md, 'a', encoding='utf-8') as f:
            f.write(append_text)
        print(f"  已将离线事件检测指令追加到 BOOT.md（{boot_md}）")
    except Exception as e:
        print(f"  [WARN] 无法写入 BOOT.md：{e}")


def register_weekly_summary_cron(base_dir: Path):
    """注册每周日 21:00 的周总结重型定时器。"""
    name = "secretary_weekly_summary"
    cron_expr = "0 21 * * 0"
    message = (
        "[SECRETARY_TIMER] 现在是每周总结时间，请调用 "
        f"python3 {base_dir}/tools/reflection_tool.py run_weekly_summary '{{}}' "
        "获取本周数据，生成周总结，发给用户一起讨论，"
        "根据用户反馈调用 write_weekly 写入，并调用 update_weekly_feedback 记录反馈。"
    )

    try:
        # 检查是否已注册（通过数据库）
        db_path = get_db_path()
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            existing = conn.execute(
                "SELECT id FROM timers WHERE name=?", (name,)
            ).fetchone()
            conn.close()
            if existing:
                print("  每周总结定时器已存在，跳过注册。")
                return

        result = subprocess.run(
            ['openclaw', 'cron', 'add',
             '--name', name,
             '--cron', cron_expr,
             '--session', 'main',
             '--system-event', message],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            # 写入数据库记录
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                conn.execute(
                    """INSERT OR IGNORE INTO timers
                       (name, timer_type, trigger_mode, cron_expr, context, status)
                       VALUES (?,?,?,?,?,?)""",
                    (name, 'heavy', 'recurring', cron_expr,
                     '每周总结时间，生成并与用户讨论周总结', 'active')
                )
                conn.commit()
                conn.close()
            print(f"  已注册定时器：每周总结（{cron_expr}）")
        else:
            print(f"  [WARN] 周总结定时器注册失败：{result.stderr.strip()}")
    except FileNotFoundError:
        print("  [WARN] openclaw CLI 未找到，跳过周总结定时器注册。")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("OpenClaw Secretary v1.1 — 安装中...")
    print("=" * 55)

    base_dir = get_base_dir()
    data_dir = get_data_dir()

    # 1. 安装 Python 依赖
    print("\n[1/7] 安装 Python 依赖...")
    install_dependencies()

    # 2. 创建数据目录
    print("\n[2/7] 创建数据目录...")
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"  数据目录：{data_dir}")

    # 3. 初始化或迁移数据库
    print("\n[3/7] 初始化数据库...")
    init_or_migrate_db()

    # 4. 生成默认 config.json
    print("\n[4/7] 配置文件...")
    init_config()

    # 5. 下载农历 ics 资源
    print("\n[5/7] 下载农历资源...")
    download_lunar_ics()

    # 6. 注册 openclaw 命令和钩子
    print("\n[6/7] 注册 OpenClaw 集成...")
    register_openclaw_command(base_dir)
    register_openclaw_hook(base_dir)

    # 7. 注册默认定时任务
    print("\n[7/7] 注册默认定时任务...")
    register_weekly_summary_cron(base_dir)

    print("\n" + "=" * 55)
    print("✅  Secretary v1.1 安装成功。")
    print("💬  发起对话即可开始使用秘书功能。")
    print("📊  运行 `openclaw secretary` 打开 Dashboard。")
    print("=" * 55)


if __name__ == '__main__':
    main()
