# [file name]: websocket_notifier.py
"""WebSocket клиент для мгновенных уведомлений от 3x-ui 3.2.6 (упрощённая версия)"""

import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class WebSocketNotifier:
    def __init__(self, application):
        self.application = application
        self.bot = application.bot
        self.running = False
        self._task = None
        logger.info("🔌 WebSocketNotifier инициализирован (режим совместимости)")

    async def start(self):
        if self.running:
            return
        self.running = True
        # Пока отключаем WebSocket, используем обычный polling
        logger.info("🔌 WebSocket уведомления: используется polling режим")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("🔌 WebSocket уведомления остановлены")

ws_notifier = None

async def init_ws_notifier(application):
    global ws_notifier
    ws_notifier = WebSocketNotifier(application)
    await ws_notifier.start()
    return ws_notifier

async def stop_ws_notifier():
    global ws_notifier
    if ws_notifier:
        await ws_notifier.stop()
