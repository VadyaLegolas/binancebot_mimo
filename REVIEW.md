# Code Review Report

**Date**: 2026-06-16
**Scope**: 23 source files in `src/`
**Reviewed by**: MiMo Code Agent

---

## Critical

| # | File | Line | Issue | Suggested Fix |
|---|------|------|-------|---------------|
| C1 | `src/learning/strategy_weighter.py` | 35 | **Pickle deserialization of untrusted data.** `pickle.load()` executes arbitrary code. If `data/strategy_weighter.pkl` is tampered with (e.g. supply-chain attack, shared directory), it can run arbitrary Python. | Replace with `json` serialization + manual weight dict, or use `joblib` with hash verification. At minimum, validate file integrity before loading. |
| C2 | `src/learning/parameter_tuner.py` | 75-77 | **Walk-forward split is inverted.** `trades[split_idx:]` (newer trades) is used for *training* and `trades[:split_idx]` (older trades) for *testing*. This means the model is tested on historical data and trained on recent data — the exact opposite of walk-forward validation, defeating its purpose entirely. | Swap the assignment: `train_trades = trades[:split_idx]` (older), `test_trades = trades[split_idx:]` (newer). |
| C3 | `src/learning/trading_env.py` | 67 | **Look-ahead bias in RL environment.** SELL action evaluates PnL at `next_price` (step+1 close), not `current_price`. The agent sees the future price before deciding to sell, producing inflated training rewards that won't generalize to live trading. | Change line 67 to use `current_price` for sell evaluation: `sell_total = self._position * current_price`. |
| C4 | `src/strategies/manager.py` | 130-135 | **Dead code / unreachable sell branch.** The `elif action.price and action.quantity` branch is unreachable because `action.quantity` is already truthy in the preceding `if` condition. Limit sells can never be placed. | Restructure to check for limit orders first: `if action.price and action.quantity: ... elif action.quantity: ...` |
| C5 | `src/dashboard/routes.py` | 133-137 | **Unsanitized URL path parameter.** The `strategy` parameter in `/api/learning/history/<strategy>` is passed directly to `get_param_history()` which queries the DB. While SQLAlchemy parameterizes queries (no SQLi), the value is also returned in JSON responses — a stored XSS vector if the dashboard is rendered in a browser. | Sanitize: `strategy = strategy.strip()[:20]` and validate against allowed strategy names. |

## Warning

