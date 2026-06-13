#!/usr/bin/env python3
"""Уведомления о трафике: предупреждение при 95%, сброс 1-го числа"""
import asyncio, logging
from datetime import datetime
from xui_api import get_inbounds_list

logger = logging.getLogger(__name__)

THRESHOLD_PERCENT = 95  # порог предупреждения
NOTIFIED_FILE = "/opt/SLV_Bot/.traffic_notified"

def get_notified():
    """Загружает список уже уведомлённых клиентов"""
    try:
        with open(NOTIFIED_FILE) as f:
            return set(f.read().strip().split(','))
    except:
        return set()

def save_notified(emails):
    """Сохраняет список уведомлённых"""
    with open(NOTIFIED_FILE, 'w') as f:
        f.write(','.join(emails))

async def traffic_monitor(app):
    """Проверяет трафик клиентов раз в час"""
    await asyncio.sleep(30)  # ждём инициализации бота
    
    while True:
        try:
            today = datetime.now()
            is_first_day = (today.day == 1)
            
            # Сбрасываем список уведомлённых 1-го числа
            if is_first_day and today.hour == 0:
                save_notified([])
                logger.info("🔄 Новый месяц — список уведомлений сброшен")
            
            # Получаем клиентов из панели
            inbounds = get_inbounds_list()
            notified = get_notified()
            new_notified = set()
            alerts = []
            
            for inbound in inbounds:
                settings = inbound.get('settings', {})
                if isinstance(settings, str):
                    import json
                    try:
                        settings = json.loads(settings) if settings.strip() else {}
                    except:
                        settings = {}
                
                if not isinstance(settings, dict):
                    continue
                    
                for client in settings.get('clients', []):
                    email = client.get('email', '')
                    total_gb = client.get('totalGB', 0)
                    
                    if total_gb <= 0:
                        continue  # безлимит
                    
                    # Трафик: up + down
                    up = client.get('up', 0)
                    down = client.get('down', 0)
                    used = up + down
                    used_gb = used / (1024**3)
                    total_gb_val = total_gb / (1024**3)
                    percent = (used_gb / total_gb_val) * 100 if total_gb_val > 0 else 0
                    
                    if percent >= THRESHOLD_PERCENT and email not in notified:
                        alerts.append({
                            'email': email,
                            'used': used_gb,
                            'total': total_gb_val,
                            'percent': percent,
                            'remaining': total_gb_val - used_gb
                        })
                        new_notified.add(email)
            
            # Отправляем уведомления
            from config import ADMIN_IDS
            for alert in alerts:
                # Клиенту (если есть Telegram ID)
                from database import db
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
                
                # Админу
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
            
            if new_notified:
                save_notified(notified | new_notified)
                logger.info(f"Отправлено {len(new_notified)} уведомлений о трафике")
                
        except Exception as e:
            logger.error(f"Ошибка проверки трафика: {e}")
        
        await asyncio.sleep(3600)  # раз в час
