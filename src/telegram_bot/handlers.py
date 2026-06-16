import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from loguru import logger
from src.core.binance_client import BinanceClient
from src.core.capital import init_capital, get_capital_info, calc_pnl
from src.database.session import SessionLocal
from src.database.models import Trade, BotSession
from src.core.constants import CORE_PAIRS, MIN_TRADE_USDT
from datetime import datetime

COMMANDS_FOOTER = (
    "\n\n──────────────────\n"
    "📋 Команды:\n"
    "/init <сумма> | /buy <монета> <сумма> | /sell <монета> <кол>\n"
    "/balance | /capital | /positions | /stats | /pnl | /fees\n"
    "/price <монета> | /pairs | /status | /mode testnet|mainnet\n"
    "/strategy auto|grid|dca|rsi_ema|mtf\n"
    "/rl on|off|status|train | /learn stats|retrain|history\n"
    "/help"
)


async def reply(update, text):
    """Ответить с закреплёнными командами."""
    await update.message.reply_text(text + COMMANDS_FOOTER)


def create_bot_app(binance_client=None) -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set")

    application = Application.builder().token(token).build()

    if binance_client:
        application.bot_data["binance"] = binance_client

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("help", handle_help))
    application.add_handler(CommandHandler("init", handle_init))
    application.add_handler(CommandHandler("balance", handle_balance))
    application.add_handler(CommandHandler("capital", handle_capital))
    application.add_handler(CommandHandler("positions", handle_positions))
    application.add_handler(CommandHandler("stats", handle_stats))
    application.add_handler(CommandHandler("pnl", handle_pnl))
    application.add_handler(CommandHandler("price", handle_price))
    application.add_handler(CommandHandler("buy", handle_buy))
    application.add_handler(CommandHandler("sell", handle_sell))
    application.add_handler(CommandHandler("sell_all", handle_sell_all))
    application.add_handler(CommandHandler("pairs", handle_pairs))
    application.add_handler(CommandHandler("status", handle_status))
    application.add_handler(CommandHandler("fees", handle_fees))
    application.add_handler(CommandHandler("mode", handle_mode))
    application.add_handler(CommandHandler("rl", handle_rl))
    application.add_handler(CommandHandler("learn", handle_learn))
    application.add_handler(CommandHandler("strategy", handle_strategy))

    return application


def get_binance(app: Application) -> BinanceClient:
    if "binance" not in app.bot_data:
        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        app.bot_data["binance"] = BinanceClient(api_key, api_secret, testnet=testnet)
    return app.bot_data["binance"]


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, 
        "🤖 Binance Trading Bot v2.0\n\n"
        "Добро пожаловать! Вот все доступные команды:\n\n"
        "💰 Торговля:\n"
        "/init <сумма> | /buy <монета> <сумма> | /sell <монета> <кол>\n"
        "/sell_all <монета>\n\n"
        "📊 Информация:\n"
        "/balance | /capital | /positions | /stats | /pnl | /fees | /price\n\n"
        "⚙️ Управление:\n"
        "/status | /pairs | /mode | /strategy\n\n"
        "🧠 Обучение:\n"
        "/rl | /learn | /help"
    )


async def handle_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply(update, "Usage: /init <amount>\nExample: /init 100")
        return

    try:
        amount = float(context.args[0])
        if amount < 10:
            await reply(update, "Minimum starting capital: 10 USDT")
            return

        binance = get_binance(context.application)
        mode = "testnet" if os.getenv("BINANCE_TESTNET", "true").lower() == "true" else "mainnet"
        session = init_capital(amount, mode)

        await reply(update, 
            f"✅ Starting capital set: {amount:.2f} USDT\n"
            f"Mode: {mode}\n"
            f"Trading ready."
        )
    except ValueError:
        await reply(update, "Invalid amount. Usage: /init 100")


async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        binance = get_binance(context.application)
        account = binance.client.get_account()
        
        balances = []
        for balance in account["balances"]:
            free = float(balance["free"])
            locked = float(balance["locked"])
            if free > 0 or locked > 0:
                balances.append((balance["asset"], free, locked))
        
        if not balances:
            await reply(update, "💰 Баланс пуст")
            return
        
        lines = ["💰 Баланс аккаунта:\n"]
        for asset, free, locked in sorted(balances, key=lambda x: -x[1]):
            if locked > 0:
                lines.append(f"  {asset}: {free:.6f} (заморожено: {locked:.6f})")
            else:
                lines.append(f"  {asset}: {free:.6f}")
        
        await reply(update, "\n".join(lines))
    except Exception as e:
        await reply(update, "⚠️ Не удалось получить баланс. Попробуйте позже.")


