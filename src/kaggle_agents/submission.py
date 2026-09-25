"""Deterministic validation for a single numeric prediction per test ID."""

import hashlib
import math
from collections import Counter
from itertools import zip_longest
from pathlib import Path

from kaggle_agents.contracts import DatasetSpec
from kaggle_agents.data import DataError, csv_table, verify_sources
from kaggle_agents.files import fingerprint, project_file

MAX_VALIDATION_ROWS = 1_000_000
MAX_ISSUES = 20


def _id(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


class Issues:
    def __init__(self) -> None:
        self.counts: Counter = Counter()
        self.examples: list[dict] = []

    def add(self, code: str, row: int | None = None) -> None:
        self.counts[code] += 1
        if len(self.examples) < MAX_ISSUES:
            # Never put raw IDs or predictions in the report.
            self.examples.append({"code": code, "row": row})


def _test_ids(path: Path, column: str) -> set[bytes]:
    seen: set[bytes] = set()
    with csv_table(path) as (header, rows):
        index = header.index(column)
        for number, row in enumerate(rows, 1):
            if number > MAX_VALIDATION_ROWS:
                raise DataError("VALIDATION_ROW_LIMIT_EXCEEDED")
            value = row[index]
            hashed = _id(value)
            if not value.strip():
                raise DataError("TEST_ID_MISSING")
            if hashed in seen:
                raise DataError("TEST_ID_DUPLICATE")
            seen.add(hashed)
    if not seen:
        raise DataError("EMPTY_TEST")
    return seen


def validate_submission(project: Path, spec: DatasetSpec, manifest: dict, file: str) -> dict:
    candidate = project_file(project, file)
    before = fingerprint(candidate)
    issues = Issues()
    expected_rows = 0
    actual_rows = 0
    complete = False
    remaining_ids = _test_ids(project_file(project, spec.test), spec.id_column)
    sample_ids: set[bytes] = set()
    actual_ids: set[bytes] = set()
    try:
        with (
            csv_table(project_file(project, spec.sample_submission)) as (expected_header, expected),
            csv_table(candidate) as (header, actual),
        ):
            if header != expected_header:
                issues.add("SUBMISSION_COLUMNS_MISMATCH")
            else:
                id_index = header.index(spec.id_column)
                prediction_index = header.index(spec.prediction_column)
                for number, (expected_row, actual_row) in enumerate(
                    zip_longest(expected, actual), 1
                ):
                    if number > MAX_VALIDATION_ROWS:
                        raise DataError("VALIDATION_ROW_LIMIT_EXCEEDED")
                    if expected_row is not None:
                        expected_rows += 1
                        value = expected_row[id_index]
                        hashed = _id(value)
                        if not value.strip():
                            issues.add("SAMPLE_ID_MISSING", number)
                        if hashed in sample_ids:
                            issues.add("SAMPLE_ID_DUPLICATE", number)
                        sample_ids.add(hashed)
                        if hashed not in remaining_ids:
                            issues.add("SAMPLE_TEST_ID_MISMATCH", number)
                        remaining_ids.discard(hashed)
                    if actual_row is not None:
                        actual_rows += 1
                        value = actual_row[id_index]
                        hashed = _id(value)
                        if not value.strip():
                            issues.add("SUBMISSION_ID_MISSING", number)
                        if hashed in actual_ids:
                            issues.add("SUBMISSION_ID_DUPLICATE", number)
                        actual_ids.add(hashed)
                        if expected_row is not None and value != expected_row[id_index]:
                            issues.add("SUBMISSION_ID_ORDER_MISMATCH", number)
                        try:
                            prediction = float(actual_row[prediction_index])
                        except ValueError:
                            issues.add("INVALID_PREDICTION", number)
                        else:
                            if not math.isfinite(prediction):
                                issues.add("NON_FINITE_PREDICTION", number)
                            elif (
                                spec.min_prediction is not None and prediction < spec.min_prediction
                            ) or (
                                spec.max_prediction is not None and prediction > spec.max_prediction
                            ):
                                issues.add("PREDICTION_OUT_OF_RANGE", number)
                complete = True
                if expected_rows != actual_rows:
                    issues.add("ROW_COUNT_MISMATCH")
                if remaining_ids:
                    issues.add("SAMPLE_TEST_ID_MISMATCH")
    except DataError as error:
        issues.add(error.code)
    verify_sources(project, manifest)
    if fingerprint(candidate) != before:
        issues.add("SUBMISSION_CHANGED")
    return {
        "schema_version": "0",
        "valid": complete and not issues.counts,
        "scan_complete": complete,
        "data_hash": manifest["data_hash"],
        "config_hash": manifest["config_hash"],
        "file": file,
        "sha256": before["sha256"],
        "expected_rows_scanned": expected_rows,
        "actual_rows_scanned": actual_rows,
        "error_count": sum(issues.counts.values()),
        "error_counts": dict(issues.counts),
        "issues": issues.examples,
    }
