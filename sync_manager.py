# [file name]: sync_manager.py
"""Синхронизация клиентов между панелью 3x-ui и базой бота"""

import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class SyncManager:
    def __init__(self, application):
        self.application = application
        self.bot = application.bot
        self.running = False
        self._task = None
        self.last_sync = None
        logger.info("🔄 SyncManager инициализирован")

    async def start(self):
        if self.running: return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("🔄 Автосинхронизация запущена (раз в 6 часов)")

    async def stop(self):
        self.running = False
        if self._task: self._task.cancel()

    async def _loop(self):
        while self.running:
            try:
                await self._sync()
            except Exception as e:
                logger.error(f"Ошибка синхронизации: {e}")
            await asyncio.sleep(21600)  # 6 часов

    async def _sync(self):
        """Выполняет синхронизацию"""
        from database import db
        from panel_manager import get_panels_list, set_active_panel, get_active_panel
        from xui_api import get_inbounds_list

        panels = get_panels_list()
        original = get_active_panel()['id']

        updated = 0
        added = 0
        deactivated = 0
        changes = []

        # Собираем всех клиентов из панелей
        panel_clients = set()
        for panel in panels:
            set_active_panel(panel['id'])
            inbounds = get_inbounds_list()
            for inbound in inbounds:
                for c in inbound.get('clientStats', []):
                    email = c.get('email', '')
                    if email:
                        panel_clients.add(email)

        set_active_panel(original)

        # Сверяем с базой
        db_users = db.get_all_clients()
        db_logins = {u['login'] for u in db_users}

        # Новые клиенты из панели (есть в панели, нет в базе)
        new_in_panel = panel_clients - db_logins
        for email in new_in_panel:
            # Добавляем в базу с минимальными данными
            try:
                import sqlite3
                conn = sqlite3.connect('/opt/SLV_Bot/clients.db')
                conn.execute(
                    "INSERT INTO clients (telegram_id, login, phone, name, is_active) VALUES (?, ?, ?, ?, 1)",
                    (0, email, '', email.split('🇷🇺')[0].strip() or email,)
                )
                conn.commit()
                conn.close()
                added += 1
                changes.append(f"➕ {email} — добавлен")
            except:
                pass

        # Клиенты удалённые из панели (есть в базе, нет в панели)
        removed = db_logins - panel_clients
        for login in removed:
            client = db.get_client_by_login(login)
            if client and client['is_active']:
                db.toggle_client_active(client['id'])
                deactivated += 1
                changes.append(f"⚠️ {login} — деактивирован")

        self.last_sync = datetime.now()

        # Отчёт админу
        if added > 0 or deactivated > 0 or updated > 0:
            from config import ADMIN_IDS

            message = f"🔄 <b>СИНХРОНИЗАЦИЯ КЛИЕНТОВ</b>\n\n"
            message += f"➕ <b>Добавлено:</b> {added}\n"
            message += f"✏️ <b>Обновлено:</b> {updated}\n"
            message += f"⚠️ <b>Деактивировано:</b> {deactivated}\n\n"

            if changes:
                message += "<b>Изменения:</b>\n"
                for ch in changes[:10]:
                    message += f"  {ch}\n"

            for admin_id in ADMIN_IDS:
                try:
                    await self.bot.send_message(admin_id, message, parse_mode='HTML')
                except:
                    pass

        logger.info(f"🔄 Синхронизация: +{added} ✏️{updated} ⚠️{deactivated}")

sync_manager = None

async def init_sync_manager(application):
    global sync_manager
    sync_manager = SyncManager(application)
    await sync_manager.start()
    return sync_manager

async def stop_sync_manager():
    global sync_manager
    if sync_manager:
        await sync_manager.stop()
