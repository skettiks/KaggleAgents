# Архитектура переиспользуемой основы

Статус: целевой дизайн, реализация по [плану](development-plan.md). Уже работающий offline-срез описан в [implementation.md](implementation.md); он еще не реализует всю схему ниже. Решения: [decisions.md](decisions.md).

## 1. Граница между основой и соревнованием

Основа владеет исполнением и учетом, competition-проект — смыслом ML-задачи.

| Слой | В основе | В competition-проекте |
| --- | --- | --- |
| Постановка | Schema задачи, проверка обязательных полей | Rules, target, IDs, metric, budget, constraints |
| Данные | Download/cache, manifest, checksum, общие profiling primitives | Файлы, типы колонок, загрузчик нестандартного формата |
| ML | Runner lifecycle, fidelity, artifacts, compare interface | Split, preprocessing, features, train/predict, metric |
| Research | Search/fetch adapter, source cards, deduplication | Вопросы, источники, domain hypotheses |
| Агенты | Базовые role templates, task contracts, tool wrappers | Model profile, специализация ролей и лимиты |
| Состояние | Registry, очередь, checkpoints, миграции | Локальные записи runs и принятые решения |
| Submission | Общие проверки структуры и привязка к run | Ожидаемые columns, ID order, диапазоны, дополнительные checks |

Competition-код подключается явным Python entrypoint из конфигурации. Это доверенный код проекта: импорт adapter не является безопасным выполнением произвольного внешнего notebook.

## 2. Поток работы

```text
Task file / GitHub Issue
        |
Competition config + rules + data manifest
        |
Profile -> fixed validation protocol -> reproducible baseline
        |
Orchestrator (strong model)
        |
        +-- researcher: competition solutions --+
        +-- researcher: methods and literature --+--> proposal registry
        +-- researcher: data/feature hypotheses -+
                                                    |
                                           dedup + budget + ranking
                                                    |
                                              experiment queue
                                                    |
                           +------------------------+-------------------+
                           |                                            |
                     config-only run                         isolated coding worker
                           |                                  patch + test evidence
                           +------------------------+-------------------+
                                                    |
                                    deterministic scheduler and runner
                                                    |
                                smoke -> one fold -> full validation
                                                    |
                                      reviewer + promotion decision
                                                    |
                                    final fit -> validate submission
                                                    |
                                            human submission
```

Источники состояния — registry и versioned files. Оркестратор получает краткие результаты и ссылки на artifacts; полный transcript между ролями не передается.

## 3. Роли и измеримые результаты

| Роль | Выход | Граница ответственности | Метрика пользы |
| --- | --- | --- | --- |
| Orchestrator | План, выбранные proposals, решения stop/promote | Распределяет бюджет, не заменяет resource scheduler | Best score under budget, cost-to-baseline |
| Researcher, несколько instances | Proposal с источниками и дешевой проверкой | Read-only research, без credentials и исполнения web-кода | Доля уникальных применимых гипотез и цена принятой гипотезы |
| Coding worker | Patch/config, tests, описание запуска | Свой worktree; metric/split contract не меняет самостоятельно | Доля корректных smoke-runs, retries и стоимость реализации |
| Reviewer | APPROVE/CHANGE с проверяемыми причинами | Read-only, отдельная сессия, без self-approval worker | Обнаруженные дефекты validation и воспроизводимости |

Отдельный постоянный data-analyst для v0.1 не нужен: интерпретация компактного профиля входит в работу оркестратора/researcher. Расширение ролей требует собственной метрики пользы.

Для разных proposals можно сохранять связь researcher ↔ worker через `proposal_id`, но выделение worker идет из общего пула. Это сохраняет обратную связь по идее без простаивающих «личных» coders.

## 4. Контракты данных и инструментов

Минимальные версии форматов фиксируются после первого end-to-end сценария:

