# [file name]: morning_greeter.py
"""Утренняя рассылка с мотивацией и погодой"""

import logging
import asyncio
import random
from datetime import datetime
from config import BOT_NAME

logger = logging.getLogger(__name__)

# Банк мотивационных фраз
def load_quotes():
    """Загружает цитаты из файла"""
    try:
        with open('/opt/SLV_Bot/quotes.txt', 'r', encoding='utf-8') as f:
            quotes = [line.strip() for line in f if line.strip()]
        return quotes if quotes else ["🚀 Отличного дня!"]
    except:
        return ["🚀 Отличного дня!"]

MOTIVATION = load_quotes()

# Сезонные советы
SEASONAL_TIPS = {
    # Весна (март, апрель, май)
    'spring': [
        "🌸 Весна в разгаре! Самое время для прогулок с любимой музыкой.",
        "🌷 Мартовское настроение — обнови плейлист через быстрый VPN!",
        "🌱 Природа просыпается, а твой интернет всегда на высоте!",
        "🦋 Весенний ветер перемен — открой для себя новые сайты!",
        "🌺 Апрельская капель? Оставайся онлайн с тёплым пледиком.",
        "🐝 Майский день — работай на свежем воздухе с надёжным VPN!",
        "🌿 Весна — время обновлений! Проверь новые приложения.",
        "💐 Цветущая весна за окном, быстрый интернет — в твоём кармане!",
        "🌞 Солнечный денёк! Бери ноутбук в парк — VPN защитит.",
        "🍃 Весенняя прохлада? Согрейся горячим чаем и любимым сериалом.",
    ],
    # Лето (июнь, июль, август)
    'summer': [
        "☀️ Жаркий денёк! Охладись лимонадом и быстрым интернетом.",
        "🏖️ Лето — пора путешествий! VPN с тобой в любой точке мира.",
        "🌊 Море, пляж и... свободный интернет! Что может быть лучше?",
        "🍉 Летняя жара? Спрячься в тень и смотри кино без границ!",
        "🌴 Отпускной сезон — не забудь взять VPN с собой!",
        "🕶️ Солнце, лето, быстрый VPN — идеальное трио!",
        "⛱️ Загораешь? Пусть интернет будет таким же горячим, как песок!",
        "🍦 Мороженое в одной руке, смартфон с VPN — в другой!",
        "🌅 Летний вечер — идеальное время для онлайн-игр с друзьями.",
        "🎵 Летний фестиваль? Смотри трансляции через VPN без границ!",
    ],
    # Осень (сентябрь, октябрь, ноябрь)
    'autumn': [
        "🍂 Осенняя прохлада — укутайся в плед и смотри кино!",
        "🎃 Октябрьский вечер? Время для хорроров под VPN!",
        "🍁 Золотая осень за окном — твой интернет сияет ярче!",
        "🌧️ Дождливый день? Идеально для онлайн-шопинга с VPN!",
        "☕ Горячий кофе + быстрый интернет = уютная осень!",
        "🍄 Грибной сезон! А твой VPN собирает только лучшие сайты.",
        "📚 Осенний вечер — скачай любимую книгу через быстрый VPN.",
        "🎧 За окном серо? Раскрась день любимой музыкой без границ!",
        "🍎 Урожайный сезон! Собери коллекцию любимых сайтов.",
        "💨 Ветреная погода? Твой VPN устойчив к любым бурям!",
    ],
    # Зима (декабрь, январь, февраль)
    'winter': [
        "❄️ Снежно и холодно? Согрейся горячим чаем и быстрым интернетом!",
        "⛄ Зимняя сказка за окном — смотри любимые фильмы онлайн!",
        "🎄 Новогоднее настроение! Скачай праздничный плейлист через VPN.",
        "🧣 Укутайся потеплее — твой VPN уже работает на полную!",
        "☃️ Морозный денёк? Оставайся дома с быстрым интернетом!",
        "🎁 Зимние скидки! Ищи подарки на любых сайтах через VPN.",
        "🛷 Катайся с горки, а вечером — любимый сериал без границ!",
        "🕯️ Долгий зимний вечер? Время для онлайн-игр с друзьями!",
        "🌟 Звёздная зимняя ночь — твой интернет такой же быстрый!",
        "🏔️ За окном сугробы, а у тебя — свободный доступ ко всему!",
    ],
}


