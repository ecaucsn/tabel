-- Добавление паспортных полей в таблицу recipients_recipient

ALTER TABLE recipients_recipient ADD COLUMN IF NOT EXISTS passport_series VARCHAR(4) DEFAULT '';
ALTER TABLE recipients_recipient ADD COLUMN IF NOT EXISTS passport_number VARCHAR(6) DEFAULT '';
ALTER TABLE recipients_recipient ADD COLUMN IF NOT EXISTS passport_issued_by VARCHAR(255) DEFAULT '';
ALTER TABLE recipients_recipient ADD COLUMN IF NOT EXISTS passport_issue_date DATE DEFAULT NULL;
ALTER TABLE recipients_recipient ADD COLUMN IF NOT EXISTS passport_department_code VARCHAR(7) DEFAULT '';

-- Проверка
SELECT column_name FROM information_schema.columns WHERE table_name = 'recipients_recipient' AND column_name LIKE 'passport%';
