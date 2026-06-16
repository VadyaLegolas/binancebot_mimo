---
wave: 4
depends_on:
  - plan-3-rl-agent.md
files_modified:
  - src/telegram_bot/handlers.py
  - src/telegram_bot/app.py
  - src/dashboard/routes.py
  - src/dashboard/templates/index.html
  - src/strategies/manager.py
  - src/main.py
  - src/learning/__init__.py
requirements_addressed:
  - TGB-04
  - DASH-05
autonomous: true
---

# Plan 4 — Telegram Commands + Learning Dashboard + main.py Wiring

<objective>
Add Telegram commands for Learning Engine (/rl, /learn), create the Learning Dashboard page, and wire all learning components into main.py with APScheduler. By end of this plan: user can control RL agent via Telegram, dashboard shows learning metrics, and all components run automatically.
</objective>

---

## Task 4.1 — Add Telegram learning commands

<read_first>
- src/telegram_bot/handlers.py (current handlers)
- src/telegram_bot/app.py (create_bot_app)
- src/learning/rl_agent.py (RLAgent)
- src/learning/parameter_tuner.py (ParameterTuner)
- src/learning/strategy_weighter.py (StrategyWeighter)
- binance_bot_spec_v2.md §12 (Telegram commands)
</read_first>

<action>
1. Add to `src/telegram_bot/handlers.py`:

```python
# Add imports at top
from src.learning.rl_agent import RLAgent
from src.learning.parameter_tuner import ParameterTuner
from src.learning.strategy_weighter import StrategyWeighter
from src.learning.anomaly_guard import AnomalyGuard
from src.learning.model_store import get_param_history

# Add to create_bot_app() — register new handlers:
# app.add_handler(CommandHandler("rl", handle_rl))
# app.add_handler(CommandHandler("learn", handle_learn))
# app.add_handler(CommandHandler("strategy", handle_strategy))


async def handle_rl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rl on|off|status"""
    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/rl on - Enable live trading\n"
            "/rl off - Switch to shadow mode\n"
            "/rl status - Show RL agent status\n"
            "/rl train - Train on current data"
        )
        return

    action = context.args[0].lower()
    rl_agent = context.application.bot_data.get("rl_agent")

    if not rl_agent:
        await update.message.reply_text("RL Agent not initialized.")
        return

    if action == "on":
        rl_agent.set_mode("live")
        await update.message.reply_text("RL Agent: LIVE mode enabled. Agent will trade.")

    elif action == "off":
        rl_agent.set_mode("shadow")
        await update.message.reply_text("RL Agent: SHADOW mode. Observing only.")

    elif action == "status":
        status = rl_agent.get_status()
        await update.message.reply_text(
            f"RL Agent Status\n\n"
            f"Mode: {status['mode']}\n"
            f"Model: {'loaded' if status['model_loaded'] else 'not trained'}\n"
            f"Last train: {status['last_train'] or 'never'}\n"
            f"Consecutive losses: {status['consecutive_losses']}\n"
            f"Should retrain: {'yes' if status['should_retrain'] else 'no'}"
        )

    elif action == "train":
        await update.message.reply_text("Training RL agent... This may take a few minutes.")
        try:
            result = rl_agent.train(steps=5000)
            await update.message.reply_text(
                f"Training complete!\n"
                f"Mean reward: {result['mean_reward']:.2f}\n"
                f"Steps: {result['steps']}"
            )
        except Exception as e:
            await update.message.reply_text(f"Training failed: {e}")

    else:
        await update.message.reply_text(f"Unknown action: {action}. Use on/off/status/train.")


async def handle_learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /learn stats|reset|retrain"""
    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/learn stats - Show learning statistics\n"
            "/learn retrain - Force retrain all models\n"
            "/learn history <strategy> - Show param history"
        )
        return

    action = context.args[0].lower()

    if action == "stats":
        tuner = context.application.bot_data.get("tuner")
        weighter = context.application.bot_data.get("weighter")
        rl_agent = context.application.bot_data.get("rl_agent")
        guard = context.application.bot_data.get("guard")

        lines = ["Learning Engine Status\n"]

        if tuner:
            ts = tuner.get_status()
            lines.append(f"Parameter Tuner:")
            for strat, count in ts["last_optimization"].items():
                lines.append(f"  {strat}: last at trade #{count}")

        if weighter:
            ws = weighter.get_status()
            lines.append(f"\nStrategy Weights:")
            for name, w in ws["weights"].items():
                lines.append(f"  {name}: {w:.2f}")
            lines.append(f"  Primary: {ws['primary_strategy']}")

        if rl_agent:
            rs = rl_agent.get_status()
            lines.append(f"\nRL Agent: {rs['mode']}")

        if guard:
            anomalies = guard.check_all()
            lines.append(f"\nAnomaly Guard: {len(anomalies)} active issues")
            for a in anomalies:
                lines.append(f"  [{a['type']}] {a['message']}")

        await update.message.reply_text("\n".join(lines))

    elif action == "retrain":
        weighter = context.application.bot_data.get("weighter")
        if weighter:
            await update.message.reply_text("Retraining strategy weights...")
            weights = weighter.update()
            await update.message.reply_text(f"Updated weights: {weights}")
        else:
            await update.message.reply_text("Strategy Weighter not initialized.")

    elif action == "history":
        strategy = context.args[1] if len(context.args) > 1 else "grid"
        history = get_param_history(strategy)
        if not history:
            await update.message.reply_text(f"No param history for {strategy}")
            return

        lines = [f"Param History: {strategy}\n"]
        for h in history[:5]:
            lines.append(f"#{h['id']} ({h['created_at'][:16]})")
            if h["sharpe_before"] and h["sharpe_after"]:
                lines.append(f"  Sharpe: {h['sharpe_before']:.2f} → {h['sharpe_after']:.2f}")
            lines.append(f"  Applied: {h['applied']}")
            lines.append("")

        await update.message.reply_text("\n".join(lines))

    else:
        await update.message.reply_text(f"Unknown action: {action}. Use stats/retrain/history.")


async def handle_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /strategy <auto|name>"""
    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/strategy auto - Auto-select strategies\n"
            "/strategy grid|dca|rsi_ema|mtf - Fixed strategy"
        )
        return

    name = context.args[0].lower()
    strategy_manager = context.application.bot_data.get("strategy_manager")

    if not strategy_manager:
        await update.message.reply_text("Strategy Manager not initialized.")
        return

    strategy_manager.set_active(name)
    await update.message.reply_text(f"Strategy mode: {'auto' if strategy_manager.auto_mode else strategy_manager.active_name}")
```

