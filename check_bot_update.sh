#!/bin/bash
TOKEN="7556014679:AAHejN8iuZzn9txfPRnmnOe6PyKkhqoIx3A"
CHAT_ID="1823752240"
LAST_VER_FILE="/opt/SLV_Bot/.last_bot_version"

# Ждём запуска бота
sleep 30

while true; do
    GIT_VER=$(curl -s https://raw.githubusercontent.com/elifecomp/slk-telegram-bot/main/version.txt 2>/dev/null)
    BOT_VER=$(grep 'BOT_VERSION' /opt/SLV_Bot/handlers.py | head -1 | cut -d'"' -f2)
    
    if [ -n "$GIT_VER" ] && [ "$GIT_VER" != "$BOT_VER" ]; then
        LAST_VER=$(cat "$LAST_VER_FILE" 2>/dev/null)
        if [ "$GIT_VER" != "$LAST_VER" ]; then
            curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
                -d "chat_id=${CHAT_ID}" -d "parse_mode=HTML" \
                -d "text=🆕 <b>ОБНОВЛЕНИЕ БОТА!</b>%0A━━━━━━━━━━━━━━━━━%0A📦 Версия: ${GIT_VER}%0A📋 Текущая: ${BOT_VER}%0A%0AВыполните: <code>slk-menu</code> → Обновить" \
                > /dev/null 2>&1
        fi
        echo "$GIT_VER" > "$LAST_VER_FILE"
    fi
    sleep 1800
done
