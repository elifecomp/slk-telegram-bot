# [file name]: connection_notifier.py
"""
Модуль уведомлений о подключении/отключении клиентов.
Проверяет онлайн-статус каждые 15 секунд и отправляет уведомления админам.
"""

import logging
import asyncio
import time
from datetime import datetime
from typing import Set, Dict

logger = logging.getLogger(__name__)

class ConnectionNotifier:
    def __init__(self, application):
        self.application = application
        self.bot = application.bot
        self.running = False
        self._task = None
        self._previous_online: Set[str] = set()
        self._last_notification: Dict[str, float] = {}
        self.cooldown = 120  # пауза между уведомлениями (сек)
        self.check_interval = 15  # интервал проверки (сек)
        logger.info("🔔 ConnectionNotifier инициализирован")

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"🔔 Мониторинг подключений запущен (интервал: {self.check_interval}с)")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("🔔 Мониторинг подключений остановлен")

    async def _monitor_loop(self):
        while self.running:
            try:
                await self._check_connections()
            except Exception as e:
                logger.error(f"Ошибка в мониторинге: {e}")
            await asyncio.sleep(self.check_interval)

    async def _check_connections(self):
        try:
            from xui_api import get_online_clients
            from panel_manager import get_panels_list, set_active_panel, get_active_panel

            panels = get_panels_list()
            original = get_active_panel()['id']

            for panel in panels:
                set_active_panel(panel['id'])
                await self._check_panel(panel)

            set_active_panel(original)
        except Exception as e:
            logger.error(f"Ошибка проверки подключений: {e}")

    async def _check_panel(self, panel):
        global notifications_enabled
        if not notifications_enabled:
            return
        try:
            from xui_api import get_online_clients
            from database import db
            from panel_manager import get_active_panel

            panel_name = panel["name"]
            current_online = set(get_online_clients())


            if not current_online and not self._previous_online:
                return

            new_connections = current_online - self._previous_online
            disconnected = self._previous_online - current_online
            now = time.time()

            for email in new_connections:
                if self._can_notify(email, now):
                    await self._notify_connected(email, panel_name)
                    self._last_notification[email] = now

            for email in disconnected:
                if self._can_notify(email, now):
                    if email not in current_online:
                        await self._notify_disconnected(email, panel_name)
                        self._last_notification[email] = now

            self._previous_online = current_online

        except Exception as e:
            logger.error(f"Ошибка проверки подключений: {e}")

    def _can_notify(self, email: str, now: float) -> bool:
        last_time = self._last_notification.get(email, 0)
        return (now - last_time) >= self.cooldown

    async def _notify_connected(self, email: str, panel_name: str):
        try:
            from database import db
            from config import ADMIN_IDS

            client = db.get_client_by_login(email)

            if client:
                # Получаем IP и оператора
                ip_info = ""
                try:
                    from xui_api import get_client_ips
                    import requests as req
                    ips = get_client_ips(email)
                    if ips:
                        ip = str(ips[0]).split(' ')[0].strip()
                        if ip and '.' in ip:
                            ip_info = f"\n🌐 <b>IP:</b> <code>{ip}</code>"
                            try:
                                r = req.get(f"http://ip-api.com/json/{ip}?fields=isp", timeout=3)
                                if r.status_code == 200:
                                    isp = r.json().get('isp', '')
                                    if isp:
                                        ip_info += f"\n📡 <b>Оператор:</b> {isp}"
                            except: pass
                except: pass

                message = (
                    f"🟢 <b>КЛИЕНТ ПОДКЛЮЧИЛСЯ</b>\n\n"
                    f"🏷️ <b>Панель:</b> {panel_name}\n"
                    f"👤 <b>Имя:</b> {client['name']}\n"
                    f"📝 <b>Логин:</b> {email}\n"
                    f"📞 <b>Телефон:</b> {client['phone']}\n"
                    f"{ip_info}\n"
                    f"🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}"
                )
            else:
                # IP для ненайденных
                ip_info = ""
                try:
                    from xui_api import get_client_ips
                    import requests as req
                    ips = get_client_ips(email)
                    if ips:
                        ip = str(ips[0]).split(' ')[0].strip()
                        if ip and '.' in ip:
                            ip_info = f"\n🌐 <b>IP:</b> <code>{ip}</code>"
                            try:
                                r = req.get(f"http://ip-api.com/json/{ip}?fields=isp", timeout=3)
                                if r.status_code == 200:
                                    isp = r.json().get('isp', '')
                                    if isp:
                                        ip_info += f"\n📡 <b>Оператор:</b> {isp}"
                            except: pass
                except: pass

                message = (
                    f"🟢 <b>КЛИЕНТ ПОДКЛЮЧИЛСЯ</b>\n\n"
                    f"🏷️ <b>Панель:</b> {panel_name}\n"
                    f"📝 <b>Логин:</b> {email}\n"
                    f"{ip_info}\n"
                    f"🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}\n"
                    f"⚠️ <i>Не найден в базе данных</i>"
                )

            for admin_id in ADMIN_IDS:
                try:
                    await self.bot.send_message(admin_id, message, parse_mode='HTML')
                except:
                    pass

            for admin_id in ADMIN_IDS:
                try:
                    await self.bot.send_message(admin_id, message, parse_mode=HTML)

                except:
                    pass

            logger.info(f"🔔 {email} подключился ({panel_name})")
        except Exception as e:
            logger.error(f"Ошибка уведомления: {e}")

    async def _notify_disconnected(self, email: str, panel_name: str):
        try:
            from database import db
            from config import ADMIN_IDS

            client = db.get_client_by_login(email)

            if client:
                message = (
                    f"🔴 <b>КЛИЕНТ ОТКЛЮЧИЛСЯ</b>\n\n"
                    f"🏷️ <b>Панель:</b> {panel_name}\n"
                    f"👤 <b>Имя:</b> {client['name']}\n"
                    f"📝 <b>Логин:</b> {email}\n"
                    f"📞 <b>Телефон:</b> {client['phone']}\n"
                    f"🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}"
                )
            else:
                message = (
                    f"🔴 <b>КЛИЕНТ ОТКЛЮЧИЛСЯ</b>\n\n"
                    f"🏷️ <b>Панель:</b> {panel_name}\n"
                    f"📝 <b>Логин:</b> {email}\n"
                    f"🕐 <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}"
                )

            for admin_id in ADMIN_IDS:
                try:
                    await self.bot.send_message(admin_id, message, parse_mode=HTML)
                except:
                    pass

            logger.info(f"🔔 {email} отключился ({panel_name})")
        except Exception as e:
            logger.error(f"Ошибка уведомления: {e}")


notifier = None
# Загружаем состояние из файла
import os as _os
_notify_file = '/opt/SLV_Bot/notify_state.txt'
if _os.path.exists(_notify_file):
    with open(_notify_file, 'r') as _f:
        notifications_enabled = _f.read().strip() == '1'
else:
    notifications_enabled = True

async def init_notifier(application):
    global notifier
    notifier = ConnectionNotifier(application)
    await notifier.start()
    return notifier


def toggle_notifications() -> bool:
    """Переключает уведомления вкл/выкл. Возвращает новое состояние."""
    global notifications_enabled
    notifications_enabled = not notifications_enabled
    with open(_notify_file, 'w') as _f:
        _f.write('1' if notifications_enabled else '0')
    logger.info(f"🔔 Уведомления: {'ВКЛЮЧЕНЫ' if notifications_enabled else 'ВЫКЛЮЧЕНЫ'}")
    return notifications_enabled

def get_notifications_status() -> bool:
    """Возвращает статус уведомлений"""
    global notifications_enabled
    return notifications_enabled

async def stop_notifier():
    global notifier
    if notifier:
        await notifier.stop()
