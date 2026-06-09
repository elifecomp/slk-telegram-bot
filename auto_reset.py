# [file name]: auto_reset.py
"""Автосброс трафика каждое 1 число в 00:01"""

import logging
import asyncio
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AutoReset:
    def __init__(self, application):
        self.application = application
        self.bot = application.bot
        self.running = False
        self._task = None
        self.last_reset = None
        logger.info("🔄 AutoReset инициализирован")
    
    async def start(self):
        if self.running: return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("🔄 Автосброс запущен (ждёт 1 числа 00:01)")
    
    async def stop(self):
        self.running = False
        if self._task: self._task.cancel()
    
    async def _loop(self):
        while self.running:
            now = datetime.now()
            # Вычисляем следующее 1 число 00:01
            if now.day == 1 and now.hour == 0 and now.minute == 1:
                target = now
            elif now.day == 1 and now.hour == 0 and now.minute < 1:
                target = now.replace(minute=1, second=0, microsecond=0)
            elif now.day == 1:
                # Уже прошло — ждём следующего месяца
                if now.month == 12:
                    target = now.replace(year=now.year+1, month=1, day=1, hour=0, minute=1, second=0, microsecond=0)
                else:
                    target = now.replace(month=now.month+1, day=1, hour=0, minute=1, second=0, microsecond=0)
            else:
                # Ждём 1 числа
                if now.month == 12:
                    target = now.replace(year=now.year+1, month=1, day=1, hour=0, minute=1, second=0, microsecond=0)
                else:
                    target = now.replace(month=now.month+1, day=1, hour=0, minute=1, second=0, microsecond=0)
            
            wait = (target - now).total_seconds()
            if wait > 0:
                logger.info(f"🔄 Следующий автосброс: {target.strftime('%d.%m.%Y %H:%M')} (через {wait/3600:.1f} ч)")
                await asyncio.sleep(min(wait, 3600))  # Проверяем каждый час
                continue
            
            # Время пришло — делаем сброс
            await self._do_reset()
            
            # Ждём минуту чтобы не сработало дважды
            await asyncio.sleep(60)
    
    async def _do_reset(self):
        """Выполняет сброс трафика на всех панелях"""
        if self.last_reset and self.last_reset.date() == datetime.now().date():
            return  # Уже сбросили сегодня
        
        logger.info("🔄 Начинаю автосброс трафика...")
        
        from panel_manager import get_panels_list, set_active_panel, get_active_panel
        from xui_api import get_inbounds_list, reset_client_traffic
        from config import ADMIN_IDS
        
        panels = get_panels_list()
        original = get_active_panel()['id']
        total_reset = 0
        
        for panel in panels:
            try:
                set_active_panel(panel['id'])
                inbounds = get_inbounds_list()
                
                for inbound in inbounds:
                    inbound_id = inbound.get('id')
                    clients = inbound.get('clientStats', [])
                    
                    for client in clients:
                        if client.get('enable', True):
                            email = client.get('email', '')
                            if email:
                                try:
                                    reset_client_traffic(inbound_id, email)
                                    total_reset += 1
                                except:
                                    pass
            except Exception as e:
                logger.error(f"Ошибка сброса на панели {panel['name']}: {e}")
        
        set_active_panel(original)
        self.last_reset = datetime.now()
        
        # Отчёт админу
        months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
                 'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']
        now = datetime.now()
        
        message = f"🔄 <b>АВТОСБРОС ТРАФИКА</b>\n\n"
        message += f"📅 <b>Дата:</b> {now.day} {months[now.month-1]} {now.year}\n"
        message += f"🕐 <b>Время:</b> {now.strftime('%H:%M')}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"👥 <b>Сброшено клиентов:</b> {total_reset}\n"
        message += f"🔗 <b>Панелей:</b> {len(panels)}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"✅ <b>Автосброс выполнен успешно!</b>"
        
        for admin_id in ADMIN_IDS:
            try:
                await self.bot.send_message(admin_id, message, parse_mode='HTML')
            except:
                pass
        
        logger.info(f"🔄 Автосброс завершён: {total_reset} клиентов")


auto_reset = None

async def init_auto_reset(application):
    global auto_reset
    auto_reset = AutoReset(application)
    await auto_reset.start()
    return auto_reset

async def stop_auto_reset():
    global auto_reset
    if auto_reset:
        await auto_reset.stop()
