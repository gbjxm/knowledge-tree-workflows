#!/usr/bin/env python3
"""Shared read-only release selection, verification, and explicit package/install actions."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

MODULE_MANIFEST = "manifest/modules.json"
PACKAGE_MANIFEST = "manifest/package-files.json"
TRUSTED_ROOT = Path(__file__).resolve().parents[1]
DENIED_DIRS = {".runtime", "secrets", "development-backups", ".git", ".learnings",
               "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".venv",
               ".trash", "temp", "tmp", "backups"}
DENIED_NAMES = {".env", ".env.local", "credentials.json", "secrets.json", "cookies.txt",
                "id_rsa", "id_ed25519", "auth.json", "metadata.json", "transcript.md",
                "subtitle.json", "audio.m4s"}
DENIED_SUFFIXES = {".clixml", ".pem", ".p12", ".pfx", ".key", ".dpapi", ".pyc", ".log",
                   ".m4s", ".m4a", ".mp3", ".wav", ".mp4", ".mov", ".webm", ".zip", ".7z"}

class ReleaseError(ValueError):
    pass

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def relative_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseError("Expected a non-empty workspace-relative path.")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if PurePosixPath(normalized).is_absolute() or any(p in {"", ".", ".."} or ":" in p for p in parts):
        raise ReleaseError(f"Unsafe relative path: {value!r}")
    return "/".join(parts)

def reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)

def bounded_path(root: Path, name: str, *, exists: bool = True) -> Path:
    name = relative_name(name)
    current = root
    for part in name.split("/"):
        current = current / part
        if current.exists() or current.is_symlink():
            if reparse(current):
                raise ReleaseError(f"Reparse points are not release inputs: {name}")
        elif exists:
            raise ReleaseError(f"Missing release path: {name}")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ReleaseError(f"Path escapes release root: {name}")
    return current

def excluded_reason(name: str, *, raw_cache: str | None = None) -> str | None:
    name = relative_name(name)
    parts = [p.casefold() for p in name.split("/")]
    if raw_cache:
        cache = raw_cache.casefold().rstrip("/")
        if name.casefold() == cache or name.casefold().startswith(cache + "/"):
            return "raw-cache"
    if any(p in DENIED_DIRS or p.startswith(".env.") for p in parts):
        return "excluded-directory"
    base = parts[-1]
    if base in DENIED_NAMES or base.startswith(".env.") or base.endswith(".credentials"):
        return "credential-or-raw-artifact"
    if Path(base).suffix in DENIED_SUFFIXES:
        return "credential-cache-or-raw-media"
    return None

def load_json(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise ReleaseError(f"Expected JSON object: {path.name}")
    return result

def load_modules(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if data.get("version") != 1 or not isinstance(data.get("modules"), list) or not data["modules"]:
        raise ReleaseError("Unsupported or empty module manifest.")
    names = set()
    for item in data["modules"]:
        if not isinstance(item, dict) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(item.get("name", ""))):
            raise ReleaseError("Invalid module name.")
        if item["name"] in names:
            raise ReleaseError("Duplicate module name.")
        names.add(item["name"])
        if item.get("channel") not in {"stable", "preview"} or not isinstance(item.get("requires"), list):
            raise ReleaseError(f"Invalid module channel or dependencies: {item['name']}")
    for item in data["modules"]:
        if any(not isinstance(dep, str) or dep not in names for dep in item["requires"]):
            raise ReleaseError(f"Unknown dependency: {item['name']}")
    return data

def select_modules(data: dict[str, Any], names: list[str] | None = None) -> list[dict[str, Any]]:
    lookup = {item["name"]: item for item in data["modules"]}
    if names is None:
        names = [item["name"] for item in data["modules"] if item["channel"] == "stable"]
    if not names or len(names) != len(set(names)) or any(name not in lookup for name in names):
        raise ReleaseError("SkillNames must be non-empty, unique, known module names.")
    return [lookup[name] for name in names]

def dependency_errors(modules: list[dict[str, Any]], available: set[str],
                      catalog: list[dict[str, Any]] | None = None) -> list[str]:
    """Check the dependency closure, including already-installed dependencies; cycles are valid."""
    lookup = {item["name"]: item for item in (catalog or modules)}
    pending = [item["name"] for item in modules]
    visited: set[str] = set()
    errors: set[str] = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        item = lookup.get(name)
        if item is None:
            errors.add(f"Unknown dependency module: {name}")
            continue
        for dep in item["requires"]:
            if dep not in available:
                errors.add(f"{name} requires {dep}")
            pending.append(dep)
    return sorted(errors)

def target_config(root: Path):
    """Resolve target data with our trusted shared loader; never execute target code."""
    module_name = "_portable_release_shared_config"
    if module_name not in sys.modules:
        loader_path = TRUSTED_ROOT / "skills/operate-personal-knowledge-tree/scripts/knowledge_tree_config.py"
        spec = importlib.util.spec_from_file_location(module_name, loader_path)
        if spec is None or spec.loader is None:
            raise ReleaseError("Trusted knowledge-tree configuration loader is unavailable.")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[module_name]
            raise
    loader = sys.modules[module_name]
    try:
        config = loader.load_config(bounded_path(root, ".codex/knowledge-tree.json"))
    except loader.KnowledgeTreeConfigError as exc:
        raise ReleaseError(str(exc)) from exc
    if config.workspace.resolve() != root.resolve():
        raise ReleaseError("Shared loader selected a different workspace.")
    return config

def config_paths(root: Path) -> dict[str, Any]:
    resolved = target_config(root)
    if resolved.version != 2:
        raise ReleaseError("A release requires an explicit portable version 2 configuration.")
    config: dict[str, Any] = {"version": resolved.version, "vault_name": resolved.vault_name}
    for field in ("vault", "knowledge_library", "source_notes", "prompt_box", "raw_cache", "skills_root", "source_evidence", "creation_root", "learning_root"):
        value = getattr(resolved, field)
        if value is None:
            config[field] = None
        else:
            config[field] = relative_name(value.relative_to(root.resolve()).as_posix())
            bounded_path(root, config[field], exists=False)
    return config

def parents_of(name: str) -> set[str]:
    path = PurePosixPath(name)
    return {str(parent) for parent in path.parents if str(parent) != "."}

def release_selection(root: Path, manifest: Path | None = None) -> dict[str, Any]:
    root = root.resolve(strict=True)
    manifest = manifest or root / MODULE_MANIFEST
    if ".." in manifest.parts:
        raise ReleaseError("Release manifest path must not contain '..'.")
    try:
        module_path = manifest.resolve(strict=True).relative_to(root).as_posix()
    except ValueError as exc:
        raise ReleaseError("Module manifest must stay inside the release workspace.") from exc
    manifest = bounded_path(root, module_path)
    data, config = load_modules(manifest), config_paths(root)
    modules = select_modules(data)
    names = {item["name"] for item in modules}
    missing = dependency_errors(modules, names, data["modules"])
    if missing:
        raise ReleaseError("; ".join(missing))
    include = data.get("include")
    if not isinstance(include, dict):
        raise ReleaseError("Module manifest needs an include allowlist.")
    files: set[str] = set()
    directories: set[str] = set()
    excluded: list[dict[str, str]] = []
    raw_cache = config["raw_cache"]

    def visit(name: str) -> None:
        name = relative_name(name)
        reason = excluded_reason(name, raw_cache=raw_cache)
        if reason:
            if PurePosixPath(name).is_relative_to(PurePosixPath(config["vault"])):
                raise ReleaseError(f"Protected Vault contains an excluded credential/raw/cache path; nothing was read or removed: {name}")
            excluded.append({"path": name, "reason": reason})
            return
        path = bounded_path(root, name)
        if path.is_dir():
            directories.add(name)
            directories.update(parents_of(name))
            for child in sorted(path.iterdir(), key=lambda p: p.name.casefold()):
                visit(name + "/" + child.name)
        elif path.is_file():
            files.add(name)
            directories.update(parents_of(name))
        else:
            raise ReleaseError(f"Not a regular release file: {name}")

    for key in ("files", "directories"):
        if not isinstance(include.get(key), list):
            raise ReleaseError(f"include.{key} must be a list.")
        for name in include[key]:
            visit(name)
    if include.get("vault") is not True:
        raise ReleaseError("Stable portable releases must preserve the active Vault.")
    visit(config["vault"])
    if include.get("source_evidence") and config.get("source_evidence"):
        visit(config["source_evidence"])
    for item in modules:
        visit(config["skills_root"] + "/" + item["name"])
    visit(module_path)
    files.discard(PACKAGE_MANIFEST)
    scaffolds = {config["raw_cache"], *parents_of(config["raw_cache"])}
    directories.update(scaffolds)
    # Preserve required empty configured directories when they are valid in the source workspace.
    for field in ("source_notes", "knowledge_library", "skills_root", "creation_root", "learning_root"):
        if config.get(field) is None:
            continue
        bounded_path(root, config[field])
        directories.add(config[field])
        directories.update(parents_of(config[field]))
    directories.add("manifest")
    if not bounded_path(root, config["vault"] + "/.obsidian").is_dir():
        raise ReleaseError("The source Vault has no .obsidian directory.")
    directories.add(config["vault"] + "/.obsidian")
    return {"files": sorted(files), "directories": sorted(directories), "scaffolds": sorted(scaffolds),
            "modules": sorted(names), "module_manifest": module_path, "excluded": excluded,
            "raw_cache": raw_cache}

def release_manifest(root: Path, selection: dict[str, Any]) -> dict[str, Any]:
    return {"version": 2, "purpose": "portable-release", "root_name": root.name,
            "generated_at": datetime.now(timezone.utc).isoformat(), "manifest_path": PACKAGE_MANIFEST,
            "module_manifest": selection["module_manifest"], "modules": selection["modules"],
            "directories": selection["directories"], "scaffolds": selection["scaffolds"],
            "files": [{"path": name, "size": bounded_path(root, name).stat().st_size,
                       "sha256": sha256(bounded_path(root, name))} for name in selection["files"]]}

def release_inventory(root: Path, scaffolds: set[str]) -> tuple[set[str], set[str], list[str]]:
    files, dirs, forbidden = set(), set(), []
    def walk(base: Path, prefix: str = "") -> None:
        for path in sorted(base.iterdir(), key=lambda p: p.name.casefold()):
            name = (prefix + "/" + path.name).lstrip("/")
            reason = excluded_reason(name)
            if reason and name not in scaffolds:
                forbidden.append(name)  # Do not open or recurse into excluded credential/cache inputs.
                continue
            if reparse(path):
                forbidden.append(name + " (reparse)")
                continue
            if path.is_dir():
                dirs.add(name)
                walk(path, name)
            elif path.is_file():
                files.add(name)
            else:
                forbidden.append(name)
    walk(root)
    return files, dirs, forbidden

def verify_release(root: Path, manifest: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    try:
        if ".." in manifest.parts:
            raise ReleaseError("Release manifest path must not contain '..'.")
        manifest_name = manifest.resolve(strict=True).relative_to(root).as_posix()
    except ValueError as exc:
        raise ReleaseError("Release verification manifest must be inside the verified root.") from exc
    manifest = bounded_path(root, manifest_name)
    payload = load_json(manifest)
    if payload.get("version") != 2 or payload.get("purpose") != "portable-release":
        raise ReleaseError("Release mode requires a version 2 portable-release manifest.")
    if payload.get("manifest_path") != manifest_name or manifest_name != PACKAGE_MANIFEST:
        raise ReleaseError("Release manifest self-exclusion path does not match.")
    expected: dict[str, dict[str, Any]] = {}
    for row in payload.get("files", []):
        if not isinstance(row, dict):
            raise ReleaseError("Invalid release file record.")
        name = relative_name(row.get("path"))
        if name in expected or name == manifest_name or excluded_reason(name):
            raise ReleaseError(f"Invalid or forbidden manifest file: {name}")
        if type(row.get("size")) is not int or row["size"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", ""))):
            raise ReleaseError(f"Invalid size/hash: {name}")
        expected[name] = row
    if not expected:
        raise ReleaseError("Release file list is empty.")
    directories = {relative_name(v) for v in payload.get("directories", [])}
    scaffolds = {relative_name(v) for v in payload.get("scaffolds", [])}
    config = config_paths(root)
    required_scaffolds = {config["raw_cache"], *parents_of(config["raw_cache"])}
    if scaffolds != required_scaffolds or not scaffolds.issubset(directories):
        raise ReleaseError("Only the configured empty cache scaffolds may bypass directory exclusions.")
    actual, actual_dirs, forbidden = release_inventory(root, scaffolds)
    actual.discard(manifest_name)
    missing, extra = sorted(set(expected) - actual), sorted(actual - set(expected))
    changed = [name for name in sorted(set(expected) & actual)
               if bounded_path(root, name).stat().st_size != expected[name]["size"]
               or sha256(bounded_path(root, name)) != expected[name]["sha256"]]
    module_name = relative_name(payload.get("module_manifest"))
    modules = load_modules(bounded_path(root, module_name))
    selected = select_modules(modules, payload.get("modules"))
    if any(item["channel"] != "stable" for item in selected):
        raise ReleaseError("Preview modules cannot be included in stable portable releases.")
    available = {item["name"] for item in selected if (root / config["skills_root"] / item["name"] / "SKILL.md").is_file()}
    dependencies = dependency_errors(selected, available, modules["modules"])
    from quick_validate import validate as validate_skill
    for item in selected:
        valid, message = validate_skill(root / config["skills_root"] / item["name"])
        if not valid:
            dependencies.append(f"{item['name']}: {message}")
    expected_stable = {item["name"] for item in select_modules(modules)}
    if available != expected_stable:
        dependencies.append("Released modules do not equal the declared stable module set.")
    security: list[str] = []
    evidence = {"status": "not_run", "content_reverified": False}
    if not (missing or extra or changed or forbidden):
        selected_files = set(release_selection(root, root / module_name)["files"])
        if set(expected) != selected_files:
            dependencies.append("Manifest file set does not match the module allowlist.")
        from portable_security_scan import scan
        security = scan(root, paths=sorted(actual))
        checker = TRUSTED_ROOT / "skills/grow-creative-library/scripts/audit_source_evidence.py"
        if config.get("source_evidence") and checker.is_file():
            env = os.environ.copy()
            env.update(KNOWLEDGE_TREE_CONFIG=str(root / ".codex/knowledge-tree.json"), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
            checked = subprocess.run([sys.executable, "-B", "-X", "utf8", str(checker), "--config",
                                      str(root / ".codex/knowledge-tree.json"), "--strict", "--json"],
                                     capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
            evidence = {"status": "checked" if checked.returncode == 0 else "invalid",
                        "content_reverified": False, "output": checked.stdout.strip()}
            if checked.returncode:
                dependencies.append("Long-term evidence identity/note binding validation failed.")
        elif config.get("source_evidence"):
            evidence = {"status": "unavailable", "content_reverified": False}
            dependencies.append("Required long-term evidence checker is missing from trusted tools.")
    result = {"ok": not (missing or extra or changed or forbidden or dependencies or security or directories != actual_dirs),
              "mode": "Release", "missing": missing, "extra": extra, "changed": changed,
              "missing_directories": sorted(directories - actual_dirs), "extra_directories": sorted(actual_dirs - directories),
              "forbidden": forbidden, "dependency_errors": dependencies, "security_findings": security,
              "evidence": evidence}
    return result

def daily_check(root: Path, *, skip_audits: bool = False) -> dict[str, Any]:
    root = root.resolve(strict=True)
    env = os.environ.copy()
    env.update(KNOWLEDGE_TREE_CONFIG=str(root / ".codex/knowledge-tree.json"), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    config = target_config(root).as_dict()
    data = load_modules(bounded_path(root, MODULE_MANIFEST))
    modules = select_modules(data)
    skills_root = Path(config["skills_root"])
    available = {item["name"] for item in modules if (skills_root / item["name"] / "SKILL.md").is_file()}
    errors = dependency_errors(modules, available, data["modules"])
    for item in modules:
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(TRUSTED_ROOT / "scripts/quick_validate.py"),
                                 str(skills_root / item["name"])], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", env=env)
        if result.returncode:
            errors.append(f"{item['name']}: {result.stdout.strip()} {result.stderr.strip()}")
    evidence_path = config.get("source_evidence")
    evidence_result: dict[str, Any] = {"status": "not_configured"}
    if evidence_path:
        evidence = Path(evidence_path)
        if not evidence.is_dir() or not evidence.resolve().is_relative_to(root):
            errors.append("source_evidence is missing or outside workspace.")
        else:
            evidence_result = {"status": "identity_files_checked", "records": 0,
                               "source_recheck": "not_run"}
            # Full identity/reference validation is delegated to the configured evidence checker when present.
            checker = TRUSTED_ROOT / "skills/grow-creative-library/scripts/audit_source_evidence.py"
            if checker.is_file():
                checked = subprocess.run([sys.executable, "-B", "-X", "utf8", str(checker),
                                          "--config", str(root / ".codex/knowledge-tree.json"), "--strict", "--json"],
                                         capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
                evidence_result = {"status": "checked" if checked.returncode == 0 else "needs_attention",
                                   "output": checked.stdout.strip(), "source_recheck": "not_run"}
                if checked.returncode:
                    errors.append("Evidence identity/binding validation failed: " + checked.stderr.strip())
            else:
                evidence_result = {"status": "unavailable", "source_recheck": "not_run"}
                errors.append("Required long-term evidence checker is missing from trusted tools.")
    audit_results = []
    if not skip_audits:
        library_relative = Path(config["knowledge_library"]).relative_to(Path(config["vault"])).as_posix()
        jobs = [
            [TRUSTED_ROOT / "skills/grow-creative-library/scripts/audit_knowledge_system.py", "--scope", library_relative, "--strict"],
            [TRUSTED_ROOT / "skills/weave-film-knowledge-connections/scripts/audit_connections.py", "--strict"],
            [TRUSTED_ROOT / "skills/curate-ai-prompt-treasure-box/scripts/inspect_prompt_box.py", "--check"],
        ]
        for job in jobs:
            result = subprocess.run([sys.executable, "-B", "-X", "utf8", *map(str, job)],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
            audit_results.append({"script": Path(job[0]).name, "exit_code": result.returncode,
                                  "output": result.stdout.strip()})
            if result.returncode:
                errors.append(f"Audit failed: {Path(job[0]).name}")
    markdown_count = sum(1 for p in Path(config["vault"]).rglob("*.md") if ".trash" not in p.parts and p.is_file())
    return {"ok": not errors, "mode": "Daily", "workspace": str(root), "markdown": markdown_count,
            "stable_modules": sorted(available), "preview_modules": [m["name"] for m in data["modules"] if m["channel"] == "preview"],
            "evidence": evidence_result, "audits": audit_results, "errors": errors,
            "migration_baseline": "not_compared"}

def installed_target(explicit: Path | None) -> Path:
    """Match install-skills.ps1's existing target precedence, without creating it."""
    if explicit is not None:
        return explicit
    if os.environ.get("CODEX_HOME"):
        return Path(os.environ["CODEX_HOME"]) / "skills"
    profile = os.environ.get("USERPROFILE")
    if profile and (Path(profile) / ".codex").exists():
        return Path(profile) / ".codex" / "skills"
    raise ReleaseError("Pass -TargetSkillsRoot explicitly; no Codex Skills root was found.")


