import os
import sys
import threading
import yaml
from loguru import logger
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))
logger.add("logs/bot.log", rotation="10 MB", retention="7 days", level="DEBUG")


def load_config() -> dict:
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def setup_strategies(binance_client, config: dict):
    from src.strategies.manager import StrategyManager
    from src.strategies import ALL_STRATEGIES

    manager = StrategyManager(binance_client, config)

    for name, strategy_cls in ALL_STRATEGIES.items():
        strategy = strategy_cls(binance_client, config)
        manager.register(name, strategy)

    manager.set_active("auto")
    logger.info(f"Strategies registered: {list(ALL_STRATEGIES.keys())}")
    return manager


def setup_scheduler(strategy_manager) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=strategy_manager.tick_all,
        trigger="interval",
        minutes=5,
        misfire_grace_time=60,
        id="strategy_tick",
    )
    scheduler.start()
    logger.info("APScheduler started: strategy tick every 5 minutes")
    return scheduler


def run_flask():
    from src.dashboard.app import create_dash_app
    app = create_dash_app()
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        use_reloader=False,
    )


def main():
    logger.info("Starting Binance Trading Bot...")

    from src.database.migrations import run_migrations
    run_migrations()
    logger.info("Database ready")

    config = load_config()

    from src.core.binance_client import BinanceClient
    binance_client = BinanceClient(
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
        testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
    )
    logger.info(f"Binance client initialized (testnet={binance_client.testnet})")

    strategy_manager = setup_strategies(binance_client, config)
    scheduler = setup_scheduler(strategy_manager)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask dashboard started on port 5000")

    from src.telegram_bot.app import run_telegram_bot
    logger.info("Starting Telegram bot...")
    try:
        run_telegram_bot(binance_client)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
