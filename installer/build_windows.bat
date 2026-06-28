@echo off
REM ============================================================
REM  Сборка EBLAN Browser 6.7 под Windows (PyInstaller)
REM  Потом собери установщик: ISCC.exe installer\eblan_setup.iss
REM ============================================================
setlocal
cd /d "%~dp0\.."

echo [1/3] Ставлю зависимости...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo [2/3] Собираю EBLAN.exe (onedir)...
pyinstaller --noconfirm --clean ^
  --name EBLAN ^
  --windowed ^
  --icon images\EblanSetup.ico ^
  --add-data "images;images" ^
  --add-data "plugins;plugins" ^
  EBLAN_DEBUG.py

echo [3/3] Готово. Билд: dist\EBLAN\EBLAN.exe
echo Теперь собери установщик:  ISCC.exe installer\eblan_setup.iss
endlocal
