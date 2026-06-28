<?php
/**
 * EBLAN ID Accounts Repository.
 *
 * БЕЗ ПАРОЛЕЙ — только email + 6-значный код.
 * Поток:
 *   1. auth_start(email) — отправляет код на почту
 *   2. auth_complete(email, code) — проверяет код, создаёт аккаунт если нет, логинит
 */

declare(strict_types=1);

require_once __DIR__ . '/Config.php';
require_once __DIR__ . '/Database.php';
require_once __DIR__ . '/Mailer.php';

final class AccountRepo
{
    private PDO $db;

    public function __construct()
    {
        $this->db = Database::get();
    }

    // =========================================================================
    //  АВТОРИЗАЦИЯ (email + код, без пароля)
    // =========================================================================

    /**
     * Шаг 1: Отправить код на email.
     * Если аккаунта нет — будет создан при подтверждении кода (если IP не заблокирован).
     */
    public function authStart(string $email, string $ip): array
    {
        $email = $this->normalizeEmail($email);
        if (!$this->isValidEmail($email)) {
            return ['ok' => false, 'error' => 'invalid_email'];
        }

        $accountExists = $this->emailExists($email);

        // Если аккаунта нет — проверяем лимит IP для регистрации
        if (!$accountExists && !$this->checkIpLimit($ip)) {
            return ['ok' => false, 'error' => 'ip_limit_reached'];
        }

        // Кулдаун: не даём спамить кодами (защита от email-бомбинга и SMTP-абьюза).
        $cooldown = Config::codeResendCooldown();
        if ($cooldown > 0 && $this->recentCodeAge($email) < $cooldown) {
            return ['ok' => false, 'error' => 'too_many_requests'];
        }

        // Удаляем старые коды
        $this->deleteOldCodes($email);

        // Генерируем 6-значный код
        $code = $this->generateCode();
        $expiresAt = date('Y-m-d H:i:s', time() + Config::codeLifetime());

        $stmt = $this->db->prepare("
            INSERT INTO email_codes (email, code, purpose, expires_at, ip)
            VALUES (?, ?, 'auth', ?, ?)
        ");
        $stmt->execute([$email, $code, $expiresAt, $ip]);

        // Отправляем на почту
        $purpose = $accountExists ? 'login' : 'register';
        $sent = Mailer::sendCode($email, $code, $purpose);
        if (!$sent) {
            return ['ok' => false, 'error' => 'mail_failed'];
        }

        return [
            'ok'      => true,
            'message' => 'code_sent',
            'is_new'  => !$accountExists,
        ];
    }

    /**
     * Шаг 2: Подтвердить код — логин или создание аккаунта.
     */
    public function authComplete(string $email, string $code, string $ip): array
    {
        $email = $this->normalizeEmail($email);

        // Код всегда ровно 6 цифр — отсекаем мусор и сужаем перебор.
        $code = trim($code);
        if (!preg_match('/^\d{6}$/', $code)) {
            $this->registerFailedAttempt($email);
            return ['ok' => false, 'error' => 'invalid_code'];
        }

        // Анти-брутфорс: слишком много неверных попыток по коду → гасим код.
        if ($this->tooManyAttempts($email)) {
            $this->deleteOldCodes($email);
            return ['ok' => false, 'error' => 'too_many_attempts'];
        }

        // Проверяем код
        if (!$this->verifyCode($email, $code)) {
            $this->registerFailedAttempt($email);
            return ['ok' => false, 'error' => 'invalid_code'];
        }

        // Помечаем код как использованный
        $this->markCodeUsed($email, $code);

        // Проверяем, есть ли аккаунт
        $account = $this->getAccountByEmail($email);

        if (!$account) {
            // Создаём новый аккаунт
            if (!$this->checkIpLimit($ip)) {
                return ['ok' => false, 'error' => 'ip_limit_reached'];
            }

            $stmt = $this->db->prepare("
                INSERT INTO accounts (email, email_verified, created_ip)
                VALUES (?, 1, ?)
            ");
            $stmt->execute([$email, $ip]);
            $accountId = (int) $this->db->lastInsertId();

            // Увеличиваем счётчик IP
            $this->incrementIpCount($ip);

            $account = $this->getAccountById($accountId);
        } else {
            // Существующий аккаунт
            if ($account['is_banned']) {
                return ['ok' => false, 'error' => 'account_banned', 'reason' => $account['ban_reason']];
            }

            // Обновляем last_login
            $stmt = $this->db->prepare("
                UPDATE accounts SET last_login_at = NOW(), last_login_ip = ? WHERE id = ?
            ");
            $stmt->execute([$ip, $account['id']]);

            $account = $this->getAccountById((int) $account['id']);
        }

        // Создаём сессию
        $token = $this->createSession((int) $account['id'], $ip);

        return [
            'ok'      => true,
            'token'   => $token,
            'account' => $account,
        ];
    }

    // =========================================================================
    //  СЕССИИ
    // =========================================================================

    /**
     * Проверить токен и вернуть аккаунт.
     */
    public function validateSession(string $token): ?array
    {
        $stmt = $this->db->prepare("
            SELECT s.account_id, a.is_banned
            FROM sessions s
            JOIN accounts a ON a.id = s.account_id
            WHERE s.token = ? AND s.expires_at > NOW()
        ");
        $stmt->execute([$token]);
        $row = $stmt->fetch();

        if (!$row || $row['is_banned']) {
            return null;
        }

        return $this->getAccountById((int) $row['account_id']);
    }

    /**
     * Выйти (удалить сессию).
     */
    public function logout(string $token): bool
    {
        $stmt = $this->db->prepare("DELETE FROM sessions WHERE token = ?");
        $stmt->execute([$token]);
        return $stmt->rowCount() > 0;
    }

    /**
     * Создать сессию.
     */
    private function createSession(int $accountId, string $ip): string
    {
        $token = bin2hex(random_bytes(32));
        $expiresAt = date('Y-m-d H:i:s', time() + Config::sessionLifetime());
        $userAgent = substr($_SERVER['HTTP_USER_AGENT'] ?? '', 0, 500);

        $stmt = $this->db->prepare("
            INSERT INTO sessions (account_id, token, expires_at, ip, user_agent)
            VALUES (?, ?, ?, ?, ?)
        ");
        $stmt->execute([$accountId, $token, $expiresAt, $ip, $userAgent]);

        return $token;
    }

    // =========================================================================
    //  EBLAN ID KEY (хранит ключ из браузера)
    // =========================================================================

    /**
     * Сохранить EBLAN ID ключ.
     */
    public function saveEblanIdKey(int $accountId, string $key): bool
    {
        // Совместимость с PHP < 8.0 (str_starts_with появился в PHP 8)
        if (substr($key, 0, 4) !== 'ebl_') {
            return false;
        }
        // Ограничиваем длину — защита от раздувания хранилища (abuse MEDIUMTEXT).
        if (strlen($key) > 8192) {
            return false;
        }
        $stmt = $this->db->prepare("UPDATE accounts SET eblan_id_key = ? WHERE id = ?");
        $stmt->execute([$key, $accountId]);
        return $stmt->rowCount() > 0;
    }

    /**
     * Получить EBLAN ID ключ.
     */
    public function getEblanIdKey(int $accountId): ?string
    {
        $stmt = $this->db->prepare("SELECT eblan_id_key FROM accounts WHERE id = ?");
        $stmt->execute([$accountId]);
        $row = $stmt->fetch();
        return $row ? ($row['eblan_id_key'] ?: null) : null;
    }

    /**
     * Удалить EBLAN ID ключ.
     */
    public function clearEblanIdKey(int $accountId): bool
    {
        $stmt = $this->db->prepare("UPDATE accounts SET eblan_id_key = NULL WHERE id = ?");
        $stmt->execute([$accountId]);
        return $stmt->rowCount() > 0;
    }

    // =========================================================================
    //  ХЕЛПЕРЫ
    // =========================================================================

    public function getAccountById(int $id): ?array
    {
        $stmt = $this->db->prepare("
            SELECT id, email, eblan_id_key, email_verified, created_at, created_ip,
                   last_login_at, last_login_ip, hwid, is_banned, ban_reason
            FROM accounts WHERE id = ?
        ");
        $stmt->execute([$id]);
        return $stmt->fetch() ?: null;
    }

    public function getAccountByEmail(string $email): ?array
    {
        $email = $this->normalizeEmail($email);
        $stmt = $this->db->prepare("
            SELECT id, email, eblan_id_key, email_verified, created_at, created_ip,
                   last_login_at, last_login_ip, hwid, is_banned, ban_reason
            FROM accounts WHERE email = ?
        ");
        $stmt->execute([$email]);
        return $stmt->fetch() ?: null;
    }

    private function emailExists(string $email): bool
    {
        $stmt = $this->db->prepare("SELECT 1 FROM accounts WHERE email = ?");
        $stmt->execute([$email]);
        return $stmt->fetch() !== false;
    }

    private function normalizeEmail(string $email): string
    {
        return strtolower(trim($email));
    }

    private function isValidEmail(string $email): bool
    {
        // Длина по RFC + защита от мусора, плюс базовая валидация формата.
        if ($email === '' || strlen($email) > 254) {
            return false;
        }
        return filter_var($email, FILTER_VALIDATE_EMAIL) !== false;
    }

    private function generateCode(): string
    {
        return str_pad((string) random_int(0, 999999), 6, '0', STR_PAD_LEFT);
    }

    private function verifyCode(string $email, string $code): bool
    {
        $stmt = $this->db->prepare("
            SELECT 1 FROM email_codes
            WHERE email = ? AND code = ? AND purpose = 'auth'
              AND expires_at > NOW() AND used = 0
        ");
        $stmt->execute([$email, $code]);
        return $stmt->fetch() !== false;
    }

    private function markCodeUsed(string $email, string $code): void
    {
        $stmt = $this->db->prepare("
            UPDATE email_codes SET used = 1 WHERE email = ? AND code = ? AND purpose = 'auth'
        ");
        $stmt->execute([$email, $code]);
    }

    private function deleteOldCodes(string $email): void
    {
        $stmt = $this->db->prepare("DELETE FROM email_codes WHERE email = ? AND purpose = 'auth'");
        $stmt->execute([$email]);
    }

    /**
     * Возраст (в секундах) самого свежего кода для email.
     * Если кодов нет — возвращает большое число (кулдаун не активен).
     */
    private function recentCodeAge(string $email): int
    {
        $stmt = $this->db->prepare("
            SELECT TIMESTAMPDIFF(SECOND, created_at, NOW()) AS age
            FROM email_codes
            WHERE email = ? AND purpose = 'auth'
            ORDER BY id DESC LIMIT 1
        ");
        $stmt->execute([$email]);
        $row = $stmt->fetch();
        if (!$row || $row['age'] === null) {
            return PHP_INT_MAX;
        }
        return (int) $row['age'];
    }

    /**
     * Превышено ли число попыток ввода кода.
     * Best-effort: если колонки attempts ещё нет (миграция не накатана) —
     * молча возвращаем false, логин при этом продолжает работать.
     */
    private function tooManyAttempts(string $email): bool
    {
        try {
            $stmt = $this->db->prepare("
                SELECT COALESCE(MAX(attempts), 0) AS att
                FROM email_codes
                WHERE email = ? AND purpose = 'auth' AND used = 0 AND expires_at > NOW()
            ");
            $stmt->execute([$email]);
            $row = $stmt->fetch();
            return $row && (int) $row['att'] >= Config::maxCodeAttempts();
        } catch (\Throwable $e) {
            return false;
        }
    }

    /**
     * Зафиксировать неудачную попытку ввода кода.
     * Best-effort — без колонки attempts просто ничего не делает.
     */
    private function registerFailedAttempt(string $email): void
    {
        try {
            $stmt = $this->db->prepare("
                UPDATE email_codes SET attempts = attempts + 1
                WHERE email = ? AND purpose = 'auth' AND used = 0 AND expires_at > NOW()
            ");
            $stmt->execute([$email]);
        } catch (\Throwable $e) {
            // колонки attempts нет — пропускаем
        }
    }

    private function checkIpLimit(string $ip): bool
    {
        $stmt = $this->db->prepare("SELECT registrations FROM ip_limits WHERE ip = ?");
        $stmt->execute([$ip]);
        $row = $stmt->fetch();
        if (!$row) {
            return true;
        }
        return (int) $row['registrations'] < Config::maxRegistrationsPerIp();
    }

    private function incrementIpCount(string $ip): void
    {
        $stmt = $this->db->prepare("
            INSERT INTO ip_limits (ip, registrations, last_attempt)
            VALUES (?, 1, NOW())
            ON DUPLICATE KEY UPDATE registrations = registrations + 1, last_attempt = NOW()
        ");
        $stmt->execute([$ip]);
    }
}
