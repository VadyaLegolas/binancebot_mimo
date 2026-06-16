---
wave: 3
depends_on:
  - 01-PLAN.md
  - 02-PLAN.md
  - 03-PLAN.md
files_modified:
  - Dockerfile
  - docker-compose.yml
  - .dockerignore
  - src/main.py
requirements_addressed:
  - INFRA-02
autonomous: true
---

# Plan 4: Docker + Final Integration

<objective>
Create Docker and docker-compose configuration, wire all subsystems together in main.py, and run a full integration smoke test. By end of this plan: `docker-compose up` starts the complete bot (Telegram + Binance + Flask + SQLite) in a single container.
</objective>

<tasks>

## Task 4.1: Docker and docker-compose configuration

<read_first>
  - .planning/phases/phase-01/01-RESEARCH.md (Docker section)
  - .planning/REQUIREMENTS.md (INFRA-02)
</read_first>

<action>
1. Create `Dockerfile`:
   ```dockerfile
   FROM python:3.11-slim

   WORKDIR /app

   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   COPY . .

   RUN mkdir -p /app/data /app/logs

   EXPOSE 5000

   CMD ["python", "src/main.py"]
   ```

2. Create `docker-compose.yml`:
   ```yaml
   services:
     bot:
       build: .
       env_file: .env
       volumes:
         - ./data:/app/data
       ports:
         - "5000:5000"
       restart: unless-stopped
   ```

3. Create `.dockerignore`:
   ```
   .git
   .env
   __pycache__
   *.pyc
   .planning
   data/
   logs/
   *.db
   .venv
   ```

4. Build and verify:
   ```bash
   docker-compose build
   docker-compose up -d
   docker-compose logs bot | head -20
   curl http://localhost:5000/health
   docker-compose down
   ```
</action>

<acceptance_criteria>
- [ ] `docker-compose build` succeeds
- [ ] `docker-compose up` starts the container
- [ ] Container logs show "Starting Binance Trading Bot..."
- [ ] `curl http://localhost:5000/health` returns `{"status": "ok"}`
- [ ] Data volume mounted at `/app/data` persists SQLite database
- [ ] `.env` file loaded via `env_file` (not `environment:`)
- [ ] Container restarts automatically on failure (`restart: unless-stopped`)
</acceptance_criteria>

## Task 4.2: Wire all subsystems in main.py

<read_first>
  - src/main.py (current skeleton)
  - src/telegram_bot/app.py (create_app)
  - src/core/binance_client.py (BinanceClient)
  - src/database/migrations.py (run_migrations)
</read_first>

<action>
1. Finalize `src/main.py` to wire ALL subsystems:
   ```python
   import os
   import sys
   import threading
   from loguru import logger
   from dotenv import load_dotenv

   load_dotenv()

   logger.remove()
   logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))
   logger.add("logs/bot.log", rotation="10 MB", retention="7 days", level="DEBUG")

   def run_flask():
       from src.dashboard.app import create_app
       app = create_app()
       app.run(
           host=os.getenv("FLASK_HOST", "0.0.0.0"),
           port=int(os.getenv("FLASK_PORT", "5000")),
           use_reloader=False,
       )

   def main():
       logger.info("Starting Binance Trading Bot...")

       # 1. Database migrations
       from src.database.migrations import run_migrations
       run_migrations()
       logger.info("Database ready")

       # 2. Binance client
       from src.core.binance_client import BinanceClient
       binance = BinanceClient(
           os.getenv("BINANCE_API_KEY"),
           os.getenv("BINANCE_API_SECRET"),
           testnet=os.getenv("BINANCE_TESTNET", "true") == "true",
       )
       logger.info(f"Binance client initialized (testnet={binance.testnet})")

       # 3. Flask dashboard (background thread)
       flask_thread = threading.Thread(target=run_flask, daemon=True)
       flask_thread.start()
       logger.info("Flask dashboard started on port 5000")

       # 4. Telegram bot (blocks — runs asyncio loop)
       from src.telegram_bot.app import create_app
       tg_app = create_app(
           token=os.getenv("TELEGRAM_BOT_TOKEN"),
           binance_client=binance,
       )
       logger.info("Telegram bot starting...")
       tg_app.run_polling()  # Blocks here

   if __name__ == "__main__":
       main()
   ```

2. Order of initialization matters:
   - DB migrations first (tables must exist before anything else)
   - Binance client second (needed by Telegram handlers)
   - Flask third (background, independent)
   - Telegram last (blocks, owns the main thread)
