<?php
/**
 * MySQL PDO connection for EBLAN ID.
 * Settings from Config.php.
 */

declare(strict_types=1);

require_once __DIR__ . '/Config.php';

final class Database
{
    private static $pdo = null;

    /**
     * Get PDO instance (lazy init, singleton).
     */
    public static function get(): PDO
    {
        if (self::$pdo !== null) {
            return self::$pdo;
        }

        $host    = Config::dbHost();
        $port    = Config::dbPort();
        $name    = Config::dbName();
        $user    = Config::dbUser();
        $pass    = Config::dbPass();
        $charset = Config::dbCharset();

        $dsn = sprintf(
            'mysql:host=%s;port=%d;dbname=%s;charset=%s',
            $host, $port, $name, $charset
        );

        $options = array(
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,
        );

        self::$pdo = new PDO($dsn, $user, $pass, $options);
        return self::$pdo;
    }

    /**
     * Close connection.
     */
    public static function close(): void
    {
        self::$pdo = null;
    }
}
