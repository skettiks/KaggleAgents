"""A trusted local Python script runner for audit telemetry, not a sandbox or ML framework."""

import hashlib
import importlib.metadata
import json
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import psutil
from pydantic import ValidationError

from kaggle_agents import __version__
from kaggle_agents.contracts import (
    Artifact,
    AttemptResult,
    ExperimentSpec,
    RunResult,
    Status,
    TaskSpec,
    Usage,
    WorkerOutput,
)
from kaggle_agents.files import fingerprint, load_json, project_file, write_json
from kaggle_agents.telemetry import BudgetExhausted, BudgetLedger, EventLog, timestamp


def load_specs(
    project: Path, task_path: str, experiment_path: str
) -> tuple[TaskSpec, ExperimentSpec]:
    task = TaskSpec.model_validate(load_json(project_file(project, task_path)))
    experiment = ExperimentSpec.model_validate(load_json(project_file(project, experiment_path)))
    script = project_file(project, experiment.script)
    if script.suffix != ".py":
        raise ValueError("The experiment script must be a Python file")
    for path in experiment.input_files:
        project_file(project, path)
    return task, experiment


def _git(project: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _inputs(project: Path, experiment: ExperimentSpec) -> dict:
    return {
        path: fingerprint(project_file(project, path))
        for path in sorted({experiment.script, *experiment.input_files})
    }


def _provenance(project: Path, experiment: ExperimentSpec) -> dict:
    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": sorted(
            (dist.metadata["Name"], dist.version)
            for dist in importlib.metadata.distributions()
            if dist.metadata["Name"]
        ),
    }
    dirty = _git(project, "status", "--porcelain", "--untracked-files=normal")
    return {
        "foundation_version": __version__,
        "git_commit": _git(project, "rev-parse", "HEAD"),
        "git_dirty": None if dirty is None else bool(dirty),
        "environment": environment,
        "environment_sha256": hashlib.sha256(
            json.dumps(environment, sort_keys=True).encode()
        ).hexdigest(),
        "inputs": _inputs(project, experiment),
    }


def _stop(process: subprocess.Popen) -> None:
    """Kill a POSIX process group, or the currently discoverable Windows process tree."""
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        try:
            parent = psutil.Process(process.pid)
            children = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            children = []
        for child in reversed(children):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        if process.poll() is None:
            process.kill()
        psutil.wait_procs(children, timeout=5)
    process.wait(timeout=5)


def _attempt(
    project: Path,
    task: TaskSpec,
    experiment: ExperimentSpec,
    directory: Path,
    timeout: float,
    expected_inputs: dict,
) -> AttemptResult:
    started_at = timestamp()
    started = time.monotonic()
    status: Status = "FAILED"
    failure = None
    exit_code = None
    metric = None
    usage = Usage()
    artifacts: list[Artifact] = []
    process = None
    request_path = directory / "request.json"
    output_path = directory / "output.json"
    write_json(
        request_path,
        {
            "schema_version": "0",
            "task": task.model_dump(),
            "experiment": experiment.model_dump(),
            "attempt_id": directory.name,
        },
    )
    command = [
        sys.executable,
        str(project / experiment.script),
        "--spec",
        str(request_path),
        "--output",
        str(output_path),
    ]
    try:
        with (
            (directory / "stdout.log").open("wb") as stdout,
            (directory / "stderr.log").open("wb") as stderr,
        ):
            if timeout <= time.monotonic() - started:
                status, failure = "TIMED_OUT", "TIMEOUT"
            else:
                process = subprocess.Popen(
                    command,
                    cwd=project,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=os.name != "nt",
                )
                try:
                    process.wait(timeout=max(0, timeout - (time.monotonic() - started)))
                except subprocess.TimeoutExpired:
                    _stop(process)
                    status, failure = "TIMED_OUT", "TIMEOUT"
                except KeyboardInterrupt:
                    _stop(process)
                    status, failure = "INTERRUPTED", "INTERRUPTED"
                exit_code = process.returncode
        if failure is None and exit_code != 0:
            failure = "EXECUTION"
    except OSError:
        failure = "ENV"
    finally:
        if process is not None and process.poll() is None:
            _stop(process)

    # Reported usage is retained even when the process fails or the metric is invalid.
    try:
        raw = load_json(output_path)
        if isinstance(raw, dict) and "usage" in raw:
            try:
                usage = Usage.model_validate(raw["usage"])
            except ValidationError:
                pass
        if failure is None:
            output = WorkerOutput.model_validate(raw)
            metric = output.metrics[task.metric.name]
            for relative in output.artifacts:
                path = project_file(directory, relative)
                if path in {
                    output_path,
                    request_path,
                    directory / "stdout.log",
                    directory / "stderr.log",
                    directory / "result.json",
                }:
                    raise ValueError("Reserved runner file is not a worker artifact")
                artifacts.append(Artifact(path=relative, **fingerprint(path)))
            status = "SUCCEEDED"
    except (OSError, ValueError, KeyError, RecursionError):
        if failure is None:
            failure = "INVALID_RESULT"
    try:
        if _inputs(project, experiment) != expected_inputs:
            status, failure = "FAILED", "INPUT_CHANGED"
    except (OSError, ValueError):
        status, failure = "FAILED", "INPUT_CHANGED"
    if failure is not None:
        metric = None
        artifacts = []
    return AttemptResult(
        attempt_id=directory.name,
        status=status,
        failure_code=failure,
        exit_code=exit_code,
        started_at=started_at,
        finished_at=timestamp(),
        wall_seconds=time.monotonic() - started,
        metric_value=metric,
        usage=usage,
        artifacts=artifacts,
    )