def get_weather_by_ip(ip):
    """Получает погоду по IP клиента"""
    try:
        import requests as req
        # Сначала получаем город
        r = req.get(f"http://ip-api.com/json/{ip}?fields=city", timeout=3)
        city = "Москва"
        if r.status_code == 200:
            data = r.json()
            city = data.get('city', 'Москва')

        # Получаем погоду
        r2 = req.get(f"http://wttr.in/{city}?format=%c+%t&lang=ru", timeout=5)
        if r2.status_code == 200:
            weather = r2.text.strip()
            return f"🌤️ <b>Погода в {city}:</b>\n   {weather}"
    except:
        pass
    return ""

def get_seasonal_tip():
    """Возвращает совет по текущему сезону"""
    month = datetime.now().month
    if month in [3, 4, 5]:
        return random.choice(SEASONAL_TIPS['spring'])
    elif month in [6, 7, 8]:
        return random.choice(SEASONAL_TIPS['summer'])
    elif month in [9, 10, 11]:
        return random.choice(SEASONAL_TIPS['autumn'])
    else:
        return random.choice(SEASONAL_TIPS['winter'])

# Банк приветствий
GREETINGS = [
    "☀️ Доброе утро!",
    "🌤️ С добрым утром!",
    "🌸 Прекрасное утро!",
    "🌅 Доброе утро, мир!",
    "⭐ Утро начинается с тебя!",
    "💫 Счастливого нового дня!",
    "🦋 Лёгкого и яркого утра!",
    "🌺 Доброе утро, красота!",
    "🍀 Удачное утро!",
    "🎋 Пусть утро будет добрым!",
]

class MorningGreeter:
    def __init__(self, application):
        self.application = application
        self.bot = application.bot
        self.running = False
        self._task = None
        self.last_send_date = None
        logger.info("🌅 MorningGreeter инициализирован")

    async def start(self):
        if self.running: return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("🌅 Утренняя рассылка запущена (каждое утро в 08:00)")

    async def stop(self):
        self.running = False
        if self._task: self._task.cancel()

    async def _loop(self):
        while self.running:
            now = datetime.now()
            target = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now >= target:
                target = target.replace(day=now.day + 1)

            wait = (target - now).total_seconds()
            logger.info(f"🌅 Следующая рассылка: {target.strftime('%d.%m.%Y %H:%M')} (через {wait/3600:.1f} ч)")

            await asyncio.sleep(wait)
            await self._send_morning()
            await asyncio.sleep(60)  # чтобы не сработало дважды

    async def _send_morning(self):
        today = datetime.now().date()
        if self.last_send_date == today:
            return

        from database import db
        users = db.get_all_clients()

        if not users:
            return

        logger.info(f"🌅 Отправка утренних сообщений {len(users)} пользователям...")

        sent = 0
        for user in users:
            try:
                greeting = random.choice(GREETINGS)
                now = datetime.now()
                months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
                         'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']
                weekdays = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']

                greeting = random.choice(GREETINGS)
                motivation = random.choice(MOTIVATION)
                season_tip = get_seasonal_tip()

                real_weather = ""
                city = user.get('city', '')
                if city:
                    try:
                        import requests as req
                        import urllib.parse
                        encoded_city = urllib.parse.quote(city)
                        r = req.get(f"http://wttr.in/{encoded_city}?format=3&lang=ru", timeout=5)
                        if r.status_code == 200:
                            w = r.text.strip()
                            real_weather = f"🌤️ <b>Погода в {city} сейчас:</b>\n   {w}"
                    except:
                        pass

                message = f"{greeting} <b>{user['name']}</b>!\n"
                message += f"📅 <i>{now.day} {months[now.month-1]}, {weekdays[now.weekday()]}</i>\n\n"
                if real_weather:
                    message += f"{real_weather}\n\n"
                message += f"{motivation}\n\n"
                message += f"{season_tip}\n\n"
                message += BOT_NAME

                try:
                    await self.bot.send_sticker(user['telegram_id'], 'CAACAgIAAxkBAAI1pWohpKq-oXMroLn6_KG-3IAZdRRQAAL1KAACCKQwStmJ6UyR9MekOwQ')
                except:
                    pass
                await self.bot.send_message(user['telegram_id'], message, parse_mode='HTML')
                sent += 1
                await asyncio.sleep(0.5)  # Пауза чтобы не упереться в лимиты Telegram
            except Exception as e:
                logger.error(f"Ошибка отправки {user['name']}: {e}")

        self.last_send_date = today
        logger.info(f"🌅 Утренняя рассылка завершена: {sent}/{len(users)}")


greeter = None

async def init_greeter(application):
    global greeter
    greeter = MorningGreeter(application)
    await greeter.start()
    return greeter

async def stop_greeter():
    global greeter
    if greeter:
        await greeter.stop()
