-- OpenClaw Secretary Database Schema v1
-- SQLite

CREATE TABLE calendar_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  date         TEXT NOT NULL,
  time_start   TEXT,
  time_end     TEXT,
  title        TEXT NOT NULL,
  description  TEXT,
  event_type   TEXT NOT NULL,          -- 'event'|'reminder'|'special_date'
  recurrence   TEXT,                   -- NULL|'daily'|'weekly'|'monthly'|'yearly'|'lunar_yearly'
  recurrence_rule TEXT,                -- JSON: {"weekday":2} etc.
  source       TEXT DEFAULT 'user',    -- 'user'|'api'|'system'
  plan_id      INTEGER,
  created_at   TEXT DEFAULT (datetime('now')),
  updated_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE plans (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title        TEXT NOT NULL,
  goal         TEXT,
  status       TEXT DEFAULT 'active',  -- 'active'|'paused'|'completed'|'archived'|'deleted'
  priority     INTEGER DEFAULT 2,      -- 1=高 2=中 3=低
  start_date   TEXT,
  end_date     TEXT,
  granularity  TEXT DEFAULT 'day',     -- 'day'|'hour'|'custom'
  progress_pct INTEGER DEFAULT 0,
  created_at   TEXT DEFAULT (datetime('now')),
  updated_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE plan_tasks (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id      INTEGER NOT NULL REFERENCES plans(id),
  date         TEXT,
  time_slot    TEXT,
  title        TEXT NOT NULL,
  status       TEXT DEFAULT 'pending', -- 'pending'|'done'|'skipped'|'deferred'
  note         TEXT,
  sort_order   INTEGER DEFAULT 0,
  created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE plan_logs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id      INTEGER NOT NULL REFERENCES plans(id),
  log_date     TEXT NOT NULL,
  completed    TEXT,
  not_done     TEXT,
  reason       TEXT,
  ai_note      TEXT,
  created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE plan_revisions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id      INTEGER NOT NULL REFERENCES plans(id),
  revised_at   TEXT DEFAULT (datetime('now')),
  change_summary TEXT NOT NULL,
  change_reason  TEXT,
  revised_by   TEXT DEFAULT 'user'     -- 'user'|'ai'
);

CREATE TABLE timers (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT NOT NULL,
  timer_type   TEXT NOT NULL,          -- 'heavy'|'light'
  trigger_mode TEXT NOT NULL,          -- 'once'|'recurring'
  cron_expr    TEXT,
  trigger_at   TEXT,
  context      TEXT,
  message      TEXT,
  platform     TEXT,
  status       TEXT DEFAULT 'active',  -- 'active'|'paused'|'done'
  last_run     TEXT,
  created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE user_profile (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  category     TEXT NOT NULL,          -- 'hard'|'soft'
  key          TEXT NOT NULL,
  value        TEXT NOT NULL,
  note         TEXT,
  updated_at   TEXT DEFAULT (datetime('now')),
  UNIQUE(category, key)
);

CREATE TABLE memos (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title        TEXT NOT NULL,
  content      TEXT NOT NULL,
  tags         TEXT,
  event_date   TEXT,
  created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE event_queue (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type   TEXT NOT NULL,          -- 'timer_heavy'|'timer_light'|'system'
  timer_id     INTEGER,
  scheduled_at TEXT NOT NULL,
  payload      TEXT,
  status       TEXT DEFAULT 'pending', -- 'pending'|'processed'
  created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT INTO meta (key, value) VALUES ('schema_version', '1'), ('installed_at', datetime('now'));
