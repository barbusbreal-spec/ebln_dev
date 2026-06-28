<?php
/**
 * Аудит-лог EBLAN Backend → Discord webhook.
 *
 * Особенности:
 *   - Не блокирует ответ клиенту: события копятся в очередь и отправляются
 *     в shutdown-хуке, после fastcgi_finish_request() (если доступен).
 *   - Секреты (пароли, токены, коды, ключи) НИКОГДА не попадают в лог —
 *     редактируются как «***».
 *   - Сбой вебхука никогда не роняет запрос (всё в try/catch + короткие таймауты).
 *
 * Использование:
 *   Logger::event('API', 'auth_start', ['email' => $email], 'info');
 *   Logger::flush();   // вызывается автоматически на shutdown
 */

declare(strict_types=1);

require_once __DIR__ . '/Config.php';

final class Logger
{
    /** Ключи параметров, которые нельзя логировать ни при каких условиях. */
    private const SENSITIVE = [
        'password', 'new', 'new_password', 'new_password_confirm',
        'token', 'code', 'key', 'eblan_id_key', 'csrf',
        'pass', 'secret', 'authorization',
    ];

    /** @var array<int,array> очередь событий */
    private static array $queue = [];

    private static bool $registered = false;

    /** Цвета Discord-эмбеда по уровню. */
    private const COLORS = [
        'info'    => 0x3498DB, // синий
        'success' => 0x2ECC71, // зелёный
        'warn'    => 0xE67E22, // оранжевый
        'error'   => 0xE74C3C, // красный
        'admin'   => 0x9B59B6, // фиолетовый
    ];

    /**
     * Поставить событие в очередь на отправку.
     */
    public static function event(string $category, string $action, array $fields = [], string $level = 'info'): void
    {
        if (!Config::loggingEnabled()) {
            return;
        }
        self::$queue[] = [
            'category' => $category,
            'action'   => $action,
            'fields'   => self::redact($fields),
            'level'    => $level,
            'ip'       => self::clientIp(),
            'ua'       => substr((string) ($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 200),
            'time'     => gmdate('c'),
        ];
        self::register();
    }

    /**
     * Зарегистрировать shutdown-хук (один раз).
     */
    public static function register(): void
    {
        if (self::$registered) {
            return;
        }
        self::$registered = true;
        register_shutdown_function([self::class, 'flush']);
    }

    /**
     * Отправить все накопленные события. Вызывается автоматически на shutdown.
     */
    public static function flush(): void
    {
        if (empty(self::$queue)) {
            return;
        }
        // Сначала закрываем соединение с клиентом, чтобы вебхук не тормозил ответ.
        if (function_exists('fastcgi_finish_request')) {
            @fastcgi_finish_request();
        }

        $webhook = Config::discordWebhook();
        if ($webhook === '') {
            self::$queue = [];
            return;
        }

        $events = self::$queue;
        self::$queue = [];

        foreach ($events as $ev) {
            try {
                self::send($webhook, self::buildPayload($ev));
            } catch (\Throwable $e) {
                error_log('[EBLAN][logger] ' . $e->getMessage());
            }
        }
    }

    // =========================================================================
    //  ВНУТРЕННЕЕ
    // =========================================================================

    private static function buildPayload(array $ev): array
    {
        $fieldList = [];
        foreach ($ev['fields'] as $name => $value) {
            if ($value === '' || $value === null) {
                continue;
            }
            $fieldList[] = [
                'name'   => substr((string) $name, 0, 256),
                'value'  => substr((string) $value, 0, 1024),
                'inline' => true,
            ];
        }
        $fieldList[] = ['name' => 'IP', 'value' => $ev['ip'] !== '' ? $ev['ip'] : '—', 'inline' => true];
        if ($ev['ua'] !== '') {
            $fieldList[] = ['name' => 'UA', 'value' => $ev['ua'], 'inline' => false];
        }

        $color = self::COLORS[$ev['level']] ?? self::COLORS['info'];

        return [
            'username' => 'EBLAN Audit',
            'embeds'   => [[
                'title'     => substr($ev['category'] . ' · ' . $ev['action'], 0, 256),
                'color'     => $color,
                'fields'    => array_slice($fieldList, 0, 25),
                'footer'    => ['text' => 'EBLAN Backend'],
                'timestamp' => $ev['time'],
            ]],
        ];
    }

    /**
     * Отправить JSON в Discord. Короткие таймауты, ошибки не критичны.
     */
    private static function send(string $webhook, array $payload): void
    {
        $json = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        if ($json === false) {
            return;
        }

        if (function_exists('curl_init')) {
            $ch = curl_init($webhook);
            curl_setopt_array($ch, [
                CURLOPT_POST           => true,
                CURLOPT_POSTFIELDS     => $json,
                CURLOPT_HTTPHEADER     => ['Content-Type: application/json'],
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_CONNECTTIMEOUT => 2,
                CURLOPT_TIMEOUT        => 4,
            ]);
            curl_exec($ch);
            curl_close($ch);
            return;
        }

        // Фоллбэк без curl.
        $ctx = stream_context_create([
            'http' => [
                'method'        => 'POST',
                'header'        => "Content-Type: application/json\r\n",
                'content'       => $json,
                'timeout'       => 4,
                'ignore_errors' => true,
            ],
        ]);
        @file_get_contents($webhook, false, $ctx);
    }

    /**
     * Заменяем чувствительные значения на «***».
     */
    private static function redact(array $fields): array
    {
        $out = [];
        foreach ($fields as $k => $v) {
            $key = strtolower((string) $k);
            if (in_array($key, self::SENSITIVE, true)) {
                $out[$k] = '***';
                continue;
            }
            if (is_array($v)) {
                $v = json_encode($v, JSON_UNESCAPED_UNICODE);
            }
            $out[$k] = (string) $v;
        }
        return $out;
    }

    private static function clientIp(): string
    {
        $cands = [
            $_SERVER['HTTP_CF_CONNECTING_IP'] ?? '',
            $_SERVER['HTTP_X_FORWARDED_FOR'] ?? '',
            $_SERVER['REMOTE_ADDR'] ?? '',
        ];
        foreach ($cands as $c) {
            $c = trim((string) $c);
            if ($c !== '') {
                return trim(explode(',', $c)[0]);
            }
        }
        return '';
    }
}
