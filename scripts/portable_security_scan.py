#!/usr/bin/env python3
"""Fail closed on machine paths, credential files, or non-empty secret-like JSON values."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from release_core import bounded_path, excluded_reason


SECRET_KEY = re.compile(r"(?:api.?key|access.?token|refresh.?token|client.?secret|password|cookie)", re.I)
SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    "cookies.txt",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "secrets.json",
    "auth.json",
}
RUNTIME_SUFFIXES = {".py", ".ps1", ".json", ".md", ".yaml", ".yml"}
ABSOLUTE_WINDOWS = re.compile(r"(?i)(?:[A-Z]:\\(?:obsidian|ProgramData\\CodexHome|Users\\))")


def nonempty(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def inspect_json(value: Any, source: Path, trail: str, findings: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            next_trail = f"{trail}.{key}" if trail else str(key)
            if SECRET_KEY.search(str(key)) and nonempty(item):
                findings.append(f"non-empty secret-like field: {source}::{next_trail}")
            inspect_json(item, source, next_trail, findings)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            inspect_json(item, source, f"{trail}[{index}]", findings)


def scan(root: Path, paths: list[str] | None = None) -> list[str]:
    findings: list[str] = []
    root = root.resolve(strict=True)
    runtime_roots = [root / ".codex", root / "scripts", root / "skills"]
    if paths is None:
        # Prune excluded directories before traversal; never open credential containers.
        selected: list[str] = []
        def visit(base: Path) -> None:
            for item in base.iterdir():
                name = item.relative_to(root).as_posix()
                if excluded_reason(name):
                    findings.append(f"excluded path: {name}")
                    continue
                bounded_path(root, name)
                if item.is_dir():
                    visit(item)
                elif item.is_file():
                    selected.append(name)
        visit(root)
    else:
        selected = paths
    for name in selected:
        if excluded_reason(name):
            findings.append(f"excluded path: {name}")
            continue
        path = bounded_path(root, name)
        if not path.is_file():
            continue
        if path.name.casefold() in SENSITIVE_NAMES or path.suffix.casefold() in {".pem", ".p12", ".key", ".pfx", ".clixml", ".dpapi"}:
            findings.append(f"sensitive filename: {path.relative_to(root)}")
            continue
        if path.suffix.casefold() == ".json":
            try:
                inspect_json(json.loads(path.read_text(encoding="utf-8-sig")), path.relative_to(root), "", findings)
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        if path.suffix.casefold() not in RUNTIME_SUFFIXES:
            continue
        if not any(path == base or base in path.parents for base in runtime_roots):
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        if ABSOLUTE_WINDOWS.search(text):
            findings.append(f"machine-specific runtime path: {path.relative_to(root)}")
    return sorted(set(findings))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    findings = scan(root)
    print(json.dumps({"ok": not findings, "findings": findings}, ensure_ascii=False, indent=2))
    return 0 if not findings else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
