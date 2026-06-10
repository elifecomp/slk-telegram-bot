#!/usr/bin/env python3
# start_services.py
import logging
import sys
import os
from pathlib import Path

# Добавляем путь к проекту в sys.path
sys.path.insert(0, str(Path(__file__).parent))

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Запуск всех сервисов бота"""
    try:
        logger.info("🚀 Запуск SLV Telegram Bot...")

        # Импортируем и запускаем бота
        from bot import main as run_bot
        run_bot()

    except ImportError as e:
        logger.error(f"❌ Ошибка импорта: {e}")
        logger.error("Проверьте структуру проекта и наличие всех файлов")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()