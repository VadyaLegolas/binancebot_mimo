# Binance Trading Bot v2.0

## What This Is

Автономный самообучающийся торговый бот для Binance с управлением через Telegram и веб-дашбордом. Работает 24/7, автоматически выбирает и оптимизирует стратегии, обучается через Reinforcement Learning (PPO), обеспечивает полное ручное управление через Telegram-команды. Стартует на Testnet, опционально переходит на Mainnet.

## Core Value

Бот должен автоматически торговать на Binance с учётом комиссий, корректно считать PnL (нетто) и позволять пользователю управлять всем через Telegram.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Работа на Binance Testnet с возможностью переключения на Mainnet
- [ ] Telegram-бот с командами: /buy, /sell, /sell_all, /balance, /positions, /stats, /pnl, /init, и др.
- [ ] Веб-дашборд (Flask + Chart.js, localhost, без пароля) с блоком капитала и графиком баланса
- [ ] 4 торговые стратегии: Grid, DCA, RSI+EMA, Multi-Timeframe Momentum
- [ ] Автовыбор стратегии на основе рыночных условий (ADX, RSI, волатильность)
- [ ] Учёт комиссий (0.1% за сторону) во всех расчётах PnL — только нетто
- [ ] Система управления рисками (макс. позиции, дневной лимит убытков, стоп-лосс)
- [ ] SQLite (dev) / PostgreSQL (prod) с таблицами: trades, bot_session, model_history, alerts
- [ ] Learning Engine: Parameter Tuner (Optuna), Strategy Weighter (SGD), RL Agent (PPO)
- [ ] Anomaly Guard: откат параметров при деградации, стоп при drawdown > 8%
- [ ] Docker + docker-compose для деплоя
- [ ] Конфигурация через .env + YAML

### Out of Scope

- Торговля на Mainnet по умолчанию — Testnet优先, Mainnet опционально
- Мобильное приложение — веб-дашборд только
- Маржинальная/фьючерсная торговля — только Spot
- DOGE — только Grid, только после 100+ успешных сделок с основными парами
- OAuth/авторизация на дашборде — localhost/SSH только

## Context

- Python 3.11+, стек: python-binance, python-telegram-bot v20+, Flask, SQLAlchemy, pandas-ta, optuna, stable-baselines3
- Торговые пары: BTC, ETH, SOL (ядро, день 1); BNB, XRP, ADA (после 50+ сделок)
- Минимальная сделка: 10-15 USDT
- Стартовый капитал: 50-100 USDT (Testnet), 500-1000 USDT (Mainnet)
- Три уровня самообучения: параметры (Optuna), веса стратегий (SGD), RL (PPO)
- Фазы разработки из спеки: Основа → Стратегии → Learning Engine → Полировка

## Constraints

- **Tech Stack**: Python 3.11+, Binance API (python-binance/ccxt) — обосновано спекой
- **Капитал**: Минимум 50 USDT на Testnet — реалистичный порог для тестирования
- **Комиссии**: 0.1% за сторону, 0.2% за круг — все PnL нетто
- **Безопасность**: API ключи только в .env, никогда в коде
- **Dashboard**: Без аутентификации — только localhost/SSH

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| python-binance как основной API | Спецификация указывает, ccxt как fallback | — Pending |
| SQLite для dev, PostgreSQL для prod | Простота старта, масштабируемость | — Pending |
| Flask для дашборда (не Streamlit) | Гибкость, Chart.js для графиков | — Pending |
| 4 стратегии с автовыбором | Покрытие всех рыночных условий | — Pending |
| PPO для RL (stable-baselines3) | Спецификация, shadow→live режим | — Pending |
| v2 спека как авторитетная | v1 устарела, v2 включает Learning Engine | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-16 after initialization*
