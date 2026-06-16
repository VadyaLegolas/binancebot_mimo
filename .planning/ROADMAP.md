# Roadmap: Binance Trading Bot v2.0

**Phases:** 4 | **Requirements mapped:** 38 | All v1 requirements covered ✓

---

### Phase 1: Основа
**Goal:** Рабочий каркас с Binance API, Telegram-ботом, дашбордом и БД — всё готово к добавлению стратегий
**Mode:** mvp
**Requirements:** INFRA-01..05, BNCA-01..05, DB-01..04, CAP-01..03, TGB-01..03, TGB-05, DASH-01..04, PAIR-01
**Success Criteria:**
1. Бот подключается к Binance Testnet, получает баланс и цены
2. Telegram-бот принимает /buy, /sell, /balance, /positions, /init и отвечает
3. Dash покажет блок капитала с начальным балансом
4. Сделки записываются в SQLite с учётом комиссий
5. Docker-compose запускает всё одним контейнером

---

### Phase 2: Стратегии
**Goal:** 4 торговые стратегии с автовыбором и управление рисками — бот торгует автоматически
**Mode:** mvp
**Requirements:** STRAT-01..05, RISK-01..04
**Success Criteria:**
1. Grid, DCA, RSI+EMA, MTF работают и размещают ордера
2. AutoSelector выбирает стратегию по рыночным условиям
3. Risk Manager останавливает торговлю при превышении лимитов
4. Все PnL расчётные — нетто с комиссиями

---

### Phase 3: Learning Engine
**Goal:** Самообучение: оптимизация параметров, веса стратегий, RL-агент и защита от деградации
**Mode:** mvp
**Requirements:** LRN-01..05, TGB-04, DASH-05, PAIR-02, PAIR-03
**Success Criteria:**
1. Parameter Tuner оптимизирует параметры через Optuna каждые 50 сделок
2. Strategy Weighter обновляет веса через SGD каждые 4 часа
3. RL Agent обучается в shadow-режиме, переключается в live через /rl on
4. Anomaly Guard откатывает параметры при деградации
5. Learning Dashboard показывает все метрики

---

### Phase 4: Полировка
**Goal:** Тестирование на Testnet, документация, подготовка к Mainnet
**Mode:** mvp
**Requirements:** — (верификация и полировка)
**Success Criteria:**
1. 2 недели стабильной работы на Testnet без критических багов
2. Документация по запуску и конфигурации
3. Опциональное переключение на Mainnet через /mode mainnet

---

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
| LRN-01 | Phase 3 | Pending |
| LRN-02 | Phase 3 | Pending |
| LRN-03 | Phase 3 | Pending |
| LRN-04 | Phase 3 | Pending |
| LRN-05 | Phase 3 | Pending |
| TGB-04 | Phase 3 | Pending |
| DASH-05 | Phase 3 | Pending |
| PAIR-02 | Phase 3 | Pending |
| PAIR-03 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 38 total
- Mapped to phases: 38
- Unmapped: 0 ✓

---
*Created: 2026-06-16*
*Last updated: 2026-06-16 after roadmap creation*
