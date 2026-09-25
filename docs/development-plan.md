# План разработки KaggleAgents

Обновлено: 25 сентября 2026. Статус всех этапов ниже — **запланировано**. Документационный каркас уже подготовлен; runtime пока отсутствует.

## 1. Продуктовый результат

Разработчик создает отдельный competition-проект, подключает фиксированную версию основы, описывает rules/data/metric/split, выбирает модели агентов и получает воспроизводимый путь от baseline до проверенного submission artifact.

Специфика задачи развивается в этом проекте: features, модели, исследования, validation и бюджеты. В основу возвращаются только общие улучшения инструментов и контрактов, подтвержденные повторным использованием.

**Проверка успеха:** второй tabular competition подключается через шаблон и adapter без изменения исходников ядра. Измеряется время настройки от генерации проекта до первого валидного run; download и training time показываются отдельно.

## 2. Последовательность и зависимости

```text
M0 Audit -> M1 Telemetry -> M2 Deterministic baseline -> M3 Recovery
                                                        |
                                                 M4 Reusable template
                                                        |
                                                 M5 Agent workflow
                                                        |
                                                 M6 Portability/release
```

Сроки — ориентир для одного разработчика при доступных API и данных, не обязательство. Базовый диапазон 6–10 недель уточняется после M0; готовность определяется exit criteria.

### M0. Проверить исходный процесс — 2–3 рабочих дня

- [ ] Выбрать первый небольшой tabular competition и другой competition для проверки переносимости.
- [ ] Создать отдельный reference-проект; зафиксировать rules, metric, split, seed, compute и бюджет.
- [ ] Получить пять полных исходных runs с одинаковыми условиями; учитывать неудачи и retries.
- [ ] Сохранить компактный audit report: time/cost-to-baseline, usage availability, ручные операции, повторные загрузки и типы ошибок.
- [ ] Выделить минимальные общие контракты из реального workflow.

**Приемка:** есть проверенный baseline artifact и audit report со ссылками на run records. Если provider не дает стоимость, это явно отмечено; допускается оценка по версии тарифов с указанием метода.

### M1. Пакет, контракты и telemetry — 3–5 дней

- [ ] Завести `pyproject.toml`, `uv.lock`, `src/` layout и минимальный CLI на Python 3.12.
- [ ] Определить versioned TaskSpec, ExperimentSpec/Result и IDs attempts.
- [ ] Реализовать structured events, timing и адаптер usage без записи secrets/transcripts в компактный отчет.
- [ ] Добавить budget ledger: spent/reserved, неизвестная стоимость, limits и preflight checks.
- [ ] Настроить CI: lint, contract tests и малый offline smoke на синтетических fixtures.

**Приемка:** один CLI-run проходит от task до summary; каждый retry учитывается; malformed input отклоняется до выполнения; CI не требует Kaggle/API credentials.

### M2. Детерминированный baseline — 5–8 дней

- [ ] Реализовать metadata-first inspect/download, manifest, checksum и повторное использование cache.
- [ ] Сделать компактный tabular profiler и hooks competition adapter.
- [ ] Запускать training subprocess с timeout, CPU/RAM limits где поддерживаются и файловыми logs.
- [ ] Подключить reference adapter первого проекта: split, train, predict, evaluate.
- [ ] Реализовать checks submission: schema, row count, IDs/order, duplicates, NaN и диапазоны.
- [ ] Проверить cache hit, поврежденный download, ошибку metric, timeout и cleanup дочерних процессов.

**Приемка:** pipeline запускается без LLM и создает валидный artifact; повтор не скачивает неизмененные данные; версии кода/data/environment записаны. Неподдерживаемый hard resource limit явно виден в preflight.

### M3. Registry и восстановление — 3–5 дней

- [ ] Реализовать SQLite registry с миграциями и единой точкой записи.
- [ ] Хранить immutable run summaries, artifact checksums и ссылки на полный вывод.
- [ ] Добавить очередь, fingerprint deduplication, attempt statuses и checkpoint.
- [ ] Реализовать `resume`: reconcile процессов, leases и завершенных artifacts перед retry.
- [ ] Прерывать процесс в разных точках integration test и проверять восстановление.

**Приемка:** restart сохраняет очередь и расходы, не повторяет уже завершенный run и не объявляет успешным незавершенный artifact. Registry резервируется вместе с manifest artifacts; потеря локального диска описана как отдельный failure case.

### M4. Поставка основы и generator — 4–6 дней

- [ ] Упаковать стабильный public API; закрепить contract version.
- [ ] Создать generator `init` для отдельного проекта, включая configs, adapter stub, локальные инструкции и tests.
- [ ] Генерировать pin версии основы и lockfile; секреты передаются через окружение.
- [ ] Реализовать `doctor`: config, adapter hooks, paths, runner capabilities и credentials presence без вывода значений.
- [ ] Перевести первый reference-проект на установку основы как зависимости.
- [ ] Описать обновление основы и миграции state/config; generator не перезаписывает существующий проект.

