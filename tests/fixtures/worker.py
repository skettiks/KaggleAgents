"""Process fixture for lifecycle failures; never imported by the tests."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--spec", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
request = json.loads(args.spec.read_text(encoding="utf-8"))
params = request["experiment"]["params"]
mode = params["mode"]
print("PRIVATE_WORKER_LOG_MUST_NOT_APPEAR_IN_CLI", flush=True)

if mode == "spawn_timeout":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    (args.output.parent / "child.pid").write_text(str(child.pid))
if mode in {"timeout", "spawn_timeout"}:
    time.sleep(30)
if mode == "invalid_json":
    args.output.write_text("not json")
    raise SystemExit(0)
if mode == "oversized":
    args.output.write_text(" " * 65537)
    raise SystemExit(0)

payload = {"schema_version": "0", "metrics": {request["task"]["metric"]["name"]: 0.25}}
if "usage" in params:
    payload["usage"] = params["usage"]
if mode == "bad_metric":
    payload["metrics"] = {"wrong_name": 0.1}
if mode == "invalid_artifact":
    payload["artifacts"] = ["../task.json"]
if mode == "mutate_input":
    Path(request["experiment"]["input_files"][0]).write_text("modified")
if mode == "no_output":
    raise SystemExit(0)

args.output.write_text(json.dumps(payload), encoding="utf-8")
if mode == "fail" or (mode == "fail_once" and request["attempt_id"] == "attempt-001"):
    print("expected failure", file=sys.stderr)
    raise SystemExit(3)