</action>

<acceptance_criteria>
- [ ] `python src/main.py` initializes all 4 subsystems in order
- [ ] DB migrations run before any Binance/Telegram/Flask code
- [ ] Flask starts in daemon thread, does not block Telegram
- [ ] Telegram bot connects and starts polling
- [ ] All subsystems share the same BinanceClient instance
- [ ] Graceful shutdown: Ctrl+C stops all threads
</acceptance_criteria>

## Task 4.3: Full integration smoke test

<read_first>
  - All plan files (01-PLAN.md through 04-PLAN.md)
  - .planning/REQUIREMENTS.md (all Phase 1 requirements)
  - binance_bot_spec_v2.md (success criteria)
</read_first>

<action>
Run full integration smoke test:

1. **Binance connection** (requires real API keys in .env):
   ```bash
   python -c "
   from src.core.binance_client import BinanceClient
   import os
   from dotenv import load_dotenv
   load_dotenv()
   c = BinanceClient(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_API_SECRET'), testnet=True)
   print('Balance:', c.get_balance('USDT'))
   print('BTC Price:', c.get_price('BTC'))
   print('Min Notional:', c.get_min_notional('BTC'))
   "
   ```

2. **Database**:
   ```bash
   python -c "
   from src.database.migrations import run_migrations
   from src.database.session import engine
   run_migrations()
   from sqlalchemy import inspect
   tables = inspect(engine).get_table_names()
   print('Tables:', tables)
   assert 'trades' in tables
   assert 'bot_session' in tables
   assert 'model_history' in tables
   assert 'alerts' in tables
   print('All tables created!')
   "
   ```

3. **Capital tracking**:
   ```bash
   python -c "
   from src.core.capital import init_capital, get_capital_info, calc_pnl
   init_capital(100.0, 'testnet')
   info = get_capital_info()
   assert info['starting_capital'] == 100.0
   assert info['net_pnl'] == 0.0
   assert info['current_balance'] == 100.0
   pnl = calc_pnl(100, 105, 0.15)
   assert pnl['fee_buy'] > 0
   assert pnl['net_pnl'] > 0
   print('Capital tracking works!')
   "
   ```

4. **Telegram commands** (manual test):
   - `/start` → welcome message
   - `/help` → command list
   - `/init 100` → "Starting capital: 100.00 USDT"
   - `/balance` → USDT balance from Binance
   - `/price BTC` → current BTC price
   - `/buy BTC 15` → order placed, trade recorded
   - `/positions` → shows open position
   - `/sell BTC <qty>` → closes position, shows PnL
   - `/stats` → trade statistics

5. **Dashboard**:
   - `curl http://localhost:5000/` → HTML page
   - `curl http://localhost:5000/api/capital` → JSON with capital info
   - `curl http://localhost:5000/api/trades` → JSON array

6. **Docker**:
   ```bash
   docker-compose build && docker-compose up -d
   docker-compose logs bot | grep "Starting"
   curl http://localhost:5000/health
   docker-compose down
   ```

7. **Verify NO ML deps**:
   ```bash
   python -c "import pandas_ta" 2>&1 | grep "ModuleNotFoundError"
   python -c "import optuna" 2>&1 | grep "ModuleNotFoundError"
   python -c "import stable_baselines3" 2>&1 | grep "ModuleNotFoundError"
   ```
</action>

<acceptance_criteria>
- [ ] Binance Testnet connection works (balance, price, min_notional)
- [ ] All 4 SQLite tables created
- [ ] Capital init + info + PnL calculation correct
- [ ] All Telegram commands respond correctly
- [ ] Dashboard serves HTML and JSON API
- [ ] Docker-compose builds and runs successfully
- [ ] No ML dependencies installed (pandas-ta, optuna, stable-baselines3 all fail to import)
- [ ] All Phase 1 success criteria met (see ROADMAP.md §Phase 1)
</acceptance_criteria>

</tasks>

<must_haves>
- Dockerfile builds successfully
- docker-compose.yml mounts .env and data volume
- main.py wires all 4 subsystems in correct order
- Flask runs in daemon thread
- All Phase 1 success criteria verified
- No ML/strategy dependencies installed
</must_haves>

## Artifacts this phase produces

- `Dockerfile` — Python 3.11-slim, pip install, run main.py
- `docker-compose.yml` — single service with .env and data volume
- `.dockerignore` — excludes .env, __pycache__, .planning
- Finalized `src/main.py` — all subsystems wired together
