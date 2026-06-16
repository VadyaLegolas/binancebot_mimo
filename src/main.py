import os
import sys
import threading
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))
logger.add("logs/bot.log", rotation="10 MB", retention="7 days", level="DEBUG")


def main():
    logger.info("Starting Binance Trading Bot...")

    from src.database.migrations import run_migrations
    run_migrations()
    logger.info("Database migrations complete")

    from src.dashboard.app import run_dashboard
    dash_thread = threading.Thread(target=run_dashboard, daemon=True)
    dash_thread.start()
    logger.info("Dashboard started on port 5000")

    from src.telegram_bot.app import run_telegram_bot
    logger.info("Starting Telegram bot...")
    run_telegram_bot()


if __name__ == "__main__":
    main()
