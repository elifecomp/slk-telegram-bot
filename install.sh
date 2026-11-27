#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
#  SLK_BOT_3X-UI — Профессиональный интерактивный установщик
# ==============================================================================

BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="/opt/SLK_BOT_3X-UI"
SERVICE_NAME="slk-bot-3xui.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

print_banner() {
    clear || true
    echo -e "${CYAN}${BOLD}"
    echo "  ╔══════════════════════════════════════════════════════════════╗"
    echo "  ║                 SLK_BOT_3X-UI INSTALLER                      ║"
    echo "  ║          Автоматическая установка и запуск бота              ║"
    echo "  ╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

step_header() {
    echo -e "\n${BLUE}${BOLD}▶ $1${NC}"
    echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
}

ok_msg() {
    echo -e "  ${GREEN}✔${NC} $1"
}

warn_msg() {
    echo -e "  ${YELLOW}⚠${NC} $1"
}

err_msg() {
    echo -e "  ${RED}✖${NC} $1" >&2
}

progress_bar() {
    local current="$1"
    local total="$2"
    local label="$3"
    local width=28
    local filled=$(( current * width / total ))
    local empty=$(( width - filled ))
    local bar=""
    for ((i=0; i<filled; i++)); do bar+="█"; done
    for ((i=0; i<empty; i++)); do bar+="░"; done
    local pct=$(( current * 100 / total ))
    printf "\r  ${CYAN}[%s]${NC} ${BOLD}%3d%%${NC} ${DIM}| %s${NC}" "$bar" "$pct" "$label"
    if [ "$current" -eq "$total" ]; then
        echo ""
    fi
}

run_with_spinner() {
    local title="$1"
    shift
    local log_file
    log_file="$(mktemp)"

    "$@" >"$log_file" 2>&1 &
    local pid=$!
    local spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0

    while kill -0 "$pid" 2>/dev/null; do
        local c="${spin:i%${#spin}:1}"
        printf "\r  ${CYAN}${c}${NC} %s..." "$title"
        i=$((i + 1))
        sleep 0.12
    done

    wait "$pid"
    local rc=$?
    if [ "$rc" -eq 0 ]; then
        printf "\r  ${GREEN}✔${NC} %-62s\n" "$title"
        rm -f "$log_file"
    else
        printf "\r  ${RED}✖${NC} %-62s\n" "$title"
        echo -e "${RED}Подробности ошибки:${NC}"
        cat "$log_file" >&2
        rm -f "$log_file"
        return "$rc"
    fi
}

require_root() {
    if [ "${EUID:-$(id -u)}" -ne 0 ]; then
        err_msg "Запустите установщик от имени root (например: sudo bash install.sh)"
        exit 1
    fi
}

prompt_optional_token() {
    local val=""
    read -r -s -p "  ${BOLD}Токен Telegram-бота (BOT_TOKEN) [Enter — пропустить]:${NC} " val
    echo ""
    val="$(echo "$val" | xargs)"
    BOT_TOKEN="$val"
    if [ -z "$BOT_TOKEN" ]; then
        warn_msg "BOT_TOKEN пропущен — добавите его позже в .env"
    fi
}

prompt_optional_admin_id() {
    local val=""
    while true; do
        read -r -p "  ${BOLD}Telegram ID администраторов (можно через запятую) [Enter — пропустить]:${NC} " val
        val="$(echo "$val" | tr -d '[:space:]')"
        if [ -z "$val" ]; then
            ADMIN_ID=""
            warn_msg "Telegram ID пропущен — добавите его позже в .env"
            break
        fi
        if [[ "$val" =~ ^-?[0-9]+(,-?[0-9]+)*$ ]]; then
            ADMIN_ID="$val"
            break
        fi
        warn_msg "Введите числовой ID или список ID через запятую (например: 123456789,987654321) либо нажмите Enter."
    done
}

prompt_non_empty() {
    local prompt_text="$1"
    local var_name="$2"
    local is_secret="${3:-0}"
    local val=""

    while true; do
        if [ "$is_secret" -eq 1 ]; then
            read -r -s -p "  ${BOLD}${prompt_text}:${NC} " val
            echo ""
        else
            read -r -p "  ${BOLD}${prompt_text}:${NC} " val
        fi
        val="$(echo "$val" | xargs)"
        if [ -n "$val" ]; then
            printf -v "$var_name" "%s" "$val"
            break
        fi
        warn_msg "Поле не может быть пустым. Повторите ввод."
    done
}

prompt_panel_url() {
    local val=""
    while true; do
        read -r -p "  ${BOLD}URL панели (например https://panel.example.com:2053/path):${NC} " val
        val="$(echo "$val" | xargs)"
        val="${val%/}"
        if [[ "$val" =~ ^https?://.+ ]]; then
            PANEL_URL="$val"
            break
        fi
        warn_msg "URL должен начинаться с http:// или https://."
    done
}

start_or_restart_service() {
    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}"
    systemctl restart "${SERVICE_NAME}"
}

show_service_status() {
    systemctl status "${SERVICE_NAME}" --no-pager -l || true
}

main() {
    require_root
    print_banner

    progress_bar 1 6 "Проверка окружения"
    step_header "1. Проверка системы и зависимостей"

    if [ "$SCRIPT_DIR" != "$TARGET_DIR" ]; then
        run_with_spinner "Копирование файлов проекта в ${TARGET_DIR}" bash -c "
            mkdir -p '${TARGET_DIR}'
            tar --exclude='./venv' --exclude='./__pycache__' --exclude='./.git' --exclude='./.env' --exclude='*.db' --exclude='*.db-*' --exclude='*.sqlite*' -cf - -C '${SCRIPT_DIR}' . | tar -xf - -C '${TARGET_DIR}'
        "
    else
        ok_msg "Каталог проекта: ${TARGET_DIR}"
    fi

    if command -v apt-get >/dev/null 2>&1; then
        need_apt=0
        python3 -m venv --help >/dev/null 2>&1 || need_apt=1
        python3 -m pip --version >/dev/null 2>&1 || need_apt=1
        if [ "$need_apt" -eq 1 ]; then
            run_with_spinner "Установка python3-venv и python3-pip" bash -c "
                apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv python3-pip curl ca-certificates
            "
        else
            ok_msg "Python3, venv и pip уже установлены"
        fi
    fi

    progress_bar 2 6 "Настройка параметров .env"
    step_header "2. Настройка конфигурации (.env)"

    prompt_optional_token
    prompt_optional_admin_id
    prompt_panel_url
    prompt_non_empty "Токен панели (PANEL_TOKEN)" PANEL_TOKEN 1

    printf "BOT_TOKEN=%s\nADMIN_ID=%s\nPANEL_URL=%s\nPANEL_TOKEN=%s\n" \
        "$BOT_TOKEN" "$ADMIN_ID" "$PANEL_URL" "$PANEL_TOKEN" > "${TARGET_DIR}/.env"
    chmod 600 "${TARGET_DIR}/.env"
    ok_msg "Файл .env сохранён (права 600)"

    progress_bar 3 6 "Создание виртуального окружения"
    step_header "3. Виртуальное окружение и библиотеки Python"

    if [ ! -x "${TARGET_DIR}/venv/bin/python" ]; then
        run_with_spinner "Создание venv в ${TARGET_DIR}/venv" python3 -m venv "${TARGET_DIR}/venv"
    else
        ok_msg "Виртуальное окружение уже существует"
    fi

    if [ -s "${TARGET_DIR}/requirements.txt" ]; then
        run_with_spinner "Установка зависимостей из requirements.txt" \
            "${TARGET_DIR}/venv/bin/pip" install --quiet -r "${TARGET_DIR}/requirements.txt"
    else
        run_with_spinner "Установка aiogram и aiohttp" \
            "${TARGET_DIR}/venv/bin/pip" install --quiet "aiogram>=3.4,<3.25" "pydantic>=2.0,<2.12" "aiohttp>=3.9,<4.0" "python-dotenv>=1.0,<2.0"
    fi

    progress_bar 4 6 "Проверка кода и модулей"
    step_header "4. Проверка синтаксиса и импортов"

    run_with_spinner "Компиляция всех модулей бота" \
        "${TARGET_DIR}/venv/bin/python" -m compileall -q "${TARGET_DIR}"

    run_with_spinner "Проверка импорта главного роутера" bash -c "
        cd '${TARGET_DIR}' && '${TARGET_DIR}/venv/bin/python' -c 'import main, handlers; assert handlers.get_main_router() is not None'
    "

    progress_bar 5 6 "Настройка systemd-службы"
    step_header "5. Служба systemd (${SERVICE_NAME})"

    cat << SYSTEMD_EOF > "${SERVICE_FILE}"
[Unit]
Description=SLK_BOT_3X-UI Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=${TARGET_DIR}
ExecStart=${TARGET_DIR}/venv/bin/python ${TARGET_DIR}/main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

    run_with_spinner "Перезагрузка конфигурации systemd и запуск бота" start_or_restart_service

    progress_bar 6 6 "Финальная проверка"
    sleep 2

    echo -e "\n${GREEN}${BOLD}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}${BOLD}  ✔ УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО${NC}"
    echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════════════${NC}"
    echo -e "  • Директория:  ${CYAN}${TARGET_DIR}${NC}"
    echo -e "  • Админ ID:    ${CYAN}${ADMIN_ID:-не задан (добавьте в .env)}${NC}"
    echo -e "  • Панель URL:  ${CYAN}${PANEL_URL}${NC}"
    echo -e "  • База данных: ${CYAN}создаётся / сохраняется в ${TARGET_DIR}${NC}"
    show_service_status
}

main "$@"
