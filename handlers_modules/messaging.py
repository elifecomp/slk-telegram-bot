"""Рассылки и сообщения"""
import os, asyncio
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState
from keyboards import create_admin_keyboard, create_users_for_message_keyboard, create_cancel_keyboard
from database import db
from handlers_modules.common import is_admin
import logging
logger = logging.getLogger(__name__)
HTML = "HTML"

async def send_message(update: Update, context: CallbackContext) -> None:
    """Начинает процесс отправки сообщения пользователю (для админа)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return

    await update.message.reply_text("🔄 <b>Получаю список пользователей...</b>", parse_mode=HTML)

    def get_users_data():
        return db.get_all_clients()

    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_users_data)
        users = future.result()

    if users:
        context.user_data['users_for_message'] = users
        context.user_data['state'] = BotState.ADMIN_CHOOSE_USER

        keyboard = create_users_for_message_keyboard(users)

        message = "💌 <b>Отправить сообщение пользователю</b>\n\n"
        message += "👤 <b>Выберите пользователя:</b>"

        await update.message.reply_text(message, reply_markup=keyboard, parse_mode=HTML)
    else:
        await update.message.reply_text(
            "❌ <b>Нет зарегистрированных пользователей</b>\n\n"
            "В базе данных пока нет пользователей.",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        context.user_data['state'] = BotState.MAIN_MENU
async def admin_choose_user(update: Update, context: CallbackContext) -> None:
    """Обрабатывает выбор пользователя для отправки сообщения"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return

    message_text = update.message.text

    if message_text == "❌ Отменить":
        context.user_data['state'] = BotState.MAIN_MENU
        await update.message.reply_text(
            "❌ <b>Отправка сообщения отменена</b>",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        return

    users = context.user_data.get('users_for_message', [])
    selected_user = None

    for user in users:
        user_button = f"👤 {user['name']} ({user['login']})"
        if user_button == message_text:
            selected_user = user
            break

    if selected_user:
        context.user_data['selected_user_for_message'] = selected_user
        context.user_data['state'] = BotState.ADMIN_WRITE_MESSAGE

        message = "💌 <b>Отправка сообщения пользователю</b>\n\n"
        message += f"👤 <b>Получатель:</b> {selected_user['name']}\n"
        message += f"📝 <b>Логин:</b> <code>{selected_user['login']}</code>\n"
        message += f"📞 <b>Телефон:</b> <code>{selected_user['phone']}</code>\n\n"
        message += "✏️ <b>Введите ваше сообщение:</b>\n\n"
        message += "<b>📸 Вы также можете отправить:</b>\n"
        message += "• Фото (с подписью)\n"
        message += "• Видео (с подписью)\n"
        message += "• Голосовое сообщение\n"
        message += "• Документы\n\n"
        message += "<i>Просто отправьте файл или наберите текст</i>"

        await update.message.reply_text(
            message,
            reply_markup=create_cancel_keyboard(),
            parse_mode=HTML
        )
    else:
        await update.message.reply_text("❌ <b>Пользователь не найден</b>", parse_mode=HTML)
async def admin_handle_message(update: Update, context: CallbackContext) -> None:
    """Обрабатывает сообщение от админа и отправляет пользователю"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return

    selected_user = context.user_data.get('selected_user_for_message')

    if not selected_user:
        await update.message.reply_text("❌ <b>Ошибка: пользователь не выбран</b>", parse_mode=HTML)
        context.user_data['state'] = BotState.MAIN_MENU
        await update.message.reply_text(
            "🏠 <b>Главное меню:</b>",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        return

    if context.user_data.get('state') != BotState.ADMIN_WRITE_MESSAGE:
        return

    message_text = update.message.text

    if message_text == "❌ Отменить":
        context.user_data['state'] = BotState.MAIN_MENU
        await update.message.reply_text(
            "❌ <b>Отправка сообщения отменена</b>",
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )
        return

    try:
        try:
            sticker_file_id = "CAACAgIAAxkBAAI1nWohorcFBAt5OO3MvgkJON3mDx3VAAJvAAPBnGAMyw59i8DdTVY7BA"
            await context.bot.send_sticker(
                selected_user['telegram_id'],
                sticker=sticker_file_id
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить стикер пользователю {selected_user['telegram_id']}: {e}")

        await asyncio.sleep(0.5)

        from datetime import datetime
        now = datetime.now()
        months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
                 'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']
        date_str = f"{now.day} {months[now.month-1]} {now.year}"
        time_str = now.strftime('%H:%M')

        user_message = "💌 <b>Сообщение от администратора</b>\n\n"
        user_message += f"{message_text}\n\n"
        user_message += f"📅 {date_str} | 🕐 {time_str}"

        await context.bot.send_message(
            selected_user['telegram_id'],
            user_message,
            parse_mode=HTML
        )

        await send_notification_sound_to_user(context.bot, selected_user['telegram_id'])

        success_message = "✅ <b>Сообщение успешно отправлено!</b>\n\n"
        success_message += f"👤 <b>Пользователь:</b> {selected_user['name']}\n"
        success_message += f"📝 <b>Логин:</b> <code>{selected_user['login']}</code>\n"
        success_message += f"🆔 <b>Telegram ID:</b> <code>{selected_user['telegram_id']}</code>\n\n"
        success_message += f"💬 <b>Ваше сообщение:</b>\n{message_text}"

        await update.message.reply_text(
            success_message,
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )

    except Exception as e:
        logger.error(f"Ошибка отправки сообщения пользователю {selected_user['telegram_id']}: {e}")
        error_message = "❌ <b>Не удалось отправить сообщение</b>\n\n"
        error_message += f"👤 <b>Пользователь:</b> {selected_user['name']}\n"
        error_message += f"📝 <b>Логин:</b> <code>{selected_user['login']}</code>\n\n"
        error_message += "<b>Возможные причины:</b>\n"
        error_message += "• Пользователь заблокировал бота\n"
        error_message += "• Ошибка связи с Telegram\n"
        error_message += "• Пользователь удалил аккаунт"

        await update.message.reply_text(
            error_message,
            reply_markup=create_admin_keyboard(),
            parse_mode=HTML
        )

    context.user_data['state'] = BotState.MAIN_MENU

async def admin_handle_media(update: Update, context: CallbackContext) -> None:
    """Универсальный обработчик медиа от админа"""
    if not is_admin(update.effective_user.id):
        return

    selected_user = context.user_data.get('selected_user_for_message')
    if not selected_user or context.user_data.get('state') != BotState.ADMIN_WRITE_MESSAGE:
        return

    caption = update.message.caption or ""

    try:
        # Стикер
        try:
            await context.bot.send_sticker(selected_user['telegram_id'],
                "CAACAgIAAxkBAAI1nWohorcFBAt5OO3MvgkJON3mDx3VAAJvAAPBnGAMyw59i8DdTVY7BA")
        except: pass

        await asyncio.sleep(0.5)

        # Определяем тип и отправляем
        msg = update.message
        if msg.photo:
            await context.bot.send_photo(selected_user['telegram_id'], msg.photo[-1].file_id,
                caption=f"💌 <b>Сообщение от администратора</b>\n\n{caption}" if caption else "💌 <b>Сообщение от администратора</b>",
                parse_mode=HTML)
            media_type = "Фото"
        elif msg.video:
            await context.bot.send_video(selected_user['telegram_id'], msg.video.file_id,
                caption=f"💌 <b>Сообщение от администратора</b>\n\n{caption}" if caption else "💌 <b>Сообщение от администратора</b>",
                parse_mode=HTML)
            media_type = "Видео"
        elif msg.voice:
            await context.bot.send_message(selected_user['telegram_id'], "💌 <b>Голосовое сообщение от администратора</b>", parse_mode=HTML)
            await context.bot.send_voice(selected_user['telegram_id'], msg.voice.file_id)
            media_type = "Голосовое"
        elif msg.audio:
            await context.bot.send_message(selected_user['telegram_id'],
                f"🎵 <b>Музыка от администратора</b>\n\n{caption}" if caption else "🎵 <b>Музыка от администратора</b>",
                parse_mode=HTML)
            await context.bot.send_audio(selected_user['telegram_id'], msg.audio.file_id,
                performer=msg.audio.performer or "Администратор",
                title=msg.audio.title or "Аудио")
            media_type = "Аудио"
        elif msg.document:
            await context.bot.send_document(selected_user['telegram_id'], msg.document.file_id,
                filename=msg.document.file_name,
                caption=f"💌 <b>Документ от администратора</b>\n\n{caption}" if caption else "💌 <b>Документ от администратора</b>",
                parse_mode=HTML)
            media_type = "Документ"
        else:
            return

        await update.message.reply_text(
            f"✅ <b>{media_type} успешно отправлено!</b>\n\n"
            f"👤 <b>Пользователь:</b> {selected_user['name']}\n"
            f"📝 <b>Логин:</b> <code>{selected_user['login']}</code>",
            reply_markup=create_admin_keyboard(), parse_mode=HTML
        )
    except Exception as e:
        logger.error(f"Ошибка отправки медиа: {e}")
        await update.message.reply_text(
            f"❌ <b>Не удалось отправить</b>\n\n<b>Причины:</b>\n• Пользователь заблокировал бота\n• Ошибка связи",
            reply_markup=create_admin_keyboard(), parse_mode=HTML
        )

    context.user_data['state'] = BotState.MAIN_MENU

async def send_notification_sound_to_user(bot, user_id):
    """Отправляет звуковой файл пользователю с автовоспроизведением"""
    try:
        sound_path = None
        possible_paths = [
            'notification.mp3',
            './notification.mp3',
            os.path.join(os.path.dirname(__file__), 'notification.mp3'),
            os.path.join(os.getcwd(), 'notification.mp3'),
            '/app/notification.mp3',
        ]

        for path in possible_paths:
            if path and os.path.exists(path):
                sound_path = path
                logger.info(f"✅ Найден звуковой файл уведомления: {path}")
                break

        if sound_path:
            with open(sound_path, 'rb') as audio_file:
                await bot.send_audio(
                    chat_id=user_id,
                    audio=InputFile(audio_file, filename="notification.mp3"),
                    caption="🔔 Прослушайте обязательно!",
                    duration=3,
                    performer="SLV-Админ",
                    title="Уведомление"
                )
            logger.info(f"✅ Звуковое уведомление отправлено пользователю {user_id}")
        else:
            logger.warning(f"❌ Звуковой файл уведомления не найден!")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке звукового уведомления пользователю {user_id}: {e}")
# ==================== ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ====================

