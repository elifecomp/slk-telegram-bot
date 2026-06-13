#!/bin/bash
ENV_FILE="/opt/SLV_Bot/.env"
BOT_TOKEN=$(grep "^BOT_TOKEN=" "$ENV_FILE" | cut -d= -f2)
ADMIN_IDS=$(grep "^ADMIN_IDS=" "$ENV_FILE" | cut -d= -f2)
API_TOKEN=$(grep "^XUI_API_TOKEN=" "$ENV_FILE" | cut -d= -f2)
PANEL_URL=$(grep "^XUI_PANEL_URL=" "$ENV_FILE" | cut -d= -f2)
CHAT_ID="$ADMIN_IDS"
DATE=$(date '+%d.%m.%Y %H:%M')
DAY=$(date '+%d.%m.%Y')

curl -s -H "Authorization: Bearer $API_TOKEN" "$PANEL_URL/panel/api/server/getDb" -o /tmp/x-ui.db
curl -s -H "Authorization: Bearer $API_TOKEN" "$PANEL_URL/panel/api/server/getConfigJson" -o /tmp/config.json

if [ -s /tmp/x-ui.db ] && [ -s /tmp/config.json ]; then
    SIZE_DB=$(du -h /tmp/x-ui.db | cut -f1)
    SIZE_CFG=$(du -h /tmp/config.json | cut -f1)
    
    curl -s -F "chat_id=$CHAT_ID" \
         -F "document=@/tmp/x-ui.db" \
         -F "caption=🗄 x-ui.db ($DATE)" \
         "https://api.telegram.org/bot$BOT_TOKEN/sendDocument" > /dev/null
    
    curl -s -F "chat_id=$CHAT_ID" \
         -F "document=@/tmp/config.json" \
         -F "caption=⚙️ config.json ($DATE)" \
         "https://api.telegram.org/bot$BOT_TOKEN/sendDocument" > /dev/null
    
    TEXT="📦 БЭКАП ПАНЕЛИ 3X-UI
📅 $DAY
🕐 $DATE

🗄 x-ui.db — $SIZE_DB
⚙️ config.json — $SIZE_CFG

✅ Бэкап выполнен успешно"
    
    curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
         -d "chat_id=$CHAT_ID" \
         --data-urlencode "text=$TEXT" > /dev/null
    
    echo "✅ Бэкапы отправлены"
else
    curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
         -d "chat_id=$CHAT_ID" \
         -d "text=❌ Ошибка бэкапа панели! ($DATE)" > /dev/null
    echo "❌ Ошибка"
fi

rm -f /tmp/x-ui.db /tmp/config.json
