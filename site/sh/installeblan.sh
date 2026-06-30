#!/usr/bin/env bash
# ============================================================
#  EBLAN Browser 6.7 — самодостаточный установщик
#
#  Можно просто положить на сайт и запускать:
#    curl -sSL https://eblanbrowser.ru/sh/installeblan.sh | sudo bash      # Linux
#    curl -sSL https://eblanbrowser.ru/sh/installeblan.sh | bash           # macOS
#
#  Если исходники лежат рядом со скриптом — берёт их.
#  Иначе скачивает zip с $EBLAN_ZIP_URL (по умолчанию — update.riba.click).
#
#  Опции (через env, т.к. при curl|bash аргументы не передать):
#    EBLAN_ZIP_URL=...   — откуда качать zip
#    EBLAN_SCOPE=user    — ставить в $HOME (без sudo)
#    EBLAN_UNINSTALL=1    — удалить
# ============================================================
set -Eeuo pipefail

APP_NAME="EBLAN Browser"
APP_ID="eblan-browser"
APP_BIN="eblan"
ENTRY="EBLAN_DEBUG.py"
ZIP_URL="${EBLAN_ZIP_URL:-https://eblanbrowser.ru/dl/eblan.zip}"

# Поддержка аргументов, если запускают файлом (не через pipe)
for a in "$@"; do
  case "$a" in
    --uninstall) EBLAN_UNINSTALL=1 ;;
    --user)      EBLAN_SCOPE=user ;;
    -h|--help)   echo "EBLAN installer: env EBLAN_SCOPE=user|EBLAN_UNINSTALL=1|EBLAN_ZIP_URL=..."; exit 0 ;;
  esac
done
SCOPE="${EBLAN_SCOPE:-system}"
UNINSTALL="${EBLAN_UNINSTALL:-0}"

if [[ -t 1 ]]; then C_R=$'\033[0m'; C_B=$'\033[1m'; C_G=$'\033[32m'; C_Y=$'\033[33m'; C_BL=$'\033[34m'; C_RED=$'\033[31m'
else C_R=""; C_B=""; C_G=""; C_Y=""; C_BL=""; C_RED=""; fi
log()  { printf '%s[ EBLAN ]%s %s\n' "${C_BL}${C_B}" "$C_R" "$*"; }
ok()   { printf '%s[  OK   ]%s %s\n' "${C_G}${C_B}"  "$C_R" "$*"; }
warn() { printf '%s[ WARN  ]%s %s\n' "${C_Y}${C_B}"  "$C_R" "$*"; }
err()  { printf '%s[ ERROR ]%s %s\n' "${C_RED}${C_B}" "$C_R" "$*" >&2; }
trap 'err "Прервано на строке $LINENO"; exit 1' ERR

OS="linux"; [[ "$(uname -s)" == "Darwin" ]] && OS="mac"

# ----- пути -----
if [[ "$SCOPE" == "user" || "$OS" == "mac" ]]; then
  PREFIX="${HOME}/.local/share/${APP_ID}"
  BIN="${HOME}/.local/bin/${APP_BIN}"
  DESKTOP="${HOME}/.local/share/applications/${APP_ID}.desktop"
  SUDO=""
else
  PREFIX="/opt/${APP_ID}"
  BIN="/usr/local/bin/${APP_BIN}"
  DESKTOP="/usr/share/applications/${APP_ID}.desktop"
  SUDO=""
  [[ $EUID -ne 0 ]] && SUDO="sudo"
fi

# ============================================================
#   УДАЛЕНИЕ
# ============================================================
if [[ "$UNINSTALL" == "1" ]]; then
  log "Удаляю EBLAN Browser…"
  $SUDO rm -rf "$PREFIX" "$BIN" "$DESKTOP" || true
  ok "Удалено. (настройки в ~/.eblan-browser не тронуты)"
  exit 0
fi

# ============================================================
#   СИСТЕМНЫЕ ЗАВИСИМОСТИ
# ============================================================
install_deps() {
  if [[ "$OS" == "mac" ]]; then
    if ! command -v brew >/dev/null 2>&1; then
      err "Нужен Homebrew: https://brew.sh"; exit 1
    fi
    log "Ставлю зависимости через brew…"
    brew install python@3.12 >/dev/null 2>&1 || brew install python3 >/dev/null 2>&1 || true
    return
  fi
  . /etc/os-release 2>/dev/null || true
  local id="${ID:-} ${ID_LIKE:-}"
  log "Ставлю системные зависимости…"
  if   echo "$id" | grep -qiE 'debian|ubuntu|mint|pop|kali'; then
    $SUDO apt-get update -y
    $SUDO apt-get install -y python3 python3-venv python3-pip \
      libxcb-cursor0 libxcb-xinerama0 libgl1 libegl1 libxkbcommon0 \
      libnss3 libxcomposite1 libxdamage1 libasound2t64 ffmpeg curl unzip \
      || $SUDO apt-get install -y python3 python3-venv python3-pip curl unzip
  elif echo "$id" | grep -qiE 'fedora|rhel|centos|rocky|alma'; then
    $SUDO dnf install -y python3 python3-pip libxkbcommon mesa-libGL mesa-libEGL nss curl unzip || true
  elif echo "$id" | grep -qiE 'arch|manjaro|endeavour'; then
    $SUDO pacman -Sy --noconfirm python python-pip qt6-webengine curl unzip || true
  else
    warn "Неизвестный дистрибутив — ставлю по минимуму (python3, curl, unzip)."
    $SUDO bash -c 'command -v apt-get && apt-get install -y python3 python3-venv python3-pip curl unzip' || true
  fi
}

