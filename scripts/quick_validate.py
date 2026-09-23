#!/usr/bin/env python3
"""Dependency-free structural validation for one bundled Codex Skill."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def validate(skill: Path) -> tuple[bool, str]:
    skill = skill.resolve()
    source = skill / "SKILL.md"
    if not source.is_file():
        return False, f"SKILL.md not found: {skill}"
    text = source.read_text(encoding="utf-8-sig")
    match = re.match(r"^---\r?\n(.*?)\r?\n---", text, flags=re.DOTALL)
    if not match:
        return False, "Invalid or missing YAML frontmatter"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if line.startswith((" ", "\t")) or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip("\"'")
    name = fields.get("name", "")
    description = fields.get("description", "")
    if name != skill.name:
        return False, f"Skill name mismatch: {name!r} != {skill.name!r}"
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        return False, f"Invalid skill name: {name!r}"
    if not description or len(description) > 1024 or "<" in description or ">" in description:
        return False, "Invalid skill description"
    return True, "Skill is valid!"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill-directory>", file=sys.stderr)
        return 2
    ok, message = validate(Path(sys.argv[1]))
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
