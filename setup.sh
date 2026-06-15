#!/bin/bash
# Установщик SLK Telegram Bot v2.2
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'
ENV_FILE="/opt/SLV_Bot/.env"

set_env() {
    local key="$1"
    local val="$2"
    if grep -q "^$key=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^$key=.*|$key=$val|" "$ENV_FILE"
    else
        echo "$key=$val" >> "$ENV_FILE"
    fi
}

show_menu() {
    clear
    echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}     ${YELLOW}🔧 SLK TELEGRAM BOT v2.2${NC}        ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}1.${NC} 🚀 Установка бота                 ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${RED}2.${NC} 🗑️  Удалить бота                   ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}3.${NC} 🔄 Обновление бота                ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}4.${NC} ✏️  Название бота                 ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}5.${NC} 🤖 Изменить токен бота            ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}6.${NC} 🆔 Изменить Telegram ID           ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}Первая панель${NC}                         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}7.${NC} 🔑 Токен панели 1                 ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}8.${NC} 🔗 URL панели 1                   ${CYAN}║${NC}"
            echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}Вторая панель${NC}                        ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}9.${NC} 🔑 Токен панели 2                 ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}10.${NC} 🔗 URL панели 2                  ${CYAN}║${NC}"
            echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}3x-ui панель${NC}                         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}11.${NC} 🖥️ Установка                    ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${RED}12.${NC} 🗑️  Удаление                     ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}13.${NC} 🔄 Обновить меню                 ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}14.${NC} 🔑 Загрузить GitHub токен         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${RED}0.${NC}  ❌  Выход                          ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
    echo ""
    read -p "Ваш выбор: " choice
}

install_bot() {
    echo -e "${GREEN}🚀 Установка SLK бота...${NC}"
    
    # Проверка разрешения на установку
    echo -e "${CYAN}🔐 Проверка доступа...${NC}"
    read -p "Ваш Telegram ID: " TG_ID
    read -p "Ваше имя пользователя: " TG_USER
    
    if [ -z "$TG_ID" ]; then
        echo -e "${RED}❌ Telegram ID обязателен!${NC}"
        return
    fi
    
    MY_IP=$(curl -s ifconfig.me 2>/dev/null || echo "unknown")
    echo -e "${CYAN}📤 Отправляю запрос администратору...${NC}"
    
    REQ_ID=$(curl -s "http://31.76.40.27:5555/install-request?tg_id=${TG_ID}&user=${TG_USER}&ip=${MY_IP}")
    
    if [ -z "$REQ_ID" ]; then
        echo -e "${RED}❌ Сервер авторизации недоступен!${NC}"
        return
    fi
    
    echo -e "${YELLOW}⏳ Ожидайте подтверждения (ID: ${REQ_ID})...${NC}"
    
    for i in $(seq 1 60); do
        STATUS=$(curl -s "http://31.76.40.27:5555/install-check?id=${REQ_ID}")
        if [ "$STATUS" = "approved" ]; then
            echo -e "${GREEN}✅ Доступ разрешён! Начинаю установку...${NC}"
            break
        elif [ "$STATUS" = "rejected" ]; then
            echo -e "${RED}❌ Администратор отклонил запрос!${NC}"
            return
        fi
        sleep 5
    done
    
    if [ "$STATUS" != "approved" ]; then
        echo -e "${RED}⏰ Время ожидания истекло!${NC}"
        return
    fi
    
    apt update -qq && apt install -y python3 python3-pip python3-venv git curl 2>/dev/null
    
    # Проверяем speedtest-cli
    if ! command -v speedtest-cli &>/dev/null; then
        echo -e "${CYAN}📡 Устанавливаю speedtest-cli...${NC}"
        apt install -y speedtest-cli 2>/dev/null || pip install speedtest-cli 2>/dev/null
        echo -e "${GREEN}✅ speedtest-cli установлен${NC}"
    fi
    cd /tmp
    if [ -d "/opt/SLV_Bot" ]; then
        echo -e "${YELLOW}⚠️ Бот уже установлен!${NC}"
        read -p "Переустановить? (y/n): " reinstall
        [ "$reinstall" != "y" ] && return
        systemctl stop SLV-bot 2>/dev/null
        rm -rf /opt/SLV_Bot
    fi
    git clone https://github.com/elifecomp/slk-telegram-bot.git /opt/SLV_Bot
    cd /opt/SLV_Bot
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt -q
    cat > "$ENV_FILE" << 'ENVEOF'
BOT_TOKEN=ваш_токен
ADMIN_IDS=ваш_id
BOT_NAME=SLK Bot
XUI_PANEL_URL=ваш_url
XUI_API_TOKEN=ваш_токен
XUI_VERIFY_SSL=True
WELCOME_AUDIO_PATH=/opt/SLV_Bot/welcome.mp3
TRAFFIC_CACHE_MAX_SIZE=10000
TRAFFIC_CACHE_MAX_AGE_HOURS=24
TRAFFIC_CACHE_CLEANUP_INTERVAL=3600
ENVEOF
    cat > /etc/systemd/system/SLV-bot.service << 'SVCEOF'
[Unit]
Description=SLV Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/SLV_Bot
ExecStart=/opt/SLV_Bot/venv/bin/python /opt/SLV_Bot/start_services.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF
    systemctl daemon-reload
    systemctl enable SLV-bot
    systemctl start SLV-bot
    
    # Добавляем автоперезагрузку в 05:00 и 17:00
    (crontab -l 2>/dev/null | grep -v "SLV-bot"; echo "0 5,17 * * * systemctl restart SLV-bot 2>/dev/null") | crontab -
    echo -e "${GREEN}✅ Бот установлен!${NC}"
    echo -e "${YELLOW}⚠️ Не забудьте настроить токены в меню!${NC}"
    read -p "Нажмите Enter..."
}

