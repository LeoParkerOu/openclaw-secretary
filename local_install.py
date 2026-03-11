#!/usr/bin/env python3
"""
local_install.py — 本地开发安装脚本

不依赖 openclaw install 命令，直接手动完成：
1. 安装 Python 依赖
2. 初始化/迁移数据库
3. 生成 config.json
4. 将 skill 文件软链接 / 复制到 openclaw workspace skills 目录
   （替换 {baseDir} 为本项目的绝对路径）
5. 注册 cron gateway_start 检测钩子（可选）

Usage:
    python3 local_install.py
"""
import os
import sys
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR    = Path(__file__).parent.resolve()        # 本项目根目录
OPENCLAW_DIR = Path.home() / '.openclaw'
WORKSPACE   = OPENCLAW_DIR / 'workspace'
SKILLS_DIR  = WORKSPACE / 'skills'
SKILL_DEST  = SKILLS_DIR / 'secretary'               # 安装到这里

DATA_DIR    = OPENCLAW_DIR / 'secretary'             # 用户数据目录
DB_PATH     = DATA_DIR / 'secretary.db'
CONFIG_PATH = DATA_DIR / 'config.json'
VERSION_PATH = DATA_DIR / 'schema_version.txt'

TARGET_SCHEMA_VERSION = 1

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

# ── Helpers ──────────────────────────────────────────────────────────────────

def run_sql(db_path: Path, sql_file: Path):
    sql = sql_file.read_text(encoding='utf-8')
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()


def get_schema_version() -> int:
    if VERSION_PATH.exists():
        try:
            return int(VERSION_PATH.read_text().strip())
        except ValueError:
            pass
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            conn.close()
            return int(row[0]) if row else 0
        except Exception:
            pass
    return 0


def set_schema_version(v: int):
    VERSION_PATH.write_text(str(v))
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(v),))
        conn.commit()
        conn.close()


def substitute(text: str) -> str:
    """Replace {baseDir} with actual project path."""
    return text.replace('{baseDir}', str(BASE_DIR))


# ── Steps ────────────────────────────────────────────────────────────────────

def step1_deps():
    print("[1/5] 安装 Python 依赖...")
    subprocess.run(
        [sys.executable, '-m', 'pip', 'install',
         'flask', 'flask-cors', 'lunardate', 'requests', '--quiet'],
        check=True
    )
    print("  ✅ 依赖安装完毕")


def step2_data_dir():
    print("[2/5] 创建数据目录...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  ✅ 数据目录: {DATA_DIR}")


def step3_database():
    print("[3/5] 初始化/迁移数据库...")
    current = get_schema_version()
    if current == 0:
        print("  全新安装，执行 schema.sql ...")
        run_sql(DB_PATH, BASE_DIR / 'db' / 'schema.sql')
        print("  ✅ 数据库初始化完成（schema v1）")
    elif current < TARGET_SCHEMA_VERSION:
        migrations_dir = BASE_DIR / 'db' / 'migrations'
        for v in range(current + 1, TARGET_SCHEMA_VERSION + 1):
            mf = migrations_dir / f'v{v}.sql'
            if mf.exists():
                backup = DB_PATH.with_suffix('.db.bak')
                shutil.copy2(DB_PATH, backup)
                run_sql(DB_PATH, mf)
                print(f"  ✅ 迁移 v{v} 完成")
            else:
                print(f"  跳过 v{v}（无迁移文件）")
    else:
        print(f"  ✅ 数据库已是最新版本（v{current}），无需迁移")
    set_schema_version(TARGET_SCHEMA_VERSION)


def step4_config():
    print("[4/5] 配置 config.json ...")
    if CONFIG_PATH.exists():
        print("  config.json 已存在，跳过")
    else:
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"  ✅ config.json 已生成: {CONFIG_PATH}")