def checked_directory(path: Path, *, required: bool = False) -> Path:
    """Inspect the root and every ancestor before resolving any directory link."""
    if ".." in path.parts:
        raise ReleaseError("Installed comparison paths must not contain '..'.")
    path = path.absolute()
    for parent in reversed((path, *path.parents)):
        try:
            if reparse(parent):
                raise ReleaseError(f"Directory links are not comparison inputs: {parent}")
        except FileNotFoundError:
            continue
    if path.exists() and not path.is_dir():
        raise ReleaseError(f"Expected a directory: {path}")
    if required and not path.is_dir():
        raise ReleaseError(f"Required comparison directory is missing: {path}")
    return path


def skill_inventory(base: Path) -> tuple[dict[str, str], list[str]]:
    """Same install exclusions; ignored directories are counted once, not traversed."""
    files: dict[str, str] = {}
    ignored: list[str] = []
    checked_directory(base)
    if not base.exists():
        return files, ignored

    def visit(folder: Path) -> None:
        for path in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
            name = path.relative_to(base).as_posix()
            if excluded_reason(name):
                ignored.append(name)
                continue
            bounded_path(base, name)
            if path.is_dir():
                visit(path)
            elif path.is_file():
                before = path.stat()
                digest = sha256(path)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                        after.st_size, after.st_mtime_ns, after.st_ino):
                    raise ReleaseError(f"File changed while comparing: {path}")
                files[name] = digest
            else:
                raise ReleaseError(f"Not a regular comparison file: {path}")
    visit(base)
    return files, ignored


