#!/bin/bash
source /opt/SLV_Bot/.env 2>/dev/null
TOKEN="${BOT_TOKEN}"
CHAT_ID="${ADMIN_IDS}"
GITHUB_TOKEN="${GITHUB_TOKEN}"
LAST_VER_FILE="/opt/SLV_Bot/.last_bot_version"

sleep 30

while true; do
    GIT_VER=$(curl -s -H "Authorization: token ${GITHUB_TOKEN}" "https://api.github.com/repos/elifecomp/slk-telegram-bot/contents/version.txt" | python3 -c "import json,sys,base64; d=json.load(sys.stdin); print(base64.b64decode(d['content']).decode().strip())" 2>/dev/null)
    BOT_VER=$(grep 'BOT_VERSION' /opt/SLV_Bot/handlers.py | head -1 | cut -d'"' -f2)
    
    if [ -n "$GIT_VER" ] && [ "$GIT_VER" != "$BOT_VER" ]; then
        LAST_VER=$(cat "$LAST_VER_FILE" 2>/dev/null)
        if [ "$GIT_VER" != "$LAST_VER" ]; then
            curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
                -d "chat_id=${CHAT_ID}" -d "parse_mode=HTML" \
                -d "text=🆕 <b>ОБНОВЛЕНИЕ БОТА!</b>%0A━━━━━━━━━━━━━━━━━%0A📦 Версия: ${GIT_VER}%0A📋 Текущая: ${BOT_VER}%0A%0AВыполните: <code>slk-menu</code> → Обновить" > /dev/null 2>&1
        fi
        echo "$GIT_VER" > "$LAST_VER_FILE"
    fi
    sleep 1800
done