def run_experiment(
    project: Path,
    task: TaskSpec,
    experiment: ExperimentSpec,
    output_root: Path,
) -> RunResult:
    project = project.resolve()
    ledger = BudgetLedger(task.budget)
    provenance = _provenance(project, experiment)
    run_id = uuid4().hex
    directory = output_root.resolve() / run_id
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "task.json", task)
    write_json(directory / "experiment.json", experiment)
    write_json(directory / "provenance.json", provenance)
    events = EventLog(directory / "events.jsonl", run_id)
    events.emit("run_started", task_id=task.task_id, experiment_id=experiment.experiment_id)
    attempts: list[AttemptResult] = []
    status: Status = "BUDGET_EXHAUSTED"
    while True:
        try:
            timeout = ledger.reserve(experiment.timeout_seconds)
        except BudgetExhausted:
            events.emit("budget_exhausted", attempts=ledger.attempts)
            break
        attempt_dir = directory / f"attempt-{ledger.attempts:03d}"
        attempt_dir.mkdir()
        events.emit("attempt_started", attempt_id=attempt_dir.name, reserved_seconds=timeout)
        attempt = _attempt(
            project,
            task,
            experiment,
            attempt_dir,
            min(timeout, ledger.remaining),
            provenance["inputs"],
        )
        if attempt.status == "SUCCEEDED" and ledger.remaining <= 0:
            attempt = attempt.model_copy(
                update={
                    "status": "TIMED_OUT",
                    "failure_code": "TIMEOUT",
                    "metric_value": None,
                    "artifacts": [],
                }
            )
        ledger.settle(attempt.usage)
        attempts.append(attempt)
        write_json(attempt_dir / "result.json", attempt)
        events.emit(
            "attempt_finished",
            attempt_id=attempt.attempt_id,
            status=attempt.status,
            failure_code=attempt.failure_code,
            wall_seconds=attempt.wall_seconds,
            usage=attempt.usage.model_dump(),
        )
        status = attempt.status
        if status == "SUCCEEDED" or attempt.failure_code not in experiment.retry_on:
            break
        # A failure remains visible even if no further retry fits the budget.
        if ledger.attempts >= task.budget.max_attempts or ledger.remaining <= 0:
            events.emit("budget_exhausted", attempts=ledger.attempts)
            break
    result = RunResult(
        run_id=run_id,
        task_id=task.task_id,
        experiment_id=experiment.experiment_id,
        status=status,
        decision="review" if status == "SUCCEEDED" else "reject",
        rationale=(
            "Execution succeeded; validation quality requires review."
            if status == "SUCCEEDED"
            else "No successful attempt within the run budget."
        ),
        metric=task.metric,
        metric_value=attempts[-1].metric_value if attempts else None,
        wall_seconds=ledger.elapsed,
        attempt_count=len(attempts),
        usage=ledger.usage_summary(),
        result_path=str(directory / "result.json"),
    )
    write_json(directory / "result.json", result)
    events.emit("run_finished", status=result.status, attempt_count=result.attempt_count)
    return result
