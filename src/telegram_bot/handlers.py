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


def create_bot_app() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set")

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", handle_start))
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

    return application


def get_binance(app: Application) -> BinanceClient:
    if "binance" not in app.bot_data:
        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        app.bot_data["binance"] = BinanceClient(api_key, api_secret, testnet=testnet)
    return app.bot_data["binance"]


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Binance Trading Bot v2.0\n\n"
        "Commands:\n"
        "/init <amount> - Set starting capital\n"
        "/balance - Account balance\n"
        "/capital - Capital info\n"
        "/buy <coin> <amount> - Buy in USDT\n"
        "/sell <coin> <qty> - Sell quantity\n"
        "/sell_all <coin> - Sell all position\n"
        "/positions - Open positions\n"
        "/stats - Trading statistics\n"
        "/pnl - Profit/Loss\n"
        "/price <coin> - Current price\n"
        "/pairs - Active pairs\n"
        "/status - Bot status\n"
    )


async def handle_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /init <amount>\nExample: /init 100")
        return

    try:
        amount = float(context.args[0])
        if amount < 10:
            await update.message.reply_text("Minimum starting capital: 10 USDT")
            return

        binance = get_binance(context.application)
        mode = "testnet" if os.getenv("BINANCE_TESTNET", "true").lower() == "true" else "mainnet"
        session = init_capital(amount, mode)

        await update.message.reply_text(
            f"✅ Starting capital set: {amount:.2f} USDT\n"
            f"Mode: {mode}\n"
            f"Trading ready."
        )
    except ValueError:
        await update.message.reply_text("Invalid amount. Usage: /init 100")


async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        binance = get_binance(context.application)
        usdt = binance.get_balance("USDT")
        await update.message.reply_text(f"💰 USDT Balance: {usdt:.2f}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def handle_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_capital_info()
    if not info:
        await update.message.reply_text("No session found. Use /init <amount> first.")
        return

    await update.message.reply_text(
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
            await update.message.reply_text("No open positions.")
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

        await update.message.reply_text("\n".join(lines))
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

        await update.message.reply_text(
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
        await update.message.reply_text("No session found. Use /init first.")
        return

    await update.message.reply_text(
        f"📈 PnL Summary\n\n"
        f"Realized PnL: {info['net_pnl']:+.2f} USDT\n"
        f"Unrealized: {info['unrealized_pnl']:+.2f} USDT\n"
        f"ROI: {info['roi_pct']:+.1f}%"
    )


async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /price <coin>\nExample: /price BTC")
        return

    symbol = context.args[0].upper()
    try:
        binance = get_binance(context.application)
        price = binance.get_price(symbol)
        await update.message.reply_text(f"💰 {symbol}/USDT: {price:.2f}")
    except Exception as e:
        await update.message.reply_text(f"Error getting price for {symbol}: {e}")


async def handle_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /buy <coin> <amount_usdt>\nExample: /buy BTC 15")
        return

    symbol = context.args[0].upper()
    try:
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return

    if amount < MIN_TRADE_USDT:
        await update.message.reply_text(f"Minimum trade: {MIN_TRADE_USDT} USDT")
        return

    try:
        binance = get_binance(context.application)

        min_notional = binance.get_min_notional(symbol)
        if amount < min_notional:
            await update.message.reply_text(f"Minimum notional for {symbol}: {min_notional} USDT")
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

        await update.message.reply_text(
            f"✅ BUY {symbol}\n"
            f"Amount: {amount:.2f} USDT\n"
            f"Qty: {order['executedQty']}\n"
            f"Price: {order['price']}\n"
            f"Order ID: {order['orderId']}"
        )
    except Exception as e:
        await update.message.reply_text(f"Error placing buy order: {e}")


async def handle_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /sell <coin> <quantity>")
        return

    symbol = context.args[0].upper()
    try:
        quantity = float(context.args[1])
    except ValueError:
        await update.message.reply_text("Invalid quantity.")
        return

    try:
        binance = get_binance(context.application)
        order = binance.place_market_sell(symbol, quantity)

        await update.message.reply_text(
            f"✅ SELL {symbol}\n"
            f"Qty: {quantity}\n"
            f"Price: {order['price']}\n"
            f"Order ID: {order['orderId']}"
        )
    except Exception as e:
        await update.message.reply_text(f"Error placing sell order: {e}")


async def handle_sell_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /sell_all <coin>")
        return

    symbol = context.args[0].upper()
    try:
        binance = get_binance(context.application)
        account = binance.client.get_account()

        for balance in account["balances"]:
            if balance["asset"] == symbol and float(balance["free"]) > 0:
                qty = float(balance["free"])
                order = binance.place_market_sell(symbol, qty)
                await update.message.reply_text(
                    f"✅ SELL ALL {symbol}\n"
                    f"Qty: {qty}\n"
                    f"Price: {order['price']}"
                )
                return

        await update.message.reply_text(f"No {symbol} balance found.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def handle_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📋 Active Pairs:\n" + "\n".join(f"• {p}/USDT" for p in CORE_PAIRS)
    )


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_capital_info()
    mode = os.getenv("BINANCE_TESTNET", "true")
    status_text = f"🤖 Bot Status\n\nMode: {'Testnet' if mode.lower() == 'true' else 'Mainnet'}"
    if info:
        status_text += f"\nBalance: {info['current_balance']:.2f} USDT\nPnL: {info['net_pnl']:+.2f}"
    await update.message.reply_text(status_text)


async def handle_fees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        total_fees = db.query(Trade.fee_total).filter(Trade.status == "CLOSED").all()
        fees_sum = sum(f[0] for f in total_fees) if total_fees else 0
        await update.message.reply_text(f"💸 Total Fees Paid: -{fees_sum:.2f} USDT")
    finally:
        db.close()
