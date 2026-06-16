# 🤖 Binance Trading Bot — Техническая Спецификация v2.0
**Версия:** 2.0 | **Дата:** Июнь 2026 | **Среда:** Binance Testnet → Mainnet

---

## 1. Обзор проекта

### 1.1 Цели
Разработать автономного самообучающегося торгового бота для Binance с управлением через Telegram и веб-дашбордом. Бот работает 24/7, автоматически выбирает и оптимизирует торговые стратегии на основе накопленного опыта сделок, обучается через Reinforcement Learning (PPO), и обеспечивает полное ручное управление через Telegram-команды.

### 1.2 Ключевые требования
- **Запуск на минимальном капитале:** 50–100 USDT (тест на Testnet)
- **Рекомендуемые пары:** BTC, ETH, SOL, BNB, XRP, ADA (ядро + стабильные альты)
- **Работа на Binance Testnet** (с возможностью переключения на Mainnet)
- **Управление через Telegram:** короткие команды без USDT (`/buy BTC 15`)
- **Открытый веб-дашборд** (без пароля, только localhost/SSH)
- **Визуализация капитала:** стартовый + PnL + текущий баланс
- **Учёт комиссий** (0.1%) в каждой сделке, PnL только нетто
- **Автовыбор стратегии** на основе рыночных условий (ADX, RSI, волатильность)
- **Самообучение в реальном времени:**
  - Параметры стратегий оптимизируются через Optuna (каждые 50 сделок)
  - Веса стратегий адаптируются через SGD онлайн-обучение (каждые 4 часа)
  - RL-агент (PPO, stable-baselines3) обучается в shadow-режиме, затем в live
- **Минимальная сумма сделки:** 10–15 USDT (реально прибыльный порог)
- **Система управления рисками** с аномалией гардом

---

## 3. Рекомендуемые пары для торговли (2026)

### 3.0 Выбор пар: критерии

Для успешной торговли на минимальном капитале (50–100 USDT) с минимальными сделками (10–15 USDT) нужны пары с:
- **Высокой ликвидностью** (узкий спред, быстрое исполнение)
- **Умеренной волатильностью** (не < 1%, не > 10% за 24h)
- **Минимальной суммой ордера** не более 5 USDT
- **Поддержкой на Binance Testnet** и Mainnet

Bitcoin (BTC) лидирует с $47.56B дневного объёма, Ethereum (ETH) второй с $3.38B, Solana (SOL) — $329.88M. BNB производит чистое range-bound движение, подходящее для mean-reversion сетки. XRP демонстрирует взрывную волатильность со спайками особенно вокруг новостей и регуляторных событий.

### 3.1 Ядро: Топ-3 пары (обязательно)

| # | Пара | Объём 24h | Волатильность | Мин. ордер | Стратегии | Рейтинг |
|---|------|----------|---------------|-----------|-----------|---------|
| 1 | **BTC/USDT** | $47.56B | 2–4% | 10 USDT | Grid, RSI+EMA | ⭐⭐⭐⭐⭐ |
| 2 | **ETH/USDT** | $3.38B | 2–5% | 10 USDT | Grid, DCA, RSI+EMA | ⭐⭐⭐⭐⭐ |
| 3 | **SOL/USDT** | $329.88M | 3–7% | 5 USDT | Grid, MTF Momentum | ⭐⭐⭐⭐⭐ |

**Описание:**
- **BTC:** Стабильный король. Самая глубокая ликвидность, минимальный спред (0.01–0.05%). Идеален для начинающих, работает на любой стратегии.
- **ETH:** Тесно следует за BTC. Достаточно волатилен для Grid (2–5%), стабилен для DCA. Вторая по объёму пара.
- **SOL:** Высокий бета (1.3–1.8x к BTC). Быстрые движения, идеален для MTF и RSI+EMA. Популярна за скорость и активность.

**Когда начать:** День 1. На эти три пары приходится 70% рекомендуемой торговли.

---

### 3.2 Плюс: Стабильные альты (добавить 2–3 пары после 50 сделок)

