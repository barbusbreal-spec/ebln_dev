-- EBLAN ID Accounts — MySQL schema (БЕЗ ПАРОЛЯ)
-- Создай базу и выполни этот скрипт:
--   mysql -u root -p eblan_browser < schema.sql

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- =============================================
-- Таблица аккаунтов (без password_hash!)
-- =============================================
CREATE TABLE IF NOT EXISTS `accounts` (
    `id`              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    `email`           VARCHAR(255)    NOT NULL,
    `eblan_id_key`    MEDIUMTEXT      NULL COMMENT 'EBLAN ID ключ (ebl_... из браузера) для синхронизации',
    `email_verified`  TINYINT(1)      NOT NULL DEFAULT 0,
    `created_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `created_ip`      VARCHAR(45)     NOT NULL DEFAULT '',
    `last_login_at`   DATETIME        NULL,
    `last_login_ip`   VARCHAR(45)     NULL,
    `hwid`            VARCHAR(64)     NULL COMMENT 'привязанный hardware id',
    `is_banned`       TINYINT(1)      NOT NULL DEFAULT 0,
    `ban_reason`      VARCHAR(500)    NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_email` (`email`),
    KEY `idx_hwid` (`hwid`),
    KEY `idx_created_ip` (`created_ip`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Коды подтверждения email (6-значные)
-- =============================================
CREATE TABLE IF NOT EXISTS `email_codes` (
    `id`          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    `email`       VARCHAR(255)    NOT NULL,
    `code`        VARCHAR(6)      NOT NULL,
    `purpose`     ENUM('auth')    NOT NULL DEFAULT 'auth',
    `created_at`  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `expires_at`  DATETIME        NOT NULL,
    `used`        TINYINT(1)      NOT NULL DEFAULT 0,
    `attempts`    SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'неверные попытки ввода кода (анти-брутфорс)',
    `ip`          VARCHAR(45)     NOT NULL DEFAULT '',
    PRIMARY KEY (`id`),
    KEY `idx_email_purpose` (`email`, `purpose`),
    KEY `idx_expires` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Лимиты регистрации по IP (1 аккаунт с IP)
-- =============================================
CREATE TABLE IF NOT EXISTS `ip_limits` (
    `ip`              VARCHAR(45)   NOT NULL,
    `registrations`   INT UNSIGNED  NOT NULL DEFAULT 0,
    `last_attempt`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`ip`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Сессии (токены авторизации)
-- =============================================
CREATE TABLE IF NOT EXISTS `sessions` (
    `id`          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    `account_id`  INT UNSIGNED    NOT NULL,
    `token`       VARCHAR(64)     NOT NULL,
    `created_at`  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `expires_at`  DATETIME        NOT NULL,
    `ip`          VARCHAR(45)     NOT NULL DEFAULT '',
    `user_agent`  VARCHAR(500)    NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_token` (`token`),
    KEY `idx_account` (`account_id`),
    KEY `idx_expires` (`expires_at`),
    CONSTRAINT `fk_sessions_account` FOREIGN KEY (`account_id`)
        REFERENCES `accounts` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;

-- Очистка старых кодов и сессий (cron раз в час):
--   DELETE FROM email_codes WHERE expires_at < NOW();
--   DELETE FROM sessions WHERE expires_at < NOW();

-- =============================================
-- МИГРАЦИЯ для уже существующих баз (анти-брутфорс кода).
-- Безопасно: если колонка уже есть — выполнять не нужно.
--   ALTER TABLE `email_codes`
--     ADD COLUMN `attempts` SMALLINT UNSIGNED NOT NULL DEFAULT 0 AFTER `used`;
-- =============================================
