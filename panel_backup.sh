#!/bin/bash
ENV_FILE="/opt/SLV_Bot/.env"
BOT_TOKEN=$(grep "^BOT_TOKEN=" "$ENV_FILE" | cut -d= -f2)
ADMIN_IDS=$(grep "^ADMIN_IDS=" "$ENV_FILE" | cut -d= -f2)
API_TOKEN=$(grep "^XUI_API_TOKEN=" "$ENV_FILE" | cut -d= -f2)
API2_TOKEN=$(grep "^XUI2_API_TOKEN=" "$ENV_FILE" | cut -d= -f2)
PANEL_URL=$(grep "^XUI_PANEL_URL=" "$ENV_FILE" | cut -d= -f2)
PANEL2_URL=$(grep "^XUI2_PANEL_URL=" "$ENV_FILE" | cut -d= -f2)

# Извлекаем хосты
HOST1=$(echo "$PANEL_URL" | sed 's|https://||;s|:.*||;s|/.*||')
HOST2=$(echo "$PANEL2_URL" | sed 's|https://||;s|:.*||;s|/.*||')

DATE=$(date '+%d.%m.%Y %H:%M')
DAY=$(date '+%d.%m.%Y')
IFS=',' read -ra ADMINS <<< "$ADMIN_IDS"

# Скачиваем во временные файлы
curl -s -H "Authorization: Bearer $API_TOKEN" "$PANEL_URL/panel/api/server/getDb" -o /tmp/x-ui.db
curl -s -H "Authorization: Bearer $API_TOKEN" "$PANEL_URL/panel/api/server/getConfigJson" -o /tmp/config.json
curl -s -k -H "Authorization: Bearer $API2_TOKEN" "$PANEL2_URL/panel/api/server/getDb" -o /tmp/x-ui2.db
curl -s -k -H "Authorization: Bearer $API2_TOKEN" "$PANEL2_URL/panel/api/server/getConfigJson" -o /tmp/config2.json

if [ -s /tmp/x-ui.db ] && [ -s /tmp/config.json ]; then
    SIZE_DB=$(du -h /tmp/x-ui.db | cut -f1)
    SIZE_CFG=$(du -h /tmp/config.json | cut -f1)
    SIZE_DB2=$(du -h /tmp/x-ui2.db 2>/dev/null | cut -f1)
    SIZE_CFG2=$(du -h /tmp/config2.json 2>/dev/null | cut -f1)
    
    for CHAT_ID in "${ADMINS[@]}"; do
        # Файлы первой панели — с доменом в имени
        curl -s -F "chat_id=$CHAT_ID" \
             -F "document=@/tmp/x-ui.db;filename=${HOST1}.db" \
             -F "caption=🇫🇮 Финляндия — база данных (${DATE})" \
             "https://api.telegram.org/bot$BOT_TOKEN/sendDocument" > /dev/null
        
        curl -s -F "chat_id=$CHAT_ID" \
             -F "document=@/tmp/config.json;filename=${HOST1}.json" \
             -F "caption=🇫🇮 Финляндия — конфиг (${DATE})" \
             "https://api.telegram.org/bot$BOT_TOKEN/sendDocument" > /dev/null
        
        # Файлы второй панели
        if [ -s /tmp/x-ui2.db ]; then
            curl -s -F "chat_id=$CHAT_ID" \
                 -F "document=@/tmp/x-ui2.db;filename=${HOST2}.db" \
                 -F "caption=🇷🇺 Россия — база данных (${DATE})" \
                 "https://api.telegram.org/bot$BOT_TOKEN/sendDocument" > /dev/null
        fi
        
        if [ -s /tmp/config2.json ]; then
            curl -s -F "chat_id=$CHAT_ID" \
                 -F "document=@/tmp/config2.json;filename=${HOST2}.json" \
                 -F "caption=🇷🇺 Россия — конфиг (${DATE})" \
                 "https://api.telegram.org/bot$BOT_TOKEN/sendDocument" > /dev/null
        fi
        
        TEXT="📦 БЭКАП ПАНЕЛЕЙ 3X-UI
📅 $DAY
🕐 $DATE

🇫🇮 Финляндия (${HOST1}):
  🗄 ${HOST1}.db — $SIZE_DB
  ⚙️ ${HOST1}.json — $SIZE_CFG

🇷🇺 Россия (${HOST2}):
  🗄 ${HOST2}.db — $SIZE_DB2
  ⚙️ ${HOST2}.json — $SIZE_CFG2

✅ Бэкап выполнен успешно"
        
        curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
             -d "chat_id=$CHAT_ID" \
             --data-urlencode "text=$TEXT" > /dev/null
    done
    
    echo "✅ Бэкапы отправлены"
else
    for CHAT_ID in "${ADMINS[@]}"; do
        curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
             -d "chat_id=$CHAT_ID" \
             -d "text=❌ Ошибка бэкапа панели! ($DATE)" > /dev/null
    done
    echo "❌ Ошибка"
fi

rm -f /tmp/x-ui.db /tmp/config.json /tmp/x-ui2.db /tmp/config2.json