def verify_installed(root: Path, target: Path | None = None,
                     names: list[str] | None = None) -> dict[str, Any]:
    root = checked_directory(root, required=True)
    # The shared loader validates paths; inspect the declared path too, before its
    # resolution could hide a junction leading to another directory in the workspace.
    config_paths(root)
    raw_config = load_json(bounded_path(root, ".codex/knowledge-tree.json"))
    source_root = checked_directory(root / raw_config["skills_root"], required=True)
    target = checked_directory(installed_target(target))
    if target.is_relative_to(source_root) or source_root.is_relative_to(target):
        raise ReleaseError("Canonical and installed skill roots must not overlap.")
    catalog = load_modules(bounded_path(root, MODULE_MANIFEST))
    selected = select_modules(catalog, names)
    if any(item["channel"] != "stable" for item in selected):
        raise ReleaseError("Installed mode accepts only declared stable modules.")
    lookup = {item["name"]: item for item in catalog["modules"]}
    required: set[str] = set()
    pending = [item["name"] for item in selected]
    while pending:
        name = pending.pop()
        if name in required:
            continue
        required.add(name)
        if lookup[name]["channel"] != "stable":
            raise ReleaseError(f"Stable comparison depends on a preview module: {name}")
        pending.extend(lookup[name]["requires"])
    # Only dependency entry existence is checked, without loading their code/body.
    available = {name for name in required
                 if bounded_path(target, name + "/SKILL.md", exists=False).is_file()}
    dependencies = dependency_errors(selected, available, catalog["modules"])
    reports = []
    for item in selected:
        name = item["name"]
        source = bounded_path(source_root, name)
        entry = bounded_path(source_root, name + "/SKILL.md")
        if not entry.is_file():
            raise ReleaseError(f"Canonical Skill entry is missing: {name}")
        destination = bounded_path(target, name, exists=False)
        expected, source_ignored = skill_inventory(source)
        actual, target_ignored = skill_inventory(destination)
        missing = sorted(expected.keys() - actual.keys())
        changed = sorted(p for p in expected.keys() & actual.keys() if expected[p] != actual[p])
        extra = sorted(actual.keys() - expected.keys())
        reports.append({"module": name, "source_files": len(expected), "installed_files": len(actual),
                        "matching_files": len(expected.keys() & actual.keys()) - len(changed),
                        "missing": missing, "changed": changed, "extra": extra,
                        "ignored": {"source": source_ignored, "installed": target_ignored,
                                    "count": len(source_ignored) + len(target_ignored)}})
    consistent = not dependencies and not any(r["missing"] or r["changed"] or r["extra"] for r in reports)
    return {"ok": consistent, "mode": "Installed",
            "status": "consistent" if consistent else "differences",
            "workspace": str(root), "source": str(source_root), "target": str(target),
            "target_exists": target.is_dir(), "selected": [m["name"] for m in selected],
            "source_files": sum(r["source_files"] for r in reports),
            "ignored_entries": sum(r["ignored"]["count"] for r in reports),
            "modules": reports, "dependency_errors": dependencies, "writes": False,
            "interpretation": "差异须核对来源；额外文件待判断，不自动认定定制或废弃。"
                              "忽略数量按被跳过的目录或文件计数，未递归展开。仅验证文件与入口，不验证实际使用效果。"}