| # | Пара | Объём | Волатильность | Мин. ордер | Стратегия | Комментарий |
|---|------|--------|---------------|-----------|-----------|-----------|
| 4 | **BNB/USDT** | Высокий | 2–4% | 5 USDT | Grid, Range | Связана с экосистемой Binance, чистое range-bound движение. Fee скидка 0.075% vs 0.1% — плюс для частых трейдов |
| 5 | **XRP/USDT** | Высокий | 3–8% | 5 USDT | Grid, DCA, Breakout | Хорошая ликвидность, стабильные диапазоны для grid, вспышки волатильности на новостях (10–15%+ в часы) |
| 6 | **ADA/USDT** | Средний | 2–5% | 5 USDT | Grid, DCA | Стабильные движения, часто консолидируется перед большими ходами, высокий объём |

**Когда начать:** После 50–100 закрытых сделок с прибылью. Добавлять по одной паре.

**Распределение капитала (100 USDT на 6 пар):**
```
BTC:   30 USDT (главная)
ETH:   25 USDT (вторая)
SOL:   20 USDT (быстрая)
BNB:   12 USDT (стабильная)
XRP:   8 USDT (волатильная)
ADA:   5 USDT (резерв)
```

---

### 3.3 Бонус: Волатильные альты (для опытных, после 200+ сделок)

| # | Пара | Волатильность | Мин. ордер | Стратегия | Риск | Примечание |
|---|------|---------------|-----------|-----------|------|-----------|
| 7 | **DOGE/USDT** | 4–12% | 5 USDT | Grid только | 🔴 Высокий | Часто выбирается за краткосрочную волатильность и быстрые движения цены. Только Grid! |
| 8 | **LTC/USDT** | 3–6% | 5 USDT | RSI+EMA, Grid | 🟡 Средний | Стабильный альт, хороший объём |

**⚠️ Правило:** DOGE только для **Grid trading** и только после минимум **100 успешных сделок** с основными парами.

---

### 3.4 Матрица стратегий по парам

| Стратегия | BTC | ETH | SOL | BNB | XRP | ADA | DOGE |
|-----------|-----|-----|-----|-----|-----|-----|------|
| Grid | ✅✅ | ✅✅ | ✅✅ | ✅✅ | ✅✅ | ✅ | ✅✅ |
| DCA | ✅ | ✅✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| RSI+EMA | ✅✅ | ✅✅ | ✅✅ | ✅ | ✅ | ✅ | ❌ |
| MTF Momentum | ✅ | ✅ | ✅✅ | ✅ | ✅ | - | ❌ |

*(✅✅ = идеально, ✅ = хорошо, - = не тестировано, ❌ = не рекомендуется)*

---

### 3.5 Минимальные суммы по парам

| Пара | Min Notional | Рекомендуем | Обоснование |
|------|-------------|-------------|-------------|
| BTC, ETH | 10 USDT | **15 USDT** | комиссия 0.015 + запас на спред |
| SOL, BNB, XRP, ADA | 5 USDT | **10 USDT** | комиссия 0.01 + волатильность |
| DOGE (если) | 5 USDT | **15 USDT** | высокая волатильность требует буфера |
| < 5 USDT | — | ❌ Не рекомендуется | комиссия съест прибыль |

Бот читает `MIN_NOTIONAL` фильтр через API перед каждым ордером и отклоняет ордера с подсказкой в Telegram.

---

## 4. Стартовый капитал и управление средствами

### 2.1 Рекомендуемый стартовый капитал

```yaml
starting_capital:
  minimum_testnet: 50        # USDT (экономный тест)
  recommended_testnet: 100   # USDT (комфортный тест)
  minimum_mainnet: 500       # USDT (реальные деньги)
  recommended_mainnet: 1000  # USDT (оптимально)

allocation:
  per_trade_usdt: 15         # размер одной сделки
  max_concurrent_trades: 7   # максимум открытых позиций
  reserved_usdt: 20          # неприкосновенный резерв
  
# Пример с 100 USDT:
# - На торговлю: 100 USDT
# - На сделку: 15 USDT
# - Одновременно: 6–7 пар
# - Резерв (закрыт): ~20 USDT
```

### 2.2 Отслеживание капитала

Бот отслеживает **три значения**:

1. **Starting Capital** — сумма на старте (статичная)
2. **Net PnL** — реализованная прибыль/убыток (динамическая)
3. **Current Balance** — текущий баланс на аккаунте (Starting Capital + Net PnL)

```
Current Balance = Starting Capital + Net PnL (с учётом всех комиссий)
```

### 2.3 Инициализация

