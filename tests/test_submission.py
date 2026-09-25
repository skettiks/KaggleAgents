import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from kaggle_agents.contracts import DatasetSpec
from kaggle_agents.data import DataError, inspect_dataset, profile_dataset
from kaggle_agents.runner import load_specs, run_experiment
from kaggle_agents.submission import validate_submission


def write_csv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def candidate(project):
    path = project / "candidate.csv"
    write_csv(path, ["row_key", "target_value"], [[f"test-{n:02d}", 10.5] for n in range(1, 5)])
    return path


def check(project, dataset, candidate):
    return validate_submission(
        project,
        dataset,
        inspect_dataset(project, dataset),
        candidate.relative_to(project).as_posix(),
    )


def test_complete_example_produces_valid_submission(project, dataset):
    task, experiment = load_specs(project, "task.json", "experiment.json")
    result = run_experiment(project, task, experiment, project / "runs")
    assert result.status == "SUCCEEDED"
    candidate = Path(result.result_path).parent / "attempt-001" / "submission.csv"
    report = check(project, dataset, candidate)
    assert report["valid"]
    assert report["scan_complete"]
    assert report["actual_rows_scanned"] == 4
    assert report["error_count"] == 0


@pytest.mark.parametrize(
    "rows,code",
    [
        ([["test-01", 1]], "ROW_COUNT_MISMATCH"),
        ([[f"test-{n:02d}", 1] for n in range(1, 6)], "ROW_COUNT_MISMATCH"),
        ([[f"test-{n:02d}", 1] for n in [2, 1, 3, 4]], "SUBMISSION_ID_ORDER_MISMATCH"),
        ([[f"test-{n:02d}", 1] for n in [1, 1, 3, 4]], "SUBMISSION_ID_DUPLICATE"),
        ([["", 1], ["test-02", 1], ["test-03", 1], ["test-04", 1]], "SUBMISSION_ID_MISSING"),
    ],
)
def test_id_and_row_invariants(project, dataset, candidate, rows, code):
    write_csv(candidate, ["row_key", "target_value"], rows)
    report = check(project, dataset, candidate)
    assert report["valid"] is False
    assert code in report["error_counts"]


@pytest.mark.parametrize(
    "prediction,code",
    [
        ("", "INVALID_PREDICTION"),
        ("word", "INVALID_PREDICTION"),
        ("NaN", "NON_FINITE_PREDICTION"),
        ("inf", "NON_FINITE_PREDICTION"),
        ("-inf", "NON_FINITE_PREDICTION"),
        ("1e999", "NON_FINITE_PREDICTION"),
        (-0.01, "PREDICTION_OUT_OF_RANGE"),
        (25.01, "PREDICTION_OUT_OF_RANGE"),
    ],
)
def test_prediction_invariants(project, dataset, candidate, prediction, code):
    write_csv(
        candidate, ["row_key", "target_value"], [[f"test-{n:02d}", prediction] for n in range(1, 5)]
    )
    report = check(project, dataset, candidate)
    assert report["valid"] is False
    assert report["error_counts"][code] == 4


def test_column_order_is_exact(project, dataset, candidate):
    write_csv(candidate, ["target_value", "row_key"], [[1, "test-01"]])
    report = check(project, dataset, candidate)
    assert not report["valid"]
    assert report["error_counts"] == {"SUBMISSION_COLUMNS_MISMATCH": 1}


def test_sample_order_can_differ_from_test_order(project, dataset, candidate):
    rows = [[f"test-{n:02d}", 1] for n in [4, 2, 3, 1]]
    write_csv(project / dataset.sample_submission, ["row_key", "target_value"], rows)
    write_csv(candidate, ["row_key", "target_value"], rows)
    assert check(project, dataset, candidate)["valid"]


def test_matching_candidate_cannot_hide_wrong_sample_ids(project, dataset, candidate):
    rows = [["private-wrong-id", 1], ["test-02", 1], ["test-03", 1], ["test-04", 1]]
    write_csv(project / dataset.sample_submission, ["row_key", "target_value"], rows)
    write_csv(candidate, ["row_key", "target_value"], rows)
    report = check(project, dataset, candidate)
    assert not report["valid"]
    assert "SAMPLE_TEST_ID_MISMATCH" in report["error_counts"]
    assert "private-wrong-id" not in json.dumps(report)


def test_duplicate_test_ids_are_rejected(project, dataset, candidate):
    write_csv(project / dataset.test, ["row_key", "feature_x"], [["test-01", 1], ["test-01", 2]])
    with pytest.raises(DataError, match="TEST_ID_DUPLICATE"):
        check(project, dataset, candidate)


def test_empty_submission_never_passes(project, dataset, candidate):
    write_csv(candidate, ["row_key", "target_value"], [])
    report = check(project, dataset, candidate)
    assert not report["valid"]
    assert report["actual_rows_scanned"] == 0


def test_malformed_rows_are_invalid_not_ignored(project, dataset, candidate):
    candidate.write_text("row_key,target_value\ntest-01,1,extra\n")
    report = check(project, dataset, candidate)
    assert not report["valid"]
    assert not report["scan_complete"]
    assert "ROW_WIDTH_MISMATCH" in report["error_counts"]


def test_issue_output_is_bounded(project, dataset, candidate):
    write_csv(candidate, ["row_key", "target_value"], [["private-id", "NaN"]] * 100)
    report = check(project, dataset, candidate)
    assert not report["valid"]
    assert report["error_count"] > 100
    assert len(report["issues"]) == 20
    assert len(json.dumps(report)) < 4000
    assert "private-id" not in json.dumps(report)


def test_row_limit_fails_closed(project, dataset, candidate, monkeypatch):
    monkeypatch.setattr("kaggle_agents.submission.MAX_VALIDATION_ROWS", 2)
    with pytest.raises(DataError, match="VALIDATION_ROW_LIMIT_EXCEEDED"):
        check(project, dataset, candidate)


def test_column_names_are_competition_configuration(project):
    config = {
        "schema_version": "0",
        "train": "train.csv",
        "test": "test.csv",
        "sample_submission": "sample_submission.csv",
        "id_column": "custom_id",
        "target_column": "label",
        "prediction_column": "estimate",
    }
    dataset = DatasetSpec.model_validate(config)
    write_csv(project / dataset.train, ["custom_id", "feature", "label"], [["t1", 2, 7]])
    write_csv(project / dataset.test, ["custom_id", "feature"], [["001", 3], ["002", 4]])
    write_csv(
        project / dataset.sample_submission, ["custom_id", "estimate"], [["001", 0], ["002", 0]]
    )
    candidate = project / "candidate.csv"
    write_csv(candidate, ["custom_id", "estimate"], [["001", 7], ["002", 7]])
    manifest = inspect_dataset(project, dataset)
    assert (
        profile_dataset(project, manifest)["files"]["train"]["columns"]["label"]["numeric_max"] == 7
    )
    assert check(project, dataset, candidate)["valid"]
    write_csv(candidate, ["custom_id", "estimate"], [["1", 7], ["2", 7]])
    assert not check(project, dataset, candidate)["valid"]


def test_validation_cli_returns_report_and_failure_exit_code(project, candidate):
    write_csv(candidate, ["row_key", "target_value"], [["test-01", "NaN"]])
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "kaggle_agents",
            "validate-submission",
            "--project",
            str(project),
            "--file",
            "candidate.csv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    summary = json.loads(result.stdout)
    assert not summary["valid"]
    assert Path(summary["report_path"]).is_file()
    assert "NaN" not in result.stdout
