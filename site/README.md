# Сайт EBLAN Browser (eblanbrowser.ru)

«Положил всё на сайт и похуй» — раскладка для хостинга.

## Что куда положить (корень сайта = `site/`)

```
/                      → index.html          (лендинг 6.7)
/sh/installeblan.sh    → site/sh/installeblan.sh   (установщик Linux/macOS)
/dl/eblan.zip          → ← СЮДА ПОЛОЖИ ZIP с исходниками браузера
/changelog.html        → (опц.) pages/changelog.html
```

То есть: заливаешь содержимое папки `site/` в корень `eblanbrowser.ru`,
и **кладёшь zip браузера в `/dl/eblan.zip`**. Всё.

## Как собрать zip браузера

Запакуй корень репозитория (с `EBLAN_DEBUG.py`, `images/`, `plugins/`,
`requirements.txt`) в zip и положи как `/dl/eblan.zip`:

```bash
zip -r eblan.zip EBLAN_DEBUG.py images plugins requirements.txt README.md
# → загрузи на хостинг как /dl/eblan.zip
```

Установщик сам найдёт `EBLAN_DEBUG.py` внутри архива (даже если он во вложенной папке).

## Команды установки (уже зашиты в index.html)

- **Linux:** `curl -sSL https://eblanbrowser.ru/sh/installeblan.sh | sudo bash`
- **macOS:** `curl -sSL https://eblanbrowser.ru/sh/installeblan.sh | bash`
- **Windows:** кнопка качает `https://eblanbrowser.ru/dl/eblan.zip`

## Переопределить источник zip (если хостишь zip в другом месте)

```bash
curl -sSL https://eblanbrowser.ru/sh/installeblan.sh | EBLAN_ZIP_URL=https://твой-url/eblan.zip sudo -E bash
```

## Прочее
- Установка в `$HOME` без sudo: `... | EBLAN_SCOPE=user bash`
- Удаление: `... | EBLAN_UNINSTALL=1 sudo bash`
- Настройки/куки браузера: `~/.eblan-browser` (Linux/mac), `%APPDATA%\EBLAN` (Win) — установщик их не трогает.