При первом запуске бота на Testnet:

```bash
# Пользователь выделяет 100 USDT из тестового баланса
# Бот регистрирует это как starting_capital = 100.0

# Из Telegram:
/init 100
✅ Зафиксирован стартовый капитал: 100.00 USDT
Начало торговли на базе этого капитала.
```

В БД создаётся запись:
```sql
INSERT INTO bot_session (starting_capital, started_at, mode)
VALUES (100.0, NOW(), 'testnet');
```

---

## 3. Визуализация капитала на дашборде

### 3.1 Главная страница: Блок "Капитал"

```
┌─────────────────────────────────────────────────┐
│          💰 КАПИТАЛ И СТАТИСТИКА               │
├─────────────────────────────────────────────────┤
│                                                  │
│  Стартовый капитал      100.00 USDT             │
│  ────────────────────────────────────────────   │
│                                                  │
│  Net PnL (реализованный) +13.67 USDT  (+13.67%) │
│  ────────────────────────────────────────────   │
│                                                  │
│  Текущий баланс         113.67 USDT             │
│  ────────────────────────────────────────────   │
│                                                  │
│  Открытые позиции       +8.34 USDT (нереал.)    │
│  ────────────────────────────────────────────   │
│                                                  │
│  Всего (с открытыми)    122.01 USDT             │
│                                                  │
│  Максимум когда-либо    121.55 USDT             │
│  Текущая просадка       0.28% от максимума      │
│                                                  │
└─────────────────────────────────────────────────┘
```

### 3.2 График "Капитал во времени"

**Линейный граф с двумя линиями:**
1. **Балансовая кривая** — текущий баланс с реализованным PnL
2. **Максимум баланса** — штриховая линия для просадки
3. **Открытые позиции** — полупрозрачная область сверху

**Х-ось:** время (24h / 7d / 30d)
**Y-ось:** USDT

### 3.3 Таблица "Разбор средств"

| Компонент | USDT | % от стартового |
|-----------|------|-----------------|
| Стартовый капитал | 100.00 | 100.0% |
| Реализованный PnL | +13.67 | +13.67% |
| Текущий USDT баланс | 113.67 | 113.67% |
| В открытых позициях | +8.34 | +8.34% |
| **Всего на аккаунте** | **122.01** | **122.01%** |
| Максимум достигнут | 121.55 | 121.55% |
| Просадка от макс | -1.46 | -1.20% |

### 3.4 Метрики производительности

```
Прибыль на аккаунт (стартовый капитал):
  Месячная: +8.2%
  Недельная: +3.1%
  Суточная: +0.6%

ROI (Return on Investment):
  Общий: +22.01% (от 100 USDT → 122.01 USDT)
  
Sharpe Ratio: 1.43
Max Drawdown: 4.2%
Win Rate: 52%
```

---

## 5. Технический стек

| Компонент | Технология |
|-----------|-----------|
| Язык | Python 3.11+ |
| Binance API | `python-binance` / `ccxt` |
| Telegram Bot | `python-telegram-bot` v20+ |
| Веб-дашборд | Flask + Chart.js (Chart.js для графиков капитала) |
| База данных | SQLite (dev) / PostgreSQL (prod) |
| Планировщик | APScheduler |
| Технический анализ | `pandas-ta`, `ta` |
| **ML / Самообучение** | **`scikit-learn`, `optuna`, `stable-baselines3`** |
| Бэктестинг | `backtesting.py` / `vectorbt` |
| Деплой | Docker + docker-compose |
| Логи | Loguru |
| Конфиг | `.env` + YAML |

---

## 6. Торговые стратегии (2026)

### 5.1 Grid Trading — ФЛЭТ
**Когда работает:** Боковой рынок, волатильность без тренда (ADX < 20).

**Принцип:** Сетка лимитных ордеров выше и ниже цены. Шаг сетки — минимум 0.5% (чтобы покрыть комиссию 0.2% за круг и заработать сверху).

```yaml
grid:
  lower_price: auto          # рассчитывается из ATR
  upper_price: auto
  grid_count: 10             # уровней (авто-оптимизируется)
  grid_step_pct: 0.8         # % между уровнями (мин. 0.5%)
  investment: 15             # USDT на сетку
  mode: arithmetic
```

---

