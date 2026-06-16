import os
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
from loguru import logger
from src.core.binance_client import BinanceClient
from src.core.capital import init_capital, get_capital_info, calc_pnl
from src.database.session import SessionLocal
from src.database.models import Trade, BotSession
from src.core.constants import CORE_PAIRS, MIN_TRADE_USDT
from datetime import datetime


async def reply(update, text):
    """Ответить пользователю."""
    await update.message.reply_text(text)


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


async def set_bot_commands(application: Application):
    """Установить меню команд в Telegram."""
    commands = [
        BotCommand("start", "Запуск бота"),
        BotCommand("help", "Помощь"),
        BotCommand("init", "Установить капитал"),
        BotCommand("buy", "Купить монету"),
        BotCommand("sell", "Продать монету"),
        BotCommand("sell_all", "Продать всё"),
        BotCommand("balance", "Баланс аккаунта"),
        BotCommand("capital", "Информация о капитале"),
        BotCommand("positions", "Открытые позиции"),
        BotCommand("stats", "Статистика"),
        BotCommand("pnl", "Прибыль/убыток"),
        BotCommand("price", "Текущая цена"),
        BotCommand("fees", "Комиссии"),
        BotCommand("status", "Статус бота"),
        BotCommand("pairs", "Активные пары"),
        BotCommand("mode", "Режим testnet/mainnet"),
        BotCommand("strategy", "Выбор стратегии"),
        BotCommand("rl", "RL-агент"),
        BotCommand("learn", "Обучение"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Меню команд установлено")


def get_binance(app: Application) -> BinanceClient:
    if "binance" not in app.bot_data:
        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        app.bot_data["binance"] = BinanceClient(api_key, api_secret, testnet=testnet)
    return app.bot_data["binance"]


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Установить меню команд
    await set_bot_commands(context.application)
    
    await reply(update, 
        "╔══════════════════════╗\n"
        "║  🤖 Binance Bot v2.0  ║\n"
        "╚══════════════════════╝\n\n"
        "Добро пожаловать!\n\n"
        "⚡ Автоматическая торговля\n"
        "🧠 Самообучение\n"
        "📊 Веб-дашборд: http://127.0.0.1:5000\n\n"
        "Начните с /init <сумма>\n"
        "Например: /init 100"
    )


async def handle_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply(update, "📝 Использование: /init <сумма>\nПример: /init 100")
        return

    try:
        amount = float(context.args[0])
        if amount < 10:
            await reply(update, "⚠️ Минимум: 10 USDT")
            return

        binance = get_binance(context.application)
        
        # Get real balance from Binance
        real_balance = binance.get_balance("USDT")
        
        # Use the amount as starting capital
        session = init_capital(amount, "testnet")
        
        # Save the real balance at init time
        from src.database.session import SessionLocal
        from src.database.models import BotSession
        db = SessionLocal()
        try:
            session = db.query(BotSession).order_by(-BotSession.id).first()
            if session:
                session.max_balance = amount
                db.commit()
        finally:
            db.close()

        await reply(update, 
            f"╔══════════════════════╗\n"
            f"║  ✅ КАПИТАЛ УСТАНОВЛЕН  ║\n"
            f"╚══════════════════════╝\n\n"
            f"💰 Стартовый: {amount:.2f} USDT\n"
            f"🏦 Реальный: {real_balance:.2f} USDT\n"
            f"🔧 Режим: testnet\n\n"
            f"Готов к торговле!"
        )
    except ValueError:
        await reply(update, "⚠️ Неверная сумма. Используйте: /init 100")


async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        binance = get_binance(context.application)
        account = binance._request_with_retry(binance.client.get_account)
        
        tracked = ["USDT", "BTC", "ETH", "SOL"]
        balances = []
        for balance in account["balances"]:
            asset = balance["asset"]
            if asset not in tracked:
                continue
            free = float(balance["free"])
            locked = float(balance["locked"])
            if free > 0 or locked > 0:
                balances.append((asset, free, locked))
        
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
        await reply(update, f"⚠️ Ошибка: {e}")


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

        # Get tracked balance from capital info
        from src.core.capital import get_capital_info
        capital_info = get_capital_info()
        if not capital_info:
            await reply(update, "⚠️ Сначала установите капитал: /init 100")
            return
        
        tracked_balance = capital_info['balance']
        if tracked_balance < amount:
            await reply(update, f"⚠️ Недостаточно средств.\nБаланс: {tracked_balance:.2f} USDT\nНужно: {amount:.2f} USDT")
            return

        min_notional = binance.get_min_notional(symbol)
        if amount < min_notional:
            await reply(update, f"⚠️ Минимальная сумма для {symbol}: {min_notional} USDT")
            return

        order = binance.place_market_buy(symbol, amount)

        # Get actual fill price from fills
        fill_price = float(order["fills"][0]["price"]) if order.get("fills") else float(order.get("price", 0))
        fill_qty = float(order["executedQty"])

        db = SessionLocal()
        try:
            trade = Trade(
                order_id=str(order["orderId"]),
                symbol=symbol,
                side="BUY",
                type="MARKET",
                strategy=None,
                quantity=fill_qty,
                price=fill_price,
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
            f"╔══════════════════════╗\n"
            f"║  🟢 ПОКУПКА {symbol}  ║\n"
            f"╚══════════════════════╝\n\n"
            f"💵 Сумма: ${amount:.2f}\n"
            f"📦 Количество: {fill_qty}\n"
            f"💰 Цена: ${fill_price:,.2f}\n"
            f"📋 Ордер: #{order['orderId']}"
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
        
        # Check if we have enough balance
        asset_balance = binance.get_balance(symbol)
        if asset_balance < quantity:
            await reply(update, f"⚠️ Недостаточно {symbol}.\nБаланс: {asset_balance:.6f}\nНужно: {quantity:.6f}")
            return
        
        order = binance.place_market_sell(symbol, quantity)
        
        fill_price = float(order["fills"][0]["price"]) if order.get("fills") else float(order.get("price", 0))
        fill_qty = float(order["executedQty"])
        sell_amount = fill_qty * fill_price

        # Find and close the matching open trade
        db = SessionLocal()
        try:
            open_trade = db.query(Trade).filter(
                Trade.symbol == symbol,
                Trade.side == "BUY",
                Trade.status == "OPEN",
            ).order_by(Trade.opened_at).first()

            if open_trade:
                # Calculate PnL
                from src.core.capital import calc_pnl
                pnl = calc_pnl(open_trade.price, fill_price, open_trade.quantity)
                
                open_trade.status = "CLOSED"
                open_trade.closed_at = datetime.utcnow()
                open_trade.fee_sell = fill_qty * fill_price * 0.001
                open_trade.fee_total = open_trade.fee_buy + open_trade.fee_sell
                open_trade.gross_pnl = pnl["gross_pnl"]
                open_trade.net_pnl = pnl["net_pnl"]
                open_trade.net_pnl_pct = pnl["net_pnl_pct"]
                db.commit()
                
                await reply(update, 
                    f"╔══════════════════════╗\n"
                    f"║  🔴 ПРОДАЖА {symbol}  ║\n"
                    f"╚══════════════════════╝\n\n"
                    f"📦 Количество: {fill_qty}\n"
                    f"💰 Цена: ${fill_price:,.2f}\n"
                    f"💵 Сумма: ${sell_amount:,.2f}\n"
                    f"📊 PnL: ${pnl['net_pnl']:.2f} ({pnl['net_pnl_pct']:.2f}%)\n"
                    f"📋 Ордер: #{order['orderId']}"
                )
            else:
                await reply(update, 
                    f"╔══════════════════════╗\n"
                    f"║  🔴 ПРОДАЖА {symbol}  ║\n"
                    f"╚══════════════════════╝\n\n"
                    f"📦 Количество: {fill_qty}\n"
                    f"💰 Цена: ${fill_price:,.2f}\n"
                    f"💵 Сумма: ${sell_amount:,.2f}\n"
                    f"📋 Ордер: #{order['orderId']}"
                )
        finally:
            db.close()

    except Exception as e:
        await reply(update, f"Error placing sell order: {e}")


async def handle_sell_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply(update, "Usage: /sell_all <coin>")
        return

    symbol = context.args[0].upper()
    try:
        binance = get_binance(context.application)
        account = binance._request_with_retry(binance.client.get_account)

        for balance in account["balances"]:
            if balance["asset"] == symbol and float(balance["free"]) > 0:
                qty = float(balance["free"])
                order = binance.place_market_sell(symbol, qty)
                
                fill_price = float(order["fills"][0]["price"]) if order.get("fills") else float(order.get("price", 0))
                fill_qty = float(order["executedQty"])
                sell_amount = fill_qty * fill_price

                # Close all open trades for this symbol
                db = SessionLocal()
                try:
                    open_trades = db.query(Trade).filter(
                        Trade.symbol == symbol,
                        Trade.side == "BUY",
                        Trade.status == "OPEN",
                    ).all()

                    total_pnl = 0
                    for t in open_trades:
                        from src.core.capital import calc_pnl
                        pnl = calc_pnl(t.price, fill_price, t.quantity)
                        t.status = "CLOSED"
                        t.closed_at = datetime.utcnow()
                        t.fee_sell = t.quantity * fill_price * 0.001
                        t.fee_total = t.fee_buy + t.fee_sell
                        t.gross_pnl = pnl["gross_pnl"]
                        t.net_pnl = pnl["net_pnl"]
                        t.net_pnl_pct = pnl["net_pnl_pct"]
                        total_pnl += pnl["net_pnl"]
                    db.commit()
                finally:
                    db.close()

                await reply(update, 
                    f"╔══════════════════════╗\n"
                    f"║  🔴 ПРОДАЖА ВСЕ {symbol}  ║\n"
                    f"╚══════════════════════╝\n\n"
                    f"📦 Количество: {fill_qty}\n"
                    f"💰 Цена: ${fill_price:,.2f}\n"
                    f"💵 Сумма: ${sell_amount:,.2f}\n"
                    f"📊 Итого PnL: ${total_pnl:.2f}"
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
        "╔══════════════════════╗\n"
        "║  📚 СПРАВКА          ║\n"
        "╚══════════════════════╝\n\n"
        "💰 ТОРГОВЛЯ:\n"
        "  /init <сумма> — стартовый капитал\n"
        "  /buy <монета> <сумма> — купить\n"
        "  /sell <монета> <кол> — продать\n"
        "  /sell_all <монета> — продать всё\n\n"
        "📊 ИНФОРМАЦИЯ:\n"
        "  /balance — баланс аккаунта\n"
        "  /capital — информация о капитале\n"
        "  /positions — открытые позиции\n"
        "  /stats — статистика торговли\n"
        "  /pnl — прибыль/убыток\n"
        "  /price <монета> — текущая цена\n"
        "  /fees — общие комиссии\n\n"
        "⚙️ УПРАВЛЕНИЕ:\n"
        "  /status — статус бота\n"
        "  /pairs — активные пары\n"
        "  /mode testnet|mainnet — переключить\n"
        "  /strategy auto|grid|dca|rsi_ema|mtf\n\n"
        "🧠 ОБУЧЕНИЕ:\n"
        "  /rl on|off|status|train\n"
        "  /learn stats|retrain|history\n\n"
        "📌 Команды доступны в меню бота"
    )
