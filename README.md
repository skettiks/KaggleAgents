# Kaggle Agents System

Переиспользуемая основа агентных систем для Kaggle на базе OpenCode, Python и GitHub. Каждый competition получает отдельный проект с собственной ML-логикой, а общая основа обеспечивает инструменты, память, бюджеты и воспроизводимость.

Цель проекта: максимизировать подтвержденный validation score при фиксированном бюджете времени, токенов и вычислений. LLM выступает как control plane, а загрузка данных, профилирование, обучение, оценка и проверка submission выполняются детерминированным кодом.

## Статус

**M1 и часть M2: работающий offline-срез.** Реализованы Python-пакет, проверка конфигурации, CSV-manifest/profiler, запуск experiment-script, учет времени/попыток, artifacts и проверка submission. Аудит реального competition (M0) еще предстоит; полноценная система агентов и генератор проектов находятся в плане.

## Попробовать сейчас

С установленным `uv`, из корня репозитория:

```text
uv sync --locked --python 3.12
uv run --locked kaggle-agents check --project examples/offline
uv run --locked kaggle-agents inspect --project examples/offline
uv run --locked kaggle-agents profile --project examples/offline
uv run --locked kaggle-agents run --project examples/offline
uv run --locked kaggle-agents validate-submission --project examples/offline --file runs/artifacts/<run_id>/attempt-001/submission.csv
```

В последней команде подставьте `run_id` из результата `run`. Синтетический пример запускается без Kaggle, GPU и LLM API. CLI возвращает краткий JSON; подробные результаты и logs сохраняются в игнорируемом каталоге `examples/offline/runs/`. Готовый PowerShell-сценарий есть в [README примера](examples/offline/README.md).

Реальные команды, протокол worker и текущие ограничения: **[инструкция по реализации](docs/implementation.md)**.

## Что находится где

| `KaggleAgents` — общая основа | Отдельный репозиторий соревнования |
| --- | --- |
| Версионируемый Python-пакет и CLI | Зафиксированная версия основы и ML-зависимостей |
| Контракты, registry, cache, telemetry, runner | Rules, target, metric, split и budget |
| Общие роли агентов и маршрутизация моделей | Специализация research-направлений и prompts |
| Очередь гипотез, checkpoints, проверки artifacts | Features, модели, train/predict-код и эксперименты |
| Генератор проекта и reference tabular adapter | Локальные данные, logs, модели и submission artifacts |

Практичность проверяем на двух разных небольших tabular-соревнованиях: второй проект должен подключаться через конфигурацию и свой adapter без изменений ядра.

## Документация

- [Реализованные команды](docs/implementation.md) — установка, запуск, telemetry и тесты.
- [План разработки](docs/development-plan.md) — этапы, задачи, зависимости и критерии готовности.
- [Архитектура](docs/architecture.md) — границы основы, агенты, очередь и контракты.
- [Запуск нового соревнования](docs/competition-project.md) — целевой пользовательский сценарий.
- [Границы MVP](docs/mvp.md) — состав первого выпуска.
- [Решения](docs/decisions.md) — принятые решения и вопросы перед реализацией.

## Порядок разработки

1. Измерить исходный процесс на первом competition.
2. Реализовать telemetry, детерминированные инструменты и один воспроизводимый baseline.
3. Добавить registry и восстановление после остановки.
4. Упаковать основу и создать генератор отдельного competition-проекта.
5. Подключить оркестратор, параллельный research и изолированные coding workers.
6. Проверить переносимость на втором competition и выпустить `v0.1.0`.

Для первоначальной разработки выбран Python 3.12 + `uv`; OpenCode интегрируется через тонкие wrappers над Python CLI. Идентификаторы LLM задаются в проекте соревнования и фиксируются в run records.

Репозиторий: [skettiks/KaggleAgents](https://github.com/skettiks/KaggleAgents), основная ветка `main`.