### 5.2 DCA (Dollar Cost Averaging) — НИСХОДЯЩИЙ ТРЕНД
**Когда работает:** Цена падает, RSI < 35, долгосрочное накопление.

```yaml
dca:
  amount_per_buy: 10         # USDT за покупку
  max_orders: 5              # максимум докупок
  price_deviation: 2.5       # % падения для триггера
  take_profit_net: 1.8       # % нетто-прибыли (после комиссий)
  stop_loss: 12.0
```

---

### 5.3 RSI + EMA — ТЕХНИЧЕСКИЙ ТРЕНД
**Когда работает:** Трендовый рынок с коррекциями, ADX 20–35.

```yaml
rsi_ema:
  rsi_period: 14             # авто-оптимизируется
  rsi_oversold: 35
  rsi_overbought: 65
  ema_period: 200
  timeframe: 1h
  position_size: 15          # USDT
  take_profit_net: 2.0       # нетто (>0.2% breakeven)
  stop_loss: 2.5
```

---

### 5.4 Multi-Timeframe Momentum — СИЛЬНЫЙ ТРЕНД
**Когда работает:** ADX > 35, совпадение сигналов на 4h + 1h + 15m.

```yaml
mtf:
  timeframes: [4h, 1h, 15m]
  position_size: 15
  take_profit_net: 3.5
  stop_loss: 2.0
  trailing_stop: true        # скользящий стоп
```

---

## 7. Модуль самообучения (Learning Engine) — **НОВОЕ**

Самообучение реализовано в три уровня: от простого к сложному.

### 6.1 Уровень 1 — Оптимизация параметров (Parameter Tuner)

**Принцип:** После каждых N сделок по стратегии запускается оптимизация её параметров на исторических данных + реальных результатах.

**Технология:** `Optuna` — байесовская оптимизация гиперпараметров.

**Что оптимизируется:**
- RSI пороги (oversold / overbought)
- Шаг сетки Grid (grid_step_pct)
- Отступ для DCA (price_deviation)
- take_profit / stop_loss значения

**Цикл оптимизации:**
```
Каждые 50 закрытых сделок по стратегии:
  1. Собрать последние 500 свечей (исторические + живые данные)
  2. Запустить Optuna: 100 trials с разными параметрами
  3. Метрика оптимизации: Sharpe Ratio нетто (с комиссиями)
  4. Если новые параметры лучше текущих на > 10% → применить
  5. Уведомить в Telegram: "⚙️ Параметры RSI+EMA обновлены"
  6. Сохранить историю параметров в БД (model_history)
```

**Защита от переобучения:**
- Walk-Forward Validation: тренировка на 80% данных, тест на 20%
- Минимум 30 сделок для оценки новых параметров в live
- Откат к предыдущим параметрам если live Win Rate падает ниже 40%

---

### 6.2 Уровень 2 — Динамические веса стратегий (Strategy Weighter)

**Принцип:** Каждая стратегия получает вес от 0 до 1 на основе её недавних результатов. Бот предпочитает стратегии с лучшими результатами. Реализация через `scikit-learn` (SGD-классификатор с онлайн-обучением).

**Features (входные данные для модели):**
- ADX (сила тренда)
- RSI текущий
- Волатильность 24h (ATR)
- Объём торгов (24h)
- Время суток (0–23)
- День недели
- Последние 5 PnL сделок

**Labels (что предсказывает):**
- Какая стратегия даст лучший результат в следующие 4 часа

**Цикл обучения:**
```
Каждые 4 часа:
  1. Собрать результаты всех стратегий за последние 7 дней
  2. Сформировать обучающую выборку из рыночных условий → результатов
  3. Дообучить SGD-классификатор (partial_fit — онлайн-обучение)
  4. Обновить веса стратегий: weight = model.predict_proba(current_market)
  5. Стратегия с весом > 0.6 → основная, остальные в резерве
```

**Пример весов после обучения:**
```
Grid Trading:       0.72  (хорошо работает в текущих условиях)
DCA:                0.15  (слаба, рынок на восходе)
RSI+EMA:            0.09  (шумный сигнал)
MTF Momentum:       0.04  (нет тренда)
```

---

### 6.3 Уровень 3 — Reinforcement Learning агент (RL Agent)

**Принцип:** PPO-агент обучается принимать решения BUY / SELL / HOLD на основе состояния рынка. Используется `stable-baselines3`.