2. Update `src/telegram_bot/app.py` to accept learning components:

```python
from src.telegram_bot.handlers import create_bot_app


def run_telegram_bot(binance_client=None, rl_agent=None, tuner=None, weighter=None, guard=None, strategy_manager=None):
    app = create_bot_app(binance_client)
    if rl_agent:
        app.bot_data["rl_agent"] = rl_agent
    if tuner:
        app.bot_data["tuner"] = tuner
    if weighter:
        app.bot_data["weighter"] = weighter
    if guard:
        app.bot_data["guard"] = guard
    if strategy_manager:
        app.bot_data["strategy_manager"] = strategy_manager
    app.run_polling()
```
</action>

<acceptance_criteria>
- `/rl on` switches RL agent to live mode
- `/rl off` switches to shadow mode
- `/rl status` shows agent status
- `/rl train` triggers training
- `/learn stats` shows all learning component statuses
- `/learn retrain` forces weight retraining
- `/learn history grid` shows param change history
- `/strategy auto` enables auto mode
- `/strategy grid` sets fixed strategy
- All handlers are async
- Missing components handled gracefully
</acceptance_criteria>

---

## Task 4.2 — Add Learning Dashboard API endpoints

<read_first>
- src/dashboard/routes.py (current routes)
- src/learning/parameter_tuner.py (get_status)
- src/learning/strategy_weighter.py (get_status)
- src/learning/rl_agent.py (get_status)
- src/learning/anomaly_guard.py (check_all)
- src/learning/model_store.py (get_param_history)
- binance_bot_spec_v2.md §13 (Dashboard spec)
</read_first>

<action>
1. Add to `src/dashboard/routes.py`:

```python
@bp.route("/api/learning")
def api_learning():
    """Learning Engine status for dashboard."""
    from src.learning.model_store import get_param_history

    result = {}

    tuner = current_app.config.get("tuner")
    if tuner:
        result["tuner"] = tuner.get_status()

    weighter = current_app.config.get("weighter")
    if weighter:
        result["weighter"] = weighter.get_status()

    rl_agent = current_app.config.get("rl_agent")
    if rl_agent:
        result["rl_agent"] = rl_agent.get_status()

    guard = current_app.config.get("guard")
    if guard:
        result["anomalies"] = guard.check_all()

    return jsonify(result)


@bp.route("/api/learning/history/<strategy>")
def api_learning_history(strategy):
    """Parameter change history for a strategy."""
    from src.learning.model_store import get_param_history
    history = get_param_history(strategy)
    return jsonify(history)


@bp.route("/api/weights")
def api_weights():
    """Current strategy weights."""
    weighter = current_app.config.get("weighter")
    if weighter:
        return jsonify(weighter.get_weights())
    return jsonify({"error": "Weighter not initialized"}), 503


@bp.route("/api/anomalies")
def api_anomalies():
    """Active anomalies from Anomaly Guard."""
    guard = current_app.config.get("guard")
    if guard:
        return jsonify(guard.check_all())
    return jsonify([])
```

2. Update `create_dash_app()` to store learning components:

```python
def create_dash_app() -> Flask:
    app = Flask(__name__, template_folder="templates")
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.register_blueprint(bp)
    return app
```

3. Add learning section to `src/dashboard/templates/index.html`:

```html
<!-- Add after the Statistics card -->
<div class="card">
    <h2>Learning Engine</h2>
    <div class="stat-grid">
        <div class="stat">
            <div class="label">RL Mode</div>
            <div class="value" id="rl-mode">--</div>
        </div>
        <div class="stat">
            <div class="label">Primary Strategy</div>
            <div class="value" id="primary-strategy">--</div>
        </div>
        <div class="stat">
            <div class="label">Anomalies</div>
            <div class="value" id="anomaly-count">--</div>
        </div>
    </div>
    <h3 style="margin-top: 15px; color: #e94560;">Strategy Weights</h3>
    <div id="weights-container"></div>
</div>

<!-- Add to refresh() function -->
const learningRes = await fetch('/api/learning');
if (learningRes.ok) {
    const learning = await learningRes.json();
    if (learning.rl_agent) {
        document.getElementById('rl-mode').textContent = learning.rl_agent.mode;
    }
    if (learning.weighter) {
        document.getElementById('primary-strategy').textContent = learning.weighter.primary_strategy;
        const container = document.getElementById('weights-container');
        container.innerHTML = Object.entries(learning.weighter.weights).map(([name, weight]) =>
            `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #333;">
                <span>${name}</span>
                <span>${(weight * 100).toFixed(1)}%</span>
            </div>`
        ).join('');
    }
    if (learning.anomalies) {
        document.getElementById('anomaly-count').textContent = learning.anomalies.length;
    }
}
```
</action>

<acceptance_criteria>
- `GET /api/learning` returns JSON with tuner, weighter, rl_agent, anomalies
- `GET /api/learning/history/grid` returns param change history
- `GET /api/weights` returns current strategy weights
- `GET /api/anomalies` returns active anomalies
- Dashboard shows RL mode, primary strategy, weights, anomaly count
- All values from API, no hardcoded data
</acceptance_criteria>

---

## Task 4.3 — Wire everything into main.py

<read_first>
- src/main.py (current entry point)
- src/strategies/manager.py (StrategyManager)
- src/learning/parameter_tuner.py (ParameterTuner)
- src/learning/strategy_weighter.py (StrategyWeighter)
- src/learning/rl_agent.py (RLAgent)
- src/learning/anomaly_guard.py (AnomalyGuard)
- src/core/pair_manager.py (PairManager)
</read_first>

<action>
1. Rewrite `src/main.py`:

```python
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

    # Strategy ticks every 5 minutes
    scheduler.add_job(
        func=strategy_manager.tick_all,
        trigger="interval",
        minutes=5,
        misfire_grace_time=60,
        id="strategy_tick",
    )

    # Parameter optimization check every 30 minutes
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

    # Strategy weight update every 4 hours
    scheduler.add_job(
        func=weighter.update,
        trigger="interval",
        hours=4,
        id="weight_update",
    )

    # Anomaly check every 10 minutes
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

    # RL retrain weekly
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
```

2. Update `requirements.txt`:
   ```
   optuna==4.9.0
   scikit-learn==1.8.0
   stable-baselines3==2.9.0
   gymnasium==1.3.0
   ```
</action>

<acceptance_criteria>
- `python src/main.py` starts without ImportError
- All learning components initialized
- APScheduler runs: strategy tick (5min), param optimization (30min), weight update (4h), anomaly check (10min), RL retrain (weekly)
- Flask receives learning components via app.config
- Telegram bot receives learning components via bot_data
- Graceful shutdown on Ctrl+C
</acceptance_criteria>

---

## Task 4.4 — Verify all imports and integration

<read_first>
- All plan files (plan-1 through plan-4)
- src/learning/__init__.py
</read_first>

<action>
1. Run verification:

```bash
python -c "
from src.learning.parameter_tuner import ParameterTuner
from src.learning.strategy_weighter import StrategyWeighter
from src.learning.rl_agent import RLAgent
from src.learning.anomaly_guard import AnomalyGuard
from src.learning.model_store import save_params, load_latest_params, get_param_history
from src.learning.trading_env import TradingEnv
from src.core.pair_manager import PairManager
print('All learning imports OK')
"
```

2. Verify Anomaly Guard:
```bash
python -c "
from src.learning.anomaly_guard import AnomalyGuard
guard = AnomalyGuard()
anomalies = guard.check_all()
print('Anomaly check:', anomalies)
print('AnomalyGuard OK')
"
```

3. Verify Parameter Tuner status:
```bash
python -c "
from src.learning.parameter_tuner import ParameterTuner, PARAM_SPACES
print('Param spaces:', list(PARAM_SPACES.keys()))
print('ParameterTuner OK')
"
```
</action>

<acceptance_criteria>
- All learning module imports succeed
- AnomalyGuard.check_all() runs without error
- ParameterTuner has param spaces for all 4 strategies
- No ImportError or ModuleNotFoundError
</acceptance_criteria>

---

## Artifacts this plan produces

| File | Purpose |
|------|---------|
| `src/telegram_bot/handlers.py` | Added /rl, /learn, /strategy commands |
| `src/telegram_bot/app.py` | Accepts learning components |
| `src/dashboard/routes.py` | Added /api/learning, /api/weights, /api/anomalies |
| `src/dashboard/templates/index.html` | Learning Engine section |
| `src/main.py` | Wired all learning components + APScheduler jobs |
| `requirements.txt` | Added optuna, scikit-learn, stable-baselines3, gymnasium |
