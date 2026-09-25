# Как подключать новое соревнование

Это целевой workflow после реализации M4–M6, а не инструкция для уже существующего CLI.

## 1. Создать отдельный проект

Разработчик устанавливает конкретный release основы и вызывает generator. Предлагаемый интерфейс:

```text
kaggle-agents init ./my-competition --competition <slug> --template tabular
kaggle-agents doctor --project ./my-competition
```

Финальные имена flags закрепляются в M4. Generator создает файлы и инструкции, записывает версию основы, не скачивает dataset, не запускает LLM и не создает удаленный GitHub-репозиторий без отдельного действия пользователя.

## 2. Структура созданного проекта

```text
my-competition/
  pyproject.toml + uv.lock  # foundation pin + собственный ML stack
  competition.yaml        # slug, files, schema, metric, adapter, policies
  configs/
    models.yaml           # provider/model routes для ролей
    runner.yaml           # resources, concurrency, storage locations
    experiments/          # baseline и отдельные гипотезы
  src/solution/
    adapter.py            # hooks основы
    features.py
    train.py
    predict.py
    metric.py
  state/
    competition_card.md   # rules, assumptions, validation protocol
    checkpoint.json       # generated, локальное runtime state
  research/cards/         # компактные проверенные findings
  tests/                  # metric, split, schema и smoke
  .opencode/              # совместимые role/tool wrappers
  AGENTS.md               # правила конкретного соревнования
  README.md
  .gitignore
  runs/                   # registry, artifacts, logs; вне Git
```

Datasets и cache располагаются по `runner.yaml` вне отслеживаемого кода. Checkpoint содержит runtime paths и по умолчанию исключается из Git; важные решения сохраняются отдельно в versioned competition card. Секреты находятся в окружении или credential store.

## 3. Заполнить конкретику

До первого обучения нужны:

- правила и URL competition, разрешение external data, data version;
- train/test/sample_submission, target и ID columns;
- metric, направление улучшения, реализация и небольшой проверочный пример;
- split protocol: random/stratified/group/time, seed, folds, leakage checks;
- budget: wall time, LLM usage/cost, compute, disk, retries;
- runner и model profile с точными IDs, settings и лимитами;
- submission schema и способ проверки соответствия ID.

Обязательные неизвестные значения отмечаются как незаполненные и блокируют запуск, а не подменяются молчаливыми defaults. Предварительное исследование правил допустимо до model run.

## 4. Дойти до baseline

Целевые команды:

```text
kaggle-agents inspect --project ./my-competition
kaggle-agents profile --project ./my-competition
kaggle-agents run --project ./my-competition --experiment baseline
kaggle-agents validate-submission --project ./my-competition --run <run-id>
```

Сначала reference tabular adapter проверяет весь путь; затем в `src/solution/` добавляются features, модели и собственные transformations. Общий runner продолжает записывать те же run contracts.

## 5. Подключить агентов и исследование

После фиксации baseline открывается OpenCode в каталоге competition-проекта. Оркестратор получает цель, бюджет, validation protocol и best run. Researchers ищут по разным направлениям; proposals попадают в общую очередь.

Новая гипотеза обычно меняет experiment config. Если нужен новый код, worker получает изолированную копию проекта и возвращает patch с проверками. Оркестратор сравнивает результаты, reviewer проверяет решения. Каждая ветка использует один и тот же validation contract.

Восстановление: `kaggle-agents resume --project ./my-competition` сверяет registry, checkpoint и runner jobs. Сессия может продолжаться без старого transcript.

## 6. Обновлять основу отдельно от решения

- Версия основы фиксируется в dependency и lockfile, template version — в метаданных проекта.
- Перед обновлением сохраняется backup registry и фиксируются текущие config/code versions.
- Миграция проверяется на копии state; после обновления выполняются doctor и baseline regression.
- Пользовательские adapters/prompts generator не перезаписывает. Template changes применяются через просматриваемый diff.
- Если для второго competition требуется изменение ядра, создается Issue в KaggleAgents с воспроизводимым case. Обходы через локальное редактирование установленного package не считаются поддержанным подключением.

Для первого выпуска onboarding измеряется от генерации до первого valid run с отдельным учетом настройки, загрузки и обучения. Документация должна перечислять все ручные шаги и необходимые credentials, не предполагая скрытой настройки машины разработчика.
