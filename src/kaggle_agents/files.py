"""Bounded structured inputs and atomic artifact writes."""

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path, PureWindowsPath
from typing import Any

from pydantic import BaseModel

MAX_JSON_BYTES = 64 * 1024


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def _float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("Non-finite JSON number")
    return parsed


def load_json(path: Path) -> Any:
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("JSON exceeds 64 KiB")
    return json.loads(
        raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant, parse_float=_float
    )


def write_json(path: Path, value: BaseModel | dict[str, Any]) -> None:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def project_file(root: Path, relative: str) -> Path:
    # Use one portable spelling and reject drive-relative Windows paths on every OS.
    if "\\" in relative or PureWindowsPath(relative).drive:
        raise ValueError("Expected a portable relative path")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Expected a path within the project")
    resolved = (root / candidate).resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("Expected a regular file within the project")
    return resolved


def fingerprint(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"sha256": digest, "size_bytes": path.stat().st_size}
