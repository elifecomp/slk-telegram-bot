#!/bin/bash
BACKUP_DIR="/opt/SLV_Bot/backups"
BACKUP_NAME="SLV_bot_auto_$(date +%Y%m%d).tar.gz"
BACKUP_SIZE=$(du -sh "$BACKUP_DIR/$BACKUP_NAME" 2>/dev/null | cut -f1)

# Создаём бэкап
tar -czf "$BACKUP_DIR/$BACKUP_NAME" \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='logs' \
    /opt/SLV_Bot/*.py \
    /opt/SLV_Bot/.env \
    /opt/SLV_Bot/*.db \
    /opt/SLV_Bot/*.mp3 \
    /etc/systemd/system/SLV-bot.service

# Удаляем старые
find "$BACKUP_DIR" -name "SLV_bot_auto_*.tar.gz" -mtime +7 -delete

# Отправляем уведомление в Telegram
/opt/SLV_Bot/venv/bin/python3 << 'PYEOF'
import asyncio, sys
sys.path.insert(0, '/opt/SLV_Bot')
from telegram import Bot
from config import BOT_TOKEN, ADMIN_IDS
from datetime import datetime

async def send():
    bot = Bot(token=BOT_TOKEN)
    now = datetime.now()
    months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
             'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']

    import os
    backup_file = os.popen('ls -t /opt/SLV_Bot/backups/SLV_bot_auto_*.tar.gz | head -1').read().strip()
    size = os.popen(f'du -sh {backup_file}').read().split()[0] if backup_file else '?'
    name = os.path.basename(backup_file) if backup_file else '?'

    message = f"💾 <b>АВТО-БЭКАП СОЗДАН</b>\n\n"
    message += f"📁 <b>Файл:</b> {name}\n"
    message += f"📏 <b>Размер:</b> {size}\n"
    message += f"🕐 <b>Время:</b> {now.day} {months[now.month-1]} {now.year} | {now.strftime('%H:%M')}\n\n"
    message += f"<i>Бэкап создан автоматически</i>"

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message, parse_mode='HTML')
        except:
            pass

asyncio.run(send())
PYEOF

echo "$(date): Бэкап создан: $BACKUP_NAME" >> /var/log/slv_backup.log
