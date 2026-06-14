# [file name]: birthday_greeter.py
"""Авто-поздравление с днём рождения"""

import logging
from config import BOT_NAME
import asyncio
import random
from datetime import datetime

logger = logging.getLogger(__name__)

BIRTHDAY_MESSAGES = [
    "🎂 С днём рождения! Пусть этот день будет полон радости и счастья!",
    "🎉 Поздравляем с днём рождения! Здоровья, удачи и быстрого интернета!",
    "🎁 С днём рождения! Твой VPN всегда с тобой — везде и всегда!",
    "🥳 С днём рождения! Пусть сбудутся все мечты!",
    "🎈 Поздравляем! Желаем море позитива и гигабиты скорости!",
    "🎊 С днём рождения! Ты — часть нашей команды!",
    "💫 С днём рождения! Новый год жизни — новые возможности!",
    "🌟 Поздравляем! Пусть каждый день будет особенным!",
    "🍀 С днём рождения! Удачи во всём и везде!",
    "🎵 С днём рождения! Пусть жизнь будет как любимый плейлист!",
]

class BirthdayGreeter:
    def __init__(self, application):
        self.application = application
        self.bot = application.bot
        self.running = False
        self._task = None
        self.last_check_date = None
        logger.info("🎂 BirthdayGreeter инициализирован")

    async def start(self):
        if self.running: return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("🎂 Поздравления с днём рождения запущены")
        # Проверяем сразу при старте
        pass  # отключено
        # Проверяем сразу при старте
        pass  # отключено

    async def stop(self):
        self.running = False
        if self._task: self._task.cancel()

    async def _loop(self):
        while self.running:
            today = datetime.now().date()

            if self.last_check_date != today:
                await self._check_birthdays()
                self.last_check_date = today

            await asyncio.sleep(3600)  # Проверяем раз в час

    async def _check_birthdays(self):
        from database import db
        users = db.get_all_clients()
        today = datetime.now()

        for user in users:
            birthday = user.get('birthday', '')
            if not birthday:
                continue

            try:
                # Формат ДД.ММ.ГГГГ
                b_day, b_month, _ = birthday.split('.')
                if int(b_day) == today.day and int(b_month) == today.month:
                    await self._send_greeting(user)
            except:
                pass

    async def _send_greeting(self, user):
        # Проверяем не отправляли ли уже сегодня
        today = datetime.now().date()
        if hasattr(self, '_sent_today') and user['id'] in self._sent_today:
            return
        if not hasattr(self, '_sent_today'):
            self._sent_today = set()
        self._sent_today.add(user['id'])
        try:
            message = random.choice(BIRTHDAY_MESSAGES)
            msg = f"{message}\n\n"
            msg += f"👤 <b>{user['name']}</b>\n"
            msg += f"🎂 <b>С днём рождения!</b>\n\n"
            msg += BOT_NAME

            await self.bot.send_sticker(user['telegram_id'], 'CAACAgIAAxkBAAI1OWohkm8tfzWG0h8R3-HHZNSJ1vB8AAILAQAC9wLID8X0O5iVqnHbOwQ')
            await self.bot.send_message(user['telegram_id'], msg, parse_mode='HTML')
            logger.info(f"🎂 Поздравление отправлено: {user['name']}")
        except Exception as e:
            logger.error(f"Ошибка поздравления {user['name']}: {e}")


greeter = None

async def init_birthday_greeter(application):
    global greeter
    greeter = BirthdayGreeter(application)
    await greeter.start()
    return greeter

async def stop_birthday_greeter():
    global greeter
    if greeter:
        await greeter.stop()
