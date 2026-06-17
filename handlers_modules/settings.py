"""Настройки бота"""
import subprocess, os, glob, requests, re, asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from config import ADMIN_IDS, BotState
from keyboards import create_settings_keyboard, create_admin_keyboard
from xui_api import get_panel_update_info
from handlers_modules.common import is_admin
HTML = "HTML"

async def settings_menu(update: Update, context: CallbackContext) -> None:
    """Меню настроек бота"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>Нет доступа</b>", parse_mode=HTML)
        return

    context.user_data['state'] = BotState.SETTINGS_MENU

    message = "⚙️ <b>НАСТРОЙКИ БОТА</b>\n\nВыберите действие:"
    await update.message.reply_text(
        message,
        reply_markup=create_settings_keyboard(),
        parse_mode=HTML
    )

async def bot_status(update: Update, context: CallbackContext) -> None:
    """Показывает состояние бота"""
    if not is_admin(update.effective_user.id):
        return

    import psutil, os, time as time_mod
    from datetime import datetime

    process = psutil.Process(os.getpid())
    mem = process.memory_info().rss
    threads = process.num_threads()
    cpu = process.cpu_percent(interval=0.5)

    # Uptime бота
    now = datetime.now()
    start_time = datetime.fromtimestamp(process.create_time())
    uptime = now - start_time
    uptime_str = f"{uptime.days}д {uptime.seconds//3600}ч {(uptime.seconds%3600)//60}м"

    # Кэш
    try:
        from xui_api import get_traffic_cache_stats
        cache = get_traffic_cache_stats()
    except:
        cache = {}

    # База
    from database import db
    users_count = len(db.get_all_clients())

    # Уведомления
    try:
        from connection_notifier import get_notifications_status
        notif = "🟢 ВКЛ" if get_notifications_status() else "🔴 ВЫКЛ"
    except:
        notif = "❓"

    # Панель
    from panel_manager import get_active_panel
    panel = get_active_panel()

    message = "🤖 <b>СОСТОЯНИЕ БОТА</b>\n\n"
    message += f"⏰ <b>Аптайм:</b> {uptime_str}\n"
    message += f"⚡ <b>CPU:</b> {cpu:.1f}%\n"
    message += f"🧠 <b>Память:</b> {mem // 1024 // 1024} MB\n"
    message += f"🧵 <b>Потоков:</b> {threads}\n\n"

    if cache and 'error' not in cache:
        message += f"📊 <b>LRU-Кэш:</b>\n"
        message += f"  Размер: {cache.get('size', 0)}/{cache.get('max_size', 0)}\n"
        message += f"  Hit rate: {cache.get('stats', {}).get('hit_rate', 0):.1f}%\n"
        message += f"  Очисток: {cache.get('stats', {}).get('evictions', 0)}\n\n"

    message += f"👥 <b>В базе:</b> {users_count} пользователей\n"
    message += f"🔔 <b>Уведомления:</b> {notif}\n"
    message += f"🔄 <b>Панель:</b> {panel['emoji']} {panel['name']}\n"
    message += f"🔗 <b>URL:</b> <code>{panel['url'][:50]}...</code>\n\n"

    message += "✅ <b>Бот работает стабильно</b>"

    await update.message.reply_text(message, parse_mode=HTML)

async def restart_bot(update: Update, context: CallbackContext) -> None:
    """Перезагружает бота"""
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text("🔄 <b>Перезагружаю бота...</b>", parse_mode=HTML)
    import os, sys
    subprocess.run(["systemctl", "restart", "SLV-bot.service"], timeout=10)
    await asyncio.sleep(5)
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, "✅ <b>Бот перезагружен!</b>\n\nНажмите /start", parse_mode="HTML")
        except:
            pass

async def check_errors(update: Update, context: CallbackContext) -> None:
    """Проверяет бота на ошибки"""
    if not is_admin(update.effective_user.id):
        return

    import subprocess
    result = subprocess.run(
        ['journalctl', '-u', 'SLV-bot.service', '--no-pager', '-n', '20', '-p', '3'],
        capture_output=True, text=True, timeout=5
    )

    errors = result.stdout.strip()

    if errors:
        message = f"📋 <b>ПОСЛЕДНИЕ ОШИБКИ:</b>\n\n<code>{errors[:1000]}</code>"
    else:
        message = "✅ <b>Ошибок не найдено!</b>\n\nБот работает стабильно."

    await update.message.reply_text(message, parse_mode=HTML)

async def auto_reset_status(update: Update, context: CallbackContext) -> None:
    """Показывает статус автосброса"""
    if not is_admin(update.effective_user.id):
        return

    from auto_reset import auto_reset
    from datetime import datetime

    now = datetime.now()

    # Вычисляем следующее 1 число
    if now.month == 12:
        next_reset = now.replace(year=now.year+1, month=1, day=1, hour=0, minute=1, second=0)
    else:
        next_reset = now.replace(month=now.month+1, day=1, hour=0, minute=1, second=0)

    days_left = (next_reset - now).days

    months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
             'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']

    message = "🔄 <b>АВТОСБРОС ТРАФИКА</b>\n\n"
    message += f"📅 <b>Следующий сброс:</b> {next_reset.day} {months[next_reset.month-1]} {next_reset.year}\n"
    message += f"🕐 <b>Время:</b> 00:01\n"
    message += f"⏳ <b>Осталось:</b> {days_left} дней\n\n"
    message += "<b>При сбросе:</b>\n"
    message += "• Обнуляется трафик ВСЕХ активных клиентов\n"
    message += "• На ВСЕХ панелях\n"
    message += "• Админ получает отчёт\n\n"
    message += "<i>Сброс происходит автоматически</i>"

    await update.message.reply_text(message, parse_mode=HTML)

async def create_backup(update: Update, context: CallbackContext) -> None:
    """Создаёт полный бэкап бота"""
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text("💾 <b>Создаю бэкап...</b>", parse_mode=HTML)

    def do_backup():
        import subprocess, time
        name = f"SLV_bot_FINAL_{time.strftime("%Y%m%d_%H%M%S")}.tar.gz"
        path = f"/opt/SLV_Bot/backups/{name}"
        result = subprocess.run(
            f"cd / && tar -czf {path} --exclude=venv --exclude=__pycache__ --exclude='*.pyc' --exclude=logs opt/SLV_Bot/*.py opt/SLV_Bot/.env opt/SLV_Bot/*.db opt/SLV_Bot/*.mp3 opt/SLV_Bot/*.sh opt/SLV_Bot/*.txt etc/systemd/system/SLV-bot.service ",
            shell=True, capture_output=True, timeout=60
        )
        if result.returncode == 0:
            size = subprocess.run(['du', '-sh', path], capture_output=True, text=True).stdout.split()[0]
            return name, size
        return None, None

    with ThreadPoolExecutor() as executor:
        future = executor.submit(do_backup)
        name, size = future.result()

    if name:
        await update.message.reply_text(
            f"💾 <b>БЭКАП СОЗДАН!</b>\n\n"
            f"📁 <b>Файл:</b> {name}\n"
            f"📏 <b>Размер:</b> {size}\n"
            f"📂 <b>Папка:</b> /opt/SLV_Bot/backups/",
            parse_mode=HTML
        )
    else:
        await update.message.reply_text("❌ <b>Ошибка создания бэкапа</b>", parse_mode=HTML)

async def show_changelog(update: Update, context: CallbackContext) -> None:
    """Показывает что нового в обновлениях"""
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text("🔄 <b>Получаю информацию...</b>", parse_mode=HTML)

    def get_changelog():
        import requests as req, re
        try:
            from xui_api import get_panel_update_info
            info = get_panel_update_info()
            current = info.get('currentVersion', '3.0.2')
            latest = info.get('latestVersion', 'v3.2.0')

            r = req.get("https://api.github.com/repos/MHSanaei/3x-ui/releases?per_page=5", timeout=10)
            if r.status_code != 200:
                return None

            releases = r.json()
            changelogs = []

            for rel in releases:
                tag = rel.get('tag_name', '')
                date = rel.get('published_at', '')[:10]
                body = rel.get('body', '')

                changes = []
                for line in body.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('<'):
                        continue
                    # Извлекаем текст из [текст](url)
                    match = re.search(r'\[([^\]]+)\]', line)
                    if match:
                        text = match.group(1)
                        # Очищаем префиксы
                        text = re.sub(r'^feat\([^)]*\):\s*', '', text)
                        text = re.sub(r'^feat:\s*', '', text)
                        text = re.sub(r'^fix\([^)]*\):\s*', '', text)
                        text = re.sub(r'^fix:\s*', '', text)
                        text = text.strip()
                        if len(text) > 10:
                            changes.append(text)

                if changes:
                    changelogs.append({
                        'version': tag,
                        'date': date,
                        'changes': changes[:5]
                    })

            return changelogs, current, latest
        except:
            return None

    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_changelog)
        result = future.result()

    if result:
        changelogs, current, latest = result

        message = "🆕 <b>ОБНОВЛЕНИЯ ПАНЕЛИ 3X-UI</b>\n\n"
        message += f"📦 <b>У вас:</b> {current}\n"
        message += f"🆕 <b>Доступна:</b> {latest}\n\n"

        for cl in changelogs[:1]:  # только последние 2 версии
            message += f"📋 <b>{cl['version']}</b> ({cl['date']})\n"
            for change in cl['changes']:
                message += f"  • {change}\n"
            message += "\n"

        message += "<i>Данные с GitHub</i>"
    else:
        message = "❌ <b>Не удалось получить информацию</b>"

    await update.message.reply_text(message, parse_mode=HTML)

# ==================== МОНИТОРИНГ СЕРВЕРОВ ====================

def load_servers():
    try:
        with open('/opt/SLV_Bot/servers.txt') as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []

