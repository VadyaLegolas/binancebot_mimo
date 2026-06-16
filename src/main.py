import os
import sys
import threading
import yaml
from loguru import logger
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def setup_learning(binance_client, strategy_manager, config: dict):
    from src.learning.parameter_tuner import ParameterTuner
    from src.learning.strategy_weighter import StrategyWeighter
    from src.learning.rl_agent import RLAgent
    from src.learning.anomaly_guard import AnomalyGuard

    tuner = ParameterTuner(strategy_manager)
    weighter = StrategyWeighter(binance_client, config)
    rl_agent = RLAgent(binance_client, config)
    guard = AnomalyGuard(config)

    logger.info("Learning Engine initialized")
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
                logger.info(f"Scheduler: optimizing params for {name}")
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
            elif a["action"] == "stop_trading":
                strategy_manager.set_active("stop")
                logger.warning("AnomalyGuard: trading stopped due to drawdown")

    scheduler.add_job(
        func=check_anomalies,
        trigger="interval",
        minutes=10,
        id="anomaly_check",
    )

    def check_rl_retrain():
        if rl_agent.should_retrain():
            logger.info("Scheduler: retraining RL agent")
            rl_agent.train(steps=10000)

    scheduler.add_job(
        func=check_rl_retrain,
        trigger="cron",
        day_of_week="sun",
        hour=0,
        id="rl_retrain",
    )

    scheduler.start()
    logger.info("APScheduler started with all learning jobs")
    return scheduler


def run_flask(config, tuner, weighter, rl_agent, guard):
    from src.dashboard.app import create_dash_app
    app = create_dash_app()
    app.config["tuner"] = tuner
    app.config["weighter"] = weighter
    app.config["rl_agent"] = rl_agent
    app.config["guard"] = guard
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
    tuner, weighter, rl_agent, guard = setup_learning(binance_client, strategy_manager, config)

    scheduler = setup_scheduler(strategy_manager, tuner, weighter, rl_agent, guard)

    flask_thread = threading.Thread(
        target=run_flask,
        args=(config, tuner, weighter, rl_agent, guard),
        daemon=True,
    )
    flask_thread.start()
    logger.info("Flask dashboard started on port 5000")

    from src.telegram_bot.app import run_telegram_bot
    logger.info("Starting Telegram bot...")
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
        logger.info("Shutting down...")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
