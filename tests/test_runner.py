import json
import subprocess
import sys
from pathlib import Path

import psutil
import pytest

from kaggle_agents.contracts import Budget, RunResult
from kaggle_agents.files import fingerprint
from kaggle_agents.runner import _attempt, load_specs, run_experiment


def execute(project, task, experiment, mode, **params):
    spec = experiment.model_copy(update={"params": {"mode": mode, **params}})
    return run_experiment(project, task, spec, project / "runs")


def attempts(result):
    return [
        json.loads(path.read_text())
        for path in sorted(Path(result.result_path).parent.glob("attempt-*/result.json"))
    ]


def test_offline_demo_is_repeatable_and_leaves_auditable_artifacts(project):
    task, spec = load_specs(project, "task.json", "experiment.json")
    first = run_experiment(project, task, spec, project / "runs")
    second = run_experiment(project, task, spec, project / "runs")
    assert first.run_id != second.run_id
    assert first.status == second.status == "SUCCEEDED"
    assert first.metric_value == second.metric_value
    assert first.metric_value > 0
    assert first.usage.total_tokens == 0
    assert first.usage.total_cost_usd == 0
    assert first.decision == "review"
    root = Path(first.result_path).parent
    assert RunResult.model_validate_json(Path(first.result_path).read_bytes()) == first
    provenance = json.loads((root / "provenance.json").read_text())
    assert provenance["inputs"]["train.csv"] == fingerprint(project / "train.csv")
    record = attempts(first)[0]
    artifact = record["artifacts"][0]
    assert (
        fingerprint(root / record["attempt_id"] / artifact["path"])["sha256"] == artifact["sha256"]
    )
    events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
    assert [event["event"] for event in events] == [
        "run_started",
        "attempt_started",
        "attempt_finished",
        "run_finished",
    ]


def test_retry_preserves_failure_and_charges_both_attempts(project, task, experiment):
    task = task.model_copy(update={"budget": Budget(max_wall_seconds=20, max_attempts=2)})
    experiment = experiment.model_copy(update={"retry_on": ["EXECUTION"]})
    result = execute(
        project,
        task,
        experiment,
        "fail_once",
        usage={
            "total_tokens": 10,
            "cost_usd": 0.025,
            "cost_source": "reported",
        },
    )
    records = attempts(result)
    assert result.status == "SUCCEEDED"
    assert [record["status"] for record in records] == ["FAILED", "SUCCEEDED"]
    assert records[0]["exit_code"] == 3
    assert records[0]["metric_value"] is None
    assert result.usage.total_cost_usd == 0.05
    assert result.usage.total_tokens == 20


def test_no_implicit_retries(project, task, experiment):
    task = task.model_copy(update={"budget": Budget(max_wall_seconds=20, max_attempts=3)})
    result = execute(project, task, experiment, "fail")
    assert result.attempt_count == 1
    assert result.decision == "reject"
    assert result.usage.total_cost_usd is None


def test_attempt_limit_stops_repeated_errors(project, task, experiment):
    task = task.model_copy(update={"budget": Budget(max_wall_seconds=20, max_attempts=2)})
    experiment = experiment.model_copy(update={"retry_on": ["EXECUTION"]})
    result = execute(project, task, experiment, "fail")
    assert result.status == "FAILED"
    assert result.attempt_count == 2
    assert result.usage.unknown_cost_attempts == 2


@pytest.mark.parametrize(
    "mode", ["bad_metric", "invalid_artifact", "invalid_json", "oversized", "no_output"]
)
def test_exit_zero_is_not_enough_for_success(project, task, experiment, mode):
    result = execute(project, task, experiment, mode)
    assert result.status == "FAILED"
    assert result.metric_value is None
    assert attempts(result)[0]["failure_code"] == "INVALID_RESULT"


def test_invalid_metric_does_not_erase_known_usage(project, task, experiment):
    result = execute(
        project,
        task,
        experiment,
        "bad_metric",
        usage={
            "total_tokens": 12,
            "cost_usd": 0.2,
            "cost_source": "estimated",
        },
    )
    assert result.status == "FAILED"
    assert result.usage.known_tokens == 12
    assert result.usage.estimated_cost_attempts == 1


def test_changed_data_invalidates_attempt(project, task, experiment):
    result = execute(project, task, experiment, "mutate_input")
    assert result.status == "FAILED"
    assert attempts(result)[0]["failure_code"] == "INPUT_CHANGED"


def test_timeout_leaves_record_and_kills_child(project, task, experiment):
    experiment = experiment.model_copy(update={"timeout_seconds": 1.0})
    result = execute(project, task, experiment, "spawn_timeout")
    assert result.status == "TIMED_OUT"
    assert result.metric_value is None
    assert result.wall_seconds < 10
    record = attempts(result)[0]
    assert record["failure_code"] == "TIMEOUT"
    child_pid = int((Path(result.result_path).parent / "attempt-001" / "child.pid").read_text())
    if psutil.pid_exists(child_pid):
        assert psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE


def test_run_wall_budget_limits_retries(project, task, experiment):
    task = task.model_copy(update={"budget": Budget(max_wall_seconds=0.8, max_attempts=10)})
    experiment = experiment.model_copy(update={"timeout_seconds": 0.3, "retry_on": ["TIMEOUT"]})
    result = execute(project, task, experiment, "timeout")
    assert result.status in {"TIMED_OUT", "BUDGET_EXHAUSTED"}
    assert result.attempt_count < 10
    assert result.wall_seconds < 5


def test_expired_reservation_does_not_start_process(project, task, experiment, monkeypatch):
    def forbidden_spawn(*args, **kwargs):
        raise AssertionError("Expired budget must not dispatch a worker")

    monkeypatch.setattr("kaggle_agents.runner.subprocess.Popen", forbidden_spawn)
    output = project / "expired-attempt"
    output.mkdir()
    expected = {
        name: fingerprint(project / name) for name in {experiment.script, *experiment.input_files}
    }
    result = _attempt(project, task, experiment, output, 0, expected)
    assert result.status == "TIMED_OUT"
    assert result.exit_code is None


def test_interrupt_while_waiting_cleans_up_and_returns_record(
    project, task, experiment, monkeypatch
):
    original_wait = subprocess.Popen.wait
    interrupted = []

    def interrupt_once(process, *args, **kwargs):
        if not interrupted:
            interrupted.append(process.pid)
            raise KeyboardInterrupt
        return original_wait(process, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "wait", interrupt_once)
    output = project / "interrupted-attempt"
    output.mkdir()
    expected = {
        name: fingerprint(project / name) for name in {experiment.script, *experiment.input_files}
    }
    result = _attempt(project, task, experiment, output, 10, expected)
    assert result.status == "INTERRUPTED"
    assert result.metric_value is None
    assert not psutil.pid_exists(interrupted[0])


def test_cli_outputs_one_compact_record_and_never_worker_logs(project):
    result = subprocess.run(
        [sys.executable, "-m", "kaggle_agents", "run", "--project", str(project)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) == 1
    assert json.loads(result.stdout)["status"] == "SUCCEEDED"
    assert "Completed offline" not in result.stdout


def test_cli_validation_error_is_structured_and_redacted(project):
    raw = json.loads((project / "task.json").read_text())
    raw["budget"]["max_wall_seconds"] = "secret-value-should-not-be-printed"
    (project / "task.json").write_text(json.dumps(raw))
    result = subprocess.run(
        [sys.executable, "-m", "kaggle_agents", "run", "--project", str(project)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == "INVALID_CONTRACT"
    assert "secret-value" not in result.stderr
    assert not (project / "runs").exists()
