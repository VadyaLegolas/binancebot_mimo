# Requirements: Binance Trading Bot v2.0

**Defined:** 2026-06-16
**Core Value:** Бот должен автоматически торговать на Binance с учётом комиссий, корректно считать PnL (нетто) и позволять пользователю управлять всем через Telegram.

## v1 Requirements

### Infrastructure

- [ ] **INFRA-01**: Проект имеет структуру src/ с подпакетами: core, strategies, indicators, telegram_bot, dashboard, database, learning
- [ ] **INFRA-02**: Docker + docker-compose для запуска всех сервисов
- [ ] **INFRA-03**: Конфигурация через .env (API ключи, Telegram токен) + config.yaml (параметры стратегий)
- [ ] **INFRA-04**: SQLite для разработки, PostgreSQL для продакшена, переключение через DATABASE_URL
- [ ] **INFRA-05**: Логирование через Loguru в файл и stdout

### Binance API

- [ ] **BNCA-01**: Клиент Binance API с поддержкой Testnet и Mainnet
- [ ] **BNCA-02**: WebSocket для получения рыночных данных в реальном времени
- [ ] **BNCA-03**: REST API для размещения и управления ордерами
- [ ] **BNCA-04**: Проверка MIN_NOTIONAL фильтра через API перед каждым ордером
- [ ] **BNCA-05**: Автоматическое переключение Testnet/Mainnet через Telegram команду

### Database

- [ ] **DB-01**: Таблица trades с полями: order_id, symbol (только base asset), side, type, strategy, quantity, price, total_usdt, fee_*, gross_pnl, net_pnl, net_pnl_pct, status
- [ ] **DB-02**: Таблица bot_session с starting_capital, started_at, mode, statistics
- [ ] **DB-03**: Таблица model_history для истории изменений параметров Learning Engine
- [ ] **DB-04**: Таблица alerts для уведомлений (trade, anomaly, learn, error)

### Capital Management

- [ ] **CAP-01**: Фиксация стартового капитала через /init <amount>
- [ ] **CAP-02**: Трёхзначное отслеживание: Starting Capital, Net PnL, Current Balance
- [ ] **CAP-03**: Блок капитала на дашборде: стартовый + нетто PnL + текущий баланс + открытые позиции + максимум + просадка

### Telegram Bot

- [ ] **TGB-01**: Команды торговли: /buy <монета> <сумма>, /sell <монета> <кол>, /sell_all <монета>
- [ ] **TGB-02**: Информационные команды: /balance, /positions, /stats, /pnl, /fees, /price <монета>
- [ ] **TGB-03**: Управление: /status, /strategy <auto|имя>, /pairs, /add_pair, /mode testnet|mainnet, /dashboard
- [ ] **TGB-04**: Команды Learning: /rl on|off|status, /learn stats|reset|retrain
- [ ] **TGB-05**: Уведомления о сделках, стоп-лосс, тейк-профит, аномалии

### Trading Strategies

- [ ] **STRAT-01**: Grid Trading — сетка лимитных ордеров, шаг мин. 0.5%, авто-расчёт из ATR
- [ ] **STRAT-02**: DCA — покупки при падении цены, take_profit_net 1.8%, stop_loss 12%
- [ ] **STRAT-03**: RSI+EMA — RSI oversold/overbought + EMA200 фильтр, take_profit_net 2.0%
- [ ] **STRAT-04**: Multi-Timeframe Momentum — совпадение сигналов на 4h+1h+15m, trailing stop
- [ ] **STRAT-05**: AutoSelector — автовыбор стратегии по ADX, RSI, волатильности

### Risk Management

- [ ] **RISK-01**: Максимум открытых позиций (7 по умолчанию)
- [ ] **RISK-02**: Дневной лимит убытков (5% от капитала)
- [ ] **RISK-03**: Минимальный USDT буфер (20 USDT резерв)
- [ ] **RISK-04**: Cooldown после стоп-лосс (15 минут)

### Web Dashboard

- [ ] **DASH-01**: Главная страница: блок капитала, метрики (Win Rate, Sharpe, Max DD), графики (баланс, PnL, комиссии)
- [ ] **DASH-02**: Страница позиций: таблица с монетой, количеством, ценой входа, текущей ценой, PnL%, стратегией
- [ ] **DASH-03**: Страница истории: фильтрация, пагинация, колонки с net PnL и комиссиями
- [ ] **DASH-04**: Страница стратегий: Net PnL, Win Rate, сделок, Sharpe, вес от Learning Engine
- [ ] **DASH-05**: Learning Dashboard: Parameter Tuner, Strategy Weights, RL Agent, Anomaly Log

