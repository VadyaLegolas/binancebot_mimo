# Binance Trading Bot v2.0

Автономный самообучающийся торговый бот для Binance с управлением через Telegram и веб-дашборд.

## Возможности

- **4 торговые стратегии**: Grid, DCA, RSI+EMA, MTF Momentum
- **AutoSelector**: Автоматический выбор стратегии по рыночным условиям (ADX/RSI)
- **Learning Engine**: Оптимизация параметров (Optuna), обучение весов стратегий (SGD), RL-агент (PPO)
- **Управление рисками**: Максимум позиций, дневной лимит убытков, буфер резерва, кулдаун, стоп при просадке
- **Telegram бот**: 17+ команд для торговли, мониторинга и управления обучением
- **Веб-дашборд**: Отслеживание капитала в реальном времени, история сделок, метрики стратегий, статус обучения

## Быстрый старт

### Требования
- Python 3.11+
- Аккаунт Binance Testnet (API ключ + секрет)
- Токен Telegram бота (от @BotFather)

### Установка

```bash
# Клонирование репозитория
git clone https://github.com/VadyaLegolas/binancebot_mimo.git
cd binancebot_mimo

# Установка зависимостей
pip install -r requirements.txt

# Настройка окружения
cp .env.example .env
# Отредактируйте .env с вашими API ключами

# Запуск бота
python src/main.py
```

### Docker

```bash
docker-compose up -d
```

## Конфигурация

### Переменные окружения (.env)
- `BINANCE_API_KEY` - API ключ Binance
- `BINANCE_API_SECRET` - API секрет Binance
- `BINANCE_TESTNET` - Использовать тестнет (true/false)
- `TELEGRAM_BOT_TOKEN` - Токен Telegram бота
- `TELEGRAM_CHAT_ID` - Chat ID Telegram для уведомлений
- `DATABASE_URL` - Строка подключения к базе данных

### Параметры стратегий (config.yaml)
- `strategies.grid` - Параметры Grid торговли
- `strategies.dca` - Параметры DCA
- `strategies.rsi_ema` - Параметры RSI+EMA
- `strategies.mtf` - Параметры MTF Momentum
- `risk` - Настройки управления рисками

## Telegram команды

### Торговля
- `/init <сумма>` - Установить стартовый капитал
- `/buy <монета> <сумма>` - Купить в USDT
- `/sell <монета> <кол>` - Продать количество
- `/sell_all <монета>` - Продать всю позицию

### Информация
- `/balance` - Баланс аккаунта
- `/capital` - Информация о капитале
- `/positions` - Открытые позиции
- `/stats` - Статистика торговли
- `/pnl` - Прибыль/Убыток
- `/price <монета>` - Текущая цена

### Управление
- `/status` - Статус бота
- `/pairs` - Активные пары
- `/mode testnet|mainnet` - Переключение режима
- `/strategy auto|grid|dca|rsi_ema|mtf` - Выбор стратегии

### Обучение
- `/rl on|off|status|train` - Управление RL-агентом
- `/learn stats|retrain|history` - Learning Engine
- `/help` - Список всех команд

## Архитектура

```
src/
├── main.py              # Точка входа
├── core/
│   ├── binance_client.py    # Обертка Binance API
│   ├── capital.py           # Отслеживание капитала
│   ├── risk_manager.py      # Управление рисками
│   ├── pair_manager.py      # Динамическое расширение пар
│   └── ws_manager.py        # Менеджер WebSocket
├── strategies/
│   ├── base.py              # Базовый класс стратегии
│   ├── grid.py              # Grid Trading
│   ├── dca.py               # DCA
│   ├── rsi_ema.py           # RSI+EMA
│   ├── mtf.py               # MTF Momentum
│   ├── auto_selector.py     # Маршрутизация стратегий
│   └── manager.py           # Оркестрация стратегий
├── learning/
│   ├── parameter_tuner.py   # Оптимизация Optuna
│   ├── strategy_weighter.py # Обучение весов SGD
│   ├── rl_agent.py          # PPO RL-агент
│   ├── trading_env.py       # Среда Gymnasium
│   ├── anomaly_guard.py     # Обнаружение деградации
│   └── model_store.py       # Сохранение моделей
├── indicators/
│   └── __init__.py          # RSI, EMA, ADX, ATR
├── database/
│   ├── models.py            # Модели SQLAlchemy
│   ├── session.py           # Сессия БД
│   └── migrations.py        # Создание таблиц
├── telegram_bot/
│   ├── app.py               # Настройка бота
│   └── handlers.py          # Обработчики команд
└── dashboard/
    ├── app.py               # Приложение Flask
    ├── routes.py            # API эндпоинты
    └── templates/
        └── index.html       # Интерфейс дашборда
```

## Торговые пары

- **Ядро (день 1)**: BTC, ETH, SOL
- **Расширение (50+ сделок)**: BNB, XRP, ADA
- **DOGE (100+ побед, только Grid)**: DOGE

## Управление рисками

- Максимум открытых позиций: 7
- Дневной лимит убытков: 5% от капитала
- Буфер резерва: 20 USDT
- Кулдаун после стоп-лосс: 15 минут
- Стоп при просадке: 8% останавливает всю торговлю

## Лицензия

MIT
