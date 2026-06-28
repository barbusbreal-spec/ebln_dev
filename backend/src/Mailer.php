<?php
/**
 * Send email with confirmation code.
 * Settings from Config.php.
 */

declare(strict_types=1);

require_once __DIR__ . '/Config.php';

final class Mailer
{
    /**
     * Send email with 6-digit code.
     */
    public static function sendCode(string $to, string $code, string $purpose = 'register'): bool
    {
        $subjects = array(
            'register' => 'Kod registracii EBLAN ID',
            'login'    => 'Kod vhoda EBLAN ID',
        );
        $subject = isset($subjects[$purpose]) ? $subjects[$purpose] : $subjects['login'];

        $body = self::buildCodeEmail($code, $purpose);

        return self::send($to, $subject, $body);
    }

    /**
     * Send arbitrary email.
     */
    public static function send(string $to, string $subject, string $htmlBody): bool
    {
        $fromEmail = Config::mailFrom();
        $fromName  = Config::mailFromName();

        // Check SMTP settings
        $smtpHost = Config::smtpHost();
        if ($smtpHost !== '') {
            return self::sendViaSMTP($to, $subject, $htmlBody, $fromEmail, $fromName);
        }

        // Fallback to mail()
        return self::sendViaMail($to, $subject, $htmlBody, $fromEmail, $fromName);
    }

    /**
     * Build HTML email with code.
     */
    private static function buildCodeEmail(string $code, string $purpose): string
    {
        $purposeText = array(
            'register' => 'registracii',
            'login'    => 'vhoda',
        );
        $text = isset($purposeText[$purpose]) ? $purposeText[$purpose] : 'vhoda';

        $html = '<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>EBLAN ID</title></head>
<body>
<h1>EBLAN Browser</h1>
<p>Tvoy kod dlya ' . $text . ':</p>
<h2>' . $code . '</h2>
<p>Kod deystvitelen 10 minut.</p>
<hr>
<p>Esli ty ne zaprosil etot kod - prosto proignoriruy.</p>
</body>
</html>';

        return $html;
    }

    /**
     * Send via built-in mail().
     */
    private static function sendViaMail(
        string $to,
        string $subject,
        string $body,
        string $fromEmail,
        string $fromName
    ): bool {
        $headers = array(
            'MIME-Version: 1.0',
            'Content-Type: text/html; charset=utf-8',
            'From: ' . $fromName . ' <' . $fromEmail . '>',
            'Reply-To: ' . $fromEmail,
            'X-Mailer: EBLAN-Backend/1.0',
        );

        return @mail($to, $subject, $body, implode("\r\n", $headers));
    }

