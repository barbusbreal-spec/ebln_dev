<?php
/**
 * EBLAN — Web-админка банов.
 *
 * Самодостаточная страница: логин по паролю (тот же admin.json, что у API),
 * сессия, CSRF, формы для ban / unban / forget / смены пароля,
 * фильтр по строке и статусу.
 *
 * Гейминг/консольный скин: единый <style> в <head>, стилизация строго по
 * тегам (нативный HTML5: table, fieldset, details, button, nav, section) —
 * разметка и PHP-логика не меняются, только presentation-слой.
 *
 * URL:  /admin.php  (или, если включён mod_rewrite — /admin)
 *
 * Пароль по умолчанию (создаётся при первом запуске):  allah671488228
 * Файл с паролем: backend/data/admin.json
 */

declare(strict_types=1);

require_once __DIR__ . '/../src/Config.php';
require_once __DIR__ . '/../src/BanRepo.php';
require_once __DIR__ . '/../src/Logger.php';

// Понятная диагностика вместо криптового "Class BanRepo not found".
// Обычно это значит, что на сервер залит НЕ весь backend/src/ (файл устарел,
// пустой или не загрузился), либо OPcache держит старую версию.
if (!class_exists('BanRepo')) {
    http_response_code(500);
    header('Content-Type: text/plain; charset=utf-8');
    echo "Ошибка конфигурации сервера: класс BanRepo не загрузился.\n";
    echo "Проверь, что файл существует и не пустой:\n";
    echo "  " . realpath(__DIR__ . '/..') . "/src/BanRepo.php\n";
    echo "Затем перезалей ВЕСЬ каталог backend/src/ и сбрось OPcache.\n";
    exit;
}

session_name('eblan_admin');
session_start();

