import os
import sys
import threading
import yaml
from loguru import logger
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"), 
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")
logger.add("logs/bot.log", rotation="10 MB", retention="7 days", level="DEBUG")


def send_telegram(message: str):
    """Отправить сообщение в Telegram."""
    try:
        import requests
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if token and chat_id:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение в Telegram: {e}")


def load_config() -> dict:
    try:
        with open("config.yaml") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("Файл config.yaml не найден!")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Ошибка парсинга config.yaml: {e}")
        raise


def setup_strategies(binance_client, config: dict):
    from src.strategies.manager import StrategyManager
    from src.strategies import ALL_STRATEGIES

    manager = StrategyManager(binance_client, config)
    for name, strategy_cls in ALL_STRATEGIES.items():
        strategy = strategy_cls(binance_client, config)
        manager.register(name, strategy)
    manager.set_active("auto")
    logger.info(f"Стратегии зарегистрированы: {list(ALL_STRATEGIES.keys())}")
    return manager


def setup_learning(binance_client, strategy_manager, config: dict):
    from src.learning.parameter_tuner import ParameterTuner
    from src.learning.strategy_weighter import StrategyWeighter
    from src.learning.rl_agent import RLAgent
    from src.learning.anomaly_guard import AnomalyGuard

    tuner = ParameterTuner(strategy_manager)
    weighter = StrategyWeighter(binance_client, config)
    rl_agent = RLAgent(binance_client, config)
    guard = AnomalyGuard(config)

    logger.info("Learning Engine инициализирован")
    return tuner, weighter, rl_agent, guard


def setup_scheduler(strategy_manager, tuner, weighter, rl_agent, guard) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        func=strategy_manager.tick_all,
        trigger="interval",
        minutes=5,
        misfire_grace_time=60,
        id="strategy_tick",
    )

    def check_optimization():
        for name in strategy_manager.strategies:
            if tuner.should_optimize(name):
                logger.info(f"Планировщик: оптимизация параметров для {name}")
                tuner.optimize(name)

    scheduler.add_job(
        func=check_optimization,
        trigger="interval",
        minutes=30,
        id="param_optimization",
    )

    scheduler.add_job(
        func=weighter.update,
        trigger="interval",
        hours=4,
        id="weight_update",
    )

    def check_anomalies():
        anomalies = guard.check_all()
        for a in anomalies:
            guard.save_anomaly_alert(a)
            if a["action"] == "rollback":
                for name in strategy_manager.strategies:
                    guard.rollback_latest_params(name)
                send_telegram(f"⚠️ AnomalyGuard: откат параметров для стратегий")
            elif a["action"] == "stop_trading":
                strategy_manager.set_active("stop")
                logger.warning("AnomalyGuard: торговля остановлена из-за просадки")
                send_telegram("🛑 AnomalyGuard: торговля остановлена (просадка > 8%)")

    scheduler.add_job(
        func=check_anomalies,
        trigger="interval",
        minutes=10,
        id="anomaly_check",
    )

    def check_rl_retrain():
        if rl_agent.should_retrain():
            logger.info("Планировщик: переобучение RL-агента")
            rl_agent.train(steps=10000)

    scheduler.add_job(
        func=check_rl_retrain,
        trigger="cron",
        day_of_week="sun",
        hour=0,
        id="rl_retrain",
    )

    def show_prices_job():
        show_prices(strategy_manager.binance)

    scheduler.add_job(
        func=show_prices_job,
        trigger="interval",
        minutes=5,
        id="price_ticker",
    )

    scheduler.start()
    logger.info("APScheduler запущен со всеми задачами learning")
    return scheduler


_last_prices = {}

# ANSI цвета
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def show_prices(binance_client):
    """Показать текущие цены в терминале с изменением."""
    global _last_prices
    pairs = ["BTC", "ETH", "SOL"]
    
    logger.info("═══════════════════════════════════════")
    logger.info("  📊 ТЕКУЩИЕ ЦЕНЫ")
    logger.info("───────────────────────────────────────")
    
    for symbol in pairs:
        try:
            price = binance_client.get_price(symbol)
            prev = _last_prices.get(symbol)
            if prev and prev > 0:
                change = price - prev
                change_pct = (change / prev) * 100
                arrow = "📈" if change >= 0 else "📉"
                sign = "+" if change >= 0 else ""
                
                if change_pct > 0:
                    color = GREEN
                elif change_pct < 0:
                    color = RED
                else:
                    color = YELLOW
                
                print(f"  {arrow} {symbol}/USDT: ${price:,.2f} {color}({sign}{change_pct:.2f}%){RESET}")
            else:
                print(f"  💰 {symbol}/USDT: ${price:,.2f}")
            _last_prices[symbol] = price
        except Exception:
            print(f"  ❓ {symbol}/USDT: загрузка...")
    
    logger.info("───────────────────────────────────────")


def run_flask(config, tuner, weighter, rl_agent, guard, binance_client):
    import logging
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    from src.dashboard.app import create_dash_app
    app = create_dash_app()
    app.config["tuner"] = tuner
    app.config["weighter"] = weighter
    app.config["rl_agent"] = rl_agent
    app.config["guard"] = guard
    app.config["binance"] = binance_client
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        use_reloader=False,
    )


def main():
    logger.info("Запуск Binance Trading Bot...")
    send_telegram("🚀 Бот запущен!")

    from src.database.migrations import run_migrations
    run_migrations()
    logger.info("База данных готова")

    config = load_config()

    from src.core.binance_client import BinanceClient
    binance_client = BinanceClient(
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
        testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
    )
    mode = "Testnet" if binance_client.testnet else "Mainnet"
    logger.info(f"Binance клиент инициализирован ({mode})")
    show_prices(binance_client)

    strategy_manager = setup_strategies(binance_client, config)
    tuner, weighter, rl_agent, guard = setup_learning(binance_client, strategy_manager, config)

    scheduler = setup_scheduler(strategy_manager, tuner, weighter, rl_agent, guard)

    flask_thread = threading.Thread(
        target=run_flask,
        args=(config, tuner, weighter, rl_agent, guard, binance_client),
        daemon=True,
    )
    flask_thread.start()
    port = int(os.getenv("FLASK_PORT", "5000"))
    logger.info(f"Dashboard запущен: http://127.0.0.1:{port}")

    from src.telegram_bot.app import run_telegram_bot
    logger.info("Запуск Telegram бота...")
    
    # Показать баланс
    try:
        account = binance_client.client.get_account()
        balances = []
        for b in account["balances"]:
            free = float(b["free"])
            if free > 0:
                balances.append(f"{b['asset']}: {free:.4f}")
        if balances:
            logger.info("💰 Баланс: " + " | ".join(balances[:5]))
    except Exception:
        pass
    
    send_telegram(f"✅ Бот готов к работе!\nРежим: {mode}\nСтратегии: {', '.join(strategy_manager.strategies.keys())}")

    try:
        run_telegram_bot(
            binance_client=binance_client,
            rl_agent=rl_agent,
            tuner=tuner,
            weighter=weighter,
            guard=guard,
            strategy_manager=strategy_manager,
        )
    except KeyboardInterrupt:
        logger.info("Остановка бота...")
        send_telegram("🛑 Бот остановлен!")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