def install_modules(root: Path, target: Path, names: list[str] | None, apply: bool) -> dict[str, Any]:
    data = load_modules(bounded_path(root, MODULE_MANIFEST))
    config = config_paths(root)
    source_root = bounded_path(root, config["skills_root"])
    selected = select_modules(data, names)
    previews = [item for item in selected if item["channel"] == "preview"]
    result: dict[str, Any] = {"ok": True, "apply": apply, "target": str(target),
                              "selected": [item["name"] for item in selected],
                              "count": len(selected), "preview_units": []}
    if previews:
        units = {item["unit"] for item in previews}
        result["preview_units"] = [{"unit": unit, "members": [m["name"] for m in data["modules"] if m.get("unit") == unit],
                                    "requires": sorted({dep for m in data["modules"] if m.get("unit") == unit for dep in m["requires"]}),
                                    "status": "preview_not_accepted"} for unit in sorted(units)]
        if apply:
            raise ReleaseError("Preview modules are not accepted for installation; no files were written.")
        return result
    available = {m["name"] for m in selected}
    if target.is_dir():
        available.update(m["name"] for m in data["modules"] if (target / m["name"] / "SKILL.md").is_file())
    dependencies = dependency_errors(selected, available, data["modules"])
    result["dependency_errors"] = dependencies
    if not apply:
        return result
    if dependencies:
        raise ReleaseError("Missing installed/selected dependencies: " + "; ".join(dependencies))
    if target.resolve().is_relative_to(source_root.resolve()):
        raise ReleaseError("Cannot install onto canonical skills.")
    # Preflight every source and destination before the first write.
    from quick_validate import validate as validate_skill
    for item in selected:
        valid, message = validate_skill(source_root / item["name"])
        if not valid:
            raise ReleaseError(f"Invalid source Skill {item['name']}: {message}")
    selection: list[tuple[Path, str]] = []
    for item in selected:
        source = bounded_path(root, config["skills_root"] + "/" + item["name"])
        def visit_install(base: Path) -> None:
            for path in base.iterdir():
                relative = path.relative_to(source).as_posix()
                if excluded_reason(relative):
                    continue
                bounded_path(source, relative)
                if path.is_dir():
                    visit_install(path)
                elif path.is_file():
                    destination = item["name"] + "/" + relative
                    bounded_path(target, destination, exists=False)
                    selection.append((path, destination))
        visit_install(source)
    for source, name in selection:
        destination = bounded_path(target, name, exists=False)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if sha256(source) != sha256(destination):
            raise ReleaseError(f"Installed hash mismatch: {name}")
    # Existing unselected or older installed modules are deliberately not removed.
    return result