header('Content-Type: text/html; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('Pragma: no-cache');
header('X-Frame-Options: DENY');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');

$repo = new BanRepo();

/* ----------------------------------------------------------
 *  Хелперы
 * ---------------------------------------------------------- */

function h($v): string
{
    return htmlspecialchars((string) $v, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function csrf_token(): string
{
    if (empty($_SESSION['csrf'])) {
        $_SESSION['csrf'] = bin2hex(random_bytes(16));
    }
    return $_SESSION['csrf'];
}

function csrf_check(): bool
{
    $given = (string) ($_POST['csrf'] ?? '');
    $expected = (string) ($_SESSION['csrf'] ?? '');
    return $expected !== '' && hash_equals($expected, $given);
}

function is_logged_in(): bool
{
    return !empty($_SESSION['admin_ok']);
}

function client_ip(): string
{
    $h = $_SERVER['HTTP_X_FORWARDED_FOR'] ?? '';
    if ($h !== '') {
        $first = trim(explode(',', $h)[0]);
        if ($first !== '') {
            return $first;
        }
    }
    return (string) ($_SERVER['REMOTE_ADDR'] ?? '');
}

function fmt_ts($ts): string
{
    if (!$ts) {
        return '—';
    }
    return date('Y-m-d H:i', (int) $ts);
}

function self_url(): string
{
    return strtok((string) ($_SERVER['REQUEST_URI'] ?? '/admin.php'), '?');
}

/* ----------------------------------------------------------
 *  POST-обработчики
 * ---------------------------------------------------------- */

$flash_login = null;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $action = (string) ($_POST['action'] ?? '');

    if ($action === 'login') {
        $pw = (string) ($_POST['password'] ?? '');
        // примитивный rate-limit
        $last = (float) ($_SESSION['last_attempt'] ?? 0);
        if (microtime(true) - $last < 0.4) {
            usleep(400000);
        }
        $_SESSION['last_attempt'] = microtime(true);

        if ($pw !== '' && $repo->checkAdmin($pw)) {
            session_regenerate_id(true);
            $_SESSION['admin_ok'] = true;
            csrf_token();
            Logger::event('ADMIN', 'login_success', [], 'admin');
            header('Location: ' . self_url());
            exit;
        }
        Logger::event('ADMIN', 'login_failed', [], 'warn');
        $flash_login = 'Неверный пароль.';
    } elseif ($action === 'logout') {
        Logger::event('ADMIN', 'logout', [], 'admin');
        $_SESSION = [];
        if (ini_get('session.use_cookies')) {
            $p = session_get_cookie_params();
            setcookie(
                session_name(),
                '',
                time() - 42000,
                $p['path'],
                $p['domain'],
                $p['secure'],
                $p['httponly']
            );
        }
        session_destroy();
        header('Location: ' . self_url());
        exit;
    } else {
        if (!is_logged_in()) {
            Logger::event('ADMIN', 'denied_unauthorized', ['action' => $action], 'warn');
            http_response_code(401);
            echo 'Не авторизован.';
            exit;
        }
        if (!csrf_check()) {
            Logger::event('ADMIN', 'denied_csrf', ['action' => $action], 'warn');
            http_response_code(403);
            echo 'CSRF mismatch.';
            exit;
        }

        $hwid    = trim((string) ($_POST['hwid'] ?? ''));
        $profile = trim((string) ($_POST['profile'] ?? ''));
        $reason  = trim((string) ($_POST['reason'] ?? ''));
        $flash   = null;

        switch ($action) {
            case 'ban':
                if ($hwid === '') {
                    $flash = ['err', 'Не указан HWID.'];
                    break;
                }
                if ($reason === '') {
                    $flash = ['err', 'Причина обязательна.'];
                    break;
                }
                $repo->ban($hwid, $profile, $reason);
                $flash = ['ok', 'Забанен: ' . ($profile !== '' ? $profile : $hwid)];
                break;

            case 'unban':
                if ($hwid === '') {
                    $flash = ['err', 'Не указан HWID.'];
                    break;
                }
                $ok = $repo->unban($hwid);
                $flash = $ok
                    ? ['ok', 'Разбанен: ' . ($profile !== '' ? $profile : $hwid)]
                    : ['err', 'Запись не найдена.'];
                break;

            case 'forget':
                if ($hwid === '') {
                    $flash = ['err', 'Не указан HWID.'];
                    break;
                }
                $ok = $repo->forget($hwid);
                $flash = $ok
                    ? ['ok', 'Удалена запись: ' . ($profile !== '' ? $profile : $hwid)]
                    : ['err', 'Запись не найдена.'];
                break;

            case 'add_ban':
                if ($hwid === '') {
                    $flash = ['err', 'Не указан HWID.'];
                    break;
                }
                if ($reason === '') {
                    $flash = ['err', 'Причина обязательна.'];
                    break;
                }
                $repo->ban($hwid, $profile !== '' ? $profile : 'manual', $reason);
                $flash = ['ok', 'Добавлен в баны: ' . $hwid];
                break;

            case 'change_password':
                $new = (string) ($_POST['new_password'] ?? '');
                $confirm = (string) ($_POST['new_password_confirm'] ?? '');
                if ($new === '' || strlen($new) < 8) {
                    $flash = ['err', 'Новый пароль слишком короткий (минимум 8 символов).'];
                    break;
                }
                if ($new !== $confirm) {
                    $flash = ['err', 'Пароли не совпадают.'];
                    break;
                }
                $ok = $repo->setAdminPassword($new);
                $flash = $ok
                    ? ['ok', 'Пароль обновлён.']
                    : ['err', 'Не удалось сохранить пароль.'];
                break;

            default:
                $flash = ['err', 'Неизвестное действие.'];
        }

        // Аудит-лог действия админки (результат берём из flash).
        $ok = is_array($flash) && ($flash[0] ?? '') === 'ok';
        Logger::event('ADMIN', $action, [
            'hwid'    => $hwid,
            'profile' => $profile,
            'reason'  => $reason,
            'result'  => $ok ? 'ok' : 'fail',
            'message' => is_array($flash) ? (string) ($flash[1] ?? '') : '',
        ], $ok ? 'admin' : 'warn');

        // PRG: после POST → редирект, чтобы F5 не повторял действие.
        $_SESSION['flash'] = $flash;
        header('Location: ' . self_url());
        exit;
    }
}

// Подхватываем flash после PRG-редиректа.
$flash = null;
if (!empty($_SESSION['flash'])) {
    $flash = $_SESSION['flash'];
    unset($_SESSION['flash']);
}

/* ----------------------------------------------------------
 *  Фильтр (GET)
 * ---------------------------------------------------------- */

$filter_q      = trim((string) ($_GET['q'] ?? ''));
$filter_status = (string) ($_GET['status'] ?? 'all');   // all | banned | active

?><!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>EBLAN — Админка банов</title>
<style>
/* ============================================================
   EBLAN ADMIN — gaming/console UI
   Кибер-терминальный скин. Чистый CSS по тегам, разметку не трогаем.
   ============================================================ */
:root{
  --bg:#05080d; --bg2:#0a0f17; --panel:#0c121c; --panel2:#101826;
  --neon:#00ff9c; --cyan:#00e5ff; --magenta:#ff3d81; --amber:#ffcc00;
  --text:#c8f7e4; --dim:#5e7a86; --grid:rgba(0,229,255,.06);
  --br:#163040;
  --glow:0 0 6px rgba(0,255,156,.7),0 0 14px rgba(0,255,156,.25);
  --glow-cy:0 0 6px rgba(0,229,255,.7),0 0 16px rgba(0,229,255,.25);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0; padding:0 18px 60px;
  font-family:'JetBrains Mono','Cascadia Code','Consolas','Courier New',monospace;
  font-size:13px; line-height:1.5;
  color:var(--text);
  background:
    radial-gradient(1200px 600px at 80% -10%,rgba(0,229,255,.08),transparent 60%),
    radial-gradient(900px 500px at -10% 110%,rgba(255,61,129,.07),transparent 60%),
    linear-gradient(var(--grid) 1px,transparent 1px) 0 0/32px 32px,
    linear-gradient(90deg,var(--grid) 1px,transparent 1px) 0 0/32px 32px,
    var(--bg);
  text-shadow:0 0 1px rgba(0,255,156,.25);
}
/* CRT scanlines + лёгкое мерцание */
body::before{
  content:""; position:fixed; inset:0; z-index:9999; pointer-events:none;
  background:repeating-linear-gradient(0deg,rgba(0,0,0,.16) 0,rgba(0,0,0,.16) 1px,transparent 1px,transparent 3px);
  mix-blend-mode:multiply; animation:flicker 4s infinite steps(60);
}
@keyframes flicker{0%,97%{opacity:.55}98%{opacity:.35}100%{opacity:.6}}

::selection{background:var(--neon);color:#02110b}
a{color:var(--cyan);text-decoration:none;text-shadow:var(--glow-cy)}
a:hover{color:#fff;text-decoration:underline}

/* ---- Заголовок как титулка терминала ---- */
header{
  margin:18px 0 14px; padding:14px 18px;
  border:1px solid var(--br); border-radius:10px;
  background:linear-gradient(180deg,var(--panel2),var(--panel));
  box-shadow:inset 0 0 30px rgba(0,229,255,.05),0 0 0 1px rgba(0,0,0,.5);
  position:relative; overflow:hidden;
}
header::after{ /* бегущая верхняя линия */
  content:""; position:absolute; top:0; left:-100%; width:100%; height:2px;
  background:linear-gradient(90deg,transparent,var(--neon),var(--cyan),transparent);
  animation:sweep 3.5s linear infinite;
}
@keyframes sweep{to{left:100%}}
header h1{
  margin:0; font-size:20px; letter-spacing:2px; text-transform:uppercase;
  color:var(--neon); text-shadow:var(--glow);
}
header h1::before{content:"▚ "; color:var(--cyan)}
header h1::after{
  content:" ▮"; color:var(--neon);
  animation:blink 1.1s step-end infinite;
}
@keyframes blink{50%{opacity:0}}

/* ---- Навигация как командная панель ---- */
nav{
  position:sticky; top:0; z-index:50; margin:0 0 16px;
  background:rgba(5,8,13,.92); backdrop-filter:blur(4px);
  border:1px solid var(--br); border-radius:10px; padding:8px 12px;
}
nav ul{list-style:none; margin:0; padding:0; display:flex; flex-wrap:wrap; gap:10px; align-items:center}
nav ul li{margin:0}
nav a{
  display:inline-block; padding:6px 12px; border:1px solid var(--br); border-radius:6px;
  color:var(--cyan); background:var(--panel); text-transform:uppercase; font-size:11px; letter-spacing:1px;
}
nav a:hover{border-color:var(--cyan); box-shadow:var(--glow-cy); text-decoration:none; color:#fff}
nav a::before{content:"› "}

main{max-width:1280px; margin:0 auto}

/* ---- Секции = панели ---- */
section{
  margin:0 0 22px; padding:18px;
  border:1px solid var(--br); border-radius:12px;
  background:linear-gradient(180deg,var(--panel),var(--bg2));
  box-shadow:0 0 0 1px rgba(0,0,0,.5),inset 0 0 40px rgba(0,229,255,.03);
}
h2{
  margin:0 0 14px; font-size:15px; text-transform:uppercase; letter-spacing:2px;
  color:var(--cyan); text-shadow:var(--glow-cy);
  border-bottom:1px dashed var(--br); padding-bottom:8px;
}
h2::before{content:"// "; color:var(--neon)}

/* ---- Поля/фиелдсеты ---- */
fieldset{border:1px solid var(--br); border-radius:8px; padding:14px; margin:0 0 14px; background:rgba(0,0,0,.25)}
legend{color:var(--amber); padding:0 8px; text-transform:uppercase; font-size:11px; letter-spacing:1px}
label{color:var(--dim)}
input,textarea,select{
  font-family:inherit; font-size:13px; color:var(--neon);
  background:#040a0f;
  border:1px solid var(--br); border-radius:6px; padding:8px 10px; margin:4px 0;
  outline:none; transition:border-color .15s,box-shadow .15s;
  caret-color:var(--neon);
}
input:focus,textarea:focus,select:focus{border-color:var(--neon); box-shadow:var(--glow)}
input[type=radio]{accent-color:var(--neon)}

/* ---- Кнопки = консольные клавиши ---- */
button{
  font-family:inherit; font-size:12px; font-weight:bold; letter-spacing:1px; text-transform:uppercase;
  color:var(--neon); background:linear-gradient(180deg,#0c1a16,#07120e);
  border:1px solid var(--neon); border-radius:6px; padding:8px 16px; margin:4px 4px 4px 0;
  cursor:pointer; transition:all .15s; text-shadow:var(--glow);
}
button:hover{background:var(--neon); color:#02110b; box-shadow:var(--glow); text-shadow:none}
button:active{transform:translateY(1px)}

code{color:var(--cyan); background:rgba(0,229,255,.08); padding:1px 5px; border-radius:4px}
small,.ffHint{color:var(--dim)}
hr{border:none; border-top:1px dashed var(--br); margin:18px 0}

/* ---- Алерты ---- */
p[role=alert]{
  border:1px solid var(--magenta); border-left:4px solid var(--magenta);
  background:rgba(255,61,129,.08); padding:10px 14px; border-radius:6px;
  color:#ffd0e0; box-shadow:0 0 14px rgba(255,61,129,.18);
}
p[role=alert] strong{color:var(--magenta)}

/* ---- Статистика ---- */
#stats ul{list-style:none; padding:0; margin:0; display:flex; flex-wrap:wrap; gap:10px}
#stats li{
  flex:1 1 150px; border:1px solid var(--br); border-radius:8px; padding:10px 14px;
  background:rgba(0,0,0,.3); color:var(--dim);
}
#stats li strong{display:block; font-size:22px; color:var(--neon); text-shadow:var(--glow)}

/* ---- Таблица юзеров = дата-грид ---- */
table{border-collapse:collapse; width:100%; margin:8px 0; font-size:12px}
thead th{
  position:sticky; top:54px; z-index:5;
  background:var(--panel2); color:var(--cyan); text-transform:uppercase; font-size:10px; letter-spacing:1px;
  border:1px solid var(--br); padding:8px 6px; text-align:left; text-shadow:var(--glow-cy);
}
tbody td{border:1px solid var(--br); padding:7px 6px; vertical-align:top; background:rgba(0,0,0,.18)}
tbody tr:hover td{background:rgba(0,229,255,.06)}
td strong{color:var(--magenta); text-shadow:0 0 8px rgba(255,61,129,.6)}
abbr{text-decoration:none; border-bottom:1px dotted var(--dim)}
details summary{cursor:pointer; color:var(--cyan); list-style:none}
details summary::-webkit-details-marker{display:none}
details summary::before{content:"▸ "; color:var(--neon)}
details[open] summary::before{content:"▾ "}
details table{font-size:11px}
details td{padding:3px 6px}

/* ---- Подвал ---- */
footer{margin-top:30px; text-align:center; color:var(--dim); border-top:1px dashed var(--br); padding-top:12px}
footer small::before{content:"[ "; color:var(--neon)}
footer small::after{content:" ]"; color:var(--neon)}

@media (max-width:720px){
  thead th{position:static}
  nav{position:static}
}
</style>
</head>
<body>

<header>
    <h1>EBLAN — Админка банов</h1>
</header>

<?php if (!is_logged_in()): ?>

    <main>
        <section>
            <h2>Вход</h2>
            <?php if ($flash_login): ?>
                <p role="alert"><strong>Ошибка:</strong> <?= h($flash_login) ?></p>
            <?php endif; ?>
            <form method="post" action="<?= h(self_url()) ?>" autocomplete="off">
                <input type="hidden" name="action" value="login">
                <fieldset>
                    <legend>Авторизация</legend>
                    <p>
                        <label for="pw">Секретный пароль:</label><br>
                        <input type="password" id="pw" name="password" required autofocus size="40">
                    </p>
                    <p>
                        <button type="submit">Войти</button>
                    </p>
                </fieldset>
            </form>
            <p>
                <small>
                    Дефолтный пароль при первом запуске: <code>allah671488228</code>.
                    После входа сразу смени его в разделе «Сменить пароль».
                </small>
            </p>
        </section>
    </main>

<?php else: ?>

    <nav>
        <ul>
            <li><a href="#users">Пользователи</a></li>
            <li><a href="#add-ban">Добавить бан</a></li>
            <li><a href="#password">Сменить пароль</a></li>
            <li>
                <form method="post" action="<?= h(self_url()) ?>">
                    <input type="hidden" name="action" value="logout">
                    <button type="submit">Выйти</button>
                </form>
            </li>
        </ul>
    </nav>

    <?php if ($flash): ?>
        <p role="alert">
            <strong><?= $flash[0] === 'ok' ? 'OK:' : 'Ошибка:' ?></strong>
            <?= h($flash[1]) ?>
        </p>
    <?php endif; ?>

    <main>

        <?php
            $all_users = $repo->listUsers();
            // Активные баны вверх, потом по last_seen.
            usort($all_users, function ($a, $b) {
                $aa = !empty($a['active']) ? 1 : 0;
                $bb = !empty($b['active']) ? 1 : 0;
                if ($aa !== $bb) {
                    return $bb - $aa;
                }
                return (int) ($b['last_seen'] ?? 0) - (int) ($a['last_seen'] ?? 0);
            });

            $total = count($all_users);
            $banned_count = 0;
            foreach ($all_users as $u) {
                if (!empty($u['active'])) {
                    $banned_count++;
                }
            }

            // Применяем фильтр.
            $needle = mb_strtolower($filter_q);
            $users = array_filter($all_users, function ($u) use ($needle, $filter_status) {
                if ($filter_status === 'banned' || $filter_status === 'active') {
                    $is_banned = !empty($u['active']);
                    if ($filter_status === 'banned' && !$is_banned) {
                        return false;
                    }
                    if ($filter_status === 'active' && $is_banned) {
                        return false;
                    }
                }
                if ($needle === '') {
                    return true;
                }
                $hay = mb_strtolower(
                    (string) ($u['profile']  ?? '') . ' ' .
                    (string) ($u['hwid']     ?? '') . ' ' .
                    (string) ($u['reason']   ?? '') . ' ' .
                    (string) ($u['last_ip']  ?? '') . ' ' .
                    (string) ($u['real_ip']  ?? '') . ' ' .
                    (string) ($u['local_ip'] ?? '')
                );
                return mb_strpos($hay, $needle) !== false;
            });
            $users = array_values($users);
        ?>

        <section id="stats">
            <h2>Статистика</h2>
            <ul>
                <li>Всего записей: <strong><?= $total ?></strong></li>
                <li>Активных банов: <strong><?= $banned_count ?></strong></li>
                <li>Не забанены: <strong><?= $total - $banned_count ?></strong></li>
                <li>Показано: <strong><?= count($users) ?></strong></li>
            </ul>
        </section>

        <section id="users">
            <h2>Пользователи</h2>

            <form method="get" action="<?= h(self_url()) ?>">
                <fieldset>
                    <legend>Фильтр</legend>
                    <p>
                        <label>Поиск (профиль / hwid / IP / причина):<br>
                            <input type="text" name="q" value="<?= h($filter_q) ?>" size="40">
                        </label>
                    </p>
                    <p>
                        <label>Статус:</label>
                        <label><input type="radio" name="status" value="all"
                            <?= $filter_status === 'all' ? 'checked' : '' ?>> все</label>
                        <label><input type="radio" name="status" value="banned"
                            <?= $filter_status === 'banned' ? 'checked' : '' ?>> только забаненные</label>
                        <label><input type="radio" name="status" value="active"
                            <?= $filter_status === 'active' ? 'checked' : '' ?>> только не забаненные</label>
                    </p>
                    <p>
                        <button type="submit">Применить</button>
                        <a href="<?= h(self_url()) ?>#users">Сбросить</a>
                    </p>
                </fieldset>
            </form>

            <?php if (empty($users)): ?>
                <p><em>
                    <?= $total === 0
                        ? 'Пока никого. Юзеры появятся, как только запустят браузер.'
                        : 'Под фильтр ничего не попало.' ?>
                </em></p>
            <?php else: ?>
                <table border="1" cellspacing="0" cellpadding="6">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Профиль</th>
                            <th>HWID</th>
                            <th>Статус</th>
                            <th>Причина</th>
                            <th>Первый вход</th>
                            <th>Последний</th>
                            <th>IP (соединение)</th>
                            <th>Реальный IP</th>
                            <th>Железо</th>
                            <th>Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                    <?php foreach ($users as $i => $u): ?>
                        <?php
                            $hwid    = (string) ($u['hwid'] ?? '');
                            $prof    = (string) ($u['profile'] ?? '');
                            $reason  = (string) ($u['reason'] ?? '');
                            $active  = !empty($u['active']);
                            $hwShort = $hwid !== '' ? substr($hwid, 0, 12) . '…' : '';
                        ?>
                        <tr>
                            <td><?= $i + 1 ?></td>
                            <td><?= h($prof !== '' ? $prof : '—') ?></td>
                            <td>
                                <abbr title="<?= h($hwid) ?>"><code><?= h($hwShort) ?></code></abbr>
                            </td>
                            <td><?php
                                if ($active) {
                                    echo !empty($u['auto_banned'])
                                        ? '<strong>БАН (авто)</strong>'
                                        : '<strong>БАН</strong>';
                                } else {
                                    echo 'ok';
                                }
                            ?></td>
                            <td><?= h($reason) ?></td>
                            <td><?= h(fmt_ts($u['first_seen'] ?? null)) ?></td>
                            <td><?= h(fmt_ts($u['last_seen']  ?? null)) ?></td>
                            <td><?= h((string) ($u['last_ip'] ?? '')) ?></td>
                            <td>
                                <?php
                                    $realIp  = (string) ($u['real_ip'] ?? '');
                                    $localIp = (string) ($u['local_ip'] ?? '');
                                ?>
                                <?php if ($realIp !== ''): ?>
                                    <abbr title="<?= h($localIp !== '' ? 'LAN: ' . $localIp : '') ?>">
                                        <strong><?= h($realIp) ?></strong>
                                    </abbr>
                                    <?php
                                        $connIp = (string) ($u['last_ip'] ?? '');
                                        if ($connIp !== '' && $realIp !== $connIp):
                                    ?>
                                        <br><small>⚠ ≠ соединение (VPN/прокси?)</small>
                                    <?php endif; ?>
                                <?php else: ?>
                                    —
                                <?php endif; ?>
                            </td>
                            <td>
                                <?php
                                    $comp   = is_array($u['components'] ?? null) ? $u['components'] : [];
                                    $tokens = is_array($u['tokens'] ?? null) ? $u['tokens'] : [];
                                ?>
                                <?php if (empty($comp)): ?>
                                    —
                                <?php else: ?>
                                    <details>
                                        <summary><?= count($tokens) ?> комп.</summary>
                                        <?php if (!empty($u['matched_hwid'])): ?>
                                            <p><small>⚠ совпало с
                                                <code><?= h(substr((string) $u['matched_hwid'], 0, 12)) ?>…</code>
                                            </small></p>
                                        <?php endif; ?>
                                        <table border="1" cellspacing="0" cellpadding="2">
                                            <?php foreach ($comp as $ck => $cv): ?>
                                                <tr>
                                                    <td><code><?= h((string) $ck) ?></code></td>
                                                    <td><code><?= h(is_array($cv) ? implode(', ', $cv) : (string) $cv) ?></code></td>
                                                </tr>
                                            <?php endforeach; ?>
                                        </table>
                                    </details>
                                <?php endif; ?>
                            </td>
                            <td>
                                <details>
                                    <summary>действия</summary>

                                    <?php if (!$active): ?>
                                        <form method="post" action="<?= h(self_url()) ?>" autocomplete="off">
                                            <input type="hidden" name="csrf" value="<?= h(csrf_token()) ?>">
                                            <input type="hidden" name="action" value="ban">
                                            <input type="hidden" name="hwid" value="<?= h($hwid) ?>">
                                            <input type="hidden" name="profile" value="<?= h($prof) ?>">
                                            <fieldset>
                                                <legend>Забанить</legend>
                                                <p>
                                                    <label>Причина:<br>
                                                        <input type="text" name="reason" maxlength="500" required size="36">
                                                    </label>
                                                </p>
                                                <p>
                                                    <button type="submit"
                                                            onclick="return confirm('Забанить <?= h($prof !== '' ? $prof : $hwid) ?>?')">
                                                        Забанить
                                                    </button>
                                                </p>
                                            </fieldset>
                                        </form>
                                    <?php else: ?>
                                        <form method="post" action="<?= h(self_url()) ?>">
                                            <input type="hidden" name="csrf" value="<?= h(csrf_token()) ?>">
                                            <input type="hidden" name="action" value="unban">
                                            <input type="hidden" name="hwid" value="<?= h($hwid) ?>">
                                            <input type="hidden" name="profile" value="<?= h($prof) ?>">
                                            <button type="submit"
                                                    onclick="return confirm('Разбанить <?= h($prof !== '' ? $prof : $hwid) ?>?')">
                                                Разбанить
                                            </button>
                                        </form>
                                    <?php endif; ?>

                                    <form method="post" action="<?= h(self_url()) ?>">
                                        <input type="hidden" name="csrf" value="<?= h(csrf_token()) ?>">
                                        <input type="hidden" name="action" value="forget">
                                        <input type="hidden" name="hwid" value="<?= h($hwid) ?>">
                                        <input type="hidden" name="profile" value="<?= h($prof) ?>">
                                        <button type="submit"
                                                onclick="return confirm('Полностью удалить запись? Юзер появится снова при следующем запуске браузера.')">
                                            Забыть запись
                                        </button>
                                    </form>
                                </details>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            <?php endif; ?>
        </section>

        <section id="add-ban">
            <h2>Добавить бан вручную</h2>
            <p>Если знаешь HWID заранее — можешь забанить, не дожидаясь первого запуска браузера.</p>
            <form method="post" action="<?= h(self_url()) ?>" autocomplete="off">
                <input type="hidden" name="csrf" value="<?= h(csrf_token()) ?>">
                <input type="hidden" name="action" value="add_ban">
                <fieldset>
                    <legend>Новый бан</legend>
                    <p>
                        <label>HWID:<br>
                            <input type="text" name="hwid" size="48" maxlength="64" required>
                        </label>
                    </p>
                    <p>
                        <label>Имя профиля (необязательно):<br>
                            <input type="text" name="profile" size="32" maxlength="64">
                        </label>
                    </p>
                    <p>
                        <label>Причина:<br>
                            <textarea name="reason" rows="3" cols="60" required></textarea>
                        </label>
                    </p>
                    <p>
                        <button type="submit">Забанить</button>
                    </p>
                </fieldset>
            </form>
        </section>

        <section id="password">
            <h2>Сменить пароль админки</h2>
            <form method="post" action="<?= h(self_url()) ?>" autocomplete="off">
                <input type="hidden" name="csrf" value="<?= h(csrf_token()) ?>">
                <input type="hidden" name="action" value="change_password">
                <fieldset>
                    <legend>Новый пароль</legend>
                    <p>
                        <label>Новый пароль:<br>
                            <input type="password" name="new_password" minlength="8" required>
                        </label>
                    </p>
                    <p>
                        <label>Повтор:<br>
                            <input type="password" name="new_password_confirm" minlength="8" required>
                        </label>
                    </p>
                    <p>
                        <button type="submit"
                                onclick="return confirm('Сменить пароль админки?')">Сменить</button>
                    </p>
                </fieldset>
            </form>
        </section>

    </main>

<?php endif; ?>

<hr>
<footer>
    <p>
        <small>
            EBLAN Browser — admin panel ·
            <?= date('Y-m-d H:i') ?> ·
            IP <?= h(client_ip()) ?>
        </small>
    </p>
</footer>

</body>
</html>