    /**
     * Send via SMTP directly.
     */
    private static function sendViaSMTP(
        string $to,
        string $subject,
        string $body,
        string $fromEmail,
        string $fromName
    ): bool {
        $host   = Config::smtpHost();
        $port   = Config::smtpPort();
        $user   = Config::smtpUser();
        $pass   = Config::smtpPass();
        $secure = Config::smtpSecure();

        // Защита от SMTP header / command injection: вырезаем CR/LF из адресов и имени.
        $to        = self::sanitizeHeader($to);
        $fromEmail = self::sanitizeHeader($fromEmail);
        $fromName  = self::sanitizeHeader($fromName);
        if ($to === '' || $fromEmail === '') {
            error_log('SMTP: invalid to/from after sanitize');
            return false;
        }

        $socket = null;
        try {
            $prefix = ($secure === 'ssl') ? 'ssl://' : '';
            $socket = @fsockopen($prefix . $host, $port, $errno, $errstr, 15);
            if (!$socket) {
                error_log('SMTP connect failed: ' . $errstr . ' (' . $errno . ')');
                return false;
            }
            stream_set_timeout($socket, 15);

            // Приветствие сервера.
            if (!self::expect($socket, 220, 'greeting')) {
                return false;
            }

            $ehlo = 'EHLO ' . (gethostname() ?: 'localhost');

            // EHLO
            self::cmd($socket, $ehlo);
            if (!self::expect($socket, 250, 'EHLO')) {
                return false;
            }

            // STARTTLS — обязательно проверяем, что шифрование реально поднялось.
            if ($secure === 'tls') {
                self::cmd($socket, 'STARTTLS');
                if (!self::expect($socket, 220, 'STARTTLS')) {
                    return false;
                }
                $crypto = @stream_socket_enable_crypto(
                    $socket,
                    true,
                    STREAM_CRYPTO_METHOD_TLS_CLIENT
                );
                if ($crypto !== true) {
                    error_log('SMTP: TLS handshake failed');
                    return false;
                }
                // Повторный EHLO уже по шифрованному каналу.
                self::cmd($socket, $ehlo);
                if (!self::expect($socket, 250, 'EHLO/TLS')) {
                    return false;
                }
            }

            // AUTH LOGIN — каждый шаг с проверкой кода ответа.
            if ($user !== '') {
                self::cmd($socket, 'AUTH LOGIN');
                if (!self::expect($socket, 334, 'AUTH LOGIN')) {
                    return false;
                }
                self::cmd($socket, base64_encode($user));
                if (!self::expect($socket, 334, 'AUTH user')) {
                    return false;
                }
                self::cmd($socket, base64_encode($pass));
                if (!self::expect($socket, 235, 'AUTH pass')) {
                    return false;
                }
            }

            // MAIL FROM
            self::cmd($socket, 'MAIL FROM:<' . $fromEmail . '>');
            if (!self::expect($socket, 250, 'MAIL FROM')) {
                return false;
            }

            // RCPT TO
            self::cmd($socket, 'RCPT TO:<' . $to . '>');
            // 250 либо 251 (will forward) считаем успехом.
            if (!self::expect($socket, [250, 251], 'RCPT TO')) {
                return false;
            }

            // DATA
            self::cmd($socket, 'DATA');
            if (!self::expect($socket, 354, 'DATA')) {
                return false;
            }

            // Заголовки и тело письма.
            $headers = array(
                'Date: ' . date('r'),
                'From: ' . ($fromName !== '' ? $fromName . ' ' : '') . '<' . $fromEmail . '>',
                'To: <' . $to . '>',
                'Subject: =?utf-8?B?' . base64_encode($subject) . '?=',
                'MIME-Version: 1.0',
                'Content-Type: text/html; charset=utf-8',
                'Content-Transfer-Encoding: 8bit',
            );

            // Dot-stuffing: строки, начинающиеся с точки, экранируем (RFC 5321).
            $safeBody = preg_replace('/^\./m', '..', str_replace("\r\n", "\n", $body));
            $safeBody = str_replace("\n", "\r\n", (string) $safeBody);

            $message = implode("\r\n", $headers) . "\r\n\r\n" . $safeBody . "\r\n.";
            self::cmd($socket, $message);
            if (!self::expect($socket, 250, 'end-of-DATA')) {
                return false;
            }

            self::cmd($socket, 'QUIT');
            return true;
        } catch (Throwable $e) {
            error_log('SMTP error: ' . $e->getMessage());
            return false;
        } finally {
            if (is_resource($socket)) {
                @fclose($socket);
            }
        }
    }

    /**
     * Отправить SMTP-команду (строку) с завершающим CRLF.
     */
    private static function cmd($socket, string $line): void
    {
        fwrite($socket, $line . "\r\n");
    }

    /**
     * Прочитать (возможно многострочный) ответ SMTP-сервера и сверить код.
     * $expected — int или массив допустимых кодов.
     */
    private static function expect($socket, $expected, string $stage): bool
    {
        $code = self::readResponse($socket);
        $ok = is_array($expected)
            ? in_array($code, $expected, true)
            : $code === $expected;
        if (!$ok) {
            error_log('SMTP: unexpected ' . $code . ' at ' . $stage . ' (want ' . json_encode($expected) . ')');
        }
        return $ok;
    }

    /**
     * Считать многострочный ответ, вернуть числовой код первой строки.
     */
    private static function readResponse($socket): int
    {
        $code = 0;
        while (($line = fgets($socket, 515)) !== false) {
            $code = (int) substr($line, 0, 3);
            // Многострочный ответ: "250-..." продолжается, "250 ..." — последняя строка.
            if (!isset($line[3]) || $line[3] === ' ') {
                break;
            }
        }
        return $code;
    }

    /**
     * Убираем CR/LF и обрезаем — защита от инъекции SMTP-команд/заголовков.
     */
    private static function sanitizeHeader(string $value): string
    {
        return trim(str_replace(["\r", "\n", "\0"], '', $value));
    }
}
