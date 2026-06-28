<?php
/**
 * Репозиторий обновлений: читает versions.json и rollback.json.
 */

declare(strict_types=1);

final class UpdateRepo
{
    private array $versions;
    private array $rollback;

    public function __construct()
    {
        $this->versions = $this->readJson(Config::versionsFile());
        $this->rollback = $this->readJson(Config::rollbackFile());
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

    /** Полный манифест в формате, совместимом с EBLAN_DEBUG.py */
    public function manifest(): array
    {
        return [
            'branches' => $this->versions['branches'] ?? new stdClass(),
            'rollback' => $this->rollback['versions'] ?? [],
            'meta'     => [
                'api_version' => Config::API_VERSION,
                'updated_at'  => $this->versions['updated_at'] ?? null,
            ],
        ];
    }

    /** Инфа о ветке или null. */
    public function branch(string $name): ?array
    {
        $b = $this->versions['branches'] ?? [];
        return isset($b[$name]) && is_array($b[$name]) ? $b[$name] : null;
    }

    public function branches(): array
    {
        return array_keys($this->versions['branches'] ?? []);
    }

    /**
     * Сравнивает текущую версию клиента с последней в ветке.
     */
    public function check(string $branch, string $current): array
    {
        $info = $this->branch($branch);
        if ($info === null) {
            return [
                'update_available' => false,
                'error'            => 'unknown_branch',
                'branch'           => $branch,
            ];
        }
        $latest = (string) ($info['version'] ?? '');
        return [
            'update_available' => $latest !== '' && $latest !== $current,
            'branch'           => $branch,
            'current'          => $current,
            'latest'           => $latest,
            'info'             => $info,
        ];
    }

    public function rollbackList(): array
    {
        return $this->rollback['versions'] ?? [];
    }
}
