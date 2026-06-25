"""Мониторинг узлов 3x-ui"""
import asyncio, requests, logging
from datetime import datetime
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext

logger = logging.getLogger(__name__)

NODES_FILE = "/opt/SLV_Bot/.nodes_status"
CHECK_INTERVAL = 300  # 5 минут

def get_nodes():
    """Получает список узлов из панели"""
    import os
    from xui_api import _get
    r = _get('/panel/api/nodes/list')
    return r.get('obj', []) if r.get('success') else []

def load_status():
    try:
        with open(NODES_FILE) as f:
            return __import__('json').load(f)
    except:
        return {}

def save_status(data):
    with open(NODES_FILE, 'w') as f:
        __import__('json').dump(data, f)

async def node_monitor(app):
    """Фоновый мониторинг узлов"""
    await asyncio.sleep(30)
    last_status = load_status()
    
    while True:
        try:
            nodes = get_nodes()
            current = {}
            alerts = []
            
            for node in nodes:
                node_id = str(node.get('id', ''))
                name = node.get('name', node.get('address', 'Без имени'))
                status = node.get('status', 'unknown')
                current[node_id] = status
                prev = last_status.get(node_id, 'online')
                
                if status != 'online' and prev == 'online':
                    alerts.append(
                        f"🔴 <b>УЗЕЛ НЕДОСТУПЕН!</b>\n\n"
                        f"📡 <b>{name}</b>\n"
                        f"📍 {node.get('address', '?')}\n"
                        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
                    )
                elif status == 'online' and prev != 'online':
                    latency = node.get('latencyMs', '?')
                    alerts.append(
                        f"🟢 <b>УЗЕЛ В СЕТИ</b>\n\n"
                        f"📡 <b>{name}</b>\n"
                        f"📍 {node.get('address', '?')}\n"
                        f"⚡ Задержка: {latency} мс\n"
                        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
                    )
            
            if alerts:
                from config import ADMIN_IDS
                for alert in alerts:
                    for admin_id in ADMIN_IDS:
                        try:
                            await app.bot.send_message(admin_id, alert, parse_mode='HTML')
                        except:
                            pass
            
            save_status(current)
            last_status = current
        except Exception as e:
            logger.error(f"Ошибка мониторинга узлов: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)
