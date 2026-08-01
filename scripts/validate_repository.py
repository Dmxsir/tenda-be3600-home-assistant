"""Validate tracked repository files without third-party dependencies."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {".cfg", ".har", ".key", ".log", ".pem", ".pyc", ".sha256", ".zip"}
FORBIDDEN_PARTS = {"__pycache__", "sources"}
BINARY_SUFFIXES = {".gif", ".ico", ".jpg", ".jpeg", ".png", ".webp"}
SECRET_PATTERNS = {
    "GitHub token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    "OpenAI token": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "router session URL": re.compile(r";stok=[A-Za-z0-9]{16,}"),
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return [ROOT / item for item in result.stdout.decode("utf-8").split("\0") if item]


def main() -> None:
    errors: list[str] = []
    files = tracked_files()

    for path in files:
        relative = path.relative_to(ROOT)
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or FORBIDDEN_PARTS.intersection(relative.parts):
            errors.append(f"forbidden tracked file: {relative.as_posix()}")
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"not valid UTF-8: {relative.as_posix()}")
            continue

        if path.suffix.lower() == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as err:
                errors.append(f"invalid JSON: {relative.as_posix()}: {err}")

        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"possible {name}: {relative.as_posix()}")

    if errors:
        raise SystemExit("Repository validation failed:\n- " + "\n- ".join(errors))
    print(f"Repository validation passed ({len(files)} tracked files).")


if __name__ == "__main__":
    main()