**Приемка:** чистый проект устанавливается по инструкции, проходит doctor и offline smoke. Настройки соревнования не требуют edits в package source; reference-проект использует тот же путь установки.

### M5. Агенты и ограниченный параллелизм — 5–8 дней

- [ ] Зафиксировать совместимую версию OpenCode и thin tool wrappers над CLI.
- [ ] Добавить role templates: orchestrator, researcher, coding worker, reviewer; model profiles хранятся отдельно.
- [ ] Research возвращает карточки со ссылками и датами; разные instances получают разные вопросы.
- [ ] Реализовать dedup/ranking proposals и связь researcher -> coding task -> runs.
- [ ] Config-only эксперименты отправлять в runner; новый код — в отдельный worktree и изолированный процесс.
- [ ] Ввести concurrency/resource reservations; начать с 3 researchers / 1 coder / 1 training job.
- [ ] Добавить smoke -> one fold -> full validation gates и stop conditions.
- [ ] Проверить отсутствие файловых гонок, превышения budget caps и самостоятельной смены split worker-ом.

**Приемка:** одна ограниченная сессия от hypothesis до reviewed result проходит с трассировкой затрат. После остановки сессия восстанавливается. Добавление второго coder допускается только после concurrency tests.

### M6. Второе соревнование и выпуск v0.1.0 — 4–7 дней

- [ ] Создать второй отдельный проект через generator: другие columns/target и собственный validation adapter.
- [ ] Получить baseline и validated submission без изменения ядра; найденные общие дефекты исправить и повторить проверку обоих проектов.
- [ ] Измерить onboarding time и перечислить все ручные операции.
- [ ] Сравнить последовательный и параллельный workflow на равном бюджете, одинаковых данных, моделях и hardware; повторить нестабильные случаи.
- [ ] Выбрать default concurrency по cost-to-success и best score, а не по числу агентов.
- [ ] Подготовить quickstart, compatibility matrix, migration notes и release checklist.
- [ ] После приемки создать tag/release `v0.1.0` и закрепить его в reference-проектах.

**Приемка:** выполнен [MVP DoD](mvp.md), два проекта работают с одним выпуском основы, а измерения и ограничения опубликованы в компактном отчете.

## 3. Целевая структура основного репозитория

Это план, каталоги появляются вместе с работающими компонентами.

```text
src/kaggle_agents/
  cli.py
  contracts/            # versioned input/output models
  telemetry/           # usage, timing, budget ledger
  data/                # download, cache, manifest, profile primitives
  experiments/         # adapter protocol, runner, validation, compare
  state/               # registry, migrations, checkpoints
  research/            # source cards, search adapter, dedup
  orchestration/       # queue, scheduler, leases, promotion
  integrations/        # OpenCode bridge and provider adapters
templates/competition/ # generated files owned by competition project
tests/                 # unit, contract, integration; tiny synthetic data
evals/                 # benchmark protocol and compact reports
docs/
.github/workflows/     # offline CI
```

Модели, datasets, raw web pages и полные logs хранятся вне Git. В evals — только разрешенные малые fixtures, спецификации и агрегаты.

## 4. Как разрабатывать каждую задачу

1. Создать Issue с milestone, ожидаемым artifact, зависимостями и проверяемым acceptance criterion.
2. Описать вход/выход на одном reference case; изменившееся архитектурное решение записать в decisions.
3. Реализовать самый узкий рабочий путь и тест важных failure cases.
4. Проверить offline CI, затем при необходимости integration-run в reference-проекте.
5. В PR указать contract changes, версии, измеренную стоимость/время и способ воспроизведения.
6. После review обновить документацию и checklist этапа. Код competition остается в его репозитории.

Изменение считается общим, если оно нужно обоим reference-проектам либо обеспечивает единый invariant: учет бюджета, воспроизводимость, изоляцию, contract validation. Обобщение «на будущее» само по себе не является задачей этапа.

## 5. Первые задачи в backlog

| ID | Задача | Результат | Зависимость |
| --- | --- | --- | --- |
| P0-01 | Выбрать reference competitions и бюджеты | Два slug, критерии успеха и compute profile | — |
| P0-02 | Описать первый validation protocol | Competition card + metric/split/seed | P0-01 |
| P0-03 | Собрать пять audit-runs | Audit report + компактные records | P0-02 |
| P1-01 | Создать Python package и offline CI | Установка, CLI entrypoint, green CI | P0-03 |
| P1-02 | Определить contracts v0 и telemetry | Schema checks + run summary | P1-01 |
| P1-03 | Реализовать budget ledger | Проверки reservation/retry/unknown cost | P1-02 |

## 6. После v0.1

Приоритет следующих улучшений определяется traces: remote/Kaggle runner, дополнительные типы данных, object storage, полноценный research-service и retrieval. Общие adapter contracts расширяются с migration plan и тестом обратной совместимости. Соревновательные идеи и ML-стратегии продолжают развиваться независимо в competition-проектах.
