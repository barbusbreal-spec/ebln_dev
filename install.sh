#!/usr/bin/env bash
# ============================================================
#  EBLAN Browser — установщик для Linux
#
#  Поддерживаемые дистрибутивы (через ID/ID_LIKE из /etc/os-release):
#    - Debian / Ubuntu / Linux Mint / Pop!_OS / Kali     (apt)
#    - Fedora / RHEL / CentOS Stream / Rocky / Alma      (dnf)
#    - Arch / Manjaro / EndeavourOS                      (pacman)
#
#  Что делает:
#    1) Ставит системные зависимости (python3, venv, libxcb*, ffmpeg и т.д.)
#    2) Кладёт исходники в /opt/eblan-browser
#    3) Создаёт venv и ставит pip-пакеты из requirements.txt
#    4) Кладёт лаунчер /usr/local/bin/eblan
#    5) Регистрирует .desktop, иконку и MIME-обработчики
#
#  Использование:
#    sudo ./install.sh                # установка/обновление
#    sudo ./install.sh --uninstall    # удаление
#    sudo ./install.sh --user         # установка только для текущего юзера
#    ./install.sh --help              # помощь
# ============================================================

set -Eeuo pipefail

# ----- константы -----
APP_NAME="EBLAN Browser"
APP_ID="eblan-browser"
APP_BIN="eblan"
APP_VERSION_FILE_HINT="EBLAN_DEBUG.py"

PREFIX_SYSTEM="/opt/${APP_ID}"
BIN_SYSTEM="/usr/local/bin/${APP_BIN}"
DESKTOP_SYSTEM="/usr/share/applications/${APP_ID}.desktop"
ICON_DIR_SYSTEM="/usr/share/icons/hicolor"

PREFIX_USER="${HOME}/.local/share/${APP_ID}"
BIN_USER="${HOME}/.local/bin/${APP_BIN}"
DESKTOP_USER="${HOME}/.local/share/applications/${APP_ID}.desktop"
ICON_DIR_USER="${HOME}/.local/share/icons/hicolor"

# ----- режимы -----
MODE="install"          # install | uninstall
SCOPE="system"          # system | user
ASSUME_YES="0"

# ----- цвета (с проверкой TTY) -----
if [[ -t 1 ]]; then
    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'
else
    C_RESET=""; C_BOLD=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""
fi

log()  { printf '%s[ EBLAN ]%s %s\n' "${C_BLUE}${C_BOLD}" "${C_RESET}" "$*"; }
ok()   { printf '%s[  OK   ]%s %s\n' "${C_GREEN}${C_BOLD}" "${C_RESET}" "$*"; }
warn() { printf '%s[ WARN  ]%s %s\n' "${C_YELLOW}${C_BOLD}" "${C_RESET}" "$*"; }
err()  { printf '%s[ ERROR ]%s %s\n' "${C_RED}${C_BOLD}"   "${C_RESET}" "$*" >&2; }

trap 'err "Установка прервана на строке $LINENO"; exit 1' ERR

usage() {
    cat <<EOF
${C_BOLD}EBLAN Browser — установщик${C_RESET}

  $0 [опции]

Опции:
  --uninstall      удалить браузер (и venv, и .desktop)
  --user           установка в \$HOME (без sudo) — только текущий юзер
  -y, --yes        не задавать вопросов
  -h, --help       эта справка

Примеры:
  sudo $0
  sudo $0 --uninstall
  $0 --user
EOF
}

# ----- разбор аргументов -----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --uninstall)  MODE="uninstall" ;;
        --user)       SCOPE="user" ;;
        -y|--yes)     ASSUME_YES="1" ;;
        -h|--help)    usage; exit 0 ;;
        *) err "Неизвестный аргумент: $1"; usage; exit 2 ;;
    esac
    shift
done

# ----- определение путей по scope -----
if [[ "$SCOPE" == "system" ]]; then
    PREFIX="$PREFIX_SYSTEM"
    BIN_PATH="$BIN_SYSTEM"
    DESKTOP_PATH="$DESKTOP_SYSTEM"
    ICON_DIR="$ICON_DIR_SYSTEM"
else
    PREFIX="$PREFIX_USER"
    BIN_PATH="$BIN_USER"
    DESKTOP_PATH="$DESKTOP_USER"
    ICON_DIR="$ICON_DIR_USER"
fi

# ----- проверка прав -----
need_root() {
    if [[ "$SCOPE" == "system" && "$(id -u)" -ne 0 ]]; then
        err "Нужны права root. Запусти через sudo, либо используй --user."
        exit 1
    fi
}

confirm() {
    [[ "$ASSUME_YES" == "1" ]] && return 0
    local prompt="$1"
    read -r -p "${prompt} [y/N]: " ans
    [[ "$ans" =~ ^[YyДд]$ ]]
}

