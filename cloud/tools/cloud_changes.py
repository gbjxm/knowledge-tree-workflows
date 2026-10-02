#!/usr/bin/env python3
"""Export committed Markdown candidates; import them for review, never into the Vault."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
import uuid

SCHEMA = "knowledge-tree-cloud-change-package/v1"
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_FILES = 128
SHA = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class ChangeError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative_name(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ChangeError("A path must be a non-empty POSIX relative path.")
    parts = value.split("/")
    if any(p in {"", ".", ".."} or ":" in p or any(c in p for c in '\x00\r\n<>\"|?*')
           or p.endswith((" ", ".")) for p in parts):
        raise ChangeError("Unsafe relative path: " + repr(value))
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                *(f"lpt{i}" for i in range(1, 10))}
    if any(p.split(".", 1)[0].casefold() in reserved for p in parts):
        raise ChangeError("A path contains a Windows reserved name.")
    return value


def markdown_path(name: str, vault: str) -> str:
    name = relative_name(name)
    if not name.startswith(vault + "/") or not name.endswith(".md"):
        raise ChangeError("Only existing Vault Markdown content changes are supported: " + name)
    remainder = name[len(vault) + 1:].split("/")
    if any(p.startswith(".") for p in remainder):
        raise ChangeError("Hidden Vault paths are outside the candidate scope: " + name)
    return name


def is_reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def bounded_file(root: Path, name: str) -> Path:
    relative_name(name)
    current = root
    for part in name.split("/"):
        current = current / part
        if not current.exists() or is_reparse(current):
            raise ChangeError("Missing or redirected local source: " + name)
    if not current.is_file() or not current.resolve().is_relative_to(root):
        raise ChangeError("Local source is not a bounded regular file: " + name)
    return current


def git(root: Path, *arguments: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True)
    if result.returncode:
        raise ChangeError("Git command failed: " + result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def text_bytes(text: str) -> bytes:
    if not isinstance(text, str) or "\x00" in text:
        raise ChangeError("Candidate content must be UTF-8 Markdown text without NUL.")
    data = text.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise ChangeError("A Markdown file exceeds the 8 MiB candidate limit.")
    return data


def utf8(data: bytes) -> str:
    if len(data) > MAX_FILE_BYTES:
        raise ChangeError("A Markdown file exceeds the 8 MiB candidate limit.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ChangeError("A candidate is not valid UTF-8 Markdown.") from exc
    text_bytes(text)
    return text


def config_vault(config: dict) -> str:
    if not isinstance(config, dict) or config.get("version") != 2:
        raise ChangeError("A workspace-relative knowledge-tree v2 configuration is required.")
    return relative_name(config.get("vault"))


def export_package(root: Path, base: str, head: str) -> dict:
    root = root.resolve(strict=True)
    base_commit = git(root, "rev-parse", "--verify", base + "^{commit}").decode().strip()
    head_commit = git(root, "rev-parse", "--verify", head + "^{commit}").decode().strip()
    if not COMMIT.fullmatch(base_commit) or not COMMIT.fullmatch(head_commit):
        raise ChangeError("Both revisions must resolve to full commit IDs.")
    common = git(root, "merge-base", base_commit, head_commit).decode().strip()
    if common != base_commit:
        raise ChangeError("The selected base must be an ancestor of the candidate head.")
    config = json.loads(git(root, "show", base_commit + ":.codex/knowledge-tree.json").decode("utf-8-sig"))
    vault = config_vault(config)
    dirty = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", vault + "/")
    if dirty:
        raise ChangeError("Commit or discard pending Vault changes before exporting; only committed candidates are packaged.")
    fields = git(root, "diff", "--name-status", "-z", "--no-renames", base_commit, head_commit,
                 "--", vault + "/").split(b"\x00")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise ChangeError("Unexpected Git change listing.")
    rows = []
    seen = set()
    for index in range(0, len(fields), 2):
        status = fields[index].decode("ascii")
        name = fields[index + 1].decode("utf-8")
        if status != "M":
            raise ChangeError("Adding, deleting or moving Vault files is unsupported: " + status + " " + name)
        markdown_path(name, vault)
        if name.casefold() in seen:
            raise ChangeError("Duplicate or case-colliding path: " + name)
        seen.add(name.casefold())
        before = git(root, "show", base_commit + ":" + name)
        after = git(root, "show", head_commit + ":" + name)
        if before == after:
            continue
        rows.append({"path": name, "status": "modify", "before_sha256": digest(before),
                     "after_sha256": digest(after), "before_utf8": utf8(before), "after_utf8": utf8(after)})
    if not rows:
        raise ChangeError("There are no committed existing-Markdown changes in the selected range.")
    if len(rows) > MAX_FILES:
        raise ChangeError("Export at most 128 Markdown files per review batch.")
    package = {"schema": SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(),
               "vault": vault, "base_commit": base_commit, "head_commit": head_commit,
               "files": rows}
    if len(serialize(package)) > MAX_PACKAGE_BYTES:
        raise ChangeError("The candidate package exceeds 32 MiB; use smaller review batches.")
    return package


def serialize(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_package(path: Path) -> tuple[dict, str]:
    if path.stat().st_size > MAX_PACKAGE_BYTES:
        raise ChangeError("The candidate package exceeds 32 MiB.")
    raw = path.read_bytes()
    package = json.loads(raw.decode("utf-8-sig"))
    expected = {"schema", "created_utc", "vault", "base_commit", "head_commit", "files"}
    if not isinstance(package, dict) or set(package) != expected or package.get("schema") != SCHEMA:
        raise ChangeError("Unsupported candidate package schema.")
    vault = relative_name(package["vault"])
    if not COMMIT.fullmatch(package["base_commit"]) or not COMMIT.fullmatch(package["head_commit"]):
        raise ChangeError("Candidate commit IDs are invalid.")
    rows = package["files"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_FILES:
        raise ChangeError("A package must contain between 1 and 128 existing-Markdown changes.")
    seen = set()
    row_fields = {"path", "status", "before_sha256", "after_sha256", "before_utf8", "after_utf8"}
    for row in rows:
        if not isinstance(row, dict) or set(row) != row_fields or row["status"] != "modify":
            raise ChangeError("Only existing Markdown modifications are supported.")
        name = markdown_path(row["path"], vault)
        if name.casefold() in seen:
            raise ChangeError("Duplicate or case-colliding path: " + name)
        seen.add(name.casefold())
        for phase in ("before", "after"):
            claimed = row[phase + "_sha256"]
            if not isinstance(claimed, str) or not SHA.fullmatch(claimed) or digest(text_bytes(row[phase + "_utf8"])) != claimed:
                raise ChangeError("Candidate hash/content mismatch: " + phase + " " + name)
        if row["before_sha256"] == row["after_sha256"]:
            raise ChangeError("A candidate must actually change content: " + name)
    return package, digest(raw)


def local_configuration(root: Path) -> dict:
    path = bounded_file(root, ".codex/knowledge-tree.json")
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    config_vault(config)
    relative_name(config.get("raw_cache"))
    return config


def inspect_import(root: Path, package: dict, package_sha256: str) -> dict:
    root = root.resolve(strict=True)
    config = local_configuration(root)
    if package["vault"] != config_vault(config):
        raise ChangeError("Candidate Vault differs from the local authoritative configuration.")
    rows = []
    for change in package["files"]:
        name = change["path"]
        try:
            path = bounded_file(root, name)
            current = digest(path.read_bytes())
            status = "ready" if current == change["before_sha256"] else "conflict"
            detail = "before_hash_matches" if status == "ready" else (
                "already_matches_candidate" if current == change["after_sha256"] else "local_content_changed")
            rows.append({"path": name, "status": status, "detail": detail, "current_sha256": current,
                         "before_sha256": change["before_sha256"], "after_sha256": change["after_sha256"]})
        except (ChangeError, OSError) as exc:
            rows.append({"path": name, "status": "conflict", "detail": str(exc)})
    return {"ok": all(r["status"] == "ready" for r in rows), "mode": "preview", "writes": False,
            "vault_writes": False, "formal_adoption": False, "package_sha256": package_sha256,
            "base_commit": package["base_commit"], "head_commit": package["head_commit"], "files": rows}


def safe_review_target(root: Path, config: dict, target: Path) -> Path:
    raw_cache = root / relative_name(config["raw_cache"])
    allowed = raw_cache / "cloud-review"
    absolute = Path(os.path.abspath(target))
    if not absolute.is_relative_to(allowed) or absolute == allowed:
        raise ChangeError("Review output must be a new child directory of configured raw_cache/cloud-review.")
    current = root
    for part in absolute.relative_to(root).parts:
        current = current / part
        if current.exists() and is_reparse(current):
            raise ChangeError("Review output contains a redirected path.")
    if absolute.exists():
        raise ChangeError("The review destination already exists; choose a new child directory.")
    if absolute.resolve().is_relative_to(root / config_vault(config)):
        raise ChangeError("Review output cannot be inside the protected Vault.")
    return absolute


def stage_review(root: Path, package: dict, package_sha256: str, target: Path | None = None) -> dict:
    root = root.resolve(strict=True)
    report = inspect_import(root, package, package_sha256)
    if not report["ok"]:
        raise ChangeError("Local conflicts block candidate staging; preview the package first. Nothing was written.")
    config = local_configuration(root)
    default_name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + package_sha256[:12]
    target = safe_review_target(root, config, target or root / config["raw_cache"] / "cloud-review" / default_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / (".staging-" + uuid.uuid4().hex)
    staging.mkdir()
    try:
        for index, row in enumerate(package["files"], 1):
            name = row["path"]
            for phase, folder in (("before", "before"), ("after", "candidate")):
                output = staging / folder / name
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(text_bytes(row[phase + "_utf8"]))
            diff = "".join(difflib.unified_diff(row["before_utf8"].splitlines(keepends=True),
                          row["after_utf8"].splitlines(keepends=True), fromfile="before/" + name,
                          tofile="candidate/" + name))
            diff_path = staging / "diffs" / (f"{index:03d}.diff")
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            diff_path.write_bytes(diff.encode("utf-8"))
        # Candidate staging is reversible, but a changed source still invalidates the review batch.
        recheck = inspect_import(root, package, package_sha256)
        if not recheck["ok"]:
            raise ChangeError("Local content changed during staging; no review batch was published and the Vault was untouched.")
        report.update(mode="staged-for-review", writes=True, vault_writes=False, formal_adoption=False,
                      review_path=str(target), required_next_step="Review and explicitly adopt through the existing knowledge-tree/Obsidian workflow, then run the normal verified backup.")
        (staging / "change-package.json").write_bytes(serialize(package))
        (staging / "review.json").write_bytes(serialize(report))
        instructions = (
            "# 云端候选回流审阅\n\n"
            "本目录只保存候选；正式 Vault 未改写，main 与备份工具未改动。\n\n"
            "1. 对照 `diffs/`、`before/` 与 `candidate/` 审阅内容和保留项。\n"
            "2. 使用原知识树流程逐篇明确采纳；先重新核对正式原件 before_sha256，验证当前 Obsidian Vault。\n"
            "3. 若原件已变化，停止覆盖，重新比较。新增、删除、移动不受本工具支持。\n"
            "4. 正式采纳后运行原有笔记与知识库检查，再由原 backup.ps1 -Apply 生成正式快照及验证标签。\n"
            "5. 更新 cloud-work 基线前核对未回流候选；不要将候选分支直接合并 main。\n"
        )
        (staging / "README.md").write_bytes(instructions.encode("utf-8"))
        staging.rename(target)
    except BaseException:
        # Only remove the exact new staging directory created above, bounded to this review parent.
        if staging.exists() and staging.parent.resolve() == target.parent.resolve() and not is_reparse(staging):
            shutil.rmtree(staging)
        raise
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Package committed existing Markdown candidates.")
    export.add_argument("--root", type=Path, default=Path.cwd())
    export.add_argument("--base", default="origin/main")
    export.add_argument("--head", default="HEAD")
    export.add_argument("--output", type=Path, required=True)
    incoming = commands.add_parser("import", help="Default: zero-write preview. --apply stages an independent review copy only.")
    incoming.add_argument("--root", type=Path, required=True)
    incoming.add_argument("--package", type=Path, required=True)
    incoming.add_argument("--apply", action="store_true")
    incoming.add_argument("--review-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            package = export_package(args.root, args.base, args.head)
            data = serialize(package)
            output_path = args.output.resolve()
            repo_root = args.root.resolve(strict=True)
            if output_path.is_relative_to(repo_root / package["vault"]) or output_path.is_relative_to(repo_root / ".git"):
                raise ChangeError("Export output cannot be inside the protected Vault or Git metadata.")
            if args.output.suffix.lower() != ".json":
                raise ChangeError("Export output must be a new .json file.")
            if not args.output.parent.is_dir():
                raise ChangeError("Create/select the output parent directory explicitly before exporting.")
            with args.output.open("xb") as output:
                output.write(data)
            result = {"ok": True, "mode": "export", "files": len(package["files"]),
                      "output": str(args.output.resolve()), "package_sha256": digest(data),
                      "base_commit": package["base_commit"], "head_commit": package["head_commit"],
                      "vault_writes": False, "formal_adoption": False}
        else:
            package, sha = read_package(args.package)
            result = stage_review(args.root, package, sha, args.review_dir) if args.apply else inspect_import(args.root, package, sha)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 2
    except (ChangeError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "vault_writes": False,
                          "formal_adoption": False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