### Learning Engine

- [ ] **LRN-01**: Parameter Tuner — Optuna оптимизация параметров каждые 50 сделок, Walk-Forward Validation
- [ ] **LRN-02**: Strategy Weighter — SGD онлайн-обучение весов каждые 4 часа, 7 признаков
- [ ] **LRN-03**: RL Agent — PPO через stable-baselines3, 11 признаков, 3 действия (HOLD/BUY/SELL)
- [ ] **LRN-04**: Anomaly Guard — откат при Win Rate < 40% за 20 сделок, стоп при drawdown > 8%
- [ ] **LRN-05**: Shadow mode по умолчанию, live через /rl on

### Pairs

- [ ] **PAIR-01**: Ядро (день 1): BTC, ETH, SOL
- [ ] **PAIR-02**: Расширение (после 50 сделок): BNB, XRP, ADA
- [ ] **PAIR-03**: DOGE только Grid, только после 100+ успешных сделок

## v2 Requirements

### Advanced Features

- **ADV-01**: Бэктестинг на исторических данных (backtesting.py / vectorbt)
- **ADV-02**: Экспорт истории сделок в CSV
- **ADV-03**: Inline-клавиатура Telegram для быстрых действий
- **ADV-04**: Ежедневный/еженедельный отчёт PnL в Telegram
- **ADV-05**: Аутентификация на дашборде (логин/пароль)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Маржинальная торговля | Только Spot по спеке |
| Мобильное приложение | Веб-дашборд, не требуется |
| Short позиции | Только Long на Spot |
| Автоматический вывод средств | Только торговля, вывод вручную |
| Мульти-биржа | Только Binance |
| Продвинутая аналитика (ML прогнозы цен) | Learning Engine оптимизирует стратегии, не прогнозирует цену |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Pending |
| INFRA-02 | Phase 1 | Pending |
| INFRA-03 | Phase 1 | Pending |
| INFRA-04 | Phase 1 | Pending |
| INFRA-05 | Phase 1 | Pending |
| BNCA-01 | Phase 1 | Pending |
| BNCA-02 | Phase 1 | Pending |
| BNCA-03 | Phase 1 | Pending |
| BNCA-04 | Phase 1 | Pending |
| BNCA-05 | Phase 1 | Pending |
| DB-01 | Phase 1 | Pending |
| DB-02 | Phase 1 | Pending |
| DB-03 | Phase 1 | Pending |
| DB-04 | Phase 1 | Pending |
| CAP-01 | Phase 1 | Pending |
| CAP-02 | Phase 1 | Pending |
| CAP-03 | Phase 1 | Pending |
| TGB-01 | Phase 1 | Pending |
| TGB-02 | Phase 1 | Pending |
| TGB-03 | Phase 1 | Pending |
| TGB-05 | Phase 1 | Pending |
| DASH-01 | Phase 1 | Pending |
| DASH-02 | Phase 1 | Pending |
| DASH-03 | Phase 1 | Pending |
| DASH-04 | Phase 1 | Pending |
| PAIR-01 | Phase 1 | Pending |
| STRAT-01 | Phase 2 | Pending |
| STRAT-02 | Phase 2 | Pending |
| STRAT-03 | Phase 2 | Pending |
| STRAT-04 | Phase 2 | Pending |
| STRAT-05 | Phase 2 | Pending |
| RISK-01 | Phase 2 | Pending |
| RISK-02 | Phase 2 | Pending |
| RISK-03 | Phase 2 | Pending |
| RISK-04 | Phase 2 | Pending |
| TGB-04 | Phase 3 | Pending |
| LRN-01 | Phase 3 | Pending |
| LRN-02 | Phase 3 | Pending |
| LRN-03 | Phase 3 | Pending |
| LRN-04 | Phase 3 | Pending |
| LRN-05 | Phase 3 | Pending |
| DASH-05 | Phase 3 | Pending |
| PAIR-02 | Phase 3 | Pending |
| PAIR-03 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 38 total
- Mapped to phases: 38
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-16*
*Last updated: 2026-06-16 after initial definition*