# ============================================================
#   ИСХОДНИКИ: локально рядом или скачать zip
# ============================================================
fetch_sources() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"
  if [[ -n "$here" && -f "${here}/${ENTRY}" ]]; then
    log "Беру исходники рядом со скриптом: ${here}"
    $SUDO mkdir -p "$PREFIX"
    $SUDO cp -rf "${here}/." "${PREFIX}/"
    return
  fi
  log "Качаю EBLAN из ${ZIP_URL}…"
  local tmp; tmp="$(mktemp -d)"
  curl -sSL "$ZIP_URL" -o "${tmp}/eblan.zip"
  unzip -q "${tmp}/eblan.zip" -d "${tmp}/x"
  # найдём папку с EBLAN_DEBUG.py (может быть вложенной)
  local root; root="$(dirname "$(find "${tmp}/x" -maxdepth 3 -name "$ENTRY" | head -n1)")"
  if [[ -z "$root" || ! -f "${root}/${ENTRY}" ]]; then
    err "В архиве не нашёл ${ENTRY}. Проверь EBLAN_ZIP_URL."; exit 1
  fi
  $SUDO rm -rf "$PREFIX"; $SUDO mkdir -p "$PREFIX"
  $SUDO cp -rf "${root}/." "${PREFIX}/"
  rm -rf "$tmp"
  ok "Исходники установлены в ${PREFIX}"
}

# ============================================================
#   VENV + PIP
# ============================================================
build_venv() {
  log "Создаю venv и ставлю PyQt6/WebEngine/requests…"
  $SUDO python3 -m venv "${PREFIX}/.venv"
  # requirements без мусорных строк (например 'allah' или комментариев)
  $SUDO bash -c "grep -E '^[A-Za-z0-9_.-]+([<>=!~].*)?$' '${PREFIX}/requirements.txt' > '${PREFIX}/.venv/req.txt' 2>/dev/null || true"
  if [[ ! -s "${PREFIX}/.venv/req.txt" ]]; then
    $SUDO bash -c "printf 'PyQt6>=6.5.0\nPyQt6-WebEngine>=6.5.0\nrequests>=2.31.0\n' > '${PREFIX}/.venv/req.txt'"
  fi
  $SUDO "${PREFIX}/.venv/bin/pip" install --upgrade pip wheel >/dev/null
  $SUDO "${PREFIX}/.venv/bin/pip" install -r "${PREFIX}/.venv/req.txt"
  ok "Зависимости установлены."
}

# ============================================================
#   ЛАУНЧЕР + ЯРЛЫК
# ============================================================
make_launcher() {
  log "Создаю лаунчер ${BIN}…"
  $SUDO mkdir -p "$(dirname "$BIN")"
  $SUDO tee "$BIN" >/dev/null <<EOF
#!/usr/bin/env bash
cd "${PREFIX}" || exit 1
exec "${PREFIX}/.venv/bin/python" "${PREFIX}/${ENTRY}" "\$@"
EOF
  $SUDO chmod +x "$BIN"

  if [[ "$OS" == "linux" ]]; then
    local icon="${PREFIX}/images/ma-icon-256.png"
    $SUDO mkdir -p "$(dirname "$DESKTOP")"
    $SUDO tee "$DESKTOP" >/dev/null <<EOF
[Desktop Entry]
Type=Application
Name=${APP_NAME} 6.7
Comment=Халяль снаружи, передоз 67 внутри
Exec=${BIN} %U
Icon=${icon}
Terminal=false
Categories=Network;WebBrowser;
EOF
    command -v update-desktop-database >/dev/null 2>&1 && \
      $SUDO update-desktop-database "$(dirname "$DESKTOP")" >/dev/null 2>&1 || true
  fi
  ok "Лаунчер: запусти командой '${APP_BIN}' или из меню приложений."
}

# ============================================================
main() {
  log "Установка ${APP_NAME} 6.7 (${OS}, scope=${SCOPE})…"
  install_deps
  fetch_sources
  build_venv
  make_launcher
  echo
  ok "Готово! Запуск: ${C_B}${APP_BIN}${C_R}"
  [[ -n "$SUDO" ]] && warn "Если '${APP_BIN}' не находится — добавь $(dirname "$BIN") в PATH."
}
main
