from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
OPERATE_SCRIPTS = SKILLS_ROOT / "operate-personal-knowledge-tree" / "scripts"
if str(OPERATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATE_SCRIPTS))

from knowledge_tree_config import load_config


CONFIG = load_config()

HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")


def inspect_note(path: Path, root: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    headings = []
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            headings.append({"level": len(match.group(1)), "text": match.group(2)})
    title = next((item["text"] for item in headings if item["level"] == 1), path.stem)
    return {
        "path": path.relative_to(root).as_posix(),
        "title": title,
        "headings": headings,
        "characters": len(text),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory Markdown notes without modifying the vault.")
    parser.add_argument("vault", nargs="?", type=Path, default=CONFIG.vault)
    parser.add_argument("--exclude", action="append", default=[], help="Top-level directory to exclude.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args()

    root = args.vault.resolve()
    excluded = set(args.exclude)
    notes = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if relative.parts and relative.parts[0] in excluded:
            continue
        notes.append(inspect_note(path, root))

    if args.json:
        print(json.dumps({"vault": str(root), "count": len(notes), "notes": notes}, ensure_ascii=False, indent=2))
        return 0

    print(f"# 笔记盘点\n\n共发现 {len(notes)} 篇 Markdown 笔记。\n")
    for note in notes:
        print(f"- `{note['path']}`｜{note['title']}｜{note['characters']} 字符")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
