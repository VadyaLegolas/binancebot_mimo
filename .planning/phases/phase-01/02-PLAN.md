---
wave: 2
depends_on:
  - 01-PLAN.md
files_modified:
  - src/telegram_bot/app.py
  - src/telegram_bot/handlers.py
  - src/core/constants.py
requirements_addressed:
  - TGB-01
  - TGB-02
  - TGB-03
  - TGB-05
  - CAP-01
  - CAP-02
  - BNCA-05
autonomous: true
---

# Plan 2: Telegram Bot with All Commands

<objective>
Build the full Telegram bot with python-telegram-bot v22.8 (async). All trade commands (/buy, /sell, /sell_all), info commands (/balance, /positions, /stats, /pnl, /fees, /price), management commands (/status, /pairs, /mode, /dashboard), and notifications. Capital initialization via /init. By end of this plan: sending /init 100 then /buy BTC 15 in Telegram creates a trade in SQLite and replies with confirmation.
</objective>

<tasks>

## Task 2.1: Telegram bot application setup

<read_first>
  - .planning/phases/phase-01/01-RESEARCH.md (Telegram Bot Setup, Common Pitfalls sections)
  - binance_bot_spec_v2.md §12 (Telegram commands)
  - .planning/REQUIREMENTS.md (TGB-01, TGB-02, TGB-03)
</read_first>

<action>
1. Create `src/telegram_bot/app.py`:
   ```python
   from telegram.ext import Application, CommandHandler, ContextTypes
   from loguru import logger

   def create_app(token: str, binance_client) -> Application:
       from src.telegram_bot.handlers import (
           handle_init, handle_buy, handle_sell, handle_sell_all,
           handle_balance, handle_positions, handle_stats, handle_pnl,
           handle_fees, handle_price, handle_status, handle_pairs,
           handle_mode, handle_dashboard, handle_start, handle_help,
       )

       app = Application.builder().token(token).build()

       # Store binance client in bot_data for handlers to access
       app.bot_data["binance"] = binance_client

       # Trade commands
       app.add_handler(CommandHandler("init", handle_init))
       app.add_handler(CommandHandler("buy", handle_buy))
       app.add_handler(CommandHandler("sell", handle_sell))
       app.add_handler(CommandHandler("sell_all", handle_sell_all))

       # Info commands
       app.add_handler(CommandHandler("balance", handle_balance))
       app.add_handler(CommandHandler("positions", handle_positions))
       app.add_handler(CommandHandler("stats", handle_stats))
       app.add_handler(CommandHandler("pnl", handle_pnl))
       app.add_handler(CommandHandler("fees", handle_fees))
       app.add_handler(CommandHandler("price", handle_price))

       # Management commands
       app.add_handler(CommandHandler("status", handle_status))
       app.add_handler(CommandHandler("pairs", handle_pairs))
       app.add_handler(CommandHandler("mode", handle_mode))
       app.add_handler(CommandHandler("dashboard", handle_dashboard))

       # General
       app.add_handler(CommandHandler("start", handle_start))
       app.add_handler(CommandHandler("help", handle_help))

       logger.info("Telegram bot initialized with all handlers")
       return app
   ```

2. Store `binance_client` in `app.bot_data` so handlers access it via `context.application.bot_data["binance"]`.
</action>

<acceptance_criteria>
- [ ] `create_app("fake_token", mock_client)` returns an Application with all handlers registered
- [ ] No import errors in telegram_bot package
- [ ] All 16 command handlers are registered
</acceptance_criteria>

## Task 2.2: Core trade handlers (/buy, /sell, /sell_all, /init)

<read_first>
  - binance_bot_spec_v2.md §12.1, §12.2 (init, trade commands)
  - .planning/phases/phase-01/01-RESEARCH.md (Telegram Pitfalls — async handlers, context.args)
  - src/core/capital.py (init_capital, calc_pnl)
  - src/core/binance_client.py (place_market_buy, place_market_sell)
  - src/database/models.py (Trade model)
</read_first>

