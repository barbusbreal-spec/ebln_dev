# EBLAN Update Backend

Мини-бекенд обновлений для EBLAN Browser. Пишет JSON, держится на PHP 7.4+.

## 🔒 Security (важно)

Бэкенд хардернут от типовых атак. Что нужно знать при деплое:

- **Ошибки наружу не текут.** Текст исключений пишется только в server log.
  Чтобы временно видеть детали в ответе — выставь `APP_DEBUG=1` (на проде держи `0`).
- **Анти-брутфорс кода.** Код подтверждения (6 цифр) блокируется после
  `MAX_CODE_ATTEMPTS` неверных попыток (по умолчанию 5).
- **Кулдаун на отправку кода.** Повторный код на тот же email не отправится
  чаще, чем раз в `CODE_RESEND_COOLDOWN` секунд (по умолчанию 60) —
  защита от email-бомбинга и SMTP-абьюза.
- **SMTP-отправка чинена:** проверяются коды ответов сервера на каждом шаге,
  обязательная проверка TLS-хендшейка, dot-stuffing тела и защита от
  header/command-инъекции в адресах.
- **Security-заголовки** (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`) ставятся на каждый ответ API.
- **HWID санитизируется** (только `A-Za-z0-9._:-`, максимум 64 символа) —
  публичный `heartbeat` нельзя завалить мусором.
- `data/` закрыт `.htaccess`, секреты и `admin.json`/`bans.json` — в `.gitignore`.

### Анти-обход бана (нечёткое совпадение железа)

Клиент шлёт в `heartbeat`/`check_ban` поле `components` (JSON) с набором
аппаратных идентификаторов: серийники дисков, MAC физических NIC, UUID/серийник
матплаты, MachineGuid/machine-id, серийник тома, RAM, EDID мониторов и т.д.

Сервер хранит их и извлекает «сильные» (уникальные) токены. Машина считается
**той же**, если у неё ≥ `HWID_MATCH_THRESHOLD` (по умолчанию 3) общих токенов
с уже забаненной. Тогда обходчик авто-банится (`auto_banned`, в админке —
статус «БАН (авто)» и ссылка на исходный hwid).

Почему так, а не один общий хэш: единый хэш из всего железа ломается при смене
любой железки/дуалбуте и легко обходится. Нечёткое совпадение переживает смену
hostname/одного компонента и узнаёт дуалбут (диски совпадают). Основной HWID
при этом остаётся стабильным (см. `get_hardware_id` в клиенте).

Описательные поля (модель CPU, названия GPU) в матчинге **не участвуют** —
они не уникальны и дали бы ложные баны. Порог регулируется
`HWID_MATCH_THRESHOLD` (меньше — строже ловит, но выше риск ложных совпадений).

### Миграция БД (анти-брутфорс)

Для уже существующих баз нужно добавить колонку попыток (новые ставятся
из `schema.sql` автоматически):

```sql
ALTER TABLE `email_codes`
  ADD COLUMN `attempts` SMALLINT UNSIGNED NOT NULL DEFAULT 0 AFTER `used`;
```

Без миграции логин продолжит работать — анти-брутфорс просто не активируется
(degrade gracefully), пока колонку не добавишь.

## Структура

```
backend/
├── public/          # корень веб-сервера (DocumentRoot)
│   ├── index.php    # единая точка входа API, разбирает ?route=
│   ├── admin.php    # web-админка банов (HTML без CSS, логин по паролю)
│   └── .htaccess    # красивые /api/* и /admin URL (Apache mod_rewrite)
├── src/
│   ├── Config.php       # ВСЕ настройки: БД, SMTP, CORS, кеш
│   ├── Response.php     # JSON-ответы
│   ├── BanRepo.php      # репозиторий банов (bans.json + admin.json)
│   ├── UpdateRepo.php   # чтение data/*.json
│   ├── Database.php     # MySQL PDO соединение (берёт настройки из Config)
│   ├── Mailer.php       # отправка email с кодами (берёт SMTP из Config)
│   └── AccountRepo.php  # EBLAN ID аккаунты (без пароля!)
├── sql/
│   └── schema.sql       # MySQL схема для аккаунтов
└── data/
    ├── versions.json    # ветки (main / public_beta / closed_beta)
    ├── rollback.json    # список версий для отката
    ├── bans.json        # юзеры и баны (создаётся автоматически)
    └── admin.json       # пароль админки (создаётся автоматически)
```

## Настройка

**ВСЕ настройки в одном файле** — `src/Config.php`:

```php
// База данных MySQL
const DB_HOST = 'localhost';
const DB_PORT = 3306;
const DB_NAME = 'eblan_browser';
const DB_USER = 'root';
const DB_PASS = '';

// SMTP для отправки кодов
const SMTP_ENABLED = true;  // false = php mail()
const SMTP_HOST = 'smtp.gmail.com';
const SMTP_PORT = 587;
const SMTP_USER = 'your@gmail.com';
const SMTP_PASS = 'app-password';
const SMTP_FROM_EMAIL = 'noreply@eblan.browser';
const SMTP_FROM_NAME = 'EBLAN ID';

// Ограничения
const IP_REGISTRATION_LIMIT = 1;  // макс аккаунтов с одного IP
const CODE_EXPIRY_MINUTES = 10;   // срок действия кода
const SESSION_DAYS = 30;          // срок сессии
```

## EBLAN ID Аккаунты — БЕЗ ПАРОЛЕЙ

Авторизация только через **email + 6-значный код**:

1. Юзер вводит email
2. На почту приходит код (123456)
3. Юзер вводит код → залогинен

Если email новый — аккаунт создаётся автоматически.  
**Ограничение:** с одного IP можно зарегистрировать только 1 аккаунт.

### Endpoints

| Метод | URL                                    | Описание                                |
|-------|----------------------------------------|-----------------------------------------|
| POST  | `/api/auth_start`  body: `email`       | Отправить код на email (регистрация ИЛИ логин) |
| POST  | `/api/auth_complete`  body: `email`, `code` | Подтвердить код → получить токен    |
| GET   | `/api/session?token=...`               | Проверить сессию                        |
| POST  | `/api/logout`  body: `token`           | Выйти                                   |
| POST  | `/api/save_eblan_id_key`  body: `token`, `key` | Сохранить EBLAN ID ключ         |
| GET   | `/api/get_eblan_id_key?token=...`      | Получить EBLAN ID ключ                  |
| POST  | `/api/clear_eblan_id_key`  body: `token` | Удалить ключ                          |

## Деплой

### Shared hosting (serv00, beget, etc.)

1. Заливай всю папку `backend/` куда угодно.
2. Точка входа — `backend/public/index.php`.
3. **Отредактируй `src/Config.php`** — впиши свои данные БД и SMTP.
4. Выполни `sql/schema.sql` в своей MySQL базе.
5. Если есть `mod_rewrite`, получаешь `/api/auth_start`, `/api/auth_complete` и т.д.

### nginx (важно!)

nginx **не читает `.htaccess`** — это файл только для Apache. Поэтому на nginx
красивые URL `/api/<route>` сами по себе не работают и сервер отдаёт сырой
`403 Forbidden` на `/api/check_ban` и прочие. Два варианта:

- **Ничего не настраивать.** Указывай API base прямо на `index.php`
  (`https://host/.../public/index.php`) — клиент ходит через
  `index.php?route=<route>`, и всё работает без rewrite. Клиент к тому же сам
  падает на `index.php` при 403, даже если base задан в форме `/api/*`.
- **Включить красивые URL.** Возьми готовый конфиг
  `public/nginx.conf.example` (аналог `.htaccess`: `/api/<name>` →
  `index.php?route=<name>`, `/admin` → `admin.php`, `data/` закрыт).

### MySQL схема

```bash
mysql -u root -p eblan_browser < sql/schema.sql
```

## Баны по железу

При первом запуске создаётся `data/admin.json` с дефолтным паролем `eblan-666-admin`. **Поменяй его** через `/api/admin_password` или вручную.

### Endpoints (обновления и баны)

| Метод | URL                                                  | Описание                                |
|-------|------------------------------------------------------|-----------------------------------------|
| GET   | `/api/ping`                                          | Жив ли бекенд                           |
| GET   | `/api/manifest`                                      | Полный манифест                         |
| GET   | `/api/branches`                                      | Список доступных веток                  |
| GET   | `/api/check?branch=main&current=R1.0.101`            | Есть ли обновление                      |
| GET   | `/api/rollback`                                      | Список версий для отката                |
| POST  | `/api/heartbeat`  body: `hwid`, `profile`            | Регистрация юзера                       |
| GET   | `/api/check_ban?hwid=...`                            | Публичная проверка бана                 |
| GET   | `/api/bans?password=...`                             | **Админ:** список юзеров                |
| POST  | `/api/ban?password=&hwid=&profile=&reason=`          | **Админ:** забанить                     |
| POST  | `/api/unban?password=&hwid=`                         | **Админ:** снять бан                    |
| POST  | `/api/forget?password=&hwid=`                        | **Админ:** удалить запись               |
| POST  | `/api/admin_password?password=&new=`                 | **Админ:** сменить пароль               |

## EBLAN ID Key

**Ключ генерируется браузером** (`export_eblanid()`) — это `ebl_<base64(zlib(json))>`. Бэкенд просто хранит его для синхронизации между устройствами.

### Как использовать

1. Юзер в браузере делает «Экспорт EBLAN ID» → получает ключ `ebl_...`
2. Логинится в аккаунт и сохраняет ключ: `POST /api/save_eblan_id_key`
3. На другом устройстве логинится и получает ключ: `GET /api/get_eblan_id_key`
4. Вставляет ключ в браузер через «Импорт EBLAN ID»
