#!/usr/bin/env python3
"""Уведомления о трафике: предупреждение при 95%"""
import asyncio, logging
from datetime import datetime

logger = logging.getLogger(__name__)
THRESHOLD_PERCENT = 95
NOTIFIED_FILE = "/opt/SLV_Bot/.traffic_notified"

def get_notified():
    try:
        with open(NOTIFIED_FILE) as f:
            return set(f.read().strip().split(','))
    except:
        return set()

def save_notified(emails):
    with open(NOTIFIED_FILE, 'w') as f:
        f.write(','.join(emails))

async def traffic_monitor(app):
    await asyncio.sleep(30)
    while True:
        try:
            today = datetime.now()
            if today.day == 1 and today.hour == 0:
                save_notified([])
                logger.info("Новый месяц — список уведомлений сброшен")

            from xui_api import _get
            r = _get('/panel/api/clients/list')
            if not r.get('success'):
                await asyncio.sleep(3600)
                continue

            clients = r.get('obj', [])
            notified = get_notified()
            new_notified = set()
            alerts = []

            for client in clients:
                email = client.get('email', '')
                if email == 'Admin':
                    continue

                traffic = _get(f'/panel/api/clients/traffic/{email}')
                if not traffic.get('success'):
                    continue

                data = traffic.get('obj', {})
                total_bytes = data.get('total', 0)
                if total_bytes <= 0:
                    continue

                up = data.get('up', 0)
                down = data.get('down', 0)
                used = up + down
                used_gb = used / (1024**3)
                total_gb = total_bytes / (1024**3)
                percent = min((used_gb / total_gb) * 100, 100) if total_gb > 0 else 0

                if percent >= THRESHOLD_PERCENT and email not in notified:
                    alerts.append({
                        'email': email,
                        'used': used_gb,
                        'total': total_gb,
                        'percent': percent,
                        'remaining': max(total_gb - used_gb, 0)
                    })
                    new_notified.add(email)

            if alerts:
                from config import ADMIN_IDS
                from database import db
                for alert in alerts:
                    client_db = db.get_client_by_login(alert['email'])
                    tg_id = client_db['telegram_id'] if client_db else None

                    msg = (
                        f"⚠️ <b>ТРАФИК ЗАКАНЧИВАЕТСЯ!</b>\n\n"
                        f"📊 Использовано: <b>{alert['used']:.1f} GB</b> из {alert['total']:.1f} GB ({alert['percent']:.0f}%)\n"
                        f"⏳ Осталось: <b>{alert['remaining']:.1f} GB</b>\n\n"
                        f"🔄 Трафик обновится 1-го числа\n"
                        f"💡 Рекомендуем экономить трафик"
                    )

                    if tg_id and tg_id > 0:
                        try:
                            await app.bot.send_message(tg_id, msg, parse_mode='HTML')
                        except:
                            pass

                    admin_msg = (
                        f"⚠️ <b>КЛИЕНТ ИСЧЕРПАЛ ТРАФИК</b>\n\n"
                        f"👤 {alert['email']}\n"
                        f"📊 {alert['used']:.1f} / {alert['total']:.1f} GB ({alert['percent']:.0f}%)\n"
                        f"⏳ Осталось: {alert['remaining']:.1f} GB"
                    )

                    for admin_id in ADMIN_IDS:
                        try:
                            await app.bot.send_message(admin_id, admin_msg, parse_mode='HTML')
                        except:
                            pass

                save_notified(notified | new_notified)
                logger.info(f"Отправлено {len(new_notified)} уведомлений")
        except Exception as e:
            logger.error(f"Ошибка проверки трафика: {e}")
        await asyncio.sleep(3600)