<action>
1. Create `src/telegram_bot/handlers.py` with all handlers as `async def`:

   **handle_init** — `/init <amount>`:
   ```python
   async def handle_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
       if not context.args:
           await update.message.reply_text("Usage: /init <amount_usdt>")
           return
       try:
           amount = float(context.args[0])
       except ValueError:
           await update.message.reply_text("Amount must be a number")
           return
       from src.core.capital import init_capital
       session = init_capital(amount)
       await update.message.reply_text(
           f"Starting capital: {amount:.2f} USDT\n"
           f"Mode: {session.mode}\n"
           f"Trading ready."
       )
   ```

   **handle_buy** — `/buy <coin> <amount_usdt>`:
   - Validate 2 args, coin in CORE_PAIRS
   - Check MIN_NOTIONAL via binance_client.get_min_notional()
   - Check balance via binance_client.get_balance()
   - Place market buy via binance_client.place_market_buy()
   - Record Trade in DB with status="OPEN", fee_buy=total*0.001, opened_at=now()
   - Reply: order confirmation with quantity, price, fee
   - Handle BinanceAPIException and insufficient balance

   **handle_sell** — `/sell <coin> <quantity>`:
   - Validate 2 args, find OPEN trade for this coin
   - Place market sell via binance_client.place_market_sell()
   - Calculate PnL using calc_pnl()
   - Update Trade: status="CLOSED", closed_at=now(), set all PnL/fee fields
   - Reply: trade result with net_pnl

   **handle_sell_all** — `/sell_all <coin>`:
   - Find all OPEN trades for this coin, sum quantities
   - Sell total quantity
   - Close all matched trades

2. All handlers MUST be `async def` (python-telegram-bot v20+ requirement).
3. All handlers use `await update.message.reply_text()` (not sync send_message).
4. Parse args from `context.args` (list of strings).
</action>

<acceptance_criteria>
- [ ] `/init 100` creates BotSession with starting_capital=100.0
- [ ] `/buy BTC 15` places order on Testnet and records Trade with status="OPEN"
- [ ] `/buy BTC 15` checks MIN_NOTIONAL before placing order
- [ ] `/sell BTC 0.0003` closes the OPEN trade, calculates net_pnl with fees
- [ ] `/sell_all BTC` sells all open BTC quantity
- [ ] All handlers reply with formatted text (not raw dicts)
- [ ] BinanceAPIException is caught and user-friendly error is sent
- [ ] Insufficient balance sends clear error message
</acceptance_criteria>

## Task 2.3: Info handlers (/balance, /positions, /stats, /pnl, /fees, /price)

<read_first>
  - binance_bot_spec_v2.md §12.3 (info commands), §9.2 (capital calculation)
  - src/core/capital.py (get_capital_info)
  - src/database/models.py (Trade, BotSession)
  - src/core/binance_client.py (get_balance, get_price)
</read_first>

<action>
1. **handle_balance** — `/balance`:
   ```python
   async def handle_balance(update, context):
       binance = context.application.bot_data["binance"]
       usdt = binance.get_balance("USDT")
       await update.message.reply_text(f"USDT Balance: {usdt:.2f}")
   ```

2. **handle_positions** — `/positions`:
   - Query DB for all OPEN trades
   - For each: get current price, calculate unrealized PnL
   - Format as table: symbol, quantity, entry_price, current_price, PnL%
   - If no positions: "No open positions"

3. **handle_stats** — `/stats`:
   - Total trades (CLOSED), win count, win rate
   - Total net_pnl, total fees
   - Max drawdown from BotSession
   - Format per spec §12.6 notification format

4. **handle_pnl** — `/pnl`:
   - Get capital info via get_capital_info()
   - Show starting_capital, net_pnl (with %), current_balance
   - ROI percentage

5. **handle_fees** — `/fees`:
   - Sum all fee_total from CLOSED trades
   - Show total fees paid

6. **handle_price** — `/price <coin>`:
   - Get price via binance_client.get_price(coin)
   - Reply: f"{coin}: {price:.2f} USDT"
</action>

<acceptance_criteria>
- [ ] `/balance` shows USDT balance from Binance
- [ ] `/positions` lists all OPEN trades with unrealized PnL
- [ ] `/stats` shows total trades, win rate, net PnL, fees
- [ ] `/pnl` shows three-value capital tracking (starting, net_pnl, balance)
- [ ] `/fees` shows total fees paid across all closed trades
- [ ] `/price BTC` shows current BTC price in USDT
- [ ] Empty positions/stats show friendly "no data" messages
</acceptance_criteria>

