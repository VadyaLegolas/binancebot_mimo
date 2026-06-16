# STATE.md: Binance Trading Bot v2.0

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-16)

**Core value:** Бот должен автоматически торговать на Binance с учётом комиссий, корректно считать PnL (нетто) и позволять пользователю управлять всем через Telegram.
**Current focus:** Phase 4 — Полировка

## Workflow

**Mode:** yolo
**Granularity:** standard
**Parallelization:** yes
**Git Tracking:** yes
**Research:** yes
**Plan Check:** yes
**Verifier:** yes
**Drift Guard:** yes
**Model Profile:** balanced

## Phase Status

| Phase | Status | Progress |
|-------|--------|----------|
| Phase 1: Основа | Done (4 plans, 17 tasks) | 100% |
| Phase 2: Стратегии | Done (4 plans, 17 tasks) | 100% |
| Phase 3: Learning Engine | Done (4 plans, 17 tasks) | 100% |
| Phase 4: Полировка | Done (2 plans, 8 tasks) | 100% |

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-16 | v2 спека как авторитетная | v1 устарела, v2 включает Learning Engine |
| 2026-06-16 | Indicators on pure pandas/numpy | pandas-ta incompatible with Python 3.14 |

## Active Blockers

(None)

## Notes

- Стартовый файл: binance_bot_spec_v2.md
- AGENTS.md уже создан в корне проекта
- Git репозиторий: https://github.com/VadyaLegolas/binancebot_mimo
- PR #1: Phase 1 fixes (merged/pending)
- PR #2: Phase 2 strategies (open)

---
*Created: 2026-06-16*
*Last updated: 2026-06-16 after Phase 3 completion*