async def handle_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_capital_info()
    if not info:
        await reply(update, "No session found. Use /init <amount> first.")
        return

    await reply(update, 
        f"💰 Capital Info\n\n"
        f"Starting: {info['starting_capital']:.2f} USDT\n"
        f"Net PnL: {info['net_pnl']:+.2f} USDT ({info['roi_pct']:+.1f}%)\n"
        f"Current Balance: {info['current_balance']:.2f} USDT\n"
        f"Open Positions: {info['unrealized_pnl']:+.2f} USDT\n"
        f"Total: {info['total_with_open']:.2f} USDT\n"
        f"Max Balance: {info['max_balance']:.2f} USDT\n"
        f"Drawdown: {info['drawdown_pct']:.2f}%"
    )


async def handle_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        trades = db.query(Trade).filter(Trade.status == "OPEN").all()
        if not trades:
            await reply(update, "No open positions.")
            return

        binance = get_binance(context.application)
        lines = ["📊 Open Positions:\n"]
        for t in trades:
            try:
                current_price = binance.get_price(t.symbol)
                pnl_pct = ((current_price - t.price) / t.price) * 100
                lines.append(
                    f"{t.symbol}: {t.quantity:.6f} @ {t.price:.2f}\n"
                    f"  Current: {current_price:.2f} | PnL: {pnl_pct:+.1f}%\n"
                    f"  Strategy: {t.strategy or 'manual'}"
                )
            except Exception:
                lines.append(f"{t.symbol}: {t.quantity:.6f} @ {t.price:.2f}")

        await reply(update, "\n".join(lines))
    finally:
        db.close()


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        total = db.query(Trade).filter(Trade.status == "CLOSED").count()
        wins = db.query(Trade).filter(Trade.status == "CLOSED", Trade.net_pnl > 0).count()
        total_pnl = db.query(Trade.net_pnl).filter(Trade.status == "CLOSED").all()
        total_fees = db.query(Trade.fee_total).filter(Trade.status == "CLOSED").all()

        pnl_sum = sum(p[0] for p in total_pnl) if total_pnl else 0
        fees_sum = sum(f[0] for f in total_fees) if total_fees else 0
        win_rate = (wins / total * 100) if total > 0 else 0

        await reply(update, 
            f"📊 Statistics\n\n"
            f"Total Trades: {total}\n"
            f"Wins: {wins} | Losses: {total - wins}\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"Net PnL: {pnl_sum:+.2f} USDT\n"
            f"Total Fees: -{fees_sum:.2f} USDT"
        )
    finally:
        db.close()


async def handle_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_capital_info()
    if not info:
        await reply(update, "No session found. Use /init first.")
        return

    await reply(update, 
        f"📈 PnL Summary\n\n"
        f"Realized PnL: {info['net_pnl']:+.2f} USDT\n"
        f"Unrealized: {info['unrealized_pnl']:+.2f} USDT\n"
        f"ROI: {info['roi_pct']:+.1f}%"
    )


async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply(update, "Usage: /price <coin>\nExample: /price BTC")
        return

    symbol = context.args[0].upper()
    try:
        binance = get_binance(context.application)
        price = binance.get_price(symbol)
        await reply(update, f"💰 {symbol}/USDT: {price:.2f}")
    except Exception as e:
        await reply(update, f"Error getting price for {symbol}: {e}")