## Task 2.4: Management handlers (/status, /pairs, /mode, /dashboard)

<read_first>
  - binance_bot_spec_v2.md §12.4 (management commands)
  - src/core/constants.py (CORE_PAIRS)
  - src/core/binance_client.py (testnet flag)
</read_first>

<action>
1. **handle_status** — `/status`:
   - Show bot mode (testnet/mainnet), active strategy (None in Phase 1), uptime

2. **handle_pairs** — `/pairs`:
   - Show CORE_PAIRS list: "Active pairs: BTC, ETH, SOL"

3. **handle_mode** — `/mode testnet|mainnet`:
   - Validate arg is "testnet" or "mainnet"
   - Update BotSession.mode in DB
   - Recreate BinanceClient with new testnet flag:
     ```python
     new_testnet = context.args[0] == "testnet"
     from src.core.binance_client import BinanceClient
     new_client = BinanceClient(
         os.getenv("BINANCE_API_KEY"),
         os.getenv("BINANCE_API_SECRET"),
         testnet=new_testnet,
     )
     context.application.bot_data["binance"] = new_client
     ```
   - Reply with confirmation: f"Mode switched to {mode}. BinanceClient recreated."

4. **handle_dashboard** — `/dashboard`:
   - Reply with dashboard URL: "Dashboard: http://localhost:5000"

5. **handle_start** — `/start`:
   - Welcome message with available commands list

6. **handle_help** — `/help`:
   - Full command reference grouped by category
</action>

<acceptance_criteria>
- [ ] `/status` shows current mode and bot state
- [ ] `/pairs` lists BTC, ETH, SOL
- [ ] `/mode testnet` updates BotSession mode AND recreates BinanceClient with testnet=True
- [ ] `/dashboard` returns localhost URL
- [ ] `/start` and `/help` show command reference
</acceptance_criteria>

## Task 2.5: Notifications (TGB-05)

<read_first>
  - binance_bot_spec_v2.md §12.6 (notification format)
  - src/database/models.py (Alert model)
  - src/telegram_bot/app.py (Application instance)
</read_first>

<action>
1. Create notification helper in handlers.py:
   ```python
   async def send_notification(context: ContextTypes.DEFAULT_TYPE, message: str, alert_type: str = "trade"):
       from src.database.session import SessionLocal
       from src.database.models import Alert
       from datetime import datetime

       # Save to DB
       db = SessionLocal()
       try:
           alert = Alert(type=alert_type, message=message, sent=False, created_at=datetime.utcnow())
           db.add(alert)
           db.commit()
       finally:
           db.close()

       # Send via Telegram
       chat_id = os.getenv("TELEGRAM_CHAT_ID")
       if chat_id:
           await context.bot.send_message(chat_id=int(chat_id), text=message)
   ```

2. Call send_notification after:
   - Successful trade execution (buy/sell)
   - Stop-loss triggered (Phase 2)
   - Anomaly detected (Phase 3)
</action>

<acceptance_criteria>
- [ ] `send_notification(context, "test message")` saves Alert to DB
- [ ] `send_notification` sends message to TELEGRAM_CHAT_ID
- [ ] Alert record has correct type and sent=False initially
</acceptance_criteria>

</tasks>

<must_haves>
- All 16 Telegram commands implemented as async handlers
- /init creates BotSession, /buy places order and records Trade, /sell closes trade with PnL
- /mode testnet|mainnet updates DB AND recreates BinanceClient with correct testnet flag (BNCA-05)
- All PnL calculations include 0.1% fees per side
- MIN_NOTIONAL checked before every order
- All handlers use async def + await (not sync)
- Notifications saved to alerts table and sent via Telegram
- Error handling: BinanceAPIException caught, user-friendly messages
</must_haves>

## Artifacts this phase produces

- `src/telegram_bot/app.py` — Application factory with all handlers
- `src/telegram_bot/handlers.py` — 16 command handlers + notification helper
