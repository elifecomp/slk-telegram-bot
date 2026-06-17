"""Подтверждения и отмены"""
from telegram import Update
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState
from keyboards import create_admin_keyboard
from database import db
from handlers_modules.common import is_admin
HTML = "HTML"

async def confirm_edit(update: Update, context: CallbackContext) -> None:
    """Подтверждает редактирование пользователя"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return

    selected_user = context.user_data.get('selected_user')
    edit_field = context.user_data.get('edit_field')
    new_value = context.user_data.get('new_value')

    if not all([selected_user, edit_field, new_value]):
        await update.message.reply_text("❌ <b>Ошибка: данные для сохранения не найдены</b>", parse_mode=HTML)
        return

    success = False
    if edit_field == 'login2' or edit_field == 'birthday' or edit_field == 'city':
        pass  # без валидации для второго логина
    elif edit_field == 'login':
        success = db.update_client_login(selected_user['id'], new_value)
    elif edit_field == 'phone':
        success = db.update_client_phone(selected_user['id'], new_value)
    elif edit_field == 'name':
        success = db.update_client_name(selected_user['id'], new_value)

    if success:
        if edit_field in selected_user:
            selected_user[edit_field] = new_value

        field_names = {
            'login': 'логин',
            'phone': 'телефон',
            'name': 'имя'
        }

        await update.message.reply_text(
            f"✅ <b>{field_names[edit_field].title()} успешно обновлен</b>\n\n"
            f"Новое значение: <code>{new_value}</code>",
            parse_mode=HTML
        )

        pass  # убран вызов
    else:
        await update.message.reply_text(
            f"❌ <b>Ошибка при обновлении {edit_field}</b>\n"
            f"Возможно, такой логин уже существует.",
            parse_mode=HTML
        )

async def cancel_edit(update: Update, context: CallbackContext) -> None:
    """Отменяет редактирование пользователя"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return

    context.user_data.pop('edit_field', None)
    context.user_data.pop('new_value', None)
    context.user_data.pop('awaiting_confirmation', None)

    await update.message.reply_text("❌ <b>Редактирование отменено</b>", parse_mode=HTML)