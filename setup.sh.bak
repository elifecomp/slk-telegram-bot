#!/bin/bash
# Установщик SLK Telegram Bot с GitHub

echo "🔐 АВТОРИЗАЦИЯ"
echo "━━━━━━━━━━━━━━━━━━"
read -p "Логин: " INPUT_LOGIN
read -s -p "Пароль: " INPUT_PASS
echo ""
if [ "$INPUT_LOGIN" != "admin" ] || [ "$INPUT_PASS" != "SLK2026!" ]; then
  echo "❌ Неверный логин или пароль!"
  exit 1
fi
echo "✅ Авторизация успешна"
echo ""
echo "📋 ВЫБЕРИТЕ ДЕЙСТВИЕ:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━"

HAS_BOT=0
HAS_PANEL=0
[ -d "/opt/SLV_Bot" ] && HAS_BOT=1
[ -d "/usr/local/x-ui" ] && HAS_PANEL=1

if [ $HAS_BOT -eq 1 ] || [ $HAS_PANEL -eq 1 ]; then
    echo "⚠️ Обнаружено установленное:"
    [ $HAS_BOT -eq 1 ] && echo "   🤖 SLK бот"
    [ $HAS_PANEL -eq 1 ] && echo "   🖥️ 3x-ui панель"
    echo ""
fi

echo "1. 🖥️ Установка 3x-ui панели"
echo "2. 🚀 Установка SLK бота (с GitHub)"
[ $HAS_PANEL -eq 1 ] && echo "3. 🗑️ Удалить 3x-ui панель"
[ $HAS_BOT -eq 1 ] && echo "4. 🗑️ Удалить SLK бота"
echo "0. ❌ Выход"
echo ""
read -p "Ваш выбор: " MENU_CHOICE
echo ""

case $MENU_CHOICE in
  1)
    echo "🖥️ Устанавливаю 3x-ui панель..."
    bash <(curl -Ls https://raw.githubusercontent.com/MHSanaei/3x-ui/master/install.sh)
    echo "✅ Панель установлена!"
    ;;
  2)
    echo "🚀 Установка SLK бота с GitHub..."
    echo ""
    echo "📦 Устанавливаю пакеты..."
    apt install -y python3 python3-pip python3-venv git curl
    echo "📦 Клонирую репозиторий..."
    rm -rf /opt/SLV_Bot 2>/dev/null
    git clone https://github.com/elifecomp/slk-telegram-bot.git /opt/SLV_Bot
    cd /opt/SLV_Bot
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    echo ""
    echo "⚙️ НАСТРОЙКА БОТА"
    echo "━━━━━━━━━━━━━━━━━━"
    read -p "Токен бота Telegram: " BOT_TOKEN
    read -p "Ваш Telegram ID: " ADMIN_IDS
    read -p "URL панели 3x-ui: " XUI_PANEL_URL
    read -p "API токен панели: " XUI_API_TOKEN
    read -p "URL подписки: " SUBSCRIPTION_URL
    read -p "Доп. путь подписки: " SUBSCRIPTION_EXTRA_PATH
    read -p "Есть вторая панель? (y/n): " HAS_PANEL2
    if [ "$HAS_PANEL2" = "y" ]; then
      read -p "URL второй панели: " XUI2_PANEL_URL
      read -p "API токен второй панели: " XUI2_API_TOKEN
    fi
    cat > .env << ENVEOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_IDS=$ADMIN_IDS
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
    echo "✅ Бот установлен!"
    ;;
  3)
    if [ $HAS_PANEL -eq 1 ]; then
      echo "🗑️ Удаляю 3x-ui панель..."
      systemctl stop x-ui 2>/dev/null
      systemctl disable x-ui 2>/dev/null
      rm -rf /usr/local/x-ui
      rm -f /etc/systemd/system/x-ui.service
      systemctl daemon-reload
      echo "✅ Панель удалена!"
    fi
    ;;
  4)
    if [ $HAS_BOT -eq 1 ]; then
      echo "🗑️ Удаляю SLK бота..."
      systemctl stop SLV-bot 2>/dev/null
      systemctl disable SLV-bot 2>/dev/null
      rm -rf /opt/SLV_Bot
      rm -f /etc/systemd/system/SLV-bot.service
      systemctl daemon-reload
      echo "✅ Бот удалён!"
    fi
    ;;
  0) echo "👋 Выход" ;;
esac
