import json

import pytest
from pydantic import ValidationError

from kaggle_agents.contracts import Budget, ExperimentSpec, TaskSpec, Usage, WorkerOutput
from kaggle_agents.files import load_json, project_file
from kaggle_agents.runner import load_specs


@pytest.mark.parametrize("value", [0, -1, True, "30", float("inf"), float("nan")])
def test_invalid_time_budget(value):
    with pytest.raises(ValidationError):
        Budget(max_wall_seconds=value)


@pytest.mark.parametrize("value", [0, 11, -1, True, "2"])
def test_invalid_attempt_budget(value):
    with pytest.raises(ValidationError):
        Budget(max_wall_seconds=30, max_attempts=value)


def test_unknown_schema_and_fields_are_rejected(task):
    data = task.model_dump()
    data["schema_version"] = "99"
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(data)
    data["schema_version"] = "0"
    data["budegt"] = {}
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("hypothesis", " "),
        ("seed", True),
        ("seed", -1),
        ("input_files", []),
        ("retry_on", ["INVALID_RESULT"]),
        ("split_id", "../other"),
    ],
)
def test_experiment_requires_a_reproducible_spec(experiment, field, value):
    data = experiment.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate(data)


@pytest.mark.parametrize("value", [float("inf"), float("nan"), "0.1", True])
def test_metric_must_be_finite_number(value):
    with pytest.raises(ValidationError):
        WorkerOutput(schema_version="0", metrics={"mae": value})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cost_usd": 0},
        {"cost_source": "reported"},
        {"cost_source": "not_applicable", "cost_usd": 0},
        {"cost_source": "not_applicable", "cost_usd": 1, "total_tokens": 0},
        {"cost_source": "reported", "cost_usd": -1},
        {"total_tokens": True},
    ],
)
def test_unknown_cost_is_never_silently_zero(kwargs):
    with pytest.raises(ValidationError):
        Usage(**kwargs)


@pytest.mark.parametrize(
    "relative", ["../task.json", "/etc/passwd", "C:/secret", "C:secret", "..\\task.json"]
)
def test_project_paths_cannot_escape(project, relative):
    with pytest.raises((ValueError, OSError)):
        project_file(project, relative)


def test_missing_script_rejected_before_run(project):
    (project / "baseline.py").unlink()
    with pytest.raises(OSError):
        load_specs(project, "task.json", "experiment.json")
    assert not (project / "runs").exists()


@pytest.mark.parametrize(
    "content",
    ['{"x": 1, "x": 2}', '{"x": NaN}', '{"x": Infinity}', '{"x": 1e999}', " " * 65537],
    ids=["duplicate", "nan", "infinity", "overflow", "oversized"],
)
def test_bounded_unambiguous_json(tmp_path, content):
    path = tmp_path / "input.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        load_json(path)


def test_symlink_outside_project_is_rejected(project, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"x": 1}))
    try:
        (project / "link.json").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode or elevated permission")
    with pytest.raises(ValueError):
        project_file(project, "link.json")
