# Решения проекта

Обновлено: 25 сентября 2026. План реализации: [development-plan.md](development-plan.md).

## D-001. Переиспользуемая основа и отдельные competition-проекты

**Принято.** `KaggleAgents` содержит общий runtime, инструменты, контракты, шаблоны и evals. Каждое соревнование разрабатывается в отдельном репозитории, подключающем фиксированную версию основы.

Это уточняет первоначальную цель «один tabular pipeline»: первый pipeline остается способом проверки основы, а его прикладная логика живет в reference competition-проекте. Второй competition подтверждает переносимость до первого выпуска.

## D-002. Поставка и расширение

**Принято для v0.1.** Python 3.12 + `uv`, устанавливаемый пакет, CLI и генератор `init`. До публикации пакета допустима установка по фиксированному Git tag/commit. Имя Python distribution и доступность имени в package index проверяются перед публикацией.

Competition adapter явно задается конфигурацией и реализует узкие hooks профилирования, подготовки split, обучения, предсказания и оценки. Features и модели не добавляются в ядро. Контракты вводятся по первому сценарию и проверяются на втором.

## D-003. Агентный runtime и модели

**Принято.** OpenCode — первоначальный runtime. Его tools вызывают тот же Python CLI, что используется без LLM. Роли и tool contracts стабильны; provider/model IDs, reasoning settings и concurrency задаются model profile конкретного проекта.

Сильная GPT — стартовый кандидат на оркестратор, а не неизменная зависимость ядра. Выбор конкретной версии подтверждается доступом через provider и внутренним benchmark. Список в каталоге моделей не доказывает доступность API или качество.

Версия OpenCode фиксируется при реализации интеграции. Конфигурации разных версий не смешиваются.

## D-004. Параллельные ветки исследования и общий пул workers

**Принято как целевая схема.** Несколько researchers получают разные направления поиска. Proposal связывается с coding task и run через ID; coding worker выделяется из общего пула по мере необходимости. Для конфигурационных экспериментов LLM-кодинг не требуется.

Первый concurrency profile: до трех research-задач, один coding worker, один training job. Второй coding worker включается после проверки изоляции. Все лимиты ограничены бюджетом и доступными ресурсами.

Состояние, очереди, reservations бюджета и GPU leases управляются кодом. Workers работают в отдельных worktrees и процессах; worktree сам по себе не является sandbox.

## D-005. Состояние, данные и воспроизводимость

**Принято для v0.1.** SQLite registry на локальном диске одного coordinator, versioned configs, локальный persistent cache и отдельные artifact directories. Запись в registry идет через общий сервис/инструменты. Удаленные workers не открывают SQLite через сетевую файловую систему.

Данные, модели, полные логи и raw research не попадают в Git или LLM-контекст. Manifest содержит версии и checksums. Run фиксирует версии основы и competition-кода, конфигурацию, split, seed и environment fingerprint.

## D-006. Validation и submission

**Принято.** Metric, split, направление оптимизации, критерий улучшения и допустимое отклонение воспроизведения определяются в competition-проекте до сравнения runs. Смена metric/split создает новый протокол сравнения.

Submission создается и проверяется автоматически, отправляется человеком. External data по умолчанию выключены и включаются только с учетом правил конкретного competition.

## D-007. Research и приемка

**Принято.** Один ограниченный discovery pass, далее поиск под конкретную гипотезу. Источники и дата доступа обязательны. Начальный индекс — SQLite FTS5; embeddings вводятся по результатам retrieval eval.

Оценка системы: стоимость и время до валидного baseline, best validation score при равном бюджете, failures/retries и время подключения второго competition. Пять исходных runs — материал для аудита, а не доказательство универсального превосходства.

## Открытые вопросы по этапам

| До этапа | Нужно определить |
| --- | --- |
| M0 | Два reference competitions, бюджет аудита, целевая metric и compute для первого |
| M1 | Доступ к usage провайдера, тарификация, представление неизвестной стоимости |
| M2 | Локальные storage quotas, timeouts, retry caps и ML baseline первого проекта |
| M4 | Имя пакета, версия contract v1, политика миграций |
| M5 | Provider credentials, конкретные model profiles, search API и версия OpenCode |
| M6 | Результат сравнения последовательного и параллельного режима, release checklist |

GitHub уже выбран: публичный [skettiks/KaggleAgents](https://github.com/skettiks/KaggleAgents), ветка `main`.

## D-008. Первый исполняемый срез до реального аудита

**Принято для начала реализации.** Пока reference competitions и бюджет не выбраны, реализуется узкий
offline-инструмент M1, необходимый для будущего M0-аудита. Синтетические runs не засчитываются в пять реальных
baseline-runs. Это уточнение зависимости P1-01 от P0-03: инструмент сбора записей можно готовить раньше,
а итоговые ML adapter contracts утверждаются после реальных traces.

Реализованы предварительные Pydantic contracts с `schema_version=0`, JSON CLI и локальный Python subprocess
по протоколу `--spec/--output`. Такой протокол связывает существующий competition-script с telemetry без
преждевременного набора универсальных ML hooks. Финальные hooks из D-002 остаются задачей M2/M4.

Текущее имя distribution — `kaggle-agents-foundation`, версия `0.1.0.dev0`, установка из исходников;
публикация в package index не выполнена. Python 3.12 — целевой и проверенный runtime; package metadata
допускает 3.12–3.14, но расширение CI matrix идет отдельно.

Budget пока ограничивает wall time и attempts одного процесса. Нормализованные LLM usage/cost reports
принимаются от worker; неизвестные значения остаются null. Provider billing adapter, денежные/token caps
и persistent ledger не объявляются реализованными. SQLite и scheduler по D-005/D-004 следуют в M3/M5.

## D-009. Узкий локальный CSV-контракт

**Принято для раннего M2.** Чтобы проверить data plane без credentials и выбранного соревнования,
добавлен `DatasetSpec` v0 для train/test/sample_submission, одного строкового ID и одного числового prediction.
Имена колонок, bounds и пути принадлежат competition-проекту. Ядро предоставляет local manifest,
sampled profiler и structural submission validator; ML split/fit/predict остаются в example-script.

Статистика профиля явно отделяет first-N sample от полного row count. Raw rows/ID values в CLI и reports
не возвращаются. Форматы за пределами UTF-8 CSV и multi-output predictions добавляются по реальным cases.
`inspect` пока означает локальную инспекцию; Kaggle API, скачивание/cache и registry-bound validation — дальнейшие задачи.
