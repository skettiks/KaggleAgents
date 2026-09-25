"""Small JSON-output CLI, shared by humans and future agent tool wrappers."""

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from kaggle_agents import __version__
from kaggle_agents.data import DataError, inspect_dataset, load_dataset, profile_dataset
from kaggle_agents.files import write_json
from kaggle_agents.runner import load_specs, run_experiment
from kaggle_agents.submission import validate_submission


def _data_command(args: argparse.Namespace, project: Path) -> int:
    spec = load_dataset(project, args.dataset)
    manifest = inspect_dataset(project, spec)
    report = None
    if args.command == "profile":
        report = profile_dataset(project, manifest, args.max_rows)
    elif args.command == "validate-submission":
        report = validate_submission(project, spec, manifest, args.file)
    directory = project / "runs" / "data" / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "manifest.json", manifest)
    summary = {
        "data_hash": manifest["data_hash"],
        "manifest_path": str(directory / "manifest.json"),
    }
    if args.command == "inspect":
        summary.update(
            {
                "status": "INSPECTED",
                "files": {
                    role: {
                        "column_count": len(record["columns"]),
                        "size_bytes": record["size_bytes"],
                    }
                    for role, record in manifest["files"].items()
                },
            }
        )
    elif args.command == "profile":
        write_json(directory / "profile.json", report)
        summary.update(
            {
                "status": "PROFILED",
                "profile_path": str(directory / "profile.json"),
                "files": {
                    role: {key: value for key, value in record.items() if key != "columns"}
                    for role, record in report["files"].items()
                },
            }
        )
    else:
        write_json(directory / "submission-report.json", report)
        summary.update({**report, "report_path": str(directory / "submission-report.json")})
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
    return 1 if args.command == "validate-submission" and not report["valid"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kaggle-agents")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "run"):
        command = commands.add_parser(name)
        command.add_argument("--project", type=Path, required=True)
        command.add_argument("--task", default="task.json", help="Path relative to project")
        command.add_argument(
            "--experiment", default="experiment.json", help="Path relative to project"
        )
        if name == "run":
            command.add_argument(
                "--output-dir", type=Path, help="Artifact root, relative to project"
            )
    for name in ("inspect", "profile", "validate-submission"):
        command = commands.add_parser(name)
        command.add_argument("--project", type=Path, required=True)
        command.add_argument("--dataset", default="dataset.json", help="Path relative to project")
        if name == "profile":
            command.add_argument("--max-rows", type=int, default=1000)
        if name == "validate-submission":
            command.add_argument("--file", required=True, help="CSV path relative to project")
    args = parser.parse_args(argv)
    try:
        project = args.project.resolve(strict=True)
        if args.command in {"inspect", "profile", "validate-submission"}:
            return _data_command(args, project)
        task, experiment = load_specs(project, args.task, args.experiment)
        if args.command == "check":
            print(
                json.dumps(
                    {
                        "valid": True,
                        "schema_version": "0",
                        "task_id": task.task_id,
                        "experiment_id": experiment.experiment_id,
                    }
                )
            )
            return 0
        output = args.output_dir or Path("runs/artifacts")
        result = run_experiment(project, task, experiment, project / output)
        print(result.model_dump_json())
        return {"SUCCEEDED": 0, "TIMED_OUT": 124, "INTERRUPTED": 130}.get(result.status, 1)
    except ValidationError as error:
        # Do not echo input values (which may include secrets) into agent context.
        fields = [
            ".".join(str(part)[:40] for part in issue["loc"][:5])
            for issue in error.errors(include_input=False, include_context=False)[:20]
        ]
        print(
            json.dumps(
                {"error": "INVALID_CONTRACT", "fields": fields, "error_count": error.error_count()}
            ),
            file=sys.stderr,
        )
        return 2
    except DataError as error:
        print(json.dumps({"error": "INVALID_DATASET", "code": error.code}), file=sys.stderr)
        return 2
    except (OSError, ValueError, RecursionError):
        print(
            json.dumps(
                {
                    "error": "INVALID_INPUT_OR_IO",
                    "message": "Check JSON, project paths, file sizes and output permissions.",
                }
            ),
            file=sys.stderr,
        )
        return 2