async def handle_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply(update, "Usage: /buy <coin> <amount_usdt>\nExample: /buy BTC 15")
        return

    symbol = context.args[0].upper()
    try:
        amount = float(context.args[1])
    except ValueError:
        await reply(update, "Invalid amount.")
        return

    if amount < MIN_TRADE_USDT:
        await reply(update, f"Minimum trade: {MIN_TRADE_USDT} USDT")
        return

    try:
        binance = get_binance(context.application)

        min_notional = binance.get_min_notional(symbol)
        if amount < min_notional:
            await reply(update, f"Minimum notional for {symbol}: {min_notional} USDT")
            return

        order = binance.place_market_buy(symbol, amount)

        db = SessionLocal()
        try:
            trade = Trade(
                order_id=str(order["orderId"]),
                symbol=symbol,
                side="BUY",
                type="MARKET",
                strategy=None,
                quantity=float(order["executedQty"]),
                price=float(order["price"]),
                total_usdt=amount,
                fee_rate=0.001,
                fee_buy=amount * 0.001,
                status="OPEN",
                opened_at=datetime.utcnow(),
            )
            db.add(trade)
            db.commit()
        finally:
            db.close()

        await reply(update, 
            f"🟢 ПОКУПКА {symbol}\n"
            f"Сумма: ${amount:.2f}\n"
            f"Количество: {order['executedQty']}\n"
            f"Цена: ${float(order['price']):,.2f}\n"
            f"Ордер: #{order['orderId']}"
        )
    except Exception as e:
        await reply(update, f"Error placing buy order: {e}")


async def handle_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply(update, "Usage: /sell <coin> <quantity>")
        return

    symbol = context.args[0].upper()
    try:
        quantity = float(context.args[1])
    except ValueError:
        await reply(update, "Invalid quantity.")
        return

    try:
        binance = get_binance(context.application)
        order = binance.place_market_sell(symbol, quantity)
        
        sell_price = float(order['price'])
        sell_amount = quantity * sell_price

        await reply(update, 
            f"🔴 ПРОДАЖА {symbol}\n"
            f"Количество: {quantity}\n"
            f"Цена: ${sell_price:,.2f}\n"
            f"Сумма: ${sell_amount:,.2f}\n"
            f"Ордер: #{order['orderId']}"
        )
    except Exception as e:
        await reply(update, f"Error placing sell order: {e}")


async def handle_sell_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply(update, "Usage: /sell_all <coin>")
        return

    symbol = context.args[0].upper()
    try:
        binance = get_binance(context.application)
        account = binance.client.get_account()

        for balance in account["balances"]:
            if balance["asset"] == symbol and float(balance["free"]) > 0:
                qty = float(balance["free"])
                order = binance.place_market_sell(symbol, qty)
                
                sell_price = float(order['price'])
                sell_amount = qty * sell_price
                
                await reply(update, 
                    f"🔴 ПРОДАЖА ВСЕ {symbol}\n"
                    f"Количество: {qty}\n"
                    f"Цена: ${sell_price:,.2f}\n"
                    f"Сумма: ${sell_amount:,.2f}"
                )
                return

        await reply(update, f"Нет баланса {symbol}.")
    except Exception as e:
        await reply(update, f"Error: {e}")


async def handle_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, 
        f"📋 Active Pairs:\n" + "\n".join(f"• {p}/USDT" for p in CORE_PAIRS)
    )


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_capital_info()
    mode = os.getenv("BINANCE_TESTNET", "true")
    status_text = f"🤖 Bot Status\n\nMode: {'Testnet' if mode.lower() == 'true' else 'Mainnet'}"
    if info:
        status_text += f"\nBalance: {info['current_balance']:.2f} USDT\nPnL: {info['net_pnl']:+.2f}"
    await reply(update, status_text)


async def handle_fees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        total_fees = db.query(Trade.fee_total).filter(Trade.status == "CLOSED").all()
        fees_sum = sum(f[0] for f in total_fees) if total_fees else 0
        await reply(update, f"💸 Total Fees Paid: -{fees_sum:.2f} USDT")
    finally:
        db.close()


