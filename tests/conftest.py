import json
import shutil
from pathlib import Path

import pytest

from kaggle_agents.contracts import ExperimentSpec, TaskSpec
from kaggle_agents.data import load_dataset

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "offline"


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "competition with spaces"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("runs", "__pycache__"))
    shutil.copyfile(Path(__file__).parent / "fixtures" / "worker.py", root / "worker.py")
    return root


@pytest.fixture
def task(project):
    return TaskSpec.model_validate_json((project / "task.json").read_bytes())


@pytest.fixture
def experiment(project):
    raw = json.loads((project / "experiment.json").read_text(encoding="utf-8"))
    raw["script"] = "worker.py"
    raw["timeout_seconds"] = 3
    raw["params"] = {"mode": "success"}
    return ExperimentSpec.model_validate(raw)


@pytest.fixture
def dataset(project):
    return load_dataset(project, "dataset.json")
