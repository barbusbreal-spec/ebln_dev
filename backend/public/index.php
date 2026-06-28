<?php
/**
 * EBLAN Backend — single-file router.
 *
 * EBLAN ID Accounts (без пароля, только email + код):
 *   POST /?route=auth_start        body: email        (отправить код)
 *   POST /?route=auth_complete     body: email, code  (подтвердить код)
 *   GET  /?route=session&token=...                    (проверить сессию)
 *   POST /?route=logout            body: token        (выйти)
 *
 * EBLAN ID Key:
 *   POST /?route=save_eblan_id_key body: token, key   (сохранить ключ)
 *   GET  /?route=get_eblan_id_key&token=...           (получить ключ)
 *   POST /?route=clear_eblan_id_key body: token       (удалить ключ)
 *
 * Update endpoints:
 *   GET  /?route=ping
 *   GET  /?route=manifest
 *   GET  /?route=check&branch=main&current=R1.0.101
 *   GET  /?route=rollback
 *   GET  /?route=branches
 *
 * Ban endpoints:
 *   POST /?route=heartbeat         body: hwid, profile
 *   GET  /?route=check_ban&hwid=...
 *   GET  /?route=bans&password=...
 *   POST /?route=ban&password=...&hwid=...&reason=...
 *   POST /?route=unban&password=...&hwid=...
 *   POST /?route=forget&password=...&hwid=...
 *   POST /?route=admin_password&password=...&new=...
 */

declare(strict_types=1);

require_once __DIR__ . '/../src/Config.php';

// Глобальный обработчик ошибок — чтобы всегда возвращать JSON, а не пустой ответ.
// Реальный текст ошибки наружу НЕ отдаём (утечка путей/SQL/структуры БД),
// а только пишем в server log. Детали показываем лишь при APP_DEBUG=1.
set_exception_handler(function (Throwable $e) {
    error_log('[EBLAN] ' . $e->getMessage() . ' @ ' . $e->getFile() . ':' . $e->getLine());
    http_response_code(500);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    header('Access-Control-Allow-Origin: *');
    $payload = ['ok' => false, 'error' => 'server_error'];
    if (Config::isDebug()) {
        $payload['debug'] = $e->getMessage();
    }
    echo json_encode($payload, JSON_UNESCAPED_UNICODE);
    exit;
});

set_error_handler(function ($errno, $errstr, $errfile, $errline) {
    throw new ErrorException($errstr, 0, $errno, $errfile, $errline);
});

require_once __DIR__ . '/../src/Response.php';
require_once __DIR__ . '/../src/UpdateRepo.php';
require_once __DIR__ . '/../src/BanRepo.php';
require_once __DIR__ . '/../src/Logger.php';

/**
 * Собрать безопасный снимок параметров запроса (для аудит-лога).
 * Сырое тело/секреты не тащим — Logger дополнительно редактирует чувствительное.
 */
function eb_log_params(): array
{
    $params = [];
    foreach ($_GET as $k => $v) {
        if ($k === 'route') {
            continue;
        }
        $params[$k] = is_scalar($v) ? (string) $v : json_encode($v, JSON_UNESCAPED_UNICODE);
    }
    foreach ($_POST as $k => $v) {
        $params[$k] = is_scalar($v) ? (string) $v : json_encode($v, JSON_UNESCAPED_UNICODE);
    }
    // JSON-тело
    $raw = file_get_contents('php://input') ?: '';
    if ($raw !== '') {
        $j = json_decode($raw, true);
        if (is_array($j)) {
            foreach ($j as $k => $v) {
                if (!isset($params[$k])) {
                    $params[$k] = is_scalar($v) ? (string) $v : json_encode($v, JSON_UNESCAPED_UNICODE);
                }
            }
        }
    }
    return $params;
}

// Аудит-лог любого API-запроса (после ответа клиенту, в shutdown).
register_shutdown_function(function () {
    if (!Config::loggingEnabled()) {
        return;
    }
    $route = isset($_GET['route']) ? (string) $_GET['route'] : 'manifest';

    // Шумные health/read-only маршруты не логируем без LOG_VERBOSE.
    if (!Config::loggingVerbose() && in_array($route, Config::loggingNoiseRoutes(), true)) {
        return;
    }

    $status = http_response_code();
    $status = is_int($status) ? $status : 200;
    $level = $status >= 500 ? 'error' : ($status >= 400 ? 'warn' : 'success');

    Logger::event('API', $route, array_merge(
        [
            'method' => $_SERVER['REQUEST_METHOD'] ?? 'GET',
            'status' => (string) $status,
        ],
        eb_log_params()
    ), $level);
    Logger::flush();
});

// Preflight
if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'OPTIONS') {
    Response::json(['ok' => true]);
}

