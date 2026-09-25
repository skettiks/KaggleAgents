# Реализованный срез: локальные данные, эксперименты и telemetry

Версия пакета: `0.1.0.dev0`. Контракты: предварительная `schema_version: "0"`.
Задачи разработки: [telemetry #1](https://github.com/skettiks/KaggleAgents/issues/1),
[CSV tools #2](https://github.com/skettiks/KaggleAgents/issues/2).

## Установка и запуск

Требуется `uv` ([инструкция установки](https://docs.astral.sh/uv/getting-started/installation/)).
Команды выполняются из корня репозитория. `uv` установит Python 3.12, создаст `.venv` и
установит зависимости из `uv.lock`:

```text
uv sync --locked --python 3.12
uv run --locked kaggle-agents --version
uv run --locked kaggle-agents check --project examples/offline
uv run --locked kaggle-agents inspect --project examples/offline
uv run --locked kaggle-agents profile --project examples/offline
uv run --locked kaggle-agents run --project examples/offline
uv run --locked kaggle-agents validate-submission --project examples/offline --file runs/artifacts/<run_id>/attempt-001/submission.csv
```

Если `.venv` уже подготовлена, Windows CLI можно вызвать напрямую:

```powershell
.\.venv\Scripts\kaggle-agents.exe run --project examples/offline
```

В последней команде замените `<run_id>` на ID успешного запуска.

`check` проверяет task/experiment contracts и существование script/input files без запуска кода.
`run` сначала выполняет те же проверки, затем запускает локальный Python-script. По умолчанию
он читает `task.json` и `experiment.json`; `--task` и `--experiment` принимают пути относительно
`--project`. `--output-dir` задает каталог artifacts относительно проекта либо абсолютный путь.

Exit codes: `0` — успех, `1` — failed/budget exhausted, `2` — ошибка входа или I/O,
`124` — timeout, `130` — interruption во время ожидания процесса. stdout содержит одну строку
JSON; ошибки входа идут в stderr в JSON-формате. Вывод worker остается в файлах.

## CSV manifest, profiler и submission

Конфигурация `dataset.json` задает `train`, `test`, `sample_submission`, `id_column`, `target_column`,
`prediction_column` и необязательные `min_prediction`/`max_prediction`. Используется та же версия schema `0`.
Пример конфигурации находится в [examples/offline/dataset.json](../examples/offline/dataset.json).
Пути относительны competition-проекту. Другой файл конфигурации передается через `--dataset`.

```text
kaggle-agents inspect --project <project>
kaggle-agents profile --project <project> --max-rows 1000
kaggle-agents validate-submission --project <project> --file <relative-submission.csv>
```

- `inspect` работает с уже имеющимися локальными файлами: проверяет headers, вычисляет SHA-256,
  размеры, общий `data_hash` и отдельный `config_hash`. Это пока не Kaggle API inspector и не downloader/cache.
- `profile` строит агрегаты по первым N строкам каждого CSV: missingness, cardinality, количество
  числовых/non-finite значений, min/max и предварительный тип. По умолчанию N=1000, максимум 10000.
  Для неполного сканирования `row_count=null`, `scan_complete=false`. Это не случайная выборка и не leakage audit.
  Полный hash файла требует отдельного прохода по всем байтам; ограничение N относится к статистике.
- `validate-submission` требует точный порядок columns из sample, одинаковое число строк, непустые
  уникальные IDs и точный порядок IDs из sample. Множество sample IDs должно совпадать с test; при этом порядок
  строк sample и test может различаться. ID сравниваются как строки, включая ведущие нули.
- Все predictions должны быть конечными числами и попадать в заданные bounds. Поддерживается один числовой
  выход на ID: например, regression или вероятность бинарного класса. Multiclass/multi-target/string labels
  и проверка допустимых дискретных значений пока не поддерживаются.

CSV должен быть UTF-8 (BOM допускается), с comma delimiter, до 200 уникальных непустых headers длиной до
128 символов. Quoted commas/newlines поддерживаются. Некорректная ширина строк отклоняется. Train содержит
ID и target; test содержит тот же набор feature columns и ID без target; sample — ровно ID и prediction.
Validator ограничен миллионом строк. Достижение ограничения — ошибка, а не успешная частичная проверка.

В stdout нет исходных строк или значений IDs: profile возвращает только краткие counts и путь к полному
JSON; validation report содержит коды/номера строк, общие counters и максимум 20 примеров ошибок.
Manifest, profile и submission report сохраняются в `runs/data/<operation_id>/`.
После profiling/validation повторно проверяются hashes источников; изменение файлов отклоняет результат.

Проверка файла не означает promotion и пока не связана с registry: `--file` может указывать на любой CSV
внутри проекта. Будущий интерфейс `--run` еще не реализован. При ошибке submission CLI возвращает код `1`,
при неверном dataset/config — `2`. Автоматической отправки в Kaggle нет.

## Как подключить свой experiment-script

За основу можно взять [offline example](../examples/offline/README.md). Пакет устанавливается
в окружение competition-проекта; script запускается тем же Python, что и CLI.

В task задаются `task_id`, competition, objective, rules reference, имя/направление metric и budget.
В experiment обязательны hypothesis, split ID, seed, путь к Python-script, input files и timeout.
Произвольные ML-настройки передаются в `params`.

Протокол вызова:

```text
python <script.py> --spec <absolute-request.json> --output <absolute-output.json>
```

Рабочий каталог — competition-проект. Request содержит `schema_version`, `task`, `experiment`
и локальный `attempt_id` (глобальная ссылка на попытку — пара `run_id` + `attempt_id`).
Worker записывает результат в `--output`, дополнительные artifacts — рядом с ним:

```json
{
  "schema_version": "0",
  "metrics": {"mae": 0.25},
  "usage": {
    "scope": "llm",
    "total_tokens": 120,
    "cost_usd": null,
    "cost_source": "unknown"
  },
  "artifacts": ["predictions.json"]
}
```

Metric должна совпадать с именем из task и быть конечным числом. Для artifacts используются
относительные пути внутри каталога попытки; проверки отклоняют выход за его пределы и ссылки
на зарезервированные файлы runner. Script/input paths также должны находиться внутри проекта.
JSON входов и worker output ограничен 64 KiB на файл; дубли ключей, NaN/Infinity и лишние поля
контрактов отклоняются. Содержимое dataset через этот JSON не передается.

## Что сохраняется

```text
runs/artifacts/<run_id>/
  task.json, experiment.json  # снимки конфигурации
  provenance.json             # git commit/dirty, versions, environment, input/script hashes
  events.jsonl                # append-only lifecycle events
  result.json                 # итоговый RunResult
  attempt-001/
    request.json, output.json
    stdout.log, stderr.log
    result.json               # статус, ошибка, metric, usage, artifact checksums
    ...worker artifacts
```

Повторные попытки не перезаписывают предыдущие. Повторный CLI-вызов создает новый `run_id`.
Перед запуском и после попытки сверяются hashes объявленных inputs/script. Изменение данных
делает попытку неуспешной. Импортируемые script-ом модули отдельно не копируются; их версия
определяется Git/environment. `git_dirty=true` или отсутствие commit означает, что одной ссылки
на commit недостаточно для воспроизведения. Снимок всего исходного кода появится позже.

Успешное исполнение получает `decision=review`, а не автоматическое одобрение ML-улучшения.
Наличие корректной числовой метрики само по себе не доказывает правильность split или отсутствие leakage.

## Бюджеты и учет стоимости

- `max_wall_seconds` — временной бюджет исполнения после проверки входов, включая provenance и retries.
- `max_attempts` — от 1 до 10, по умолчанию 1. Увеличение лимита само по себе не включает retries.
- `timeout_seconds` — предел одной попытки, сокращается до оставшегося общего бюджета.
- `retry_on` — явный список `EXECUTION` и/или `TIMEOUT`; неверные результаты не повторяются автоматически.
- Таймер использует monotonic clock. Cleanup и файловый I/O могут выйти за deadline; это не hard real-time scheduler.
- Usage берется из worker output, включая неудачную попытку, если отчет сохранился. Прямого billing adapter пока нет.
- `scope=llm`: в эти суммы не входят расходы CPU/GPU, storage и web API.
- Отсутствующий usage или неизвестная стоимость сохраняются как `null`. Отдельно доступны известная сумма,
  число попыток без оценки и число estimated-cost attempts. Cache/reasoning tokens не нужно повторно прибавлять
  к `total_tokens`, если provider уже включил их в итог.
- `not_applicable` допускается только с явными нулями, когда LLM не вызывалась.

Ledger пока существует в памяти одного запуска и выгружается в events/results. Долларовые/token caps,
постоянный общий бюджет нескольких сессий и атомарные reservations для параллельных workers еще не реализованы.

## Границы текущей реализации

Скрипт считается доверенным: он наследует окружение и права текущего процесса. Runner не является sandbox.
Не помещайте credentials в specs/params и не печатайте их в worker logs. Прямых Kaggle/model API calls в основе нет.

По timeout/KeyboardInterrupt POSIX runner останавливает process group; на Windows — обнаруженное дерево
дочерних процессов. Это best-effort cleanup, а не Windows Job Object: escaped/detached processes и фоновые
процессы, оставленные уже завершившимся worker, пока не изолируются. CPU/RAM/GPU/disk quotas и log rotation — M2+.

SQLite registry, recovery после падения coordinator, generator `init`, `doctor`, Kaggle download/cache,
agent roles и promotion пока находятся в плане. Их будущие интерфейсы описаны отдельно
в [архитектуре](architecture.md) и [проекте соревнования](competition-project.md).

## Проверки разработки

```text
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv build
```

GitHub Actions настроен для Python 3.12 на Windows и Linux. Job устанавливает зависимости, после чего tests
и synthetic smoke не обращаются к Kaggle или LLM. Проверки включают контракты, path traversal, finite metrics,
неизвестную стоимость, retries, timeout/child cleanup, CSV-профиль, submission invariants и сохранение artifacts.
На Windows тест создания симлинка
пропускается, если у процесса нет соответствующих прав.
