import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from handlers import get_main_router
from handlers.client_portal import get_client_reply_keyboard
from services.clients_db import list_unnotified_clients, mark_access_notified
from services.panel_tg_access import get_panel_tg_ids
from services.panel_backup import daily_backup_loop


async def watch_panel_access_loop(bot: Bot, interval_seconds: int = 30) -> None:
    logger = logging.getLogger("panel_access_watcher")
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            pending = list_unnotified_clients()
            if not pending:
                continue

            panel_ids = await get_panel_tg_ids(force_refresh=True)
            if not panel_ids:
                continue

            for client in pending:
                raw_tg = client.get("telegram_id")
                try:
                    tg_int = int(raw_tg)
                except (TypeError, ValueError):
                    continue

                if tg_int in panel_ids:
                    mark_access_notified(tg_int, notified=True)
                    from html import escape
                    raw_client_name = str(client.get("name") or client.get("login") or "Клиент").strip()
                    client_name = escape(raw_client_name)
                    try:
                        await bot.send_message(
                            chat_id=tg_int,
                            text=(
                                "✅ <b>ДОСТУП ОТКРЫТ</b>\n"
                                "━━━━━━━━━━━━━━━━━━━━\n"
                                f"Добро пожаловать, <b>{client_name}</b>!\n"
                                "В новый обновлённый Telegram-бот от разработчика <b>SLK</b>.\n\n"
                                "🚀 <b>Встречайте новый бот!!!</b>\n"
                                "Ваш Telegram ID найден в панели, личный кабинет активирован."
                            ),
                            reply_markup=get_client_reply_keyboard(include_back_admin=False),
                            parse_mode="HTML",
                        )
                    except Exception as exc:
                        logger.warning("Не удалось отправить уведомление клиенту %s: %s", tg_int, exc)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Ошибка в фоновой проверке доступа 3X-UI: %s", exc)


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(get_main_router())

    watcher_task = asyncio.create_task(watch_panel_access_loop(bot, interval_seconds=30))
    backup_task = asyncio.create_task(daily_backup_loop(bot))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        watcher_task.cancel()
        backup_task.cancel()
        await asyncio.gather(watcher_task, backup_task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
