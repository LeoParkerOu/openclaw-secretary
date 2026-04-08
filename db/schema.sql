-- OpenClaw Secretary Database Schema v2
-- SQLite
-- 使用 IF NOT EXISTS 确保幂等性

CREATE TABLE IF NOT EXISTS calendar_events (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  date            TEXT NOT NULL,          -- ISO 8601: 2025-03-15
  time_start      TEXT,                   -- HH:MM, NULL = 全天
  time_end        TEXT,
  title           TEXT NOT NULL,
  description     TEXT,
  item_type       TEXT NOT NULL DEFAULT 'event', -- 'event'|'todo'|'special_date'|'reminder'
  calendar_type   TEXT DEFAULT 'solar',   -- 'solar'|'lunar'
  recurrence      TEXT,                   -- NULL|'daily'|'weekly'|'monthly'|'yearly'|'lunar_yearly'
  recurrence_rule TEXT,                   -- JSON
  source          TEXT DEFAULT 'user',    -- 'user'|'api'|'ics'|'system'
  goal_id         INTEGER,                -- FK to goals.id, nullable
  created_at      TEXT DEFAULT (datetime('now')),
  updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS goals (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title        TEXT NOT NULL,
  description  TEXT,
  scope        TEXT NOT NULL,             -- 'day'|'week'|'month'|'quarter'|'year'|'long_term'
  status       TEXT DEFAULT 'active',     -- 'active'|'completed'|'archived'|'deleted'
  priority     INTEGER DEFAULT 2,         -- 1=高 2=中 3=低
  start_date   TEXT,
  end_date     TEXT,
  progress_pct INTEGER DEFAULT 0,
  created_at   TEXT DEFAULT (datetime('now')),
  updated_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS goal_logs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  goal_id      INTEGER NOT NULL REFERENCES goals(id),
  log_date     TEXT NOT NULL,
  completed    TEXT,
  not_done     TEXT,
  reason       TEXT,
  ai_note      TEXT,
  created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS goal_revisions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  goal_id        INTEGER NOT NULL REFERENCES goals(id),
  revised_at     TEXT DEFAULT (datetime('now')),
  change_summary TEXT NOT NULL,
  change_reason  TEXT,
  revised_by     TEXT DEFAULT 'user'      -- 'user'|'ai'
);

CREATE TABLE IF NOT EXISTS timers (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT NOT NULL,
  timer_type   TEXT NOT NULL,             -- 'heavy'|'light'
  trigger_mode TEXT NOT NULL,             -- 'once'|'recurring'
  cron_expr    TEXT,
  trigger_at   TEXT,
  context      TEXT,                      -- heavy timer 上下文
  message      TEXT,                      -- light timer 固定消息
  platform     TEXT,                      -- NULL = 使用主平台私聊
  deliver_to   TEXT,                      -- v1.2: 明确投递目标（会话标识），NULL = 使用 session 默认
  skip_if_late INTEGER DEFAULT 0,         -- v1.2: 1=错过即丢（例行提醒），0=必须补发（重要事件）
  ttl_minutes  INTEGER,                   -- v1.2: 有效期分钟数，超过则丢弃，NULL=永不丢
  status       TEXT DEFAULT 'active',     -- 'active'|'paused'|'done'
  last_run     TEXT,
  created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_profile (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  category   TEXT NOT NULL,               -- 'hard'|'soft'
  key        TEXT NOT NULL,
  value      TEXT NOT NULL,
  note       TEXT,
  updated_at TEXT DEFAULT (datetime('now')),
  UNIQUE(category, key)
);

CREATE TABLE IF NOT EXISTS working_memory (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  scene      TEXT NOT NULL,               -- 'display_schedule'|'planning'|'reminder'|'general'
  rule       TEXT NOT NULL,
  source     TEXT,                        -- 来源说明（用户原话摘要）
  active     INTEGER DEFAULT 1,           -- 1=启用 0=停用
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memos (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  title      TEXT NOT NULL,
  content    TEXT NOT NULL,
  tags       TEXT,
  event_date TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS daily_reflections (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  reflection_date   TEXT NOT NULL UNIQUE,
  execution_pattern TEXT,                 -- 执行模式归纳
  goal_health       TEXT,                 -- 目标健康度评估
  user_state        TEXT,                 -- 用户状态感知
  planning_quality  TEXT,                 -- 规划质量反思
  raw_summary       TEXT,                 -- 完整总结文本
  week_number       TEXT,                 -- YYYY-WW，用于周总结归并
  created_at        TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS weekly_reflections (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  week_number        TEXT NOT NULL UNIQUE, -- YYYY-WW
  week_start         TEXT NOT NULL,
  week_end           TEXT NOT NULL,
  execution_patterns TEXT,
  goal_progress      TEXT,
  new_insights       TEXT,
  next_week_advice   TEXT,
  raw_summary        TEXT,
  user_feedback      TEXT,
  created_at         TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resources (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  content    TEXT NOT NULL,
  type       TEXT DEFAULT 'idea',         -- 'idea'|'note'|'link'|'other'
  tags       TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS event_queue (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type   TEXT NOT NULL,             -- 'timer_heavy'|'timer_light'|'system'
  timer_id     INTEGER,
  scheduled_at TEXT NOT NULL,
  payload      TEXT,
  status       TEXT DEFAULT 'pending',    -- 'pending'|'processed'
  created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT OR IGNORE INTO meta (key, value) VALUES
  ('schema_version', '2'),
  ('installed_at', datetime('now'));
