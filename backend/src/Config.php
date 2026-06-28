<?php
/**
 * Единый конфиг EBLAN Backend.
 *
 * ВСЕ настройки тут — база, почта, лимиты и т.д.
 * Поддерживает .env файл из backend/.env или системные переменные окружения.
 */

declare(strict_types=1);

final class Config
{
    public const API_VERSION = '2.1.0';

    private static bool $envLoaded = false;

    // =========================================================================
    //  ПУТИ
    // =========================================================================

    public static function dataDir(): string
    {
        return dirname(__DIR__) . DIRECTORY_SEPARATOR . 'data';
    }

    public static function versionsFile(): string
    {
        return self::dataDir() . DIRECTORY_SEPARATOR . 'versions.json';
    }

    public static function rollbackFile(): string
    {
        return self::dataDir() . DIRECTORY_SEPARATOR . 'rollback.json';
    }

    // =========================================================================
    //  CORS / CACHE
    // =========================================================================

    /** Разрешённые origin-ы для CORS (пусто = разрешить всем). */
    public static function allowedOrigins(): array
    {
        return [];
    }

    /** Секунд кешировать ответы на стороне клиента. */
    public static function cacheSeconds(): int
    {
        return 60;
    }

    // =========================================================================
    //  БАЗА ДАННЫХ (MySQL)
    // =========================================================================

    public static function dbHost(): string
    {
        return self::env('DB_HOST', 'mysql8.serv00.com');
    }

    public static function dbPort(): int
    {
        return (int) self::env('DB_PORT', '3306');
    }

    public static function dbName(): string
    {
        return self::env('DB_NAME', 'm5678_id');
    }

    public static function dbUser(): string
    {
        return self::env('DB_USER', 'm5678_admin');
    }

    public static function dbPass(): string
    {
        return self::env('DB_PASS', 'c!gH5S-um.JDLY.0rK0as-');
    }

    public static function dbCharset(): string
    {
        return self::env('DB_CHARSET', 'utf8mb4');
    }

    // =========================================================================
    //  ПОЧТА (SMTP)
    // =========================================================================

    public static function smtpHost(): string
    {
        return self::env('SMTP_HOST', 'mail8.serv00.com');
    }

    public static function smtpPort(): int
    {
        return (int) self::env('SMTP_PORT', '587');
    }

    public static function smtpUser(): string
    {
        return self::env('SMTP_USER', 'noreply@eblanbrowser.ru');
    }

    public static function smtpPass(): string
    {
        return self::env('SMTP_PASS', 'X10E.~T~2NIiNUD_Gb1KwrTFG=Ms9i');
    }

    public static function smtpSecure(): string
    {
        return self::env('SMTP_SECURE', 'tls'); // 'tls', 'ssl', ''
    }

    public static function mailFrom(): string
    {
        return self::env('MAIL_FROM', 'noreply@eblanbrowser.ru');
    }

    public static function mailFromName(): string
    {
        return self::env('MAIL_FROM_NAME', 'EBLAN Browser');
    }

    // =========================================================================
    //  АККАУНТЫ / ЛИМИТЫ
    // =========================================================================

    /** Максимум регистраций с одного IP. */
    public static function maxRegistrationsPerIp(): int
    {
        return (int) self::env('MAX_REGISTRATIONS_PER_IP', '1');
    }

    /** Время жизни кода подтверждения (секунды). */
    public static function codeLifetime(): int
    {
        return (int) self::env('CODE_LIFETIME', '600'); // 10 минут
    }

    /** Время жизни сессии (секунды). */
    public static function sessionLifetime(): int
    {
        return (int) self::env('SESSION_LIFETIME', '2592000'); // 30 дней
    }

    /** Максимум попыток ввода кода подтверждения до блокировки кода. */
    public static function maxCodeAttempts(): int
    {
        return max(1, (int) self::env('MAX_CODE_ATTEMPTS', '5'));
    }

    /** Кулдаун между повторными запросами кода на один email (секунды). */
    public static function codeResendCooldown(): int
    {
        return max(0, (int) self::env('CODE_RESEND_COOLDOWN', '60'));
    }

    /** Отдавать ли отладочные сообщения об ошибках наружу (НЕ включать в проде). */
    public static function isDebug(): bool
    {
        return self::flag('APP_DEBUG', false);
    }

    /**
     * Сколько совпавших аппаратных компонентов считать «той же машиной»
     * при нечётком совпадении (анти-обход бана). Меньше — строже ловит,
     * но выше риск ложных срабатываний.
     */
    public static function hwidMatchThreshold(): int
    {
        return max(1, (int) self::env('HWID_MATCH_THRESHOLD', '3'));
    }

    // =========================================================================
    //  АУДИТ-ЛОГ (Discord webhook)
    // =========================================================================

    /** URL Discord-вебхука для аудит-лога (пусто = логирование выключено). */
    public static function discordWebhook(): string
    {
        return self::env(
            'LOG_DISCORD_WEBHOOK',
            'https://discord.com/api/webhooks/1502646835091603466/jtsuc8zHom5cG6K1zhcehxOfV_8TLeJ18y2pjmXpierN2s1p-S4s0Vvrp8GDzRnGETN2'
        );
    }

    /** Включён ли аудит-лог вообще. */
    public static function loggingEnabled(): bool
    {
        return self::flag('LOG_ENABLED', true) && self::discordWebhook() !== '';
    }

    /**
     * Логировать ли шумные read-only/health маршруты (ping, heartbeat и т.п.).
     * По умолчанию выключено, чтобы не упереться в rate-limit Discord.
     */
    public static function loggingVerbose(): bool
    {
        return self::flag('LOG_VERBOSE', false);
    }

    /** Маршруты, которые НЕ логируем без LOG_VERBOSE (высокочастотный шум). */
    public static function loggingNoiseRoutes(): array
    {
        return [
            'ping', 'manifest', 'branches', 'check', 'rollback',
            'heartbeat', 'check_ban', 'session',
        ];
    }

    /** Чтение булевого флага из env (1/true/yes/on). */
    public static function flag(string $key, bool $default): bool
    {
        $raw = self::env($key, $default ? '1' : '0');
        $v = strtolower(trim($raw));
        return $v === '1' || $v === 'true' || $v === 'yes' || $v === 'on';
    }

    // =========================================================================
    //  ХЕЛПЕРЫ
    // =========================================================================

    /**
     * Получить переменную окружения с фоллбэком.
     */
    public static function env(string $key, string $default = ''): string
    {
        self::loadEnvFile();

        $val = getenv($key);
        if ($val !== false && $val !== '') {
            return $val;
        }
        return $_ENV[$key] ?? $_SERVER[$key] ?? $default;
    }

    /**
     * Загружаем .env файл из backend/ если он существует.
     */
    private static function loadEnvFile(): void
    {
        if (self::$envLoaded) {
            return;
        }
        self::$envLoaded = true;

        $envPath = dirname(__DIR__) . '/.env';
        if (!file_exists($envPath)) {
            return;
        }
        $lines = file($envPath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        if (!$lines) {
            return;
        }
        foreach ($lines as $line) {
            $line = trim($line);
            if ($line === '' || $line[0] === '#') {
                continue;
            }
            if (strpos($line, '=') === false) {
                continue;
            }
            [$key, $value] = explode('=', $line, 2);
            $key   = trim($key);
            $value = trim($value, " \t\n\r\0\x0B\"'");
            if ($key !== '' && getenv($key) === false) {
                putenv("{$key}={$value}");
                $_ENV[$key] = $value;
            }
        }
    }
}