**Observation Space (что видит агент):**
```python
[
  rsi_14, adx_14, ema_ratio,     # технические индикаторы
  volume_ratio, atr_pct,          # волатильность и объём
  unrealized_pnl_pct,             # текущая позиция
  time_in_position,               # сколько держим
  balance_pct,                    # % использованного капитала
  last_3_trades_pnl,              # история последних сделок
]  # итого: 11 признаков
```

**Action Space:** 3 действия: 0=HOLD, 1=BUY, 2=SELL

**Reward Function:**
```python
def reward(net_pnl, fee_paid, holding_time, drawdown):
    profit_reward = net_pnl / starting_capital * 100
    fee_penalty   = -fee_paid * 2          # штраф за частую торговлю
    time_penalty  = -holding_time * 0.001  # штраф за долгое ожидание
    dd_penalty    = -drawdown * 1.5        # штраф за просадку
    return profit_reward + fee_penalty + time_penalty + dd_penalty
```

**Режимы работы RL-агента:**
- **Training mode:** обучение на исторических данных (offline)
- **Shadow mode:** агент работает параллельно, но не торгует — только логирует решения
- **Live mode:** агент торгует наравне с обычными стратегиями (включается вручную: `/rl on`)

**Цикл переобучения:**
```
Еженедельно (воскресенье 00:00):
  1. Собрать все сделки за неделю как experience samples
  2. Дообучить PPO-агента: 10 000 шагов (~5 мин)
  3. Сравнить новую модель со старой на тестовой выборке
  4. Если Sharpe нового > Sharpe старого → заменить модель
  5. Уведомить в Telegram: "🧠 RL-агент обновлён (Sharpe: 1.42 → 1.67)"
```

---

### 6.4 Модуль аномалий (Anomaly Guard)

Защищает от переобучения и деградации:

```python
# Если за последние 20 сделок Win Rate < 40% → откат параметров
# Если Max Drawdown > 8% → стоп торговли + алерт в Telegram
# Если RL-агент совершил > 3 убытков подряд → перевод в Shadow mode
# Если Sharpe за неделю < 0.5 → уведомление + ручная проверка
# Если комиссии (% от PnL) > 50% → алерт "Слишком частая торговля"
```

---

### 6.5 Структура Learning Engine

```
src/learning/
├── parameter_tuner.py      # Optuna-оптимизация параметров стратегий
├── strategy_weighter.py    # SGD онлайн-обучение весов стратегий
├── rl_agent.py             # PPO RL-агент (stable-baselines3)
├── trading_env.py          # Gym-среда для RL
├── backtester.py           # Быстрый бэктест для валидации
├── anomaly_guard.py        # Защита от деградации
└── model_store.py          # Сохранение/загрузка моделей
```

---

## 8. Архитектура системы

```
┌──────────────────────────────────────────────────────────────┐
│                     TRADING BOT SYSTEM v2.0                   │
├──────────────┬────────────────────┬──────────────────────────┤
│  Telegram    │    Core Engine     │    Web Dashboard          │
│  Bot         │                    │    (Flask, localhost)     │
├──────────────┤  ┌──────────────┐  ├──────────────────────────┤
│ /buy BTC 15  │  │ Strategy     │  │  💰 Блок Капитала:       │
│ /sell ETH    │  │ Manager      │  │  - Стартовый капитал     │
│ /sell_all    │  ├──────────────┤  │  - Net PnL               │
│ /balance     │  │ Auto         │  │  - Текущий баланс        │
│ /positions   │  │ Selector     │  │  - Открытые позиции      │
│ /stats       │  ├──────────────┤  │  - Всего на аккаунте     │
│ /pnl         │  │ Order        │  │  - Max / Просадка        │
│ /strategy    │  │ Manager      │  │  Гр.: Баланс во времени  │
│ /rl on/off   │  │ + Fee Calc   │  │       (с линией макса)    │
│ /learn stats │  ├──────────────┤  │       + открытые позиции  │
│ /learn reset │  │ Risk         │  │  Таблица: разбор средств  │
│ /pairs       │  │ Manager      │  │                          │
│ /add_pair    │  ├──────────────┤  │  Страница /learning:     │
│ /price BTC   │  │ Learning     │  │  - Parameter Tuner       │
│ /mode        │  │ Engine       │  │  - Strategy Weights      │
│ /init 100    │  │ ├─ Tuner     │  │  - RL Agent Dashboard    │
│              │  │ ├─ Weighter  │  │  - Anomaly Log           │
│              │  │ └─ RL Agent  │  │                          │
│              │  ├──────────────┤  │                          │
│              │  │ Data Feed    │  │                          │
│              │  │ (WebSocket)  │  │                          │
├──────────────┴──┴──────────────┴──┴──────────────────────────┤
│                   Binance API (Testnet / Mainnet)              │
├──────────────────────────────────────────────────────────────┤
│     SQLite / PostgreSQL — trades + models + bot_session       │
└──────────────────────────────────────────────────────────────┘
```

