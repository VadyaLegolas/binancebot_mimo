---
wave: 2
depends_on:
  - 01-PLAN.md
files_modified:
  - src/dashboard/app.py
  - src/dashboard/routes.py
  - src/dashboard/templates/index.html
requirements_addressed:
  - DASH-01
  - DASH-02
  - DASH-03
  - DASH-04
  - CAP-03
autonomous: true
---

# Plan 3: Flask Dashboard

<objective>
Build the Flask web dashboard with capital block, performance metrics, balance chart (Chart.js), positions page, history page, and strategies page. By end of this plan: `http://localhost:5000` shows the capital block with starting capital/net PnL/current balance, and the JSON API serves capital data.
</objective>

<tasks>

## Task 3.1: Flask app factory and routes

<read_first>
  - .planning/phases/phase-01/01-RESEARCH.md (Flask Dashboard section, JSON API pattern)
  - binance_bot_spec_v2.md §13 (Dashboard spec)
  - .planning/REQUIREMENTS.md (DASH-01, DASH-02, DASH-03, DASH-04, CAP-03)
</read_first>

<action>
1. Create `src/dashboard/app.py`:
   ```python
   from flask import Flask
   from loguru import logger

   def create_app() -> Flask:
       app = Flask(__name__, template_folder="templates")
       app.config["TEMPLATES_AUTO_RELOAD"] = True

       from src.dashboard.routes import bp
       app.register_blueprint(bp)

       logger.info("Flask dashboard created")
       return app
   ```

2. Create `src/dashboard/routes.py` with Blueprint:
   ```python
   from flask import Blueprint, render_template, jsonify
   from src.core.capital import get_capital_info
   from src.database.session import SessionLocal
   from src.database.models import Trade, BotSession
   from sqlalchemy import func

   bp = Blueprint("dashboard", __name__)

   @bp.route("/")
   def index():
       return render_template("index.html")

   @bp.route("/health")
   def health():
       return jsonify({"status": "ok"})

   @bp.route("/api/capital")
   def api_capital():
       info = get_capital_info()
       if not info:
           return jsonify({"error": "No session found. Run /init first."}), 404
       return jsonify(info)

   @bp.route("/api/trades")
   def api_trades():
       db = SessionLocal()
       try:
           trades = db.query(Trade).order_by(-Trade.created_at).limit(100).all()
           return jsonify([{
               "id": t.id, "symbol": t.symbol, "side": t.side,
               "price": t.price, "quantity": t.quantity,
               "net_pnl": t.net_pnl, "fee_total": t.fee_total,
               "status": t.status, "strategy": t.strategy,
               "opened_at": str(t.opened_at), "closed_at": str(t.closed_at),
           } for t in trades])
       finally:
           db.close()

   @bp.route("/api/positions")
   def api_positions():
       db = SessionLocal()
       try:
           trades = db.query(Trade).filter(Trade.status == "OPEN").all()
           return jsonify([{
               "symbol": t.symbol, "quantity": t.quantity,
               "entry_price": t.price, "side": t.side,
               "strategy": t.strategy, "opened_at": str(t.opened_at),
           } for t in trades])
       finally:
           db.close()

   @bp.route("/api/strategies")
   def api_strategies():
       db = SessionLocal()
       try:
           stats = db.query(
               Trade.strategy,
               func.count(Trade.id).label("trades"),
               func.sum(Trade.net_pnl).label("net_pnl"),
               func.sum(Trade.fee_total).label("fees"),
           ).filter(Trade.status == "CLOSED").group_by(Trade.strategy).all()
           return jsonify([{
               "strategy": s.strategy or "manual",
               "trades": s.trades, "net_pnl": s.net_pnl or 0,
               "fees": s.fees or 0,
           } for s in stats])
       finally:
           db.close()
   ```

