"""Local UTF-8 CSV manifests and sampled profiles. No data rows enter CLI output."""

import csv
import hashlib
import json
import math
from contextlib import contextmanager
from itertools import islice
from pathlib import Path

from kaggle_agents.contracts import DatasetSpec
from kaggle_agents.files import fingerprint, load_json, project_file

MAX_COLUMNS = 200
MAX_PROFILE_ROWS = 10_000
DATA_ROLES = ("train", "test", "sample_submission")


class DataError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def load_dataset(project: Path, config: str) -> DatasetSpec:
    return DatasetSpec.model_validate(load_json(project_file(project, config)))


@contextmanager
def csv_table(path: Path):
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            if not header:
                raise DataError("EMPTY_CSV")
            if len(header) > MAX_COLUMNS:
                raise DataError("COLUMN_LIMIT_EXCEEDED")
            if any(not name.strip() or len(name) > 128 for name in header):
                raise DataError("INVALID_HEADER")
            if len(set(header)) != len(header):
                raise DataError("DUPLICATE_COLUMN")

            def rows():
                for row in reader:
                    if len(row) != len(header):
                        raise DataError("ROW_WIDTH_MISMATCH")
                    yield row

            yield header, rows()
    except (csv.Error, UnicodeError) as error:
        raise DataError("INVALID_CSV_ENCODING_OR_SYNTAX") from error


def inspect_dataset(project: Path, spec: DatasetSpec) -> dict:
    project = project.resolve()
    paths = {role: project_file(project, getattr(spec, role)) for role in DATA_ROLES}
    if len(set(paths.values())) != len(DATA_ROLES):
        raise DataError("DATA_FILES_MUST_DIFFER")
    files = {}
    for role, path in paths.items():
        with csv_table(path) as (header, _):
            files[role] = {"path": getattr(spec, role), "columns": header, **fingerprint(path)}
    train = files["train"]["columns"]
    test = files["test"]["columns"]
    sample = files["sample_submission"]["columns"]
    if spec.id_column not in train or spec.target_column not in train:
        raise DataError("TRAIN_COLUMNS_MISSING")
    if spec.id_column not in test or spec.target_column in test:
        raise DataError("TEST_COLUMNS_INVALID")
    if set(train) - {spec.target_column} != set(test):
        raise DataError("FEATURE_COLUMNS_MISMATCH")
    if set(sample) != {spec.id_column, spec.prediction_column}:
        raise DataError("SAMPLE_COLUMNS_INVALID")
    hashes = {role: record["sha256"] for role, record in files.items()}
    config = spec.model_dump(mode="json")
    return {
        "schema_version": "0",
        "source": "local_csv",
        "data_hash": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
        "config_hash": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "dataset": config,
        "files": files,
    }


def verify_sources(project: Path, manifest: dict) -> None:
    for record in manifest["files"].values():
        if fingerprint(project_file(project, record["path"]))["sha256"] != record["sha256"]:
            raise DataError("SOURCE_CHANGED")


class ColumnStats:
    def __init__(self) -> None:
        self.missing = 0
        self.numeric = 0
        self.non_finite = 0
        self.unique: set[bytes] = set()
        self.minimum = None
        self.maximum = None

    def add(self, value: str) -> None:
        if not value.strip():
            self.missing += 1
            return
        # Retain only hashes for cardinality; neither raw values nor examples are persisted.
        self.unique.add(hashlib.sha256(value.encode()).digest())
        try:
            number = float(value)
        except ValueError:
            return
        if not math.isfinite(number):
            self.non_finite += 1
            return
        self.numeric += 1
        self.minimum = number if self.minimum is None else min(self.minimum, number)
        self.maximum = number if self.maximum is None else max(self.maximum, number)

    def result(self, count: int) -> dict:
        nonempty = count - self.missing
        kind = "empty" if nonempty == 0 else "text"
        if self.numeric:
            kind = "numeric" if self.numeric == nonempty else "mixed"
        return {
            "kind_in_sample": kind,
            "missing_count": self.missing,
            "missing_fraction": self.missing / count if count else None,
            "unique_nonempty_in_sample": len(self.unique),
            "numeric_count": self.numeric,
            "non_finite_count": self.non_finite,
            "numeric_min": self.minimum,
            "numeric_max": self.maximum,
        }


def profile_dataset(project: Path, manifest: dict, max_rows: int = 1000) -> dict:
    if not 1 <= max_rows <= MAX_PROFILE_ROWS:
        raise DataError("INVALID_PROFILE_ROW_LIMIT")
    files = {}
    for role, record in manifest["files"].items():
        with csv_table(project_file(project, record["path"])) as (header, rows):
            stats = [ColumnStats() for _ in header]
            count = 0
            for row in islice(rows, max_rows):
                count += 1
                for column, value in zip(stats, row, strict=True):
                    column.add(value)
            complete = next(rows, None) is None
        files[role] = {
            "rows_scanned": count,
            "scan_complete": complete,
            "row_count": count if complete else None,
            "columns": {
                name: column.result(count) for name, column in zip(header, stats, strict=True)
            },
        }
    verify_sources(project, manifest)
    return {
        "schema_version": "0",
        "data_hash": manifest["data_hash"],
        "config_hash": manifest["config_hash"],
        "sampling": {"policy": "first_rows", "max_rows_per_file": max_rows},
        "files": files,
    }