async def handle_rl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply(update, 
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
        await reply(update, "RL Agent not initialized.")
        return

    if action == "on":
        rl_agent.set_mode("live")
        await reply(update, "RL Agent: LIVE mode enabled.")

    elif action == "off":
        rl_agent.set_mode("shadow")
        await reply(update, "RL Agent: SHADOW mode. Observing only.")

    elif action == "status":
        status = rl_agent.get_status()
        await reply(update, 
            f"RL Agent Status\n\n"
            f"Mode: {status['mode']}\n"
            f"Model: {'loaded' if status['model_loaded'] else 'not trained'}\n"
            f"Last train: {status['last_train'] or 'never'}\n"
            f"Consecutive losses: {status['consecutive_losses']}\n"
            f"Should retrain: {'yes' if status['should_retrain'] else 'no'}"
        )

    elif action == "train":
        await reply(update, "Training RL agent...")
        try:
            result = rl_agent.train(steps=5000)
            await reply(update, 
                f"Training complete!\n"
                f"Mean reward: {result['mean_reward']:.2f}\n"
                f"Steps: {result['steps']}"
            )
        except Exception as e:
            await reply(update, f"Training failed: {e}")

    else:
        await reply(update, f"Unknown action: {action}. Use on/off/status/train.")


async def handle_learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply(update, 
            "Usage:\n"
            "/learn stats - Show learning statistics\n"
            "/learn retrain - Force retrain weights\n"
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
            lines.append("Parameter Tuner:")
            for strat, count in ts["last_optimization"].items():
                lines.append(f"  {strat}: last at trade #{count}")

        if weighter:
            ws = weighter.get_status()
            lines.append("\nStrategy Weights:")
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

        await reply(update, "\n".join(lines))

    elif action == "retrain":
        weighter = context.application.bot_data.get("weighter")
        if weighter:
            await reply(update, "Retraining strategy weights...")
            weights = weighter.update()
            await reply(update, f"Updated weights: {weights}")
        else:
            await reply(update, "Strategy Weighter not initialized.")

    elif action == "history":
        strategy = context.args[1] if len(context.args) > 1 else "grid"
        from src.learning.model_store import get_param_history
        history = get_param_history(strategy)
        if not history:
            await reply(update, f"No param history for {strategy}")
            return

        lines = [f"Param History: {strategy}\n"]
        for h in history[:5]:
            lines.append(f"#{h['id']} ({h['created_at'][:16]})")
            if h["sharpe_before"] and h["sharpe_after"]:
                lines.append(f"  Sharpe: {h['sharpe_before']:.2f} -> {h['sharpe_after']:.2f}")
            lines.append(f"  Applied: {h['applied']}")
            lines.append("")

        await reply(update, "\n".join(lines))

    else:
        await reply(update, f"Unknown action: {action}. Use stats/retrain/history.")


async def handle_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply(update, 
            "Usage:\n"
            "/strategy auto - Auto-select strategies\n"
            "/strategy grid|dca|rsi_ema|mtf - Fixed strategy"
        )
        return

    name = context.args[0].lower()
    strategy_manager = context.application.bot_data.get("strategy_manager")

    if not strategy_manager:
        await reply(update, "Strategy Manager not initialized.")
        return

    strategy_manager.set_active(name)
    await reply(update, f"Strategy mode: {'auto' if strategy_manager.auto_mode else strategy_manager.active_name}")


async def handle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply(update, 
            "Usage:\n"
            "/mode testnet - Switch to testnet\n"
            "/mode mainnet - Switch to mainnet"
        )
        return

    mode = context.args[0].lower()
    if mode not in ("testnet", "mainnet"):
        await reply(update, "Invalid mode. Use testnet or mainnet.")
        return

    os.environ["BINANCE_TESTNET"] = "true" if mode == "testnet" else "false"

    from src.core.binance_client import BinanceClient
    new_client = BinanceClient(
        os.getenv("BINANCE_API_KEY", ""),
        os.getenv("BINANCE_API_SECRET", ""),
        testnet=(mode == "testnet"),
    )
    context.application.bot_data["binance"] = new_client

    await reply(update, f"Mode switched to: {mode.upper()}")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update, 
        "🤖 Помощь\n\n"
        "💰 Торговля:\n"
        "/init <сумма> - Установить стартовый капитал\n"
        "/buy <монета> <сумма> - Купить в USDT\n"
        "/sell <монета> <кол> - Продать количество\n"
        "/sell_all <монета> - Продать всю позицию\n\n"
        "📊 Информация:\n"
        "/balance - Баланс аккаунта\n"
        "/capital - Информация о капитале\n"
        "/positions - Открытые позиции\n"
        "/stats - Статистика торговли\n"
        "/pnl - Прибыль/Убыток\n"
        "/price <монета> - Текущая цена\n"
        "/fees - Общие комиссии\n\n"
        "⚙️ Управление:\n"
        "/status - Статус бота\n"
        "/pairs - Активные пары\n"
        "/mode testnet|mainnet - Переключить режим\n"
        "/strategy auto|grid|dca|rsi_ema|mtf\n\n"
        "🧠 Обучение:\n"
        "/rl on|off|status|train\n"
        "/learn stats|retrain|history"
    )
