#!/bin/bash
# Установщик SLK Telegram Bot v2.0

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

show_menu() {
    clear
    echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}     ${YELLOW}🔧 SLK TELEGRAM BOT — УСТАНОВКА${NC}     ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}1.${NC} 🚀 Установка бота                 ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${RED}2.${NC} 🗑️  Удалить бота                   ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}3.${NC} 🔄 Обновление бота                ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}Первая панель${NC}                         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}4.${NC} 🤖 Изменить токен бота            ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}5.${NC} 🔗 Изменить URL панели             ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}6.${NC} 📋 Изменить ссылку SUB            ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}7.${NC} 📋 Изменить ссылку JSON           ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}Вторая панель${NC}                         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}8.${NC} 🤖 Изменить токен бота (2)        ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}9.${NC} 🔗 Изменить URL панели (2)         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}10.${NC} 📋 Изменить ссылку SUB (2)        ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}11.${NC} 📋 Изменить ссылку JSON (2)       ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}3x-ui панель${NC}                         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}12.${NC} 🖥️ Установка 3x-ui панели         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${RED}13.${NC} 🗑️  Удалить 3x-ui панель           ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  ${RED}0.${NC}  ❌ Выход                          ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
    echo ""
    read -p "Ваш выбор: " choice
}

install_bot() {
    echo -e "${GREEN}🚀 Установка SLK бота...${NC}"
    echo ""
    echo "📦 Устанавливаю зависимости..."
    apt update -qq && apt install -y python3 python3-pip python3-venv git curl 2>/dev/null
    
    if [ -d "/opt/SLV_Bot" ]; then
        echo -e "${YELLOW}⚠️ Бот уже установлен!${NC}"
        read -p "Переустановить? (y/n): " reinstall
        if [ "$reinstall" != "y" ]; then
            return
        fi
        rm -rf /opt/SLV_Bot
    fi
    
    echo "📦 Клонирую с GitHub..."
    git clone https://github.com/elifecomp/slk-telegram-bot.git /opt/SLV_Bot
    cd /opt/SLV_Bot
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    
    echo ""
    echo -e "${CYAN}⚙️ НАСТРОЙКА БОТА${NC}"
    echo "━━━━━━━━━━━━━━━━━━"
    read -p "Токен бота Telegram: " BOT_TOKEN
    read -p "Ваш Telegram ID: " ADMIN_IDS
    read -p "Название бота (по умолчанию SLK): " BOT_NAME
    BOT_NAME=${BOT_NAME:-SLK}
    read -p "URL панели 3x-ui: " XUI_PANEL_URL
    read -p "API токен панели: " XUI_API_TOKEN
    read -p "URL подписки: " SUBSCRIPTION_URL
    read -p "Доп. путь подписки: " SUBSCRIPTION_EXTRA_PATH
    read -p "Есть вторая панель? (y/n): " HAS_PANEL2
    if [ "$HAS_PANEL2" = "y" ]; then
      read -p "URL второй панели: " XUI2_PANEL_URL
      read -p "API токен второй панели: " XUI2_API_TOKEN
    fi
    
    cat > /opt/SLV_Bot/.env << ENVEOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_IDS=$ADMIN_IDS
BOT_NAME=$BOT_NAME
XUI_PANEL_URL=$XUI_PANEL_URL
XUI_API_TOKEN=$XUI_API_TOKEN
SUBSCRIPTION_URL=$SUBSCRIPTION_URL
SUBSCRIPTION_EXTRA_PATH=$SUBSCRIPTION_EXTRA_PATH
SUBSCRIPTION_JSON_PATH=IOS-Android_SLK
XUI_VERIFY_SSL=True
PERSONAL_CABINET_URL=http://localhost:8080/login
WELCOME_AUDIO_PATH=/opt/SLV_Bot/welcome.mp3
TRAFFIC_CACHE_MAX_SIZE=10000
TRAFFIC_CACHE_MAX_AGE_HOURS=24
TRAFFIC_CACHE_CLEANUP_INTERVAL=3600
ENVEOF
    if [ "$HAS_PANEL2" = "y" ]; then
      echo "XUI2_PANEL_URL=$XUI2_PANEL_URL" >> .env
      echo "XUI2_API_TOKEN=$XUI2_API_TOKEN" >> .env
      echo "XUI2_VERIFY_SSL=False" >> .env
    fi
    
    cat > /etc/systemd/system/SLV-bot.service << SVC
[Unit]
Description=SLV Telegram Bot
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=/opt/SLV_Bot
ExecStart=/opt/SLV_Bot/venv/bin/python /opt/SLV_Bot/start_services.py
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
SVC
    
    systemctl daemon-reload
    systemctl enable SLV-bot
    systemctl start SLV-bot
    
    # Алиас
    echo "alias menu-slk='bash /opt/SLV_Bot/setup.sh'" >> ~/.bashrc
    source ~/.bashrc 2>/dev/null
    
    echo ""
    echo -e "${GREEN}✅ Бот установлен!${NC}"
    echo -e "${CYAN}📋 Для вызова меню: menu-slk${NC}"
    read -p "Нажмите Enter..."
}