# ============================================================
#   ОПРЕДЕЛЕНИЕ ДИСТРИБУТИВА
# ============================================================
detect_distro() {
    if [[ ! -r /etc/os-release ]]; then
        err "/etc/os-release не найден — не могу определить дистрибутив."
        exit 1
    fi
    # shellcheck disable=SC1091
    . /etc/os-release
    local id="${ID:-}"
    local id_like="${ID_LIKE:-}"
    local haystack=" $id $id_like "

    if [[ "$haystack" =~ \ (debian|ubuntu|linuxmint|pop|kali|elementary|raspbian)\  ]]; then
        DISTRO_FAMILY="debian"
    elif [[ "$haystack" =~ \ (fedora|rhel|centos|rocky|almalinux)\  ]]; then
        DISTRO_FAMILY="fedora"
    elif [[ "$haystack" =~ \ (arch|manjaro|endeavouros|garuda|artix)\  ]]; then
        DISTRO_FAMILY="arch"
    else
        err "Дистрибутив не распознан: ID=$id ID_LIKE=$id_like"
        err "Поддержка: Debian/Ubuntu, Fedora/RHEL, Arch/Manjaro."
        exit 1
    fi
    log "Обнаружен ${C_BOLD}${PRETTY_NAME:-$id}${C_RESET} (семейство: ${DISTRO_FAMILY})"
}

# ============================================================
#   СИСТЕМНЫЕ ЗАВИСИМОСТИ
# ============================================================
install_system_deps() {
    log "Установка системных зависимостей (нужно для PyQt6 + WebEngine)…"
    case "$DISTRO_FAMILY" in
        debian)
            export DEBIAN_FRONTEND=noninteractive
            apt-get update -y
            apt-get install -y --no-install-recommends \
                python3 python3-venv python3-pip python3-dev \
                ca-certificates curl git \
                libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
                libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-sync1 \
                libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0 \
                libegl1 libgl1 libfontconfig1 libdbus-1-3 \
                libnss3 libasound2 libxcomposite1 libxdamage1 libxrandr2 \
                libgtk-3-0 libxslt1.1 \
                ffmpeg \
                || warn "Часть пакетов не установилась — продолжаем."
            ;;
        fedora)
            dnf install -y \
                python3 python3-pip python3-virtualenv python3-devel \
                ca-certificates curl git \
                xcb-util-cursor xcb-util-image xcb-util-keysyms \
                xcb-util-renderutil xcb-util-wm libxkbcommon-x11 \
                mesa-libEGL mesa-libGL fontconfig dbus-libs \
                nss alsa-lib libXcomposite libXdamage libXrandr \
                gtk3 libxslt \
                ffmpeg-free \
                || warn "Часть пакетов не установилась — продолжаем."
            ;;
        arch)
            pacman -Sy --needed --noconfirm \
                python python-pip python-virtualenv \
                ca-certificates curl git \
                xcb-util-cursor xcb-util-image xcb-util-keysyms \
                xcb-util-renderutil xcb-util-wm libxkbcommon-x11 \
                mesa fontconfig dbus \
                nss alsa-lib libxcomposite libxdamage libxrandr \
                gtk3 libxslt \
                ffmpeg \
                || warn "Часть пакетов не установилась — продолжаем."
            ;;
    esac
    ok "Системные зависимости готовы."
}

# ============================================================
#   КОПИРОВАНИЕ ИСХОДНИКОВ
# ============================================================
copy_sources() {
    local src_dir
    src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ ! -f "${src_dir}/${APP_VERSION_FILE_HINT}" ]]; then
        err "Не нашёл ${APP_VERSION_FILE_HINT} рядом со скриптом."
        err "Скрипт должен лежать в корне репозитория EBLAN Browser."
        exit 1
    fi

    log "Копирую исходники в ${PREFIX}…"
    mkdir -p "$PREFIX"
    # Копируем всё, кроме .git, venv, кешей и старого install.sh
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete \
            --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
            --exclude '*.pyc' --exclude 'install.sh' \
            "${src_dir}/" "${PREFIX}/"
    else
        # Запасной путь: tar + cp
        ( cd "$src_dir" && tar --exclude='.git' --exclude='.venv' \
              --exclude='__pycache__' --exclude='*.pyc' \
              --exclude='install.sh' -cf - . ) | ( cd "$PREFIX" && tar -xf - )
    fi
    ok "Исходники скопированы."
}

