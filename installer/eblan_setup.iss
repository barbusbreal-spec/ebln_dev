; ============================================================
;  EBLAN Browser 6.7 — крутой молодёжный установщик (Inno Setup)
;  Собери: ISCC.exe installer\eblan_setup.iss
;  Перед этим собери EBLAN.exe (см. installer\build_windows.bat).
; ============================================================

#define AppName "EBLAN Browser"
#define AppVer "6.7"
#define AppPublisher "EblanSoft"
#define AppURL "https://eblansoft.ru"
#define AppExe "EBLAN.exe"

[Setup]
AppId={{E6LAN-6700-67BR-0WSR-EBLAN6720677}
AppName={#AppName}
AppVersion={#AppVer}
AppVerName={#AppName} {#AppVer} (67)
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
DefaultDirName={autopf}\EBLAN
DefaultGroupName=EBLAN Browser
DisableProgramGroupPage=yes
OutputBaseFilename=EBLAN_Setup_6.7
SetupIconFile=..\images\EblanSetup.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExe}
DisableWelcomePage=no

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Messages]
ru.WelcomeLabel1=Йо! Сейчас поставим [name] 6.7 🐐
ru.WelcomeLabel2=Самый молодёжный браузер 67 с защитой Минцифры, Еблан Секьюр, гейминг-режимом и EblanBoost™.%n%nЖми «Далее», не тормози.
ru.FinishedHeadingLabel=EBLAN 6.7 установлен, красава 🔥
ru.ClickFinish=Жми «Завершить» и врубай вайб.

[Tasks]
Name: "desktopicon"; Description: "Иконка на рабочем столе"; GroupDescription: "Ярлыки:"
Name: "quicklaunchicon"; Description: "Ярлык в панели задач"; GroupDescription: "Ярлыки:"; Flags: unchecked
Name: "dolboeb"; Description: "Включить долбаёбские функции сразу (госреклама, хаос и т.д.)"; GroupDescription: "Опции 67:"; Flags: unchecked
Name: "autostart"; Description: "Запускать EBLAN при старте Windows"; GroupDescription: "Опции 67:"; Flags: unchecked

[Files]
; Сюда кладётся собранный билд (PyInstaller onedir): dist\EBLAN\*
Source: "..\dist\EBLAN\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Иконки/ресурсы на случай, если запускается из исходников
Source: "..\images\*"; DestDir: "{app}\images"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\EBLAN Browser 6.7"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\images\EblanSetup.ico"
Name: "{group}\Удалить EBLAN"; Filename: "{uninstallexe}"
Name: "{autodesktop}\EBLAN Browser 6.7"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\images\EblanSetup.ico"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\EBLAN 6.7"; Filename: "{app}\{#AppExe}"; Tasks: quicklaunchicon

[Registry]
; Автозапуск (если выбрано)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "EBLAN"; ValueData: """{app}\{#AppExe}"""; Tasks: autostart; Flags: uninsdeletevalue
; Флаг «долбаёбских функций» для приложения (читается из реестра, если выбрано)
Root: HKCU; Subkey: "Software\EBLAN"; ValueType: dword; ValueName: "DolboebMode"; ValueData: "1"; Tasks: dolboeb; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить EBLAN Browser 6.7"; Flags: nowait postinstall skipifsilent