def step5_skill():
    print("[5/5] 安装 Secretary skill 到 openclaw workspace ...")
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove existing (in case of reinstall)
    if SKILL_DEST.exists() or SKILL_DEST.is_symlink():
        if SKILL_DEST.is_symlink():
            SKILL_DEST.unlink()
            print(f"  移除旧软链接: {SKILL_DEST}")
        else:
            shutil.rmtree(SKILL_DEST)
            print(f"  移除旧目录: {SKILL_DEST}")

    SKILL_DEST.mkdir()

    # ── Generate combined SKILL.md ─────────────────────────────────────────
    # OpenClaw injects SKILL.md content into AI context but does NOT
    # automatically load referenced files. So we embed SECRETARY.md
    # directly into SKILL.md at install time to ensure all tool instructions
    # and behavior constraints are immediately available to the AI.
    # PLANNING.md remains separate — the AI is explicitly told to read it
    # as part of entering planning mode (a deliberate, heavier action).

    skill_frontmatter = """---
name: secretary
description: |
  私人AI秘书 / Personal AI Secretary.
  必须在以下场景读取本文件：行程、日程、日历、会议、提醒、计划、规划、
  任务、进度、复盘、备忘、重要事件记录。
  Use when user mentions: scheduling, reminders, planning, tasks,
  progress tracking, reviews, or important events.
  IMPORTANT: Always read this skill file before attempting any of the above.
version: 1.0.0
metadata:
  openclaw:
    emoji: "🗂️"
    requires:
      bins: ["python3"]
---

"""
    secretary_body = substitute(
        (BASE_DIR / 'SECRETARY.md').read_text(encoding='utf-8')
    )
    # Append activation message config hint
    cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else DEFAULT_CONFIG
    act_msg = cfg.get('activation_message', '您好，秘书小C为您服务。')
    activation_section = f"""
---

## 零、进入秘书模式时的第一句话

每次本次对话中**首次**激活秘书模式时（或用户明确呼叫「秘书」时），
必须先说出以下激活语，让用户知道秘书模式已开启，再继续处理任务：

> {act_msg}

（激活语可由用户在 config.json 的 `activation_message` 字段自定义。）

---
"""
    combined = skill_frontmatter + activation_section + secretary_body
    (SKILL_DEST / 'SKILL.md').write_text(combined, encoding='utf-8')
    print("  生成合并 SKILL.md（内嵌 SECRETARY.md）")

    # PLANNING.md: copy with path substitution, AI reads on demand
    planning_content = substitute(
        (BASE_DIR / 'PLANNING.md').read_text(encoding='utf-8')
    )
    (SKILL_DEST / 'PLANNING.md').write_text(planning_content, encoding='utf-8')
    print("  复制并替换路径: PLANNING.md")

    print(f"  ✅ Skill 已安装到: {SKILL_DEST}")
    print()
    print("  📌 注意: tools/ 和 db/ 保持在原位置，AI 将通过绝对路径调用")
    print(f"     工具路径: {BASE_DIR}/tools/")
    print(f"     数据路径: {DATA_DIR}/")


def step6_verify():
    print()
    print("── 验证 ──────────────────────────────────────────────")
    try:
        result = subprocess.run(['openclaw', 'skills', 'list'], capture_output=True, text=True)
        if 'secretary' in result.stdout:
            print("  ✅ openclaw skills list 中已出现 secretary")
        else:
            print("  ⚠️  skills list 中暂未看到 secretary（可能需要重启 openclaw 守护进程）")
    except FileNotFoundError:
        print("  openclaw 未在 PATH 中，请手动验证")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("OpenClaw Secretary — 本地安装")
    print(f"项目路径: {BASE_DIR}")
    print("=" * 55)
    print()

    step1_deps()
    print()
    step2_data_dir()
    print()
    step3_database()
    print()
    step4_config()
    print()
    step5_skill()
    step6_verify()

    print()
    print("=" * 55)
    print("✅  安装完成！")
    print()
    print("下一步：")
    print("  1. 重启 openclaw 守护进程（如果正在运行）")
    print("  2. 在聊天软件里和 OpenClaw 说话，秘书会自动激活")
    print("  3. 如需打开 Dashboard：")
    print(f"     python3 {BASE_DIR}/tools/dashboard.py")
    print("=" * 55)


if __name__ == '__main__':
    main()