---

## 9. База данных: Новые таблицы

### Таблица `bot_session` (новая)

```sql
CREATE TABLE bot_session (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    starting_capital    REAL NOT NULL,          -- стартовый капитал в USDT
    started_at          DATETIME NOT NULL,
    mode                TEXT NOT NULL,          -- testnet / mainnet
    
    -- Статистика сессии
    total_trades        INTEGER DEFAULT 0,
    total_net_pnl       REAL DEFAULT 0,
    max_balance         REAL DEFAULT 0,
    current_drawdown    REAL DEFAULT 0,
    
    status              TEXT DEFAULT 'active',  -- active / paused / stopped
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME
);
```

### Таблица `trades` (обновленная)

```sql
CREATE TABLE trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        TEXT UNIQUE NOT NULL,
    symbol          TEXT NOT NULL,              -- 'BTC' (без USDT)
    side            TEXT NOT NULL,              -- BUY / SELL
    type            TEXT NOT NULL,              -- MARKET / LIMIT
    strategy        TEXT,                       -- grid / dca / rsi_ema / mtf / rl
    quantity        REAL NOT NULL,
    price           REAL NOT NULL,
    total_usdt      REAL NOT NULL,
    
    -- Комиссии
    fee_rate        REAL DEFAULT 0.001,
    fee_buy         REAL DEFAULT 0,
    fee_sell        REAL DEFAULT 0,
    fee_total       REAL DEFAULT 0,
    
    -- PnL
    gross_pnl       REAL DEFAULT 0,
    net_pnl         REAL DEFAULT 0,
    net_pnl_pct     REAL DEFAULT 0,
    
    -- Статус
    status          TEXT NOT NULL,              -- OPEN / CLOSED / CANCELLED
    opened_at       DATETIME NOT NULL,
    closed_at       DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Таблица `model_history` (новая — для Learning Engine)

```sql
CREATE TABLE model_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy        TEXT NOT NULL,      -- grid / dca / rsi_ema / rl
    model_type      TEXT NOT NULL,      -- params / weights / rl_agent
    params_before   TEXT,               -- JSON старых параметров
    params_after    TEXT,               -- JSON новых параметров
    sharpe_before   REAL,
    sharpe_after    REAL,
    win_rate_before REAL,
    win_rate_after  REAL,
    trades_count    INTEGER,            -- на скольки сделках обучено
    applied         BOOLEAN DEFAULT TRUE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Таблица `alerts`

```sql
CREATE TABLE alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT NOT NULL,          -- trade / anomaly / learn / error
    symbol      TEXT,
    message     TEXT NOT NULL,
    sent        BOOLEAN DEFAULT FALSE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 10. Управление стартовым капиталом

### 9.1 Инициализация (первый запуск)

```
Пользователь выделил 100 USDT на тестовом аккаунте.

Команда в Telegram:
/init 100

Бот:
✅ Зафиксирован стартовый капитал: 100.00 USDT
Режим: Binance Testnet
Начало торговли.

INSERT INTO bot_session (starting_capital, started_at, mode)
VALUES (100.0, NOW(), 'testnet');
```

### 9.2 Расчёт текущего баланса

```python
def get_capital_info():
    session = db.query(BotSession).order_by(-BotSession.id).first()
    starting_capital = session.starting_capital
    
    # Реализованный PnL
    net_pnl = db.query(Trade).filter(
        Trade.status == 'CLOSED'
    ).with_entities(func.sum(Trade.net_pnl)).scalar() or 0.0
    
    # Нереализованный PnL (открытые позиции)
    unrealized_pnl = db.query(Trade).filter(
        Trade.status == 'OPEN'
    ).with_entities(func.sum(Trade.gross_pnl)).scalar() or 0.0  # без комиссий пока
    
    current_balance = starting_capital + net_pnl
    
    return {
        "starting_capital": starting_capital,
        "net_pnl_realized": net_pnl,
        "unrealized_pnl": unrealized_pnl,
        "current_balance": current_balance,
        "total_with_open": current_balance + unrealized_pnl,
        "roi_pct": (net_pnl / starting_capital * 100)
    }
```

---

## 11. Комиссии и учёт

### 10.1 Константы

```python
FEE_RATE = 0.001  # 0.1% на Binance Spot
BREAKEVEN = 0.002 # 0.2% для комиссии туда-обратно
```

### 10.2 Расчёт PnL с учётом комиссий

```python
def calc_pnl(buy_price: float, sell_price: float, qty: float) -> dict:
    buy_total  = buy_price  * qty
    sell_total = sell_price * qty
    fee_buy    = buy_total  * FEE_RATE
    fee_sell   = sell_total * FEE_RATE
    gross_pnl  = sell_total - buy_total
    net_pnl    = gross_pnl - fee_buy - fee_sell
    return {
        "gross_pnl":   round(gross_pnl, 4),
        "fee_buy":     round(fee_buy, 4),
        "fee_sell":    round(fee_sell, 4),
        "fee_total":   round(fee_buy + fee_sell, 4),
        "net_pnl":     round(net_pnl, 4),
        "net_pnl_pct": round(net_pnl / buy_total * 100, 3),
    }
```

---

## 12. Telegram-бот: Команды

### 11.1 Инициализация и капитал

| Команда | Описание | Пример |
|---------|----------|--------|
| `/init <сумма>` | Установить стартовый капитал | `/init 100` |
| `/capital` | Показать стартовый + PnL + баланс | `/capital` |

### 11.2 Торговые команды

| Команда | Описание |
|---------|----------|
| `/buy <монета> <сумма>` | Купить на сумму USDT |
| `/sell <монета> <кол>` | Продать количество |
| `/sell_all <монета>` | Продать всю позицию |
| `/buy_limit <монета> <сумма> <цена>` | Лимитная покупка |
| `/cancel <order_id>` | Отменить ордер |
| `/cancel_all` | Отменить все ордера |

### 11.3 Информационные команды

| Команда | Описание |
|---------|----------|
| `/balance` | Баланс аккаунта |
| `/positions` | Открытые позиции |
| `/stats` | Статистика (сделки, Win Rate, Net PnL) |
| `/pnl` | Прибыль нетто за 24h / 7d / всё |
| `/fees` | Комиссии уплачено |
| `/price <монета>` | Текущая цена |

### 11.4 Управление ботом

| Команда | Описание |
|---------|----------|
| `/status` | Статус, активная стратегия |
| `/strategy <имя\|auto>` | Выбрать стратегию |
| `/start_strategy <имя>` | Запустить стратегию |
| `/stop_all` | Остановить всё |
| `/pairs` | Список активных пар |
| `/add_pair <монета>` | Добавить пару |
| `/mode testnet\|mainnet` | Переключить режим |
| `/dashboard` | Адрес дашборда |

### 11.5 Команды самообучения (Learning)

| Команда | Описание |
|---------|----------|
| `/rl on` | Включить RL-агента в live-режим |
| `/rl off` | Перевести RL в shadow-режим |
| `/rl status` | Статус RL-агента, Sharpe |
| `/learn stats` | Статистика обучения |
| `/learn reset` | Сбросить веса (откат) |
| `/learn retrain` | Запустить переобучение вручную |

### 11.6 Пример уведомления

```
💰 БАЛАНС ОБНОВЛЁН
Стартовый капитал: 100.00 USDT
Net PnL: +13.67 USDT (+13.67%)
Текущий баланс: 113.67 USDT

