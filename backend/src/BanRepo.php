<?php
/**
 * Репозиторий банов EBLAN Browser.
 *
 * Хранит:
 *   data/bans.json   — { "users": { "<hwid>": {"profile":..., "reason":...,
 *                                              "banned_at":..., "active":bool,
 *                                              "last_seen":..., "last_ip":...} } }
 *   data/admin.json  — { "password": "..." }   секретный пароль админа
 *
 * Любая машина регистрируется при первом heartbeat и далее видна в админке.
 */

declare(strict_types=1);

final class BanRepo
{
    public function __construct()
    {
        $dir = Config::dataDir();
        if (!is_dir($dir)) {
            @mkdir($dir, 0775, true);
        }
        // Создадим пустые файлы при первом запуске.
        $this->ensureFile(self::usersFile(), ['users' => new stdClass()]);
        $this->ensureFile(self::adminFile(), ['password' => 'allah671488228']);
    }

    public static function usersFile(): string
    {
        return Config::dataDir() . DIRECTORY_SEPARATOR . 'bans.json';
    }

    public static function adminFile(): string
    {
        return Config::dataDir() . DIRECTORY_SEPARATOR . 'admin.json';
    }

    private function ensureFile(string $path, array $default): void
    {
        if (!file_exists($path)) {
            @file_put_contents(
                $path,
                json_encode($default, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)
            );
        }
    }

    private function readJson(string $path): array
    {
        if (!is_readable($path)) {
            return [];
        }
        $raw = file_get_contents($path);
        if ($raw === false) {
            return [];
        }
        $data = json_decode($raw, true);
        return is_array($data) ? $data : [];
    }

