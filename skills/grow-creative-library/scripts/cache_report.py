from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
OPERATE_SCRIPTS = SKILLS_ROOT / "operate-personal-knowledge-tree" / "scripts"
if str(OPERATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATE_SCRIPTS))

from knowledge_tree_config import load_config


CONFIG = load_config()

def format_size(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def main() -> int:
    parser = argparse.ArgumentParser(description="Report cache usage without deleting files.")
    parser.add_argument("cache", nargs="?", type=Path, default=CONFIG.raw_cache)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = args.cache.resolve()
    by_extension: dict[str, int] = defaultdict(int)
    total = 0
    count = 0

    if root.exists():
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            size = path.stat().st_size
            total += size
            count += 1
            by_extension[path.suffix.lower() or "[无扩展名]"] += size

    result = {
        "cache": str(root),
        "file_count": count,
        "bytes": total,
        "human_size": format_size(total),
        "by_extension": dict(sorted(by_extension.items(), key=lambda item: item[1], reverse=True)),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"缓存目录：{root}")
    print(f"文件数量：{count}")
    print(f"占用空间：{format_size(total)}")
    if by_extension:
        print("按类型：")
        for extension, size in sorted(by_extension.items(), key=lambda item: item[1], reverse=True):
            print(f"- {extension}: {format_size(size)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
