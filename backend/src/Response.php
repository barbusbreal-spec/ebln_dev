<?php
/**
 * Хелпер для JSON-ответов.
 */

declare(strict_types=1);

final class Response
{
    /**
     * Маршруты, для которых ответ нельзя кешировать (баны, админка, аккаунты).
     */
    private const NO_CACHE_ROUTES = [
        'check_ban', 'bans', 'ban', 'unban', 'forget',
        'heartbeat', 'admin_password',
        'auth_start', 'auth_complete', 'session', 'logout',
        'save_eblan_id_key', 'get_eblan_id_key', 'clear_eblan_id_key',
    ];

    private static function isNoCacheRoute(): bool
    {
        $route = (string) ($_GET['route'] ?? '');
        return in_array($route, self::NO_CACHE_ROUTES, true);
    }

    public static function json($payload, int $status = 200): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        // Базовые security-заголовки на каждый ответ API.
        header('X-Content-Type-Options: nosniff');
        header('X-Frame-Options: DENY');
        header('Referrer-Policy: no-referrer');
        if (self::isNoCacheRoute()) {
            header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
            header('Pragma: no-cache');
        } else {
            header('Cache-Control: public, max-age=' . Config::cacheSeconds());
        }

        $origins = Config::allowedOrigins();
        if (empty($origins)) {
            header('Access-Control-Allow-Origin: *');
        } elseif (isset($_SERVER['HTTP_ORIGIN']) && in_array($_SERVER['HTTP_ORIGIN'], $origins, true)) {
            header('Access-Control-Allow-Origin: ' . $_SERVER['HTTP_ORIGIN']);
        }
        header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
        header('Access-Control-Allow-Headers: Content-Type');

        echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
        exit;
    }

    public static function error(string $message, int $status = 400, array $extra = []): void
    {
        self::json(array_merge([
            'ok'    => false,
            'error' => $message,
        ], $extra), $status);
    }

    public static function ok(array $payload): void
    {
        self::json(array_merge(['ok' => true], $payload));
    }
}