# ============================================================
#   PYTHON VENV + PIP
# ============================================================
build_venv() {
    log "Создаю venv в ${PREFIX}/.venv…"
    python3 -m venv "${PREFIX}/.venv"
    # shellcheck disable=SC1091
    source "${PREFIX}/.venv/bin/activate"
    pip install --upgrade pip wheel setuptools >/dev/null
    log "Ставлю Python-зависимости (PyQt6, WebEngine, requests)…"
    if [[ -f "${PREFIX}/requirements.txt" ]]; then
        # отфильтруем мусорные строки вроде "allah", если есть
        grep -E '^[A-Za-z0-9_.\-]+([<>=!~].*)?$' "${PREFIX}/requirements.txt" \
             > "${PREFIX}/.venv/requirements.clean.txt" || true
        pip install -r "${PREFIX}/.venv/requirements.clean.txt"
    else
        pip install "PyQt6>=6.5.0" "PyQt6-WebEngine>=6.5.0" "PyQt6-Qt6>=6.5.0" "requests>=2.31.0"
    fi
    deactivate
    ok "Venv готов."
}

# ============================================================
#   ЛАУНЧЕР, ICON, .desktop
# ============================================================
install_launcher() {
    log "Создаю лаунчер ${BIN_PATH}…"
    mkdir -p "$(dirname "$BIN_PATH")"
    cat > "$BIN_PATH" <<EOF
#!/usr/bin/env bash
# Запуск EBLAN Browser из ${PREFIX}/.venv
exec "${PREFIX}/.venv/bin/python" "${PREFIX}/${APP_VERSION_FILE_HINT}" "\$@"
EOF
    chmod +x "$BIN_PATH"
    ok "Лаунчер: ${BIN_PATH}"
}

install_icons() {
    local src_icon_dir="${PREFIX}/images"
    [[ -d "$src_icon_dir" ]] || { warn "Нет каталога images/, иконки не установлены."; return; }

    declare -A SIZES=( [64]=64x64 [128]=128x128 [256]=256x256 )
    for size in "${!SIZES[@]}"; do
        local src="${src_icon_dir}/ma-icon-${size}.png"
        local dst_dir="${ICON_DIR}/${SIZES[$size]}/apps"
        if [[ -f "$src" ]]; then
            mkdir -p "$dst_dir"
            cp -f "$src" "${dst_dir}/${APP_ID}.png"
        fi
    done

    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f "$ICON_DIR" >/dev/null 2>&1 || true
    fi
    ok "Иконки установлены в ${ICON_DIR}."
}

install_desktop() {
    log "Регистрирую .desktop-файл…"
    mkdir -p "$(dirname "$DESKTOP_PATH")"
    cat > "$DESKTOP_PATH" <<EOF
[Desktop Entry]
Type=Application
Name=${APP_NAME}
GenericName=Web Browser
Comment=EBLAN Browser — приватный браузер на PyQt6 WebEngine
Exec=${BIN_PATH} %U
Icon=${APP_ID}
Terminal=false
Categories=Network;WebBrowser;
MimeType=text/html;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
StartupNotify=true
StartupWMClass=EBLAN Browser
Keywords=browser;internet;web;eblan;
EOF
    chmod 644 "$DESKTOP_PATH"

    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$(dirname "$DESKTOP_PATH")" >/dev/null 2>&1 || true
    fi
    ok ".desktop: ${DESKTOP_PATH}"
}

# ============================================================
#   УДАЛЕНИЕ
# ============================================================
do_uninstall() {
    log "Удаляю ${APP_NAME} (${SCOPE})…"
    if ! confirm "Точно снести ${PREFIX} и связанные файлы?"; then
        warn "Отмена."
        exit 0
    fi
    rm -rf "$PREFIX"
    rm -f  "$BIN_PATH"
    rm -f  "$DESKTOP_PATH"
    for size in 64x64 128x128 256x256; do
        rm -f "${ICON_DIR}/${size}/apps/${APP_ID}.png"
    done
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$(dirname "$DESKTOP_PATH")" >/dev/null 2>&1 || true
    fi
    ok "Удалено."
}

# ============================================================
#   ВХОДНАЯ ТОЧКА
# ============================================================
main() {
    log "${C_BOLD}EBLAN Browser installer${C_RESET}  (mode=${MODE}, scope=${SCOPE})"

    need_root
    detect_distro

    if [[ "$MODE" == "uninstall" ]]; then
        do_uninstall
        exit 0
    fi

    install_system_deps
    copy_sources
    build_venv
    install_launcher
    install_icons
    install_desktop

    echo
    ok "${C_BOLD}Установка завершена.${C_RESET}"
    echo "  Запуск из терминала: ${C_BOLD}${APP_BIN}${C_RESET}"
    echo "  Или через меню приложений: ${APP_NAME}"
    if [[ "$SCOPE" == "user" ]]; then
        case ":$PATH:" in
            *":${HOME}/.local/bin:"*) : ;;
            *) warn "В PATH нет ~/.local/bin — добавь в ~/.bashrc:  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
        esac
    fi
}

main "$@"
