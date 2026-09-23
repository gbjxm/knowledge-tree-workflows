#!/usr/bin/env python3
"""Create or verify portable, relative SHA-256 file manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(root: Path, ignored: set[str] | None = None) -> list[dict[str, object]]:
    ignored = ignored or set()
    rows: list[dict[str, object]] = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda p: p.as_posix().casefold()):
        relative = path.relative_to(root).as_posix()
        if relative in ignored:
            continue
        stat = path.stat()
        rows.append({"path": relative, "size": stat.st_size, "sha256": sha256(path)})
    return rows


def create_manifest(root: Path, output: Path) -> int:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Root is not a directory: {root}")
    output = output.resolve()
    if output.name.casefold() == "vault-before-migration.json":
        raise ValueError("The historical migration baseline is immutable and cannot be created or overwritten.")
    if output.exists():
        raise ValueError("Manifest output already exists; it will not be overwritten.")
    ignored: set[str] = set()
    try:
        ignored.add(output.relative_to(root).as_posix())
    except ValueError:
        pass
    rows = collect(root, ignored)
    payload = {
        "version": 1,
        "root_name": root.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(rows),
        "total_bytes": sum(int(row["size"]) for row in rows),
        "files": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "manifest": str(output), "file_count": len(rows)}, ensure_ascii=False))
    return 0


def verify_manifest(root: Path, manifest: Path, ignored: set[str] | None = None) -> int:
    root = root.resolve(strict=True)
    ignored = ignored or set()
    payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
    if payload.get("version") == 2:
        if ignored:
            raise ValueError("Release verification does not permit caller-selected ignores.")
        from release_core import verify_release
        result = verify_release(root, manifest)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    if payload.get("version") != 1 or not isinstance(payload.get("files"), list):
        raise ValueError(f"Unsupported manifest: {manifest}")
    expected = {str(row["path"]): row for row in payload["files"] if str(row["path"]) not in ignored}
    actual = {str(row["path"]): row for row in collect(root, ignored)}
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(
        path for path in set(expected) & set(actual)
        if expected[path].get("size") != actual[path].get("size")
        or expected[path].get("sha256") != actual[path].get("sha256")
    )
    result = {
        "ok": not (missing or extra or changed),
        "root": str(root),
        "expected_files": len(expected),
        "actual_files": len(actual),
        "ignored": sorted(ignored),
        "missing": missing,
        "extra": extra,
        "changed": changed,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--ignore", action="append", default=[])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "create":
            return create_manifest(args.root, args.output)
        return verify_manifest(args.root, args.manifest, set(args.ignore))
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
