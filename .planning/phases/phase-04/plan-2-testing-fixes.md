---
wave: 2
depends_on:
  - plan-1-docs-config.md
files_modified:
  - src/telegram_bot/handlers.py
  - src/strategies/manager.py
  - src/dashboard/templates/index.html
requirements_addressed: []
autonomous: true
---

# Plan 2 — Integration Testing + Bug Fixes

<objective>
Run end-to-end integration tests, fix any remaining bugs, and ensure all components work together. By end of this plan: bot starts cleanly, all commands respond, dashboard loads, strategies can be toggled.
</objective>

---

## Task 2.1 — Add /mode command for Mainnet switching

<read_first>
- src/telegram_bot/handlers.py (current handlers)
- binance_bot_spec_v2.md (mode switching)
</read_first>

<action>
1. Add `handle_mode` to `src/telegram_bot/handlers.py`:

```python
async def handle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mode testnet|mainnet"""
    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/mode testnet - Switch to testnet\n"
            "/mode mainnet - Switch to mainnet"
        )
        return

    mode = context.args[0].lower()
    if mode not in ("testnet", "mainnet"):
        await update.message.reply_text("Invalid mode. Use testnet or mainnet.")
        return

    import os
    os.environ["BINANCE_TESTNET"] = "true" if mode == "testnet" else "false"

    # Recreate Binance client
    from src.core.binance_client import BinanceClient
    new_client = BinanceClient(
        os.getenv("BINANCE_API_KEY", ""),
        os.getenv("BINANCE_API_SECRET", ""),
        testnet=(mode == "testnet"),
    )
    context.application.bot_data["binance"] = new_client

    await update.message.reply_text(f"Mode switched to: {mode.upper()}")
```

2. Register in `create_bot_app`:

```python
app.add_handler(CommandHandler("mode", handle_mode))
```
</action>

<acceptance_criteria>
- `/mode testnet` switches to testnet
- `/mode mainnet` switches to mainnet
- BinanceClient is recreated with new testnet flag
</acceptance_criteria>

---

## Task 2.2 — Fix dashboard Learning Engine section

<read_first>
- src/dashboard/templates/index.html (current template)
</read_first>

<action>
1. Add Learning Engine section to `src/dashboard/templates/index.html` after Statistics card:

```html
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
```

2. Add to `refresh()` function:

```javascript
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
            '<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #333;">' +
            '<span>' + name + '</span>' +
            '<span>' + (weight * 100).toFixed(1) + '%</span>' +
            '</div>'
        ).join('');
    }
    if (learning.anomalies) {
        document.getElementById('anomaly-count').textContent = learning.anomalies.length;
    }
}
```
</action>

<acceptance_criteria>
- Dashboard shows RL mode, primary strategy, anomaly count
- Strategy weights displayed as percentages
- All values from API, no hardcoded data
</acceptance_criteria>

---

## Task 2.3 — Add /help command with all commands

<read_first>
- src/telegram_bot/handlers.py
</read_first>

<action>
1. Update `handle_start` and add `handle_help`:

```python
async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Binance Trading Bot v2.0\n\n"
        "Type /help for full command list."
    )

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Trading:\n"
        "/init <amount> - Set starting capital\n"
        "/buy <coin> <amount> - Buy in USDT\n"
        "/sell <coin> <qty> - Sell quantity\n"
        "/sell_all <coin> - Sell all position\n\n"
        "Information:\n"
        "/balance - Account balance\n"
        "/capital - Capital info\n"
        "/positions - Open positions\n"
        "/stats - Trading statistics\n"
        "/pnl - Profit/Loss\n"
        "/price <coin> - Current price\n"
        "/fees - Total fees paid\n\n"
        "Management:\n"
        "/status - Bot status\n"
        "/pairs - Active pairs\n"
        "/mode testnet|mainnet - Switch mode\n"
        "/strategy auto|grid|dca|rsi_ema|mtf\n\n"
        "Learning:\n"
        "/rl on|off|status|train\n"
        "/learn stats|retrain|history\n\n"
        "/help - This message"
    )
```

2. Register `/help` handler in `create_bot_app`.
</action>

<acceptance_criteria>
- `/help` shows all commands grouped by category
- `/start` shows brief welcome with help hint
</acceptance_criteria>

---

## Task 2.4 — Verify full integration

<read_first>
- src/main.py
- All plan files
</read_first>

<action>
1. Run integration verification:

```bash
python -c "
from src.main import load_config, setup_strategies, setup_learning
from src.database.migrations import run_migrations

run_migrations()
config = load_config()
print('Config OK:', list(config.keys()))

from src.core.binance_client import BinanceClient
class MockBinance:
    testnet = True
    def get_price(self, s): return 50000.0

mgr = setup_strategies(MockBinance(), config)
tuner, weighter, rl_agent, guard = setup_learning(MockBinance(), mgr, config)
print('All components initialized')
print('Strategies:', list(mgr.strategies.keys()))
print('RL Agent mode:', rl_agent.get_mode())
print('Integration test PASSED')
"
```
</action>

<acceptance_criteria>
- All components initialize without error
- Strategies registered correctly
- RL Agent in shadow mode by default
- No ImportError or runtime errors
</acceptance_criteria>

---

## Artifacts this plan produces

| File | Purpose |
|------|---------|
| `src/telegram_bot/handlers.py` | Added /mode, /help commands |
| `src/dashboard/templates/index.html` | Learning Engine section |
| `src/main.py` | Config validation |