update_bot() {
    echo -e "${GREEN}🔄 Обновляю бота...${NC}"
    cd /opt/SLV_Bot
    git fetch --all
    git reset --hard origin/main
    
    # Проверяем speedtest-cli
    if ! command -v speedtest-cli &>/dev/null; then
        echo -e "${CYAN}📡 Устанавливаю speedtest-cli...${NC}"
        apt install -y speedtest-cli 2>/dev/null || pip install speedtest-cli 2>/dev/null
        echo -e "${GREEN}✅ speedtest-cli установлен${NC}"
    fi
    
    source venv/bin/activate
    pip install -r requirements.txt -q
    systemctl restart SLV-bot
    echo -e "${GREEN}✅ Бот обновлён!${NC}"
    read -p "Нажмите Enter..."
}

delete_bot() {
    echo -e "${RED}🗑️ Удаление бота...${NC}"
    systemctl stop SLV-bot 2>/dev/null
    systemctl disable SLV-bot 2>/dev/null
    rm -f /etc/systemd/system/SLV-bot.service
    systemctl daemon-reload
    rm -rf /opt/SLV_Bot
    echo -e "${GREEN}✅ Бот удалён!${NC}"
    read -p "Нажмите Enter..."
}

# Главный цикл
while true; do
    show_menu
    case $choice in
        1) install_bot ;;
        2) delete_bot ;;
        3) update_bot ;;
        4) read -p "Название бота: " val; set_env "BOT_NAME" "$val"; systemctl restart SLV-bot 2>/dev/null; echo -e "${GREEN}✅ Готово!${NC}"; read -p "Enter..." ;;
        5) read -p "Токен бота: " val; set_env "BOT_TOKEN" "$val"; systemctl restart SLV-bot 2>/dev/null; echo -e "${GREEN}✅ Готово!${NC}"; read -p "Enter..." ;;
        6) read -p "Telegram ID: " val; set_env "ADMIN_IDS" "$val"; systemctl restart SLV-bot 2>/dev/null; echo -e "${GREEN}✅ Готово!${NC}"; read -p "Enter..." ;;
        7) read -p "Токен панели 1: " val; set_env "XUI_API_TOKEN" "$val"; systemctl restart SLV-bot 2>/dev/null; echo -e "${GREEN}✅ Готово!${NC}"; read -p "Enter..." ;;
        8) read -p "URL панели 1: " val; set_env "XUI_PANEL_URL" "$val"; systemctl restart SLV-bot 2>/dev/null; echo -e "${GREEN}✅ Готово!${NC}"; read -p "Enter..." ;;        9) read -p "Токен панели 2: " val; set_env "XUI2_API_TOKEN" "$val"; systemctl restart SLV-bot 2>/dev/null; echo -e "${GREEN}✅ Готово!${NC}"; read -p "Enter..." ;;
        10) read -p "URL панели 2: " val; set_env "XUI2_PANEL_URL" "$val"; set_env "XUI2_VERIFY_SSL" "False"; systemctl restart SLV-bot 2>/dev/null; echo -e "${GREEN}✅ Готово!${NC}"; read -p "Enter..." ;;        11) bash <(curl -Ls https://raw.githubusercontent.com/MHSanaei/3x-ui/master/install.sh) ;;
        12) systemctl stop x-ui 2>/dev/null; systemctl disable x-ui 2>/dev/null; rm -rf /usr/local/x-ui; rm -f /etc/systemd/system/x-ui.service; systemctl daemon-reload; echo -e "${GREEN}✅ Панель удалена!${NC}"; read -p "Enter..." ;;
        13) curl -s -o /opt/SLV_Bot/setup.sh https://raw.githubusercontent.com/elifecomp/slk-telegram-bot/main/setup.sh && chmod +x /opt/SLV_Bot/setup.sh && echo -e "${GREEN}✅ Меню обновлено!${NC}"; read -p "Enter..." ;;
        14) 
            TOKEN=$(curl -s http://144.31.133.182:9999/token 2>/dev/null)
            if [ -n "$TOKEN" ]; then
                set_env "GITHUB_TOKEN" "$TOKEN"
                echo -e "${GREEN}✅ GitHub токен загружен!${NC}"
            else
                echo -e "${RED}❌ Сервер токенов недоступен${NC}"
            fi
            read -p "Enter..."
            ;;
        0) echo -e "${GREEN}👋 До свидания!${NC}"; exit 0 ;;
        *) echo -e "${RED}❌ Неверный выбор${NC}"; sleep 1 ;;
    esac
done
