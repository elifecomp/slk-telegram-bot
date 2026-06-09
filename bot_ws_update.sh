#!/bin/bash
# Добавляем импорты в bot.py

# Добавляем импорт WebSocket
sed -i '/from connection_notifier import init_notifier, stop_notifier/a\
from websocket_notifier import init_ws_notifier, stop_ws_notifier' bot.py

# Добавляем импорт дашборда
sed -i '/from handlers import is_admin, admin_panel_command, client_mode_command/s/$/, show_dashboard, handle_dashboard_refresh/' bot.py

# Добавляем инициализацию WebSocket
sed -i '/loop.run_until_complete(init_notifier(application))/a\
    loop.run_until_complete(init_ws_notifier(application))' bot.py

# Добавляем остановку WebSocket
sed -i '/await stop_notifier()/a\
    await stop_ws_notifier()' bot.py

# Добавляем обработчик для дашборда
sed -i '/application.add_handler(CallbackQueryHandler(handle_server_refresh, pattern="^server_refresh$"))/a\
    application.add_handler(CallbackQueryHandler(handle_dashboard_refresh, pattern="^dashboard_refresh$"))' bot.py

# Добавляем команду для дашборда
sed -i '/application.add_handler(CommandHandler("clients_all", all_clients_v2))/a\
    application.add_handler(CommandHandler("dashboard", show_dashboard))' bot.py

echo "✅ bot.py обновлён для WebSocket и дашборда"
