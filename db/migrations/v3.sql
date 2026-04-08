-- Migration v3: Secretary v1.2
-- 新增 timers 表的投递管控字段

ALTER TABLE timers ADD COLUMN deliver_to   TEXT;
ALTER TABLE timers ADD COLUMN skip_if_late INTEGER DEFAULT 0;
ALTER TABLE timers ADD COLUMN ttl_minutes  INTEGER;

UPDATE meta SET value = '3' WHERE key = 'schema_version';