📊 Статистика сессии:
Сделок закрыто: 28
Win Rate: 54%
Комиссии уплачено: -8.47 USDT
Max Drawdown: 4.2%
```

---

## 13. Веб-дашборд (localhost:5000, без пароля)

### 12.1 Главная страница (/)

**Раздел 1: Капитал**
```
┌─────────────────────────────────────┐
│  Стартовый капитал    100.00 USDT   │
│  Net PnL реализованный +13.67 USDT  │
│  Текущий баланс       113.67 USDT   │
│  В открытых позициях  +8.34 USDT    │
│  Всего на аккаунте    122.01 USDT   │
│                                     │
│  ROI: +22.01%                       │
│  Max Balance: 121.55 USDT           │
│  Drawdown: 1.20% от макса           │
└─────────────────────────────────────┘
```

**Раздел 2: Метрики**
```
Win Rate: 52%  |  Sharpe: 1.43  |  Max DD: 4.2%  |  Сделок: 28
```

**Раздел 3: Графики**
- Балансовая кривая (24h / 7d / 30d)
- PnL по дням
- Комиссии по дням
- Распределение Win/Loss

### 12.2 Позиции (/positions)

Таблица: монета, кол-во, цена входа, текущая цена, gross PnL, net PnL%, стратегия, время.

### 12.3 История (/history)

Колонки: монета, сторона, цена, сумма, комиссия, **net PnL**, стратегия, время.

### 12.4 Стратегии (/strategies)

Для каждой: Net PnL, Win Rate, сделок, Sharpe, вес от Learning Engine.

### 12.5 Learning Dashboard (/learning) — НОВОЕ

- **Parameter Tuner:** текущие параметры, история изменений, Sharpe до/после
- **Strategy Weights:** бар-чарт весов (обновляется каждые 4h)
- **RL Agent:** статус (live/shadow), Sharpe по эпохам, действия, решения
- **Anomaly Log:** аномалии и откаты

---

## 14. Конфигурация

### .env
```bash
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_TESTNET=true

TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ADMIN_IDS=123456789

DATABASE_URL=sqlite:///trading_bot.db

FLASK_HOST=127.0.0.1
FLASK_PORT=5000

LOG_LEVEL=INFO
RL_MODE=shadow
LEARNING_ENABLED=true
```

### config.yaml
```yaml
starting_capital:
  testnet: 100         # USDT на тест
  mainnet: 1000        # USDT реально

capital:
  per_trade_usdt: 15
  min_trade_usdt: 10
  max_open_positions: 7
  reserved_usdt: 20

fees:
  fee_rate: 0.001
  breakeven_pct: 0.2

learning:
  enabled: true
  param_tuner:
    trigger_trades: 50
    optuna_trials: 100
  strategy_weighter:
    update_interval: 4h
  rl_agent:
    retrain_interval: 7d
```

---

## 15. Фазы разработки

### Фаза 1 — Основа (2–3 недели)
- [ ] Структура, Docker, Binance API
- [ ] `parse_coin()`, `calc_pnl()`, `get_min_notional()`
- [ ] SQLite + таблицы (включая bot_session, model_history)
- [ ] Telegram бот (без Learning команд)
- [ ] Flask дашборд (блок Капитала, график баланса)

### Фаза 2 — Стратегии (2–3 недели)
- [ ] Grid, DCA, RSI+EMA, MTF
- [ ] AutoSelector
- [ ] Risk Manager

### Фаза 3 — Learning Engine (2–3 недели)
- [ ] ParameterTuner (Optuna)
- [ ] StrategyWeighter (SGD)
- [ ] TradingEnv + RLAgent (PPO)
- [ ] AnomalyGuard
- [ ] Telegram команды: /rl, /learn
- [ ] Learning Dashboard страница

### Фаза 4 — Полировка (1 неделя)
- [ ] Тестирование на Testnet (2 недели)
- [ ] Документация
- [ ] Mainnet (опционально)

---

## 16. Зависимости (requirements.txt)

```
python-binance==1.0.19
python-telegram-bot==20.7
flask==3.0.0
flask-sqlalchemy==3.1.1
pandas==2.1.4
numpy==1.26.2
pandas-ta==0.3.14b
ta==0.11.0
scikit-learn==1.4.0
optuna==3.5.0
stable-baselines3==2.2.1
gymnasium==0.29.1
backtesting==0.3.3
apscheduler==3.10.4
python-dotenv==1.0.0
pyyaml==6.0.1
loguru==0.7.2
sqlalchemy==2.0.23
```

---

*Версия 2.0 — Июнь 2026*
*Включает: стартовый капитал, визуализацию на дашборде, Learning Engine (Optuna + SGD + PPO), самообучение в реальном времени, Anomaly Guard.*
