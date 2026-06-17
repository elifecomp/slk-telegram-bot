"""Администрирование и проверки"""
import logging
HTML = "HTML"
from concurrent.futures import ThreadPoolExecutor
from telegram import Update
from telegram.ext import CallbackContext
from config import ADMIN_IDS, WELCOME_AUDIO_PATH
from database import db
from handlers_modules.common import is_admin

async def sync_logins(update: Update, context: CallbackContext) -> None:
    """Синхронизирует логины из панели в базу"""
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text("🔄 Синхронизирую логины из панели...")

    def do_sync():
        import sqlite3, json
        from xui_api import get_inbounds_list
        from panel_manager import get_panels_list, set_active_panel, get_active_panel

        original = get_active_panel()['id']
        updated = 0

        for panel in get_panels_list():
            set_active_panel(panel['id'])
            inbounds = get_inbounds_list()
            for inbound in inbounds:
                settings = inbound.get('settings', {})
                for c in settings.get('clients', []):
                    email = c.get('email', '')
                    if email:
                        # Ищем клиента по имени в email
                        conn = sqlite3.connect('clients.db')
                        cursor = conn.cursor()
                        cursor.execute("SELECT id, name, login FROM clients")
                        for row in cursor.fetchall():
                            cid, name, login = row
                            name_clean = name.lower().replace(' ', '')
                            email_clean = email.lower().replace(' ', '')
                            if (name_clean in email_clean or email_clean in name_clean) and login != email:
                                cursor.execute("UPDATE clients SET login = ? WHERE id = ?", (email, cid))
                                updated += 1
                        conn.commit()
                        conn.close()

        set_active_panel(original)
        return updated

    with ThreadPoolExecutor() as executor:
        future = executor.submit(do_sync)
        count = future.result()

    await update.message.reply_text(f"✅ Синхронизировано: {count} логинов")


async def notify_admins_about_registration(bot, user, registration_data, name):
    """Уведомление администраторов о новой регистрации"""
    message_text = f"""🔔 <b>НОВАЯ РЕГИСТРАЦИЯ</b>

👤 <b>Пользователь:</b> {name}
📝 <b>Логин:</b> <code>{registration_data.get('login')}</code>
📞 <b>Телефон:</b> <code>{registration_data.get('phone')}</code>
🆔 <b>ID Телеграм:</b> <code>{user.id}</code>
👨‍💼 <b>Username:</b> @{user.username if user.username else 'нет'}
📛 <b>Имя в TG:</b> {user.first_name} {user.last_name or ''}"""

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message_text, parse_mode=HTML)
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление администратору {admin_id}: {e}")
