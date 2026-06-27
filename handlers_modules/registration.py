"""Регистрация пользователей"""
import logging, asyncio, os, re
from telegram import Update, InputFile
from telegram.ext import CallbackContext
from config import ADMIN_IDS, WELCOME_AUDIO_PATH, BotState, BOT_NAME
from keyboards import create_user_keyboard, create_cancel_keyboard, create_admin_keyboard
from database import db
from handlers_modules.common import is_admin
from handlers_modules.auth import notify_admins_about_registration
logger = logging.getLogger(__name__)
HTML = "HTML"

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id

    # Сбрасываем состояние пользователя
    context.user_data.clear()

    # Отправляем стикер при старте
    try:
        sticker_file_id = "CAACAgIAAxkBAAI1kGohnJ35qnpyMFwhA4EfjgeEfI6TAAINDgACbTF5SQS2aZWlIIItOwQ"
        await update.message.reply_sticker(sticker_file_id)
    except Exception as e:
        logger.warning(f"Не удалось отправить стикер: {e}")

    # Небольшая задержка перед текстом
    await asyncio.sleep(0.5)

    if is_admin(user_id):
        welcome_text = f"""⚡ <b>Привет, {user.first_name}!</b>

🛡️ <b>{BOT_NAME}</b>
   <i>Админ-панель</i>

👇 <b>Выберите действие:</b>"""

        await update.message.reply_text(
            welcome_text,
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        context.user_data['state'] = BotState.MAIN_MENU
    else:
        # Проверяем, зарегистрирован ли пользователь
        if db.client_exists(user_id):
            client = db.get_client_by_telegram_id(user_id)
            welcome_text = f"⚡ <b>Здравствуйте, {user.first_name}!</b>"

            if client:
                bd = client.get("birthday", "")
                if bd:
                    try:
                        b_day, b_month, _ = bd.split(".")
                        zodiac = get_zodiac(int(b_day), int(b_month))
                        welcome_text += f"\n\n🎂 <b>День рождения:</b> {bd}\n   {zodiac}"
                    except: pass

            # IP, страна, город, оператор (DaData + ip-api)
            try:
                from xui_api import get_client_ips
                import requests as req
                ips = get_client_ips(client['login'])
                if ips and isinstance(ips, list) and len(ips) > 0 and ips[0] != "No IP Record":
                    ip = str(ips[0]).split(' ')[0].strip()
                    if ip and '.' in ip:
                        welcome_text += f"\n\n🌐 <b>IP:</b> <code>{ip}</code>"

                        # Город и регион через DaData
                        try:
                            r = req.get(
                                f"https://suggestions.dadata.ru/suggestions/api/4_1/rs/detectAddressByIp?ip={ip}",
                                headers={"Authorization": "Token a20c77a8cc6393aee5070f10e0fc6e4116d3423c"},
                                timeout=3
                            )
                            if r.status_code == 200:
                                data = r.json()
                                loc = data.get('location', {}).get('data', {})
                                region = loc.get('region_with_type', '')
                                city = loc.get('city_with_type', '')
                                if region:
                                    welcome_text += f"\n🏙️ <b>Регион:</b> {region}"
                                if city and city != region:
                                    welcome_text += f"\n🏙️ <b>Город:</b> {city}"
                        except: pass

                        # Страна и оператор через ip-api
                        try:
                            r = req.get(f"http://ip-api.com/json/{ip}?fields=country,isp", timeout=3)
                            if r.status_code == 200:
                                geo = r.json()
                                country = geo.get('country', '')
                                isp = geo.get('isp', '')
                                flags = {'Russia': '🇷🇺', 'Finland': '🇫🇮'}
                                flag = flags.get(country, '🌍')
                                welcome_text += f"\n🌍 <b>Страна:</b> {flag} {country}"
                                if isp:
                                    welcome_text += f"\n📡 <b>Оператор:</b> {isp}"
                        except: pass
            except: pass

            welcome_text += "\n\n👇 <b>Выберите действие:</b>"

            await update.message.reply_text(
                welcome_text,
                reply_markup=create_user_keyboard(),
                parse_mode='HTML'
            )
            context.user_data['state'] = BotState.MAIN_MENU
            return
        else:
            # Новый клиент — сразу регистрация
            await start_registration(update, context)
            return



async def play_welcome_audio(update: Update, context: CallbackContext) -> None:
    """Воспроизводит приветственное аудио перед регистрацией"""
    try:
        await update.message.reply_text("🎵 Загружаю приветственное сообщение...")

        audio_file_path = None
        possible_paths = [
            WELCOME_AUDIO_PATH,
            'welcome.mp3',
            './welcome.mp3',
            '/app/welcome.mp3',
            os.path.join(os.path.dirname(__file__), 'welcome.mp3'),
            os.path.join(os.getcwd(), 'welcome.mp3'),
            '/root/vpn_bot/welcome.mp3',
        ]

        for path in possible_paths:
            if path and os.path.exists(path):
                audio_file_path = path
                logger.info(f"✅ Найден аудиофайл: {path}")
                break

        if audio_file_path:
            try:
                with open(audio_file_path, 'rb') as audio_file:
                    await update.message.reply_audio(
                        audio=InputFile(audio_file, filename="welcome.mp3"),
                        caption="🎵 Добро пожаловать! Слушайте приветственное сообщение...",
                        duration=60,
                        performer=BOT_NAME,
                        title="Приветствие"
                    )
                logger.info(f"✅ Аудио успешно отправлено пользователю {update.effective_user.id}")
                return
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке аудио из {audio_file_path}: {e}")
        else:
            logger.error(f"❌ Аудиофайл не найден! Искали в: {possible_paths}")

            await update.message.reply_text(
                "🎵 Приветственное аудиосообщение временно недоступно.\n"
                "Пожалуйста, продолжайте регистрацию.",
                parse_mode=HTML
            )

    except Exception as e:
        logger.error(f"❌ Критическая ошибка при отправке аудио: {e}")
        await update.message.reply_text(
            "🎵 Добро пожаловать! Приступаем к регистрации...",
            parse_mode=HTML
        )

async def start_registration(update: Update, context: CallbackContext) -> None:
    """Начало процесса регистрации"""
    await play_welcome_audio(update, context)
    welcome_text = """🌟 <b>Здравствуй, дорогой пользователь!</b>

👋 Давай мы с тобой познакомимся

💫 <b>Придумай Логин:</b>"""

    await update.message.reply_text(welcome_text, parse_mode=HTML)
    context.user_data['state'] = BotState.REGISTRATION_LOGIN
    context.user_data['registration_data'] = {}

async def handle_registration_login(update: Update, context: CallbackContext) -> None:
    """Обработка ввода логина"""
    login = update.message.text.strip()

    if len(login) < 2 or len(login) > 30:
        await update.message.reply_text(
            "❌ <b>Логин должен быть от 2 до 30 символов.</b>\n\n"
            "💫 Пожалуйста, введите логин еще раз:",
            parse_mode=HTML
        )
        return

    context.user_data['registration_data']['login'] = login
    context.user_data['state'] = BotState.REGISTRATION_PHONE

    await update.message.reply_text(
        "✅ <b>Отлично! Логин принят.</b>\n\n"
        "📱 <b>Теперь введи номер телефона в формате:</b>\n"
        "• <code>+79ххххххххх</code>\n"
        "• <code>+9936ххххххх</code>",
        parse_mode=HTML
    )

async def handle_registration_phone(update: Update, context: CallbackContext) -> None:
    """Обработка ввода телефона"""
    phone = update.message.text.strip()

    if not re.match(r'^(\+79\d{9}|\+9936\d{8})$', phone):
        await update.message.reply_text(
            "❌ <b>Неверный формат номера телефона.</b>\n\n"
            "📱 <b>Пожалуйста, введите номер в формате:</b>\n"
            "• <code>+79ххххххххх</code>\n"
            "• <code>+9936ххххххх</code>",
            parse_mode=HTML
        )
        return

    context.user_data['registration_data']['phone'] = phone
    context.user_data['state'] = BotState.REGISTRATION_NAME

    await update.message.reply_text(
        "✅ <b>Отлично! Номер телефона принят.</b>\n\n"
        "👤 <b>Теперь введи свое ИМЯ:</b>",
        parse_mode=HTML
    )

async def handle_registration_name(update: Update, context: CallbackContext) -> None:
    """Обработка ввода имени и завершение регистрации"""
    name = update.message.text.strip()

    if len(name) < 2 or len(name) > 50:
        await update.message.reply_text(
            "❌ <b>Имя должно быть от 2 до 50 символов.</b>\n\n"
            "👤 Пожалуйста, введите имя еще раз:",
            parse_mode=HTML
        )
        return

    user = update.effective_user
    registration_data = context.user_data.get('registration_data', {})

    success = db.add_client(
        telegram_id=user.id,
        login=registration_data.get('login'),
        phone=registration_data.get('phone'),
        name=name
    )

    if success:
        await notify_admins_about_registration(context.bot, user, registration_data, name)

        welcome_text = f"""🎉 <b>Регистрация завершена!</b>

✨ Добро пожаловать, <b>{name}</b>!
🔓 Теперь у тебя есть доступ к боту.

📋 <b>Твои данные:</b>
👤 <b>Логин:</b> <code>{registration_data.get('login')}</code>
📞 <b>Телефон:</b> <code>{registration_data.get('phone')}</code>

🚀 <b>Выберите действие:</b>"""

        await update.message.reply_text(
            welcome_text,
            reply_markup=create_user_keyboard(),
            parse_mode=HTML
        )

        context.user_data['state'] = BotState.MAIN_MENU
        context.user_data.pop('registration_data', None)
    else:
        await update.message.reply_text(
            "❌ <b>Произошла ошибка при регистрации.</b>\n"
            "Возможно, такой логин уже существует.\n\n"
            "🔄 Пожалуйста, начните регистрацию заново командой /start",
            parse_mode=HTML
        )
        context.user_data.clear()
# ==================== ФУНКЦИИ ПЕРЕКЛЮЧЕНИЯ РЕЖИМОВ ====================



async def write_to_admin(update: Update, context: CallbackContext) -> None:
    """Клиент пишет сообщение администратору"""
    user = update.effective_user
    client = db.get_client_by_telegram_id(user.id)

    if not client:
        await update.message.reply_text("❌ <b>Вы не зарегистрированы</b>", parse_mode=HTML)
        return

    context.user_data['state'] = BotState.WRITING_TO_ADMIN
    context.user_data['client_writing'] = True

    await update.message.reply_sticker('CAACAgIAAxkBAAI1jGohma-WwrzzcMUL2eo3uKKtfP5NAAIDEAACFIrJSQy6GxfYgpcDOwQ')
    message = "💬 <b>Написать администратору</b>\n\n"
    message += "<b>Введите ваше сообщение:</b>\n"
    message += "<i>• Можно отправить текст\n"
    message += "• Фото с подписью\n"
    message += "• Голосовое сообщение</i>\n\n"
    message += "<i>Администратор ответит вам в ближайшее время</i>"

    await update.message.reply_text(
        message,
        reply_markup=create_cancel_keyboard(),
        parse_mode=HTML
    )