update_bot() {
    echo -e "${GREEN}🔄 Обновляю бота...${NC}"
    cd /opt/SLV_Bot
    git pull
    source venv/bin/activate
    pip install -r requirements.txt -q
    systemctl restart SLV-bot
    echo -e "${GREEN}✅ Бот обновлён!${NC}"
    read -p "Нажмите Enter..."
}

delete_bot() {
    echo -e "${RED}🗑️ Удаляю бота...${NC}"
    systemctl stop SLV-bot 2>/dev/null
    systemctl disable SLV-bot 2>/dev/null
    rm -rf /opt/SLV_Bot
    rm -f /etc/systemd/system/SLV-bot.service
    sed -i '/menu-slk/d' ~/.bashrc
    systemctl daemon-reload
    echo -e "${GREEN}✅ Бот удалён!${NC}"
    read -p "Нажмите Enter..."
}

change_env() {
    local key=$1
    local desc=$2
    read -p "$desc: " value
    if [ -n "$value" ]; then
        if grep -q "^$key=" /opt/SLV_Bot/.env 2>/dev/null; then
            sed -i "s|^$key=.*|$key=$value|" /opt/SLV_Bot/.env
        else
            echo "$key=$value" >> /opt/SLV_Bot/.env
        fi
        echo -e "${GREEN}✅ $desc обновлён!${NC}"
        systemctl restart SLV-bot 2>/dev/null
    fi
    read -p "Нажмите Enter..."
}

# Главный цикл
while true; do
    show_menu
    case $choice in
        1) install_bot ;;
        2) delete_bot ;;
        3) update_bot ;;
        4) change_env "BOT_TOKEN" "Токен бота" ;;
        5) change_env "XUI_PANEL_URL" "URL панели" ;;
        6) change_env "SUBSCRIPTION_URL" "Ссылка SUB" ;;
        7) change_env "SUBSCRIPTION_JSON_PATH" "Ссылка JSON" ;;
        8) change_env "XUI2_API_TOKEN" "Токен бота (2)" ;;
        9) change_env "XUI2_PANEL_URL" "URL панели (2)" ;;
        10) change_env "SUBSCRIPTION_URL" "Ссылка SUB (2)" ;;
        11) change_env "SUBSCRIPTION_JSON_PATH" "Ссылка JSON (2)" ;;
        12) bash <(curl -Ls https://raw.githubusercontent.com/MHSanaei/3x-ui/master/install.sh) ;;
        13) 
            systemctl stop x-ui 2>/dev/null
            systemctl disable x-ui 2>/dev/null
            rm -rf /usr/local/x-ui
            rm -f /etc/systemd/system/x-ui.service
            systemctl daemon-reload
            echo -e "${GREEN}✅ Панель удалена!${NC}"
            read -p "Нажмите Enter..."
            ;;
        0) echo -e "${GREEN}👋 До свидания!${NC}"; exit 0 ;;
        *) echo -e "${RED}❌ Неверный выбор${NC}"; sleep 1 ;;
    esac
done
