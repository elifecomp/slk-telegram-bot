import asyncio
# [file name]: bot.py
import logging
import urllib3
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from config import BOT_TOKEN, WELCOME_AUDIO_PATH, XUI_VERIFY_SSL
from handlers import start, status, handle_message, ai_help, show_direct_keys_handler, ai_exit_handler, server_monitor, monitor_callback, error_handler, get_telegram_id, button_callback, handle_backup_delete, handle_online_info, handle_inbound_select, handle_client_button, handle_online_refresh, handle_server_refresh, handle_qr_callback, handle_copy_callback, handle_copy_callback, handle_qr_callback, handle_panel_switch
from handlers import is_admin, admin_panel_command, client_mode_command
from database import db
from connection_notifier import init_notifier, stop_notifier
from auto_reset import init_auto_reset, stop_auto_reset
from update_checker import init_update_checker, stop_update_checker
from morning_greeter import init_greeter, stop_greeter
from birthday_greeter import init_birthday_greeter, stop_birthday_greeter

# Отключаем предупреждения о небезопасных SSL соединениях
# Это делается только если SSL проверка отключена в конфиге
if not XUI_VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def cache_stats(update: Update, context) -> None:
    """Показывает статистику LRU-кэша (только для админа)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    try:
        from xui_api import get_traffic_cache_stats
        
        stats = get_traffic_cache_stats()
        
        if isinstance(stats, dict) and 'error' not in stats:
            message = "📊 <b>Статистика кэша трафика</b>\n\n"
            message += f"📦 <b>Размер:</b> {stats['size']}/{stats['max_size']} ({stats['usage_percent']:.1f}%)\n"
            message += f"🟢 <b>Активных записей:</b> {stats['active_records']}\n"
            message += f"🔴 <b>Неактивных записей:</b> {stats['inactive_records']}\n"
            message += f"⏱️ <b>Средний возраст:</b> {stats['avg_age_minutes']:.1f} мин\n"
            message += f"🎯 <b>Hit rate:</b> {stats['stats']['hit_rate']:.1f}%\n"
            message += f"🧹 <b>Очисток по размеру:</b> {stats['stats']['evictions']}\n"
            message += f"🧹 <b>Очисток по возрасту:</b> {stats['stats']['age_cleanups']}\n"
            
            await update.message.reply_text(message, parse_mode=HTML)
        else:
            await update.message.reply_text("❌ <b>Статистика кэша недоступна</b>", parse_mode=HTML)
    except Exception as e:
        logger.error(f"Ошибка получения статистики кэша: {e}")
        await update.message.reply_text("❌ <b>Ошибка получения статистики</b>", parse_mode=HTML)

async def clear_cache(update: Update, context) -> None:
    """Очищает LRU-кэш (только для админа)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>У вас нет доступа к этой команде</b>", parse_mode=HTML)
        return
    
    try:
        from traffic_cache import client_traffic_history
        
        # Получаем размер до очистки
        size_before = len(client_traffic_history)
        
        # Очищаем кэш
        client_traffic_history.clear()
        
        await update.message.reply_text(
            f"✅ <b>Кэш успешно очищен</b>\n\n"
            f"Удалено записей: {size_before}",
            parse_mode=HTML
        )
        logger.info(f"Админ {update.effective_user.id} очистил кэш трафика (удалено {size_before} записей)")
    except Exception as e:
        logger.error(f"Ошибка очистки кэша: {e}")
        await update.message.reply_text("❌ <b>Ошибка очистки кэша</b>", parse_mode=HTML)

def main() -> None:
    # Проверяем наличие аудиофайла при запуске
    check_audio_file()
    
    # Выводим информацию о SSL настройках
    print("\n" + "="*50)
    print("🔐 НАСТРОЙКИ БЕЗОПАСНОСТИ")
    print("="*50)
    if XUI_VERIFY_SSL:
        print("✅ SSL проверка: ВКЛЮЧЕНА")
        print("   Используется валидный SSL-сертификат")
    else:
        print("⚠️ SSL проверка: ОТКЛЮЧЕНА")
        print("   Режим для самоподписанных сертификатов или IP-адресов")
        print("   Для продакшена рекомендуется включить проверку")
    print("="*50 + "\n")
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(monitor_callback, pattern="^mon_"))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("id", get_telegram_id))
    application.add_handler(CommandHandler("cache", cache_stats))
    application.add_handler(CommandHandler("clearcache", clear_cache))
    application.add_handler(CommandHandler("admin", admin_panel_command))    # НОВАЯ КОМАНДА
    application.add_handler(CommandHandler("client", client_mode_command))   # НОВАЯ КОМАНДА
    
    # Добавляем обработчик callback-запросов (для inline-кнопок)
    application.add_handler(CallbackQueryHandler(show_direct_keys_handler, pattern="^show_direct_keys$"))
    application.add_handler(CallbackQueryHandler(ai_exit_handler, pattern="^ai_exit$"))
    application.add_handler(CallbackQueryHandler(handle_copy_callback, pattern="^copy_"))
    application.add_handler(CallbackQueryHandler(handle_online_info, pattern="^online_info_"))
    application.add_handler(CallbackQueryHandler(handle_inbound_select, pattern="^inbound_select_"))
    application.add_handler(CallbackQueryHandler(handle_client_button, pattern="^back_to_inbounds$"))
    application.add_handler(CallbackQueryHandler(handle_client_button, pattern="^client_btn_"))
    application.add_handler(CallbackQueryHandler(handle_online_refresh, pattern="^online_refresh$"))
    application.add_handler(CallbackQueryHandler(handle_qr_callback, pattern="^qr_"))
        
    application.add_handler(CallbackQueryHandler(handle_panel_switch, pattern="^panel_switch_"))
    application.add_handler(CallbackQueryHandler(handle_backup_delete, pattern="^backup_delete_"))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Добавляем обработчики для всех типов медиа
    application.add_handler(MessageHandler(filters.PHOTO, handle_message))
    application.add_handler(MessageHandler(filters.VIDEO, handle_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_message))
    application.add_handler(MessageHandler(filters.AUDIO, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_message))
    
    # Общий обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота
    logger.info("🤖 Бот запущен — 🇷🇺 -SLK- 🇷🇺")
    
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_notifier(application))
    loop.run_until_complete(init_auto_reset(application))
    loop.run_until_complete(init_update_checker(application))
    loop.run_until_complete(init_greeter(application))
    loop.run_until_complete(init_birthday_greeter(application))
    
    application.run_polling()

def check_audio_file():
    """Проверяет наличие аудиофайла при запуске"""
    possible_paths = [
        WELCOME_AUDIO_PATH,
        'welcome.mp3',
        './welcome.mp3',
        os.path.join(os.path.dirname(__file__), 'welcome.mp3'),
        os.path.join(os.getcwd(), 'welcome.mp3'),
        '/root/vpn_bot/welcome.mp3',
    ]
    
    found = False
    for path in possible_paths:
        if path and os.path.exists(path):
            logger.info(f"✅ Приветственный аудиофайл найден: {path}")
            found = True
            break
    
    if not found:
        logger.warning(f"❌ Приветственный аудиофайл не найден! Искали в: {possible_paths}")
        logger.warning("📢 Поместите файл welcome.mp3 в папку с ботом")

if __name__ == '__main__':
    main()