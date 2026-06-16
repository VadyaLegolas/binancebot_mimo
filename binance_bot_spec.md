# 📊 Binance Trading Bot — Техническая Спецификация
**Версия:** 1.0 | **Дата:** Июнь 2026 | **Среда:** Binance Testnet → Mainnet

---

## 1. Обзор проекта

### 1.1 Цели
Разработать автономного торгового бота для Binance с управлением через Telegram и веб-дашбордом. Бот должен работать 24/7, реализовывать несколько торговых стратегий, поддерживать тестовый аккаунт Binance и обеспечивать полное ручное управление через Telegram-команды.

### 1.2 Ключевые требования
- Работа на Binance Testnet (с возможностью переключения на Mainnet)
- Управление всеми процессами через Telegram-бота
- Веб-дашборд с real-time статистикой
- Поддержка нескольких торговых стратегий
- Система управления рисками
- Логирование и алерты

---

## 2. Технический стек

| Компонент | Технология |
|-----------|-----------|
| Язык | Python 3.11+ |
| Binance API | `python-binance` / `ccxt` |
| Telegram Bot | `python-telegram-bot` v20+ |
| Веб-дашборд | Flask + Chart.js / или Streamlit |
| База данных | SQLite (dev) / PostgreSQL (prod) |
| Планировщик | APScheduler |
| Технический анализ | `ta-lib`, `pandas-ta` |
| Деплой | Docker + docker-compose |
| Логи | Loguru |
| Конфиг | `.env` + YAML |

---

## 3. Торговые стратегии (2026)

### 3.1 Grid Trading (Сетка) — ОСНОВНАЯ
**Когда работает:** Боковой рынок (флэт), высокая волатильность без тренда.

**Принцип:**
- Бот выставляет сетку лимитных ордеров выше и ниже текущей цены
- При срабатывании ордера на покупку — автоматически выставляется ордер на продажу на шаг выше
- При срабатывании ордера на продажу — автоматически выставляется ордер на покупку на шаг ниже

**Параметры:**
```yaml
grid:
  symbol: BTCUSDT
  lower_price: 60000
  upper_price: 70000
  grid_count: 20        # количество уровней сетки
  investment: 1000      # общий капитал в USDT
  mode: arithmetic      # arithmetic / geometric
```

**Рекомендуемые пары:** BTC/USDT, ETH/USDT, BNB/USDT

---

### 3.2 DCA (Dollar Cost Averaging) — ДОЛГОСРОЧНАЯ
**Когда работает:** Нисходящий/боковой тренд, долгосрочное накопление позиции.

**Принцип:**
- Бот покупает на фиксированную сумму через равные промежутки времени
- Опционально: покупка при падении цены ниже порога (Dynamic DCA)
- При достижении целевого профита — продажа всей позиции

**Параметры:**
```yaml
dca:
  symbol: ETHUSDT
  interval: 4h           # период между покупками
  amount_per_buy: 50     # USDT за каждую покупку
  max_orders: 10         # максимум докупок
  price_deviation: 2.5   # % падения для триггера
  take_profit: 5.0       # % прибыли для продажи
  stop_loss: 15.0        # % убытка для стоп-лосс
```

---

### 3.3 RSI + EMA Strategy — ТЕХНИЧЕСКАЯ
**Когда работает:** Трендовый рынок с коррекциями.

**Принцип:**
- RSI < 30 + цена выше EMA200 → сигнал на покупку
- RSI > 70 + цена ниже EMA200 → сигнал на продажу
- Опционально: подтверждение через MACD

**Параметры:**
```yaml
rsi_ema:
  symbol: SOLUSDT
  rsi_period: 14
  rsi_oversold: 30
  rsi_overbought: 70
  ema_period: 200
  timeframe: 1h
  position_size: 100     # USDT
  take_profit: 3.0       # %
  stop_loss: 2.0         # %
```

---

### 3.4 Multi-Timeframe Momentum — ПРОДВИНУТАЯ
**Когда работает:** Сильные трендовые движения.

**Принцип:**
- Анализ на 4h, 1h, 15m таймфреймах
- Открытие позиции только при совпадении сигналов на всех таймфреймах
- Индикаторы: EMA crossover, RSI, Volume

---

## 4. Архитектура системы

```
┌─────────────────────────────────────────────────────────┐
│                    TRADING BOT SYSTEM                    │
├──────────────┬──────────────────┬───────────────────────┤
│   Telegram   │   Core Engine    │    Web Dashboard       │
│   Bot        │                  │    (Flask)             │
├──────────────┤  ┌────────────┐  ├───────────────────────┤
│  /start      │  │ Strategy   │  │  Real-time PnL         │
│  /status     │  │ Manager    │  │  Open Positions        │
│  /buy        │  ├────────────┤  │  Trade History         │
│  /sell       │  │ Order      │  │  Balance Chart         │
│  /balance    │  │ Manager    │  │  Strategy Stats        │
│  /positions  │  ├────────────┤  │  Settings Panel        │
│  /settings   │  │ Risk       │  │                        │
│  /stop       │  │ Manager    │  │                        │
│  /stats      │  ├────────────┤  │                        │
│  /pairs      │  │ Data Feed  │  │                        │
│              │  │ (WebSocket)│  │                        │
├──────────────┴──┴────────────┴──┴───────────────────────┤
│                    Binance API (Testnet/Mainnet)          │
├─────────────────────────────────────────────────────────┤
│              SQLite / PostgreSQL Database                 │
└─────────────────────────────────────────────────────────┘
```

---

## 5. Структура проекта

```
trading-bot/
├── .env                          # API ключи и конфиг
├── docker-compose.yml
├── requirements.txt
├── config/
│   ├── config.yaml               # Основная конфигурация
│   └── strategies/
│       ├── grid.yaml
│       ├── dca.yaml
│       └── rsi_ema.yaml
├── src/
│   ├── main.py                   # Точка входа
│   ├── core/
│   │   ├── bot_engine.py         # Основной движок
│   │   ├── binance_client.py     # Обёртка над Binance API
│   │   ├── order_manager.py      # Управление ордерами
│   │   └── risk_manager.py       # Управление рисками
│   ├── strategies/
│   │   ├── base_strategy.py      # Базовый класс стратегии
│   │   ├── grid_strategy.py
│   │   ├── dca_strategy.py
│   │   └── rsi_ema_strategy.py
│   ├── indicators/
│   │   ├── rsi.py
│   │   ├── ema.py
│   │   ├── macd.py
│   │   └── bollinger.py
│   ├── telegram_bot/
│   │   ├── bot.py                # Telegram бот
│   │   ├── handlers/
│   │   │   ├── trade_handlers.py # Команды торговли
│   │   │   ├── info_handlers.py  # Команды информации
│   │   │   └── admin_handlers.py # Команды управления
│   │   └── keyboards.py          # Inline-клавиатуры
│   ├── dashboard/
│   │   ├── app.py                # Flask приложение
│   │   ├── routes.py             # API роуты
│   │   ├── templates/
│   │   │   ├── index.html        # Главная страница
│   │   │   ├── positions.html
│   │   │   └── history.html
│   │   └── static/
│   │       ├── css/
│   │       └── js/
│   └── database/
│       ├── models.py             # SQLAlchemy модели
│       ├── repository.py         # CRUD операции
│       └── migrations/
├── logs/
└── tests/
    ├── test_strategies.py
    ├── test_orders.py
    └── test_risk_manager.py
```

---

## 6. Telegram-бот: Команды и функционал

### 6.1 Команды управления торговлей

| Команда | Описание | Пример |
|---------|----------|--------|
| `/start` | Запуск бота, главное меню | `/start` |
| `/buy <пара> <сумма>` | Купить на указанную сумму USDT | `/buy BTCUSDT 100` |
| `/sell <пара> <количество>` | Продать указанное количество | `/sell BTCUSDT 0.001` |
| `/sell_all <пара>` | Продать всю позицию по паре | `/sell_all ETHUSDT` |
| `/buy_limit <пара> <сумма> <цена>` | Лимитный ордер на покупку | `/buy_limit BTCUSDT 100 62000` |
| `/sell_limit <пара> <кол> <цена>` | Лимитный ордер на продажу | `/sell_limit BTCUSDT 0.001 68000` |
| `/cancel <order_id>` | Отменить ордер | `/cancel 12345` |
| `/cancel_all` | Отменить все открытые ордера | `/cancel_all` |

### 6.2 Команды информации

| Команда | Описание |
|---------|----------|
| `/balance` | Показать баланс аккаунта |
| `/positions` | Список открытых позиций |
| `/orders` | Открытые ордера |
| `/price <пара>` | Текущая цена пары |
| `/stats` | Общая статистика бота |
| `/pnl` | Прибыль/убыток за период |
| `/history` | История сделок |

