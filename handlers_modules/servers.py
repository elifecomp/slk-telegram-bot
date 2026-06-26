"""Мониторинг серверов"""
import subprocess, socket, time, requests, re, asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from config import ADMIN_IDS
from handlers_modules.settings import load_servers
from handlers_modules.common import is_admin
HTML = "HTML"

def save_servers(servers):
    with open('/opt/SLV_Bot/servers.txt', 'w') as f:
        for ip in servers:
            f.write(ip + '\n')

def ping_server(ip, port=22):
    """Проверяет доступность сервера через TCP (fallback на ICMP)"""
    import subprocess, socket
    # Сначала пробуем TCP
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        start = __import__('time').time()
        result = sock.connect_ex((ip, port))
        elapsed = (__import__('time').time() - start) * 1000
        sock.close()
        if result == 0:
            return elapsed
    except:
        pass
    # Если TCP не сработал — пробуем ICMP
    try:
        result = subprocess.run(['ping', '-c', '1', '-W', '2', ip], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            import re
            match = re.search(r'time=(\d+\.?\d*)', result.stdout)
            return float(match.group(1)) if match else 0
    except:
        pass
    return None

async def monitor_callback(update: Update, context: CallbackContext) -> None:
    """Обрабатывает inline-кнопки мониторинга"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "mon_add":
        context.user_data['waiting_for_server'] = True
        await query.edit_message_text("➕ <b>Введите IP сервера:</b>", parse_mode='HTML')
        return

    elif data == "mon_del":
        servers = load_servers()
        if not servers:
            await query.edit_message_text("📋 <b>Список пуст</b>", parse_mode='HTML')
            return
        keyboard = [[InlineKeyboardButton(f"🗑️ {ip}", callback_data=f"mon_del_{ip}")] for ip in servers]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="mon_refresh")])
        await query.edit_message_text("🗑️ <b>Выберите сервер для удаления:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return

    elif data.startswith("mon_del_"):
        ip = data.replace("mon_del_", "")
        servers = load_servers()
        if ip in servers:
            servers.remove(ip)
            save_servers(servers)
        await query.answer(f"✅ {ip} удалён")
        await server_monitor(update, context, query)
        return

    elif data == "mon_refresh":
        await query.answer("🔄 Обновляю...")
        await server_monitor(update, context, query)
        return

    elif data == "mon_back":
        await query.edit_message_text("⚙️ <b>Настройки</b>", parse_mode='HTML')
        return

async def server_monitor(update: Update, context: CallbackContext, query=None) -> None:
    """Показывает список серверов с кнопками"""
    if not is_admin(update.effective_user.id):
        return

    servers = load_servers()
    message = "🖥️ <b>МОНИТОРИНГ СЕРВЕРОВ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if servers:
        for ip in servers:
            status = ping_server(ip)
            if status is not None:
                message += f"🟢 <code>{ip}</code> — {status:.0f} ms\n"
            else:
                message += f"🔴 <code>{ip}</code> — не отвечает\n"
    else:
        message += "📋 Список серверов пуст\n"

    keyboard = [
        [InlineKeyboardButton("➕ Добавить сервер", callback_data="mon_add")],
        [InlineKeyboardButton("🗑️ Удалить сервер", callback_data="mon_del")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="mon_refresh")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="mon_back")],
    ]

    if query is not None:
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def add_server(update: Update, context: CallbackContext) -> None:
    """Добавляет сервер в мониторинг"""
    if not is_admin(update.effective_user.id):
        return
    try:
        ip = context.args[0]
        servers = load_servers()
        if ip not in servers:
            servers.append(ip)
            save_servers(servers)
            await update.message.reply_text(f"✅ <b>Сервер {ip} добавлен!</b>", parse_mode='HTML')
        else:
            await update.message.reply_text(f"⚠️ <b>{ip}</b> уже в списке", parse_mode='HTML')
    except:
        await update.message.reply_text("❌ Используйте: /addserver IP", parse_mode='HTML')

async def del_server(update: Update, context: CallbackContext) -> None:
    """Удаляет сервер из мониторинга"""
    if not is_admin(update.effective_user.id):
        return
    try:
        ip = context.args[0]
        servers = load_servers()
        if ip in servers:
            servers.remove(ip)
            save_servers(servers)
            await update.message.reply_text(f"✅ <b>Сервер {ip} удалён!</b>", parse_mode='HTML')
        else:
            await update.message.reply_text(f"⚠️ <b>{ip}</b> не найден", parse_mode='HTML')
    except:
        await update.message.reply_text("❌ Используйте: /delserver IP", parse_mode='HTML')

# ==================== ПРОВЕРКА ОБНОВЛЕНИЙ БОТА ====================
import asyncio as asyncio_bot_upd

# Читаем версию из version.txt
try:
    with open('/opt/SLV_Bot/version.txt') as f:
        BOT_VERSION = f.read().strip()
except:
    BOT_VERSION = "v1.0.0"
GITHUB_RAW = "https://raw.githubusercontent.com/elifecomp/slk-telegram-bot/main"

async def check_bot_updates():
    """Проверяет обновления бота на GitHub раз в час"""
    await asyncio_bot_upd.sleep(3)  # Быстрая проверка при старте
    while True:
        try:
            import requests
            r = requests.get(
                "https://api.github.com/repos/elifecomp/slk-telegram-bot/releases/latest",
                timeout=10
            )
            if r.status_code == 200:
                release = r.json()
                latest = release.get('tag_name', '')
                if latest != BOT_VERSION:
                    body = release.get('body', '')[:300]
                    date = release.get('published_at', '')[:10]
                    msg = f"🔔 <b>НОВЫЙ РЕЛИЗ БОТА SLK!</b>\n━━━━━━━━━━━━━━━━━\n"
                    msg += f"📦 Версия: {latest}\n"
                    msg += f"📅 Дата: {date}\n"
                    msg += f"📋 Текущая: {BOT_VERSION}\n\n"
                    if body:
                        msg += f"{body[:300]}\n\n"
                    msg += f"Для обновления: <code>slk-menu</code> → Обновить"
                    for admin_id in ADMIN_IDS:
                        try:
                            await application.bot.send_message(admin_id, msg, parse_mode='HTML')
                        except: pass
        except: pass
        await asyncio_bot_upd.sleep(3600)

async def check_bot_update_manual(update: Update, context: CallbackContext) -> None:
    """Ручная проверка обновлений бота через GitHub API"""
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🔄 <b>Проверяю обновления...</b>", parse_mode='HTML')
    import requests
    try:
        r = requests.get(
            "https://api.github.com/repos/elifecomp/slk-telegram-bot/releases/latest",
            timeout=10
        )
        if r.status_code == 200:
            release = r.json()
            latest = release.get('tag_name', '')
            body = release.get('body', '')[:800]
            date = release.get('published_at', '')[:10]

            msg = f"🆕 <b>ОБНОВЛЕНИЯ БОТА SLK</b>\n\n"
            msg += f"📦 У вас: {BOT_VERSION}\n"
            msg += f"🆕 Доступна: {latest}\n\n"
            msg += f"📋 <b>{latest}</b> ({date})\n"

            for line in body.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    if line.startswith('•') or line.startswith('-'):
                        msg += f"  {line}\n"
                    elif line[0] in '🚀🧹📦⚡💪🔧✅':
                        msg += f"\n{line}\n"
                    elif len(line) > 5:
                        msg += f"  • {line}\n"

            msg += f"\n<i>Данные с GitHub</i>"

            if latest != BOT_VERSION:
                msg += f"\n\n🔄 Для обновления:\n<code>slk-menu</code> → Обновить"

            await update.message.reply_text(msg, parse_mode='HTML')
        else:
            await update.message.reply_text("❌  Не удалось проверить обновления", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌  Ошибка подключения к GitHub", parse_mode='HTML')

async def show_cache(update: Update, context: CallbackContext) -> None:
    """Показывает статистику кэша"""
    if not is_admin(update.effective_user.id):
        return

    try:
        from xui_api import get_traffic_cache_stats
        stats = get_traffic_cache_stats()

        if stats and 'error' not in stats:
            message = "📊 <b>СТАТИСТИКА LRU-КЭША</b>\n\n"
            message += f"📦 <b>Размер:</b> {stats['size']}/{stats['max_size']} ({stats['usage_percent']:.1f}%)\n"
            message += f"🟢 <b>Активных:</b> {stats['active_records']}\n"
            message += f"🔴 <b>Неактивных:</b> {stats['inactive_records']}\n"
            message += f"⏱️ <b>Средний возраст:</b> {stats['avg_age_minutes']:.1f} мин\n"
            message += f"🎯 <b>Hit rate:</b> {stats['stats']['hit_rate']:.1f}%\n"
            message += f"🧹 <b>Очисток:</b> {stats['stats']['evictions']}\n"
        else:
            message = "❌ Статистика недоступна"
    except:
        message = "❌ Ошибка получения статистики"

    await update.message.reply_text(message, parse_mode=HTML)
