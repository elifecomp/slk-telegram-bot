HTML = "HTML"
"""Работа с группами клиентов"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState
from keyboards import create_groups_keyboard, create_group_actions_keyboard, create_admin_keyboard, create_cancel_keyboard
from database import db
from handlers_modules.common import is_admin

async def groups_menu(update: Update, context: CallbackContext) -> None:
    """Меню групп клиентов"""
    if not is_admin(update.effective_user.id):
        return
    groups = db.get_groups()
    context.user_data['state'] = BotState.GROUPS_MENU
    message = "👥 <b>ГРУППЫ КЛИЕНТОВ</b>\n\nВыберите группу:"
    await update.message.reply_text(
        message,
        reply_markup=create_groups_keyboard(groups),
        parse_mode=HTML
    )

async def send_group_message(update: Update, context: CallbackContext) -> None:
    """Отправляет сообщение всем клиентам в группе"""
    if not is_admin(update.effective_user.id):
        return
    group = context.user_data.get('selected_group')
    if not group:
        await update.message.reply_text("❌   Группа не выбрана", parse_mode=HTML)
        return
    context.user_data['state'] = BotState.GROUP_MESSAGE
    context.user_data['sending_to_group'] = True
    message = f"💌 <b>Рассылка группе:</b> {group['name']}\n\n"
    message += "<b>Введите сообщение:</b>\n"
    message += "<i>Оно будет отправлено всем клиентам в этой группе</i>"
    await update.message.reply_text(
        message,
        reply_markup=create_cancel_keyboard(),
        parse_mode=HTML
    )

async def handle_group_message(update: Update, context: CallbackContext) -> None:
    """Рассылка сообщений группе (текст, фото, файлы, музыка)"""
    if not context.user_data.get('sending_to_group'):
        return
    
    if update.message and update.message.text and update.message.text == "❌ Отменить":
        context.user_data.pop('sending_to_group', None)
        context.user_data['state'] = BotState.GROUP_DETAIL_MENU
        await update.message.reply_text("❌ Отменено")
        return
    
    group = context.user_data.get('selected_group')
    if not group:
        return
    
    context.user_data.pop('sending_to_group', None)
    context.user_data['state'] = BotState.GROUP_DETAIL_MENU
    
    clients = db.get_clients_in_group(group['id'])
    if not clients:
        await update.message.reply_text("❌ В группе нет клиентов")
        return
    
    await update.message.reply_text(f"🔄 Отправляю {len(clients)} клиентам...")
    
    sent = 0
    for client in clients:
        tg_id = client.get('telegram_id')
        if tg_id and tg_id > 0:
            try:
                if update.message:
                    if update.message.photo:
                        await context.bot.send_photo(tg_id, update.message.photo[-1].file_id, caption=update.message.caption or "")
                    elif update.message.video:
                        await context.bot.send_video(tg_id, update.message.video.file_id, caption=update.message.caption or "")
                    elif update.message.audio:
                        await context.bot.send_audio(tg_id, update.message.audio.file_id, caption=update.message.caption or "")
                    elif update.message.voice:
                        await context.bot.send_voice(tg_id, update.message.voice.file_id)
                    elif update.message.document:
                        await context.bot.send_document(tg_id, update.message.document.file_id, caption=update.message.caption or "")
                    elif update.message.sticker:
                        await context.bot.send_sticker(tg_id, update.message.sticker.file_id)
                    elif update.message.text:
                        await context.bot.send_message(tg_id, update.message.text)
                    sent += 1
            except:
                pass
    
    await update.message.reply_text(
        f"✅ Рассылка завершена!\n\nГруппа: {group['name']}\n👥 Отправлено: {sent}/{len(clients)}",
        reply_markup=create_group_actions_keyboard()
    )

async def group_detail(update: Update, context: CallbackContext) -> None:
    """Детали группы"""
    if not is_admin(update.effective_user.id):
        return
    message_text = update.message.text
    if "⬅️" in message_text:
        context.user_data['state'] = BotState.MAIN_MENU
        await update.message.reply_text("🏠 Главное меню", reply_markup=create_admin_keyboard())
        return
    group_name = message_text.split(' (')[0].strip().replace('📁 ', '')
    groups = db.get_groups()
    group = next((g for g in groups if g['name'] == group_name), None)
    if group:
        context.user_data['selected_group'] = group
        context.user_data['state'] = BotState.GROUP_DETAIL_MENU
        clients = db.get_clients_in_group(group['id'])
        message = f"<b>{group['name']}</b>\n\n"
        message += f"👥 Клиентов: {len(clients)}\n\n"
        if clients:
            message += "<b>Список:</b>\n"
            for c in clients:
                message += f"  • {c['name']} — <code>{c['login']}</code>\n"
        await update.message.reply_text(
            message,
            reply_markup=create_group_actions_keyboard(),
            parse_mode=HTML
        )
    else:
        await update.message.reply_text("❌   Группа не найдена", parse_mode=HTML)

async def add_client_to_group_handler(update: Update, context: CallbackContext) -> None:
    """Добавляет клиента в группу"""
    if not is_admin(update.effective_user.id):
        return
    group = context.user_data.get('selected_group')
    if not group:
        return
    users = db.get_all_clients()
    context.user_data['state'] = BotState.ADD_TO_GROUP
    context.user_data['users_for_group'] = users
    message = f"📁 <b>{group['name']}</b> — добавление клиента\n\n"
    message += "<b>Введите логин клиента:</b>\n"
    message += "<i>Или выберите из списка ниже:</i>"
    keyboard = []
    for u in users[:20]:
        keyboard.append([f"👤 {u['name']} ({u['login']})"])
    keyboard.append(["⬅️ Отмена"])
    await update.message.reply_text(
        message,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode=HTML
    )

async def handle_add_to_group(update: Update, context: CallbackContext) -> None:
    """Обрабатывает добавление клиента в группу"""
    if not is_admin(update.effective_user.id):
        return
    message_text = update.message.text
    group = context.user_data.get('selected_group')
    if not group or "⬅️" in message_text:
        context.user_data['state'] = BotState.GROUP_DETAIL_MENU
        await group_detail(update, context)
        return
    import re
    match = re.search(r'\(([^)]+)\)', message_text)
    login = match.group(1) if match else message_text.strip()
    client = db.get_client_by_login(login)
    if client:
        db.add_client_to_group(client['id'], group['id'])
        await update.message.reply_text(
            f"✅   <b>{client['name']}</b> добавлен в группу <b>{group['name']}</b>",
            parse_mode=HTML
        )
    else:
        await update.message.reply_text("❌   Клиент не найден", parse_mode=HTML)
    context.user_data['state'] = BotState.GROUP_DETAIL_MENU
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=create_group_actions_keyboard(),
        parse_mode=HTML
    )
