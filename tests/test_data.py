import csv
import json

import pytest
from pydantic import ValidationError

from kaggle_agents.contracts import DatasetSpec
from kaggle_agents.data import DataError, inspect_dataset, profile_dataset


def test_manifest_hashes_files_without_returning_rows(project, dataset):
    first = inspect_dataset(project, dataset)
    second = inspect_dataset(project, dataset)
    assert first == second
    assert len(first["data_hash"]) == 64
    assert first["files"]["train"]["columns"] == ["row_key", "feature_x", "target_value"]
    assert "train-01" not in json.dumps(first)
    path = project / dataset.train
    path.write_text(path.read_text().replace("train-01,0,2", "train-01,0,3"))
    changed = inspect_dataset(project, dataset)
    assert changed["data_hash"] != first["data_hash"]


def test_profile_distinguishes_partial_and_complete_counts(project, dataset):
    manifest = inspect_dataset(project, dataset)
    partial = profile_dataset(project, manifest, max_rows=3)
    train = partial["files"]["train"]
    assert train["rows_scanned"] == 3
    assert train["row_count"] is None
    assert train["scan_complete"] is False
    assert train["columns"]["target_value"]["numeric_max"] == 5
    complete = profile_dataset(project, manifest, max_rows=12)
    train = complete["files"]["train"]
    assert train["row_count"] == 12
    assert train["scan_complete"] is True
    assert train["columns"]["target_value"]["numeric_min"] == 2
    assert train["columns"]["target_value"]["numeric_max"] == 19
    assert "train-01" not in json.dumps(complete)


def test_missing_mixed_and_nonfinite_cells_are_explicit(project, dataset):
    (project / dataset.train).write_text(
        "row_key,feature_x,target_value\na,,2\nb,nan,3\nc,2,4\nd,word,5\n"
    )
    profile = profile_dataset(project, inspect_dataset(project, dataset))
    stats = profile["files"]["train"]["columns"]["feature_x"]
    assert stats["missing_count"] == 1
    assert stats["missing_fraction"] == 0.25
    assert stats["non_finite_count"] == 1
    assert stats["numeric_count"] == 1
    assert stats["kind_in_sample"] == "mixed"
    assert stats["unique_nonempty_in_sample"] == 3


@pytest.mark.parametrize("limit", [0, -1, 10001])
def test_profile_rejects_unbounded_row_requests(project, dataset, limit):
    with pytest.raises(DataError, match="INVALID_PROFILE_ROW_LIMIT"):
        profile_dataset(project, inspect_dataset(project, dataset), max_rows=limit)


def test_changed_source_invalidates_profile(project, dataset):
    manifest = inspect_dataset(project, dataset)
    path = project / dataset.train
    path.write_text(path.read_text().replace("train-01,0,2", "train-01,0,3"))
    with pytest.raises(DataError, match="SOURCE_CHANGED"):
        profile_dataset(project, manifest)


@pytest.mark.parametrize(
    "header,code",
    [
        ("row_key,feature_x,feature_x", "DUPLICATE_COLUMN"),
        ("row_key,,target_value", "INVALID_HEADER"),
        ("wrong_id,feature_x,target_value", "TRAIN_COLUMNS_MISSING"),
    ],
)
def test_bad_headers_are_rejected(project, dataset, header, code):
    (project / dataset.train).write_text(header + "\n")
    with pytest.raises(DataError, match=code):
        inspect_dataset(project, dataset)


def test_mismatched_test_features_are_rejected(project, dataset):
    (project / dataset.test).write_text("row_key,unrelated_feature\na,0\n")
    with pytest.raises(DataError, match="FEATURE_COLUMNS_MISMATCH"):
        inspect_dataset(project, dataset)


def test_row_width_errors_do_not_produce_a_successful_profile(project, dataset):
    (project / dataset.train).write_text("row_key,feature_x,target_value\na,0\n")
    with pytest.raises(DataError, match="ROW_WIDTH_MISMATCH"):
        profile_dataset(project, inspect_dataset(project, dataset))


@pytest.mark.parametrize(
    "change",
    [
        {"id_column": "target_value"},
        {"prediction_column": "row_key"},
        {"min_prediction": 2, "max_prediction": 1},
        {"max_prediction": float("inf")},
    ],
)
def test_dataset_contract_invariants(dataset, change):
    with pytest.raises(ValidationError):
        DatasetSpec.model_validate({**dataset.model_dump(), **change})


def test_csv_reader_handles_bom_quoted_commas_and_newlines(project, dataset):
    with (project / dataset.train).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["row_key", "feature_x", "target_value"])
        writer.writerow(["id,with\nnewline", "quoted,value", 2])
    profile = profile_dataset(project, inspect_dataset(project, dataset))
    assert profile["files"]["train"]["row_count"] == 1
