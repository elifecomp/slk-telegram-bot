# [file name]: update_checker.py
"""Проверка обновлений панели 3x-ui и уведомление админа"""

import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class UpdateChecker:
    def __init__(self, application):
        self.application = application
        self.bot = application.bot
        self.running = False
        self._task = None
        self._last_version = None
        logger.info("🆕 UpdateChecker инициализирован")
    
    async def start(self):
        if self.running: return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("🆕 Проверка обновлений запущена (раз в 3 часа)")
    
    async def stop(self):
        self.running = False
        if self._task: self._task.cancel()
    
    async def _loop(self):
        while self.running:
            try:
                await self._check_updates()
            except Exception as e:
                logger.error(f"Ошибка проверки обновлений: {e}")
            await asyncio.sleep(10800)  # 3 часа
    
    async def _check_updates(self):
        from xui_api import get_panel_update_info
        from config import ADMIN_IDS
        
        info = get_panel_update_info()
        if not info:
            return
        
        current = info.get('currentVersion', '')
        latest = info.get('latestVersion', '')
        update_available = info.get('updateAvailable', False)
        
        if update_available and self._last_version != latest:
            self._last_version = latest
            
            now = datetime.now()
            months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
                     'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']
            
            message = "🆕 <b>ДОСТУПНО ОБНОВЛЕНИЕ ПАНЕЛИ!</b>\n\n"
            message += f"📦 <b>Текущая версия:</b> {current}\n"
            message += f"🆕 <b>Новая версия:</b> {latest}\n"
            message += f"🕐 <b>Время:</b> {now.day} {months[now.month-1]} {now.year} | {now.strftime('%H:%M')}\n\n"
            message += f"<i>Обновите панель в настройках 3x-ui</i>"
            
            for admin_id in ADMIN_IDS:
                try:
                    await self.bot.send_message(admin_id, message, parse_mode='HTML')
                except:
                    pass
            
            logger.info(f"🆕 Уведомление об обновлении: {current} → {latest}")


checker = None

async def init_update_checker(application):
    global checker
    checker = UpdateChecker(application)
    await checker.start()
    return checker

async def stop_update_checker():
    global checker
    if checker:
        await checker.stop()