### 6.3 Команды управления ботом

| Команда | Описание |
|---------|----------|
| `/status` | Статус бота и активных стратегий |
| `/start_strategy <название>` | Запустить стратегию |
| `/stop_strategy <название>` | Остановить стратегию |
| `/stop_all` | Остановить все стратегии |
| `/pairs` | Список активных торговых пар |
| `/add_pair <пара>` | Добавить пару для торговли |
| `/remove_pair <пара>` | Удалить пару |
| `/settings` | Настройки бота |
| `/set_risk <процент>` | Установить риск на сделку |
| `/mode testnet\|mainnet` | Переключить режим |
| `/dashboard` | Ссылка на веб-дашборд |

### 6.4 Алерты (автоматические уведомления)

- ✅ Открытие/закрытие сделки
- ⚠️ Срабатывание стоп-лосс
- 🎯 Достижение take-profit
- 💰 Отчёт PnL (ежедневно/еженедельно)
- 🔴 Критическая ошибка
- 📊 Ежечасный статус (опционально)
- 🔔 Цена достигла установленного уровня

### 6.5 Inline-клавиатура главного меню

```
┌─────────────────────────────────┐
│  🤖 Binance Trading Bot         │
├─────────────┬───────────────────┤
│ 📊 Статус   │ 💰 Баланс         │
├─────────────┼───────────────────┤
│ 📈 Позиции  │ 📋 История        │
├─────────────┼───────────────────┤
│ ⚙️ Стратегии │ 🔧 Настройки     │
├─────────────┴───────────────────┤
│      ⏹ Остановить всё           │
└─────────────────────────────────┘
```

---

## 7. Веб-дашборд

### 7.1 Главная страница (/)
- **Header:** Название, статус бота (ACTIVE/STOPPED), режим (TESTNET/MAINNET)
- **Summary Cards:**
  - Общий баланс (USDT)
  - Нереализованный PnL
  - Реализованный PnL (24h / 7d / Всего)
  - Количество открытых позиций
  - Win Rate (%)
  - Всего сделок

- **Графики:**
  - Кривая баланса (линейный, за период: 24h/7d/30d)
  - PnL по дням (столбчатый)
  - Распределение по парам (пайчарт)
  - Распределение Win/Loss

### 7.2 Страница позиций (/positions)
- Таблица: пара, количество, цена входа, текущая цена, PnL%, PnL USD, стратегия, время открытия
- Кнопки быстрого действия: закрыть позицию, установить TP/SL

### 7.3 История сделок (/history)
- Фильтрация по паре, стратегии, дате, типу (long/short)
- Экспорт в CSV
- Пагинация

### 7.4 Страница стратегий (/strategies)
- Список активных стратегий
- Статистика каждой стратегии: PnL, Win Rate, количество сделок
- Кнопки: запустить / остановить / настроить

### 7.5 Настройки (/settings)
- API ключи (маскированные)
- Глобальные параметры риска
- Telegram настройки
- Переключение Testnet/Mainnet

---

## 8. База данных: Схема

### Таблица `trades`
```sql
CREATE TABLE trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT UNIQUE NOT NULL,
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL,          -- BUY / SELL
    type        TEXT NOT NULL,          -- MARKET / LIMIT / GRID / DCA
    strategy    TEXT,
    quantity    REAL NOT NULL,
    price       REAL NOT NULL,
    total_usdt  REAL NOT NULL,
    fee         REAL DEFAULT 0,
    status      TEXT NOT NULL,          -- OPEN / CLOSED / CANCELLED
    pnl         REAL DEFAULT 0,
    pnl_pct     REAL DEFAULT 0,
    opened_at   DATETIME NOT NULL,
    closed_at   DATETIME,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Таблица `balances`
```sql
CREATE TABLE balances (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    asset       TEXT NOT NULL,
    free        REAL NOT NULL,
    locked      REAL NOT NULL,
    snapshot_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Таблица `strategies`
```sql
CREATE TABLE strategies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,          -- grid / dca / rsi_ema
    symbol      TEXT NOT NULL,
    config      TEXT NOT NULL,          -- JSON конфиг
    status      TEXT DEFAULT 'stopped', -- running / stopped / error
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME
);
```

### Таблица `alerts`
```sql
CREATE TABLE alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT NOT NULL,
    symbol      TEXT,
    message     TEXT NOT NULL,
    sent        BOOLEAN DEFAULT FALSE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 9. Управление рисками

### 9.1 Глобальные параметры
```yaml
risk:
  max_position_size_pct: 20    # Максимум 20% капитала на одну пару
  max_total_positions: 5       # Максимум 5 открытых позиций
  daily_loss_limit_pct: 5      # Стоп всего бота при потере 5% в день
  default_stop_loss_pct: 3     # Дефолтный стоп-лосс
  default_take_profit_pct: 6   # Дефолтный тейк-профит
  min_usdt_balance: 100        # Минимальный резерв USDT
```

### 9.2 Автоматические защиты
- Daily Drawdown Limit: автоматическая остановка бота при достижении дневного лимита убытков
- Position Size Check: проверка перед каждым ордером
- Cooldown после стоп-лосс: пауза 15 минут после срабатывания SL
- Проверка доступного баланса перед каждой сделкой

---

## 10. Конфигурационный файл (.env)

```bash
# Binance API
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_TESTNET=true

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ADMIN_IDS=123456789,987654321

# Database
DATABASE_URL=sqlite:///trading_bot.db

# Dashboard
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_SECRET_KEY=your_secret_key
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=your_password

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
```

---

## 11. Docker Compose

```yaml
version: '3.8'
services:
  trading-bot:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config

  dashboard:
    build:
      context: .
      dockerfile: Dockerfile.dashboard
    restart: unless-stopped
    ports:
      - "5000:5000"
    env_file: .env
    depends_on:
      - trading-bot
```

---

## 12. Фазы разработки

### Фаза 1 — Основа (2-3 недели)
- [ ] Настройка проекта, структура папок
- [ ] Binance API клиент (Testnet)
- [ ] Базовые операции: баланс, цены, ордера
- [ ] SQLite база данных + модели
- [ ] Базовый Telegram бот (основные команды)
- [ ] Логирование

### Фаза 2 — Стратегии (2-3 недели)
- [ ] Grid Trading стратегия
- [ ] DCA стратегия
- [ ] RSI + EMA стратегия
- [ ] Strategy Manager (запуск/остановка)
- [ ] Risk Manager
- [ ] Бэктест на исторических данных

### Фаза 3 — Дашборд (1-2 недели)
- [ ] Flask приложение
- [ ] Главная страница с метриками
- [ ] Страница позиций и истории
- [ ] Real-time обновление (WebSocket или polling)
- [ ] Аутентификация

### Фаза 4 — Полировка (1 неделя)
- [ ] Docker-контейнеризация
- [ ] Полное тестирование на Testnet
- [ ] Документация
- [ ] Переключение на Mainnet (опционально)

---

## 13. Безопасность

- API ключи только в `.env` файле, никогда в коде
- Ограничение прав Binance API: только Spot Trading (без вывода средств)
- IP whitelist для Binance API (указать IP сервера)
- Аутентификация на дашборде (логин/пароль)
- Авторизация Telegram по chat_id (только доверенные пользователи)
- Все секреты через переменные окружения в Docker

---

## 14. Мониторинг и алерты

### Telegram уведомления
```
✅ СДЕЛКА ОТКРЫТА
Пара: BTC/USDT
Тип: BUY MARKET
Количество: 0.001 BTC
Цена: 63,450 USDT
Сумма: 63.45 USDT
Стратегия: Grid #3
⏰ 12:34:56
```

```
🎯 TAKE-PROFIT ДОСТИГНУТ
Пара: ETH/USDT
Закрыто: 0.05 ETH по 3,200 USDT
Вход: 3,050 USDT
PnL: +$7.50 (+4.92%)
Стратегия: RSI+EMA
```

```
⚠️ СТОП-ЛОСС СРАБОТАЛ
Пара: SOL/USDT
Закрыто: 2 SOL по 140 USDT
Вход: 150 USDT
PnL: -$20.00 (-6.67%)
Стратегия: DCA
```

---

## 15. Зависимости (requirements.txt)

```
python-binance==1.0.19
python-telegram-bot==20.7
flask==3.0.0
flask-sqlalchemy==3.1.1
apscheduler==3.10.4
pandas==2.1.4
numpy==1.26.2
pandas-ta==0.3.14b
ta==0.11.0
python-dotenv==1.0.0
pyyaml==6.0.1
loguru==0.7.2
aiohttp==3.9.1
websocket-client==1.7.0
sqlalchemy==2.0.23
```

---

*Документ создан: Июнь 2026. Проект предназначен для образовательных целей и тестирования на Binance Testnet.*