    private function writeJson(string $path, array $payload): bool
    {
        $tmp = $path . '.tmp';
        $ok = @file_put_contents(
            $tmp,
            json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)
        );
        if ($ok === false) {
            return false;
        }
        return @rename($tmp, $path);
    }

    /** ----- Админ-аутентификация ----- */
    public function adminPassword(): string
    {
        $data = $this->readJson(self::adminFile());
        return (string) ($data['password'] ?? '');
    }

    public function checkAdmin(string $given): bool
    {
        $expected = $this->adminPassword();
        if ($expected === '') {
            return false;
        }
        // hash_equals защищает от тайминг-атак
        return hash_equals($expected, $given);
    }

    /** ----- Пользователи ----- */
    private function loadUsers(): array
    {
        $data = $this->readJson(self::usersFile());
        $users = $data['users'] ?? [];
        // PHP json_decode превращает пустой объект в array — оставим как есть.
        return is_array($users) ? $users : [];
    }

    private function saveUsers(array $users): bool
    {
        // Гарантируем, что users остаётся объектом в JSON, даже если пуст.
        $payload = ['users' => empty($users) ? new stdClass() : $users];
        return $this->writeJson(self::usersFile(), $payload);
    }

    /**
     * Регистрирует/обновляет пользователя по hwid.
     * Возвращает запись пользователя.
     */
    public function heartbeat(string $hwid, string $profile, string $ip = '', string $realIp = '', string $localIp = '', array $components = []): array
    {
        $hwid = self::normHwid($hwid);
        if ($hwid === '') {
            return [];
        }
        $profile = self::clamp($profile, 64);
        $realIp  = self::clampIp($realIp);
        $localIp = self::clamp($localIp, 120);
        $users = $this->loadUsers();
        $now = time();
        $rec = $users[$hwid] ?? [
            'hwid'      => $hwid,
            'profile'   => $profile,
            'reason'    => '',
            'active'    => false,
            'banned_at' => null,
            'first_seen'=> $now,
        ];
        // Имя профиля можем обновлять (вдруг юзер переименовал)
        if ($profile !== '') {
            $rec['profile'] = $profile;
        }
        $rec['last_seen'] = $now;
        if ($ip !== '') {
            $rec['last_ip'] = $ip;
        }
        // Реальный IP клиента (в обход VPN/прокси) и локальные адреса.
        if ($realIp !== '') {
            $rec['real_ip'] = $realIp;
        }
        if ($localIp !== '') {
            $rec['local_ip'] = $localIp;
        }
        // Полный отпечаток железа + извлечённые «сильные» токены для fuzzy-match.
        if (!empty($components)) {
            $rec['components'] = self::sanitizeComponents($components);
            $rec['tokens']     = self::tokensFromComponents($rec['components']);
        }
        // Если такого hwid не было — назначим first_seen
        if (!isset($rec['first_seen'])) {
            $rec['first_seen'] = $now;
        }

        // Анти-обход: если железо совпало с уже забаненной машиной — авто-бан.
        $rec = $this->applyFuzzyAutoBan($rec, $hwid, $users, $now);

        $users[$hwid] = $rec;
        $this->saveUsers($users);
        return $rec;
    }

    /**
     * Сохранить отпечаток железа для hwid и сразу проверить нечёткое
     * совпадение с забаненными (вызывается из check_ban на старте клиента).
     */
    public function ingestComponents(string $hwid, array $components): array
    {
        $hwid = self::normHwid($hwid);
        if ($hwid === '' || empty($components)) {
            return [];
        }
        $users = $this->loadUsers();
        $now = time();
        $rec = $users[$hwid] ?? [
            'hwid'      => $hwid,
            'profile'   => '',
            'reason'    => '',
            'active'    => false,
            'banned_at' => null,
            'first_seen'=> $now,
        ];
        $rec['components'] = self::sanitizeComponents($components);
        $rec['tokens']     = self::tokensFromComponents($rec['components']);
        $rec['last_seen']  = $now;
        $rec = $this->applyFuzzyAutoBan($rec, $hwid, $users, $now);
        $users[$hwid] = $rec;
        $this->saveUsers($users);
        return $rec;
    }

    /**
     * Если запись ещё не забанена, но её железо совпало с активно
     * забаненной машиной (≥ порога токенов) — ставим авто-бан.
     */
    private function applyFuzzyAutoBan(array $rec, string $hwid, array $users, int $now): array
    {
        if (!empty($rec['active']) || empty($rec['tokens'])) {
            return $rec;
        }
        $match = $this->matchBannedByTokens($rec['tokens'], $hwid, $users);
        if ($match !== null) {
            $rec['active']       = true;
            $rec['banned_at']    = $now;
            $rec['auto_banned']  = true;
            $rec['matched_hwid'] = (string) ($match['hwid'] ?? '');
            $rec['reason']       = 'авто-бан: совпадение железа с '
                . substr((string) ($match['hwid'] ?? ''), 0, 12) . '… ('
                . (string) ($match['reason'] ?? '') . ')';
        }
        return $rec;
    }

    /**
     * Возвращает {banned: bool, reason: ..., profile: ...} для hwid.
     * Без побочных эффектов.
     */
    public function checkBan(string $hwid): array
    {
        $hwid = self::normHwid($hwid);
        $users = $this->loadUsers();
        $rec = $users[$hwid] ?? null;

        // Точный бан по hwid.
        if ($rec && !empty($rec['active'])) {
            return [
                'banned'    => true,
                'reason'    => (string) ($rec['reason'] ?? ''),
                'profile'   => (string) ($rec['profile'] ?? ''),
                'banned_at' => $rec['banned_at'] ?? null,
            ];
        }

        // Нечёткое совпадение: железо этой машины совпало с забаненной?
        $tokens = ($rec && !empty($rec['tokens']) && is_array($rec['tokens']))
            ? $rec['tokens'] : [];
        if (!empty($tokens)) {
            $match = $this->matchBannedByTokens($tokens, $hwid, $users);
            if ($match !== null) {
                return [
                    'banned'    => true,
                    'reason'    => (string) ($match['reason'] ?? ''),
                    'profile'   => (string) ($rec['profile'] ?? ''),
                    'banned_at' => $match['banned_at'] ?? null,
                    'matched'   => true,
                ];
            }
        }

        return [
            'banned'    => false,
            'reason'    => '',
            'profile'   => $rec ? (string) ($rec['profile'] ?? '') : '',
            'banned_at' => $rec['banned_at'] ?? null,
        ];
    }

    /**
     * Ищет активно забаненную запись, у которой ≥ порога общих токенов
     * железа с переданным набором. Возвращает запись или null.
     */
    private function matchBannedByTokens(array $tokens, string $selfHwid, array $users): ?array
    {
        $threshold = Config::hwidMatchThreshold();
        $mine = array_flip($tokens);
        $best = null;
        $bestCount = 0;
        foreach ($users as $hwid => $u) {
            if ($hwid === $selfHwid || empty($u['active'])) {
                continue;
            }
            $theirs = $u['tokens'] ?? [];
            if (!is_array($theirs) || empty($theirs)) {
                continue;
            }
            $common = 0;
            foreach ($theirs as $t) {
                if (isset($mine[$t])) {
                    $common++;
                }
            }
            if ($common >= $threshold && $common > $bestCount) {
                $bestCount = $common;
                $best = $u;
            }
        }
        return $best;
    }

    /** Все пользователи (для админки). */
    public function listUsers(): array
    {
        $users = $this->loadUsers();
        return array_values($users);
    }

    /** Бан/обновление причины. Создаёт пользователя, если не было. */
    public function ban(string $hwid, string $profile, string $reason): array
    {
        $hwid = self::normHwid($hwid);
        if ($hwid === '') {
            return [];
        }
        $profile = self::clamp($profile, 64);
        $reason  = self::clamp($reason, 500);
        $users = $this->loadUsers();
        $rec = $users[$hwid] ?? [
            'hwid'      => $hwid,
            'profile'   => $profile,
            'first_seen'=> time(),
        ];
        if ($profile !== '') {
            $rec['profile'] = $profile;
        }
        $rec['reason']    = $reason;
        $rec['active']    = true;
        $rec['banned_at'] = time();
        $users[$hwid] = $rec;
        $this->saveUsers($users);
        return $rec;
    }

    /** Снятие бана. Запись остаётся в списке. */
    public function unban(string $hwid): bool
    {
        $hwid = self::normHwid($hwid);
        $users = $this->loadUsers();
        if (!isset($users[$hwid])) {
            return false;
        }
        $users[$hwid]['active'] = false;
        $users[$hwid]['unbanned_at'] = time();
        $this->saveUsers($users);
        return true;
    }

    /** Полное удаление пользователя из списка. */
    public function forget(string $hwid): bool
    {
        $hwid = self::normHwid($hwid);
        $users = $this->loadUsers();
        if (!isset($users[$hwid])) {
            return false;
        }
        unset($users[$hwid]);
        $this->saveUsers($users);
        return true;
    }

    /** Смена админ-пароля. */
    public function setAdminPassword(string $newPassword): bool
    {
        if ($newPassword === '') {
            return false;
        }
        return $this->writeJson(self::adminFile(), ['password' => $newPassword]);
    }

    /**
     * Нормализация HWID: только безопасные символы, максимум 64 (как в схеме БД).
     * Защита от мусора/раздувания bans.json через публичный heartbeat.
     */
    private static function normHwid(string $hwid): string
    {
        $hwid = trim($hwid);
        // Допускаем буквы/цифры и типичные разделители hardware-id.
        $hwid = preg_replace('/[^A-Za-z0-9._:-]/', '', $hwid) ?? '';
        return substr($hwid, 0, 64);
    }

    /** Обрезает строку до максимальной длины (защита от гигантских значений). */
    private static function clamp(string $value, int $max): string
    {
        $value = trim($value);
        return $max > 0 ? mb_substr($value, 0, $max) : $value;
    }

    /** Возвращает валидный IP (IPv4/IPv6) или '' — если клиент прислал мусор. */
    private static function clampIp(string $value): string
    {
        $value = trim(substr($value, 0, 64));
        if ($value === '') {
            return '';
        }
        if (filter_var($value, FILTER_VALIDATE_IP) !== false) {
            return $value;
        }
        // Пытаемся выдернуть первый валидный IPv4 из строки.
        if (preg_match('/\b\d{1,3}(?:\.\d{1,3}){3}\b/', $value, $m)
            && filter_var($m[0], FILTER_VALIDATE_IP) !== false) {
            return $m[0];
        }
        return '';
    }

    /** Нормализация одного значения компонента: alnum, верхний регистр, обрезка. */
    private static function normComponent(string $value): string
    {
        $value = preg_replace('/[^A-Za-z0-9]/', '', $value) ?? '';
        return substr(strtoupper($value), 0, 64);
    }

    /**
     * Приводим присланный клиентом набор компонентов к безопасному виду
     * (только известные ключи, нормализованные значения, ограниченные списки).
     */
    private static function sanitizeComponents(array $components): array
    {
        $scalarKeys = ['board', 'bios_uuid', 'cpu_id', 'cpu_model', 'machine_guid', 'volume'];
        $listKeys   = ['disks', 'macs', 'ram', 'monitors', 'gpus'];
        $out = [];
        foreach ($scalarKeys as $k) {
            if (isset($components[$k]) && is_scalar($components[$k])) {
                $v = ($k === 'cpu_model' || $k === 'gpus')
                    ? self::clamp((string) $components[$k], 80)
                    : self::normComponent((string) $components[$k]);
                if ($v !== '') {
                    $out[$k] = $v;
                }
            }
        }
        foreach ($listKeys as $k) {
            if (!isset($components[$k]) || !is_array($components[$k])) {
                continue;
            }
            $vals = [];
            foreach (array_slice($components[$k], 0, 12) as $item) {
                if (!is_scalar($item)) {
                    continue;
                }
                $v = ($k === 'gpus')
                    ? self::clamp((string) $item, 80)
                    : self::normComponent((string) $item);
                if ($v !== '' && !in_array($v, $vals, true)) {
                    $vals[] = $v;
                }
            }
            if ($vals) {
                $out[$k] = $vals;
            }
        }
        return $out;
    }

    /**
     * Извлекаем «сильные» (уникальные) токены железа для нечёткого совпадения.
     * Описательные поля (cpu_model, gpus) НЕ используем — они не уникальны
     * и дали бы ложные совпадения у разных машин с одинаковой моделью.
     */
    private static function tokensFromComponents(array $components): array
    {
        $tokens = [];
        $scalarMap = [
            'board' => 'b', 'bios_uuid' => 'u', 'cpu_id' => 'c',
            'machine_guid' => 'g', 'volume' => 'v',
        ];
        foreach ($scalarMap as $key => $prefix) {
            if (!empty($components[$key])) {
                $tokens[] = $prefix . ':' . $components[$key];
            }
        }
        $listMap = ['disks' => 'd', 'macs' => 'm', 'ram' => 'r', 'monitors' => 'n'];
        foreach ($listMap as $key => $prefix) {
            if (!empty($components[$key]) && is_array($components[$key])) {
                foreach ($components[$key] as $v) {
                    $tokens[] = $prefix . ':' . $v;
                }
            }
        }
        $tokens = array_values(array_unique($tokens));
        sort($tokens);
        return $tokens;
    }
}