def make_package(root: Path, output: Path, module_manifest: Path | None, preview: bool) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if ".." in output.parts:
        raise ReleaseError("Output path must not contain '..'.")
    output = output.absolute()
    if output.resolve().is_relative_to(root):
        raise ReleaseError("Output ZIP must be outside the portable workspace.")
    if output.exists():
        raise ReleaseError("Output ZIP already exists; it will not be overwritten.")
    selection = release_selection(root, module_manifest)
    if preview:
        return {"ok": True, "preview": True, "output": str(output), **selection}
    if not output.parent.is_dir():
        raise ReleaseError("Output parent directory must already exist.")
    # release_selection resolves raw_cache through the shared configuration loader.
    # Allocate only after Preview returns; host TEMP is never a release path source.
    staging_parent = bounded_path(root, selection["raw_cache"] + "/release-staging", exists=False)
    staging_parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with tempfile.TemporaryDirectory(prefix="knowledge-tree-release-", dir=staging_parent) as scratch:
            scratch_root = Path(scratch).resolve()
            if not scratch_root.is_relative_to(staging_parent.resolve()):
                raise ReleaseError("Temporary release directory escaped configured raw_cache staging.")
            stage = scratch_root / root.name
            stage.mkdir()
            for name in selection["directories"]:
                bounded_path(stage, name, exists=False).mkdir(parents=True, exist_ok=True)
            for name in selection["files"]:
                shutil.copyfile(bounded_path(root, name), bounded_path(stage, name, exists=False))
            from portable_security_scan import scan
            findings = scan(stage, paths=selection["files"])
            if findings:
                raise ReleaseError("Release security scan failed (values hidden): " + "; ".join(findings))
            payload = release_manifest(stage, selection)
            (stage / PACKAGE_MANIFEST).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            checked = verify_release(stage, stage / PACKAGE_MANIFEST)
            if not checked["ok"]:
                raise ReleaseError("Staged release verification failed: " + json.dumps(checked, ensure_ascii=False))
            with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                created = True
                for name in selection["directories"]:
                    archive.writestr(root.name + "/" + name + "/", "")
                for name in [*selection["files"], PACKAGE_MANIFEST]:
                    archive.write(bounded_path(stage, name), root.name + "/" + name)
            extracted = scratch_root / "verify-extracted"
            extracted.mkdir()
            with zipfile.ZipFile(output) as archive:
                for info in archive.infolist():
                    name = info.filename.rstrip("/")
                    relative_name(name)
                    if not name.startswith(root.name + "/") or stat.S_ISLNK(info.external_attr >> 16):
                        raise ReleaseError("Unexpected ZIP member.")
                archive.extractall(extracted)
            unpacked = extracted / root.name
            checked = verify_release(unpacked, unpacked / PACKAGE_MANIFEST)
            if not checked["ok"]:
                raise ReleaseError("Extracted release verification failed.")
            return {"ok": True, "preview": False, "output": str(output), "sha256": sha256(output),
                    "files": len(selection["files"]), "modules": selection["modules"],
                    "empty_cache_scaffolds": selection["scaffolds"], "extracted_verified": True,
                    "staging_parent": str(staging_parent),
                    "excluded": selection["excluded"]}
    except BaseException:
        if created and output.is_file():
            output.unlink()
        raise

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    daily = subs.add_parser("daily")
    daily.add_argument("--root", required=True, type=Path)
    daily.add_argument("--skip-audits", action="store_true")
    migration = subs.add_parser("migration")
    migration.add_argument("--root", required=True, type=Path)
    migration.add_argument("--manifest", required=True, type=Path)
    release = subs.add_parser("verify-release")
    release.add_argument("--root", required=True, type=Path)
    release.add_argument("--manifest", required=True, type=Path)
    installed = subs.add_parser("verify-installed")
    installed.add_argument("--root", required=True, type=Path)
    installed.add_argument("--target", type=Path)
    installed.add_argument("--skill-names", nargs="+")
    package = subs.add_parser("package")
    package.add_argument("--root", required=True, type=Path)
    package.add_argument("--output", required=True, type=Path)
    package.add_argument("--module-manifest", type=Path)
    package.add_argument("--preview", action="store_true")
    install = subs.add_parser("install")
    install.add_argument("--root", required=True, type=Path)
    install.add_argument("--target", required=True, type=Path)
    install.add_argument("--skill-names", nargs="+")
    install.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "daily":
            result = daily_check(args.root, skip_audits=args.skip_audits)
        elif args.command == "migration":
            from portable_manifest import verify_manifest
            config = target_config(args.root.resolve(strict=True))
            if load_json(args.manifest).get("version") != 1:
                raise ReleaseError("Migration mode requires a historical version 1 manifest.")
            return verify_manifest(config.vault, args.manifest, {".obsidian/workspace.json"})
        elif args.command == "verify-release":
            result = verify_release(args.root, args.manifest)
        elif args.command == "verify-installed":
            result = verify_installed(args.root, args.target, args.skill_names)
        elif args.command == "package":
            result = make_package(args.root, args.output, args.module_manifest, args.preview)
        else:
            result = install_modules(args.root.resolve(strict=True), args.target, args.skill_names, args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"ok": False, "error": str(exc)}
        if args.command == "verify-installed":
            result.update(mode="Installed", status="check_failed", writes=False)
        print(json.dumps(result, ensure_ascii=False))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
