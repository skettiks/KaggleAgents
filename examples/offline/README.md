# Offline tabular example

This directory is a tiny synthetic competition-side project. The hand-authored rows in
`train.csv` and `test.csv` are not Kaggle data. The example tests the foundation's execution protocol;
it is not one of the real competition audit runs required by M0.

`dataset.json` owns the file/column mapping and prediction bounds. `baseline.py` owns the
seeded holdout, train-only mean predictor and MAE calculation. After validation it fits the
mean on all training rows and writes a submission in sample order. The foundation validates
the inputs, runs the script, records results and checks the submission structure.

From the foundation repository root, after installing dependencies:

```text
uv run --locked kaggle-agents check --project examples/offline
uv run --locked kaggle-agents inspect --project examples/offline
uv run --locked kaggle-agents profile --project examples/offline --max-rows 100
uv run --locked kaggle-agents run --project examples/offline
uv run --locked kaggle-agents validate-submission --project examples/offline --file runs/artifacts/<run_id>/attempt-001/submission.csv
```

Replace `<run_id>` with the ID printed by `run`. Execution artifacts go under
`examples/offline/runs/artifacts/`; manifests, profiles and validation reports go under
`examples/offline/runs/data/`. Both are ignored by Git. Each invocation writes to a new directory.
The terminal prints one JSON summary; logs and predictions stay in files.

On PowerShell, run and validate without copying the ID:

```powershell
$run = .\.venv\Scripts\kaggle-agents.exe run --project examples/offline | ConvertFrom-Json
if ($LASTEXITCODE -eq 0) {
    .\.venv\Scripts\kaggle-agents.exe validate-submission --project examples/offline --file "runs/artifacts/$($run.run_id)/attempt-001/submission.csv"
}
```

There are no LLM calls. Reported LLM tokens and cost are explicitly zero with
`cost_source=not_applicable`. CPU/electricity/storage costs are not measured by this example.