3. Flask uses per-request sessions via `SessionLocal()` (not Flask-SQLAlchemy's db.session).
</action>

<acceptance_criteria>
- [ ] `create_app()` returns a Flask app with / blueprint registered
- [ ] `GET /` returns HTML
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `GET /api/capital` returns JSON with starting_capital, net_pnl, current_balance
- [ ] `GET /api/trades` returns JSON array of trades (max 100)
- [ ] `GET /api/positions` returns only OPEN trades
- [ ] `GET /api/strategies` returns aggregated stats per strategy
- [ ] No Flask-SQLAlchemy db.session used (only SessionLocal)
</acceptance_criteria>

## Task 3.2: Dashboard HTML template with Chart.js

<read_first>
  - binance_bot_spec_v2.md §13.1 (capital block), §13.2 (charts)
  - .planning/phases/phase-01/01-RESEARCH.md (Chart.js CDN, Flask template section)
</read_first>

<action>
1. Create `src/dashboard/templates/index.html`:
   - Use Chart.js from CDN: `https://cdn.jsdelivr.net/npm/chart.js`
   - Responsive layout with cards/sections

2. **Capital Block** (per spec §13.1):
   ```
   ┌─────────────────────────────────────────┐
   │        CAPITAL & STATISTICS              │
   ├─────────────────────────────────────────┤
   │  Starting Capital      100.00 USDT      │
   │  Net PnL (realized)    +13.67 USDT      │
   │  Current Balance       113.67 USDT      │
   │  Open Positions        +8.34 USDT       │
   │  Total (with open)     122.01 USDT      │
   │  Max Balance           121.55 USDT      │
   │  Drawdown              1.20%            │
   │  ROI                   +22.01%          │
   └─────────────────────────────────────────┘
   ```

3. **Metrics Bar** (per spec §13.1):
   ```
   Win Rate: 52% | Sharpe: 1.43 | Max DD: 4.2% | Trades: 28
   ```

4. **Chart.js Balance Chart**:
   - Fetch `/api/trades` on load
   - Plot balance over time (starting_capital + cumulative net_pnl)
   - Line chart with max balance dashed line

5. Fetch `/api/capital` on page load, populate capital block with JS:
   ```javascript
   fetch("/api/capital")
       .then(r => r.json())
       .then(data => {
           document.getElementById("starting-capital").textContent = data.starting_capital.toFixed(2) + " USDT";
           // ... populate all fields
       });
   ```

6. All monetary values display with 2 decimal places and "USDT" suffix.
</action>

<acceptance_criteria>
- [ ] Page loads without console errors
- [ ] Capital block shows all 8 values from spec §13.1
- [ ] Chart.js renders (even with empty data — graceful fallback)
- [ ] All values fetch from /api/capital and /api/trades
- [ ] Page is responsive (works on localhost)
- [ ] No hardcoded values — all from API
</acceptance_criteria>

## Task 3.3: Dashboard integration with main.py

<read_first>
  - src/main.py (current entry point)
  - .planning/phases/phase-01/01-RESEARCH.md (Main Entry Point — Flask thread)
</read_first>

<action>
1. Update `src/main.py` to start Flask in background thread:
   ```python
   def run_flask():
       from src.dashboard.app import create_app
       app = create_app()
       app.run(
           host=os.getenv("FLASK_HOST", "0.0.0.0"),
           port=int(os.getenv("FLASK_PORT", "5000")),
           use_reloader=False,
       )

   # In main():
   flask_thread = threading.Thread(target=run_flask, daemon=True)
   flask_thread.start()
   logger.info("Flask dashboard started on port 5000")
   ```

2. Flask runs as daemon thread — dies when main process exits.
3. Use `use_reloader=False` to prevent Flask from spawning extra processes.
</action>

<acceptance_criteria>
- [ ] `python src/main.py` starts Flask on port 5000
- [ ] `curl http://localhost:5000/` returns HTML
- [ ] `curl http://localhost:5000/health` returns `{"status": "ok"}`
- [ ] `curl http://localhost:5000/api/capital` returns JSON (404 if no session)
- [ ] Flask thread is daemon (dies with main process)
</acceptance_criteria>

</tasks>

<must_haves>
- Flask app serves on port 5000
- Capital block displays all spec §13.1 values
- Chart.js renders balance chart from trade data
- JSON API endpoints: /api/capital, /api/trades, /api/positions, /api/strategies
- Health endpoint: /health
- Flask runs in daemon thread, does not block Telegram bot
- All values from database, no hardcoded data
</must_haves>

## Artifacts this phase produces

- `src/dashboard/app.py` — Flask app factory
- `src/dashboard/routes.py` — Blueprint with all routes
- `src/dashboard/templates/index.html` — Dashboard HTML with Chart.js
