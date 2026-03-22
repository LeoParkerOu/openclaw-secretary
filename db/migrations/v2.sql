-- Migration v1 → v2
-- OpenClaw Secretary Schema Migration
-- 将 v1.0 的 plans/plan_tasks/plan_logs/plan_revisions 迁移为 goals/goal_logs/goal_revisions
-- 新增 working_memory、daily_reflections、weekly_reflections、resources 表
-- 更新 calendar_events 字段

-- ─── Step 1: 更新 calendar_events 表 ───────────────────────────────────────────

-- 添加 v1.1 新字段（SQLite ALTER TABLE 只支持 ADD COLUMN）
ALTER TABLE calendar_events ADD COLUMN item_type TEXT;
ALTER TABLE calendar_events ADD COLUMN calendar_type TEXT DEFAULT 'solar';
ALTER TABLE calendar_events ADD COLUMN goal_id INTEGER;

-- 将旧 event_type 值迁移到 item_type
UPDATE calendar_events SET item_type = COALESCE(
  CASE
    WHEN event_type = 'event'        THEN 'event'
    WHEN event_type = 'reminder'     THEN 'reminder'
    WHEN event_type = 'special_date' THEN 'special_date'
    ELSE 'event'
  END,
  'event'
) WHERE item_type IS NULL;

-- 对仍为 NULL 的行补默认值
UPDATE calendar_events SET item_type = 'event' WHERE item_type IS NULL;

-- ─── Step 2: 创建 goals 表，从 plans 迁移数据 ─────────────────────────────────

CREATE TABLE IF NOT EXISTS goals (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title        TEXT NOT NULL,
  description  TEXT,
  scope        TEXT NOT NULL DEFAULT 'week',
  status       TEXT DEFAULT 'active',
  priority     INTEGER DEFAULT 2,
  start_date   TEXT,
  end_date     TEXT,
  progress_pct INTEGER DEFAULT 0,
  created_at   TEXT DEFAULT (datetime('now')),
  updated_at   TEXT DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO goals
  (id, title, description, scope, status, priority, start_date, end_date, progress_pct, created_at, updated_at)
SELECT
  id,
  title,
  goal       AS description,
  COALESCE(granularity, 'week') AS scope,
  CASE status
    WHEN 'paused' THEN 'archived'
    ELSE status
  END,
  priority,
  start_date,
  end_date,
  progress_pct,
  created_at,
  updated_at
FROM plans;

-- ─── Step 3: 创建 goal_logs，从 plan_logs 迁移 ────────────────────────────────

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

INSERT OR IGNORE INTO goal_logs
  (id, goal_id, log_date, completed, not_done, reason, ai_note, created_at)
SELECT
  id, plan_id, log_date, completed, not_done, reason, ai_note, created_at
FROM plan_logs;

-- ─── Step 4: 创建 goal_revisions，从 plan_revisions 迁移 ─────────────────────

CREATE TABLE IF NOT EXISTS goal_revisions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  goal_id        INTEGER NOT NULL REFERENCES goals(id),
  revised_at     TEXT DEFAULT (datetime('now')),
  change_summary TEXT NOT NULL,
  change_reason  TEXT,
  revised_by     TEXT DEFAULT 'user'
);

INSERT OR IGNORE INTO goal_revisions
  (id, goal_id, revised_at, change_summary, change_reason, revised_by)
SELECT
  id, plan_id, revised_at, change_summary, change_reason, revised_by
FROM plan_revisions;

-- ─── Step 5: 将 plan_tasks 中的任务迁移为 calendar_events ────────────────────
-- plan_tasks 中有 date 的任务，迁移为 calendar_events 中的 todo 类型事项

INSERT OR IGNORE INTO calendar_events
  (date, time_start, title, item_type, calendar_type, goal_id, source, created_at)
SELECT
  COALESCE(date, date('now'))  AS date,
  time_slot                    AS time_start,
  title,
  'todo'                       AS item_type,
  'solar'                      AS calendar_type,
  plan_id                      AS goal_id,
  'system'                     AS source,
  created_at
FROM plan_tasks
WHERE status != 'deleted';

-- ─── Step 6: 新增表 ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS working_memory (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  scene      TEXT NOT NULL,
  rule       TEXT NOT NULL,
  source     TEXT,
  active     INTEGER DEFAULT 1,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS daily_reflections (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  reflection_date   TEXT NOT NULL UNIQUE,
  execution_pattern TEXT,
  goal_health       TEXT,
  user_state        TEXT,
  planning_quality  TEXT,
  raw_summary       TEXT,
  week_number       TEXT,
  created_at        TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS weekly_reflections (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  week_number        TEXT NOT NULL UNIQUE,
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
  type       TEXT DEFAULT 'idea',
  tags       TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

-- ─── Step 7: 更新 schema 版本 ─────────────────────────────────────────────────

UPDATE meta SET value = '2' WHERE key = 'schema_version';
INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '2');