/**
 * Достаёт и декодирует JSON-набор компонентов железа из параметра `components`.
 * Возвращает массив (возможно пустой). Никогда не бросает.
 */
function eb_components(): array
{
    $raw = eb_param('components');
    if ($raw === '') {
        return [];
    }
    // Защита от гигантских пейлоадов.
    if (strlen($raw) > 8192) {
        $raw = substr($raw, 0, 8192);
    }
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

/** Достаёт параметр из GET либо POST. */
function eb_param(string $key, string $default = ''): string
{
    if (isset($_GET[$key])) {
        return (string) $_GET[$key];
    }
    if (isset($_POST[$key])) {
        return (string) $_POST[$key];
    }
    static $jsonBody = null;
    if ($jsonBody === null) {
        $raw = file_get_contents('php://input') ?: '';
        $j   = json_decode($raw, true);
        $jsonBody = is_array($j) ? $j : [];
    }
    if (isset($jsonBody[$key])) {
        return (string) $jsonBody[$key];
    }
    return $default;
}

function eb_client_ip(): string
{
    $cands = [
        $_SERVER['HTTP_CF_CONNECTING_IP'] ?? '',
        $_SERVER['HTTP_X_FORWARDED_FOR'] ?? '',
        $_SERVER['REMOTE_ADDR'] ?? '',
    ];
    foreach ($cands as $c) {
        $c = trim((string) $c);
        if ($c !== '') {
            $parts = explode(',', $c);
            return trim($parts[0]);
        }
    }
    return '';
}

$route = isset($_GET['route']) ? (string) $_GET['route'] : 'manifest';
$repo  = new UpdateRepo();

switch ($route) {
    case 'ping':
        Response::ok([
            'service' => 'eblan-update-backend',
            'version' => Config::API_VERSION,
            'time'    => gmdate('c'),
        ]);
        break;

    case 'manifest':
        Response::json($repo->manifest());
        break;

    case 'branches':
        Response::ok(['branches' => $repo->branches()]);
        break;

    case 'check':
        $branch  = isset($_GET['branch'])  ? (string) $_GET['branch']  : 'main';
        $current = isset($_GET['current']) ? (string) $_GET['current'] : '';
        if ($current === '') {
            Response::error('missing_current_version', 400);
        }
        Response::ok($repo->check($branch, $current));
        break;

    case 'rollback':
        Response::ok(['versions' => $repo->rollbackList()]);
        break;

    // ========== БАНЫ ==========
    case 'heartbeat': {
        $hwid    = eb_param('hwid');
        $profile = eb_param('profile');
        $realIp  = eb_param('real_ip');
        $localIp = eb_param('local_ip');
        if ($hwid === '') {
            Response::error('missing_hwid', 400);
        }
        $components = eb_components();
        $ban = new BanRepo();
        $rec = $ban->heartbeat($hwid, $profile, eb_client_ip(), $realIp, $localIp, $components);
        $check = $ban->checkBan($hwid);
        Response::ok([
            'registered' => !empty($rec),
            'banned'     => $check['banned'],
            'reason'     => $check['reason'],
        ]);
        break;
    }

    case 'check_ban': {
        $hwid = eb_param('hwid');
        if ($hwid === '') {
            Response::error('missing_hwid', 400);
        }
        $ban = new BanRepo();
        // Если клиент прислал отпечаток железа — сохраняем и сразу проверяем
        // нечёткое совпадение (ловим обходчиков на первом же запуске).
        $components = eb_components();
        if (!empty($components)) {
            $ban->ingestComponents($hwid, $components);
        }
        Response::ok($ban->checkBan($hwid));
        break;
    }

    case 'bans': {
        $ban = new BanRepo();
        if (!$ban->checkAdmin(eb_param('password'))) {
            Response::error('forbidden', 403);
        }
        Response::ok(['users' => $ban->listUsers()]);
        break;
    }

    case 'ban': {
        $ban = new BanRepo();
        if (!$ban->checkAdmin(eb_param('password'))) {
            Response::error('forbidden', 403);
        }
        $hwid    = eb_param('hwid');
        $profile = eb_param('profile');
        $reason  = eb_param('reason');
        if ($hwid === '') {
            Response::error('missing_hwid', 400);
        }
        $rec = $ban->ban($hwid, $profile, $reason);
        Response::ok(['user' => $rec]);
        break;
    }

    case 'unban': {
        $ban = new BanRepo();
        if (!$ban->checkAdmin(eb_param('password'))) {
            Response::error('forbidden', 403);
        }
        $hwid = eb_param('hwid');
        if ($hwid === '') {
            Response::error('missing_hwid', 400);
        }
        Response::ok(['ok' => $ban->unban($hwid)]);
        break;
    }

    case 'forget': {
        $ban = new BanRepo();
        if (!$ban->checkAdmin(eb_param('password'))) {
            Response::error('forbidden', 403);
        }
        $hwid = eb_param('hwid');
        if ($hwid === '') {
            Response::error('missing_hwid', 400);
        }
        Response::ok(['ok' => $ban->forget($hwid)]);
        break;
    }

    case 'admin_password': {
        $ban = new BanRepo();
        if (!$ban->checkAdmin(eb_param('password'))) {
            Response::error('forbidden', 403);
        }
        $new = eb_param('new');
        if ($new === '') {
            Response::error('missing_new_password', 400);
        }
        Response::ok(['ok' => $ban->setAdminPassword($new)]);
        break;
    }

    // ========== EBLAN ID ACCOUNTS (без пароля) ==========

    // Шаг 1: отправить код на email
    case 'auth_start': {
        require_once __DIR__ . '/../src/AccountRepo.php';
        $email = eb_param('email');
        if ($email === '') {
            Response::error('missing_email', 400);
        }
        $acc = new AccountRepo();
        $result = $acc->authStart($email, eb_client_ip());
        if ($result['ok']) {
            Response::ok([
                'message' => $result['message'] ?? 'code_sent',
                'is_new'  => $result['is_new'] ?? false,
            ]);
        } else {
            Response::error($result['error'] ?? 'unknown', 400);
        }
        break;
    }

    // Шаг 2: подтвердить код — логин или регистрация
    case 'auth_complete': {
        require_once __DIR__ . '/../src/AccountRepo.php';
        $email = eb_param('email');
        $code  = eb_param('code');
        if ($email === '' || $code === '') {
            Response::error('missing_fields', 400);
        }
        $acc = new AccountRepo();
        $result = $acc->authComplete($email, $code, eb_client_ip());
        if ($result['ok']) {
            Response::ok([
                'token'   => $result['token'],
                'account' => $result['account'],
            ]);
        } else {
            $extra = [];
            if (isset($result['reason'])) {
                $extra['reason'] = $result['reason'];
            }
            Response::error($result['error'] ?? 'unknown', 400, $extra);
        }
        break;
    }

    // Проверка сессии
    case 'session': {
        require_once __DIR__ . '/../src/AccountRepo.php';
        $token = eb_param('token');
        if ($token === '') {
            Response::error('missing_token', 400);
        }
        $acc = new AccountRepo();
        $account = $acc->validateSession($token);
        if ($account) {
            Response::ok(['account' => $account]);
        } else {
            Response::error('invalid_session', 401);
        }
        break;
    }

    // Выход
    case 'logout': {
        require_once __DIR__ . '/../src/AccountRepo.php';
        $token = eb_param('token');
        if ($token === '') {
            Response::error('missing_token', 400);
        }
        $acc = new AccountRepo();
        $acc->logout($token);
        Response::ok(['message' => 'logged_out']);
        break;
    }

    // ========== EBLAN ID KEY ==========

    // Сохранить EBLAN ID ключ
    case 'save_eblan_id_key': {
        require_once __DIR__ . '/../src/AccountRepo.php';
        $token = eb_param('token');
        $key   = eb_param('key');
        if ($token === '' || $key === '') {
            Response::error('missing_fields', 400);
        }
        $acc = new AccountRepo();
        $account = $acc->validateSession($token);
        if (!$account) {
            Response::error('invalid_session', 401);
        }
        if ($acc->saveEblanIdKey((int) $account['id'], $key)) {
            Response::ok(['message' => 'saved']);
        } else {
            Response::error('invalid_key_format', 400);
        }
        break;
    }

    // Получить EBLAN ID ключ
    case 'get_eblan_id_key': {
        require_once __DIR__ . '/../src/AccountRepo.php';
        $token = eb_param('token');
        if ($token === '') {
            Response::error('missing_token', 400);
        }
        $acc = new AccountRepo();
        $account = $acc->validateSession($token);
        if (!$account) {
            Response::error('invalid_session', 401);
        }
        $key = $acc->getEblanIdKey((int) $account['id']);
        Response::ok(['eblan_id_key' => $key]);
        break;
    }

    // Удалить EBLAN ID ключ
    case 'clear_eblan_id_key': {
        require_once __DIR__ . '/../src/AccountRepo.php';
        $token = eb_param('token');
        if ($token === '') {
            Response::error('missing_token', 400);
        }
        $acc = new AccountRepo();
        $account = $acc->validateSession($token);
        if (!$account) {
            Response::error('invalid_session', 401);
        }
        $acc->clearEblanIdKey((int) $account['id']);
        Response::ok(['message' => 'cleared']);
        break;
    }

    default:
        Response::error('unknown_route', 404, ['route' => $route]);
}