- `TaskSpec`: competition, цель, rules reference, metric direction, ограничения и бюджеты.
- `Proposal`: question, claim, sources с датами, applicability, risk, experiment, expected cost.
- `ExperimentSpec`: proposal/parent IDs, код и конфигурация, data manifest, validation protocol, seed, fidelity и budget.
- `ExperimentResult`: status, fold metrics/aggregate, время, usage/cost, errors, artifacts и decision.
- `Checkpoint`: state, best eligible run, queue references, spent/reserved budget, blockers и next actions.

Идентификаторы `task_id -> proposal_id -> experiment_id -> attempt_id` связывают исследование, реализацию и все повторные попытки. Повторная попытка не скрывает прошлую ошибку или стоимость.

Общий набор инструментов: `inspect_competition`, `download_file`, `profile_dataset`, `run_experiment`, `compare_runs`, `validate_submission`, `resume`. Они возвращают ограниченный JSON; stdout/stderr обучения остаются artifacts.

Competition adapter реализует hooks `profile`, `make_split`, `train`, `predict`, `evaluate` и при необходимости дополнительные submission checks. Точные Python signatures определяются в M2, не изобретаются отдельно для каждого агента. Общий runner управляет процессом и ресурсами, а adapter возвращает метрики и пути к результатам.

## 5. Параллелизм и восстановление

- До dispatch scheduler атомарно резервирует бюджет и CPU/RAM/GPU capacity.
- Начальные верхние границы: три research tasks, один coding worker, один training job; это defaults, а не гарантия одновременного запуска.
- Config-only experiments сразу идут в runner. Новый код сначала проходит проверки в отдельном worktree и исполняется как immutable snapshot.
- Дедупликация использует fingerprint кода/config, data, split, seed и fidelity; явный повтор для оценки стабильности остается возможным.
- Workers отправляют events одному coordinator. SQLite находится локально у него; удаленные processes не пишут напрямую в DB.
- Lease/heartbeat определяет зависший run; при restart coordinator сверяет процессы и artifacts перед retry.
- Убийство по timeout распространяется на дочерние процессы. Прерванные attempts сохраняются со статусом и затратами.
- Изменения общих hooks проходят review и последовательную интеграцию; worktrees не сливаются автоматически по лучшему score.

Git worktree предотвращает файловые конфликты, но доступ к secrets, сети и ресурсам ограничивается отдельно окружением процесса/container. Research работает без Kaggle credentials.

## 6. Сравнение и продвижение

Состояния competition: `DISCOVERED -> PROFILED -> BASELINED -> ITERATING -> REVIEW -> READY_TO_SUBMIT`; блокировки и паузы сохраняются отдельно. У attempts есть `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED`, `INTERRUPTED`.

Сравниваются runs с одинаковым protocol ID, data version и сопоставимой fidelity. Успешный smoke подтверждает исполнимость, но не превосходство над full-CV baseline. Metric вычисляется детерминированно, LLM объясняет решение.

До начала поиска фиксируются noise threshold, направление улучшения и лимит итераций. Многократный поиск по одному split может переобучить validation; лучшие варианты дополнительно проверяются на заранее выделенном holdout или robustness protocol. Leaderboard хранится отдельным сигналом.

## 7. Модели и обновления

Логические маршруты: `orchestrator`, `research`, `coding`, `review`. Model profile хранит provider, точный model ID/revision, generation settings и limits. Общие templates не содержат постоянно меняющегося «лучшего» model ID.

Сильная GPT — исходный кандидат для orchestration; coding/research challengers выбираются по фиксированным задачам и полному cost-to-success. Reviewer использует отдельную сессию, при возможности другое семейство модели. Это уменьшает общие ошибки, но не заменяет тесты.

Обновление модели выполняется между сериями экспериментов: availability/tool-call check -> небольшой внутренний eval -> явное обновление profile. Автоматическое переключение на alias `latest` внутри run запрещено. Неизвестная стоимость отмечается как unknown, а не как нулевая.
