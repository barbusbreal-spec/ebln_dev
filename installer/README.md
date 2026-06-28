# EBLAN Browser 6.7 — установщик для Windows

Крутой молодёжный установщик на [Inno Setup](https://jrsoftware.org/isinfo.php).

## Сборка

1. **Собери exe** (нужен Python на Windows):
   ```bat
   installer\build_windows.bat
   ```
   Получится `dist\EBLAN\EBLAN.exe` (PyInstaller, onedir).

2. **Собери установщик** (нужен Inno Setup 6):
   ```bat
   ISCC.exe installer\eblan_setup.iss
   ```
   Получится `installer\Output\EBLAN_Setup_6.7.exe`.

## Что умеет установщик

- Современный визард (WizardStyle=modern) с молодёжными текстами 67
- Иконка `images/EblanSetup.ico`
- Ярлыки: меню «Пуск», рабочий стол, панель задач (опц.)
- Галка «Долбаёбские функции сразу» → пишет `HKCU\Software\EBLAN\DolboebMode=1`
- Галка «Автозапуск при старте Windows»
- Запуск EBLAN сразу после установки
- Корректная деинсталляция (ярлыки/реестр чистятся)

> Куки и данные браузера сохраняются в профиле пользователя
> (`%APPDATA%\EBLAN\webdata`) и при удалении не трогаются.