| # | File | Line | Issue | Suggested Fix |
|---|------|------|-------|---------------|
| W1 | `src/main.py` | 126-130 | **Flask blocks main thread.** `app.run()` is called in a daemon thread, but the main thread runs the Telegram bot. If Flask crashes, there's no recovery. The scheduler is also never cleanly shut down on Flask error. | Move Flask to a non-daemon thread, or use `waitress`/`gunicorn`. Add a try/except in `run_flask` to log and potentially restart. |
| W2 | `src/main.py` | 119-130 | **Flask runs with `host=0.0.0.0`.** The AGENTS.md explicitly says "no auth, localhost only" but `FLASK_HOST` defaults to `0.0.0.0`, exposing the dashboard to the network. | Default to `127.0.0.1` or add a warning if binding to `0.0.0.0` without auth. |
| W3 | `src/core/binance_client.py` | 42-44 | **Wrong MIN_NOTIONAL filter type.** Binance uses filter type `"MIN_NOTIONAL"` (not `"NOTIONAL"`). The `NOTIONAL` filter was deprecated. If the API returns `MIN_NOTIONAL`, `get_min_notional()` falls back to the hardcoded `10.0`, which may be wrong for some pairs. | Change filter type check to `"MIN_NOTIONAL"` (and handle both for backwards compatibility). |
| W4 | `src/strategies/manager.py` | 100 | **Price can be 0 for limit orders.** `order.get("price", action.price or 0)` returns `"0"` for limit orders not yet filled, then falls back to `get_price()` which gives market price — not the actual limit price. This records incorrect trade prices. | For limit orders, use `action.price` directly; for market orders, use the order's filled price. |
| W5 | `src/telegram_bot/handlers.py` | 502 | **`os.environ` mutation doesn't affect existing clients.** `/mode` sets `os.environ["BINANCE_TESTNET"]` and creates a new `BinanceClient`, but other components (scheduler, strategy manager) still reference the old client. | Update the shared `binance_client` reference in `bot_data` and ensure all subsystems use the same client instance. |
| W6 | `src/core/risk_manager.py` | 19 | **Thread safety of `_cooldown_until`.** The cooldown dict is mutated by the scheduler thread and read by Telegram handlers (different threads). No locking protects it. | Use `threading.Lock` around cooldown reads/writes, or use `threading.RLock`. |
| W7 | `src/strategies/grid.py` | 49-54 | **Unbounded API calls per tick.** `get_open_orders()` is called once per unfilled grid level per symbol per tick. With 10 grid levels and 3 symbols, that's 30 API calls per 5-minute tick — hitting Binance rate limits. | Cache open orders once per tick and pass the set into the grid logic. |
| W8 | `src/strategies/manager.py` | 105-125 | **DB session created inside try but not exception-safe.** If `db.commit()` fails, the `db.close()` in `finally` still runs but the trade is silently lost. The order was already placed on Binance — now there's a mismatch between exchange state and DB. | Add retry logic or at minimum log the commit failure with order details for manual reconciliation. |
| W9 | `src/learning/rl_agent.py` | 100 | **IndexError in `log_decision`.** If `action` is not in `[0, 1, 2]` (which shouldn't happen with Discrete(3) but is possible if predict returns unexpected values), `action_names[action]` raises `IndexError`. | Use `action_names[action] if action < len(action_names) else f"UNKNOWN({action})"`. |
| W10 | `src/learning/trading_env.py` | 155 | **Hardcoded dummy data on fetch failure.** Returns 1000 identical dummy klines with price=100, which will produce meaningless indicators and train the RL agent on garbage data. | Raise the exception or return a small dataset that triggers a proper reset/retry. |
| W11 | `src/strategies/auto_selector.py` | 41-42 | **Direct `self.binance.client.get_klines()` access.** Bypasses the `BinanceClient` wrapper, accessing the raw `python-binance` client directly. If the wrapper adds retry logic, caching, or error handling, this won't benefit. | Add a `get_klines()` method to `BinanceClient` and use it consistently. |
| W12 | `src/core/pair_manager.py` | 50-56 | **Redundant DB queries.** `get_status()` calls `_count_closed_trades()` and `_count_winning_trades()` twice each. | Cache the results in local variables before building the status dict. |

## Info

| # | File | Line | Issue | Suggested Fix |
|---|------|------|-------|---------------|
| I1 | `src/database/models.py` | 22-23 | **Mutable default `datetime.utcnow`.** Using `datetime.utcnow` as `default=` in `mapped_column` calls the function once at class definition time for all rows. SQLAlchemy's `default` should be a callable, but `datetime.utcnow` without `()` is a callable reference — this works, but is confusing and deprecated in Python 3.12+. | Use `datetime.now(timezone.utc)` or `func.now()` consistently. |
| I2 | `src/database/session.py` | 10-15 | **`get_db()` generator defined but never used.** The codebase manually creates `SessionLocal()` everywhere instead of using this generator. | Either use `get_db()` consistently (e.g. with FastAPI's `Depends`) or remove it to avoid confusion. |
| I3 | `src/learning/strategy_weighter.py` | 14 | **Pickle model stored in `data/` directory.** No `.gitignore` check — this file could be committed to the repo. | Add `data/*.pkl` to `.gitignore` if not already present. |
| I4 | `src/indicators/__init__.py` | 15 | **Division by zero in RSI.** When `avg_loss` is 0, `replace(0, np.nan)` produces NaN which propagates correctly. However, if ALL values have zero loss, RSI returns NaN for the entire series. | The existing NaN handling at call sites is adequate, but document this edge case. |
| I5 | `src/strategies/dca.py` | 97-98 | **Fee deducted from `amount_per_buy` before price check.** `qty = (amount_per_buy - fee) / price` means the actual USDT spent is slightly less than `amount_per_buy`. The `total_cost` in line 111 uses `self.amount_per_buy` (the full amount), inflating `avg_entry`. | Either track actual cost (amount_per_buy - fee) or adjust `total_cost` accordingly. |
| I6 | `src/telegram_bot/handlers.py` | 447 | **IndexError if `/learn history` called with no args.** `context.args[1]` is accessed without checking `len(context.args) > 1` first. | Already guarded by `if len(context.args) > 1` on line 447 — this is correct. (No fix needed, noting for completeness.) |
| I7 | `src/core/capital.py` | 59-78 | **`update_drawdown_stats()` queries ALL closed trades.** As trade history grows, this becomes O(n) on every call. | Filter by `BotSession.id` to only sum trades for the current session. |
| I8 | `src/learning/parameter_tuner.py` | 92-93 | **Division by zero guard for `current_sharpe`.** When `current_sharpe` is 0, the improvement is calculated as `best_sharpe * 100`, which could produce misleadingly large values if `best_sharpe` is small but non-zero. | Treat any zero baseline as "infinite improvement" only if best_sharpe > 0, else skip. |

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 5 |
| Warning | 12 |
| Info | 8 |
| **Total** | **25** |

**Top 3 priorities to fix:**
1. **C2** (inverted walk-forward split) — directly invalidates the learning engine's optimization
2. **C3** (RL look-ahead bias) — the RL agent trains on impossible information
3. **C1** (pickle deserialization) — security vulnerability if model files are tampered with
