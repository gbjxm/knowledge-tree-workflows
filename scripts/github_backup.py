#!/usr/bin/env python3
"""On-demand GitHub snapshots and isolated, byte-verified restores."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
import uuid

import release_core as release
from portable_security_scan import scan

ATTRIBUTES = b"* -text -filter -ident -working-tree-encoding\n"
MAX_FILE = 100 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}")
TAG_PREFIX = "verified-backup-"


class BackupError(RuntimeError):
    pass


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(args, *, cwd=None, data=None):
    env = os.environ.copy()
    env.update(GIT_TERMINAL_PROMPT="0", GH_PROMPT_DISABLED="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    # A caller's unrelated Git worktree/index must never redirect this operation.
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        env.pop(key, None)
    try:
        result = subprocess.run([str(v) for v in args], cwd=cwd, input=data,
                                capture_output=True, env=env, timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise BackupError("Command timed out; remote state must be checked before retry.") from exc
    if result.returncode:
        raise BackupError(f"{Path(str(args[0])).name} failed ({result.returncode}): "
                          + result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


class Github:
    def __init__(self, target):
        self.repository = target["repository"]
        self.branch = target["branch"]
        self.url = f"https://github.com/{self.repository}.git"

    def api(self, endpoint):
        return json.loads(run(["gh", "api", endpoint]))

    def preflight(self):
        info = self.api(f"repos/{self.repository}")
        if (not isinstance(info, dict) or not isinstance(info.get("full_name"), str)
                or info["full_name"].casefold() != self.repository.casefold()):
            raise BackupError("Target must be the configured repository.")
        private, visibility = info.get("private"), info.get("visibility")
        if (type(private) is not bool or visibility not in ("private", "public")
                or private != (visibility == "private")):
            raise BackupError("Repository visibility must have consistent public/private metadata.")
        permissions = info.get("permissions")
        if (info.get("archived") is not False or info.get("disabled") is not False
                or not isinstance(permissions, dict)
                or permissions.get("push") is not True):
            raise BackupError("Target must be unarchived, enabled, with confirmed push access.")
        run(["git", "check-ref-format", f"refs/heads/{self.branch}"])
        user = self.api("user")
        return {"repository": info["full_name"], "private": private,
                "visibility": visibility, "branch": self.branch,
                "author": user["login"], "email": f"{user['id']}+{user['login']}@users.noreply.github.com"}

    def git(self, *args, cwd=None, data=None):
        return run(["git", "-c", "credential.helper=",
                    "-c", "credential.helper=!gh auth git-credential",
                    "-c", "core.autocrlf=false", "-c", "core.safecrlf=false",
                    "-c", "core.longpaths=true",
                    "-c", "core.attributesFile=NUL", *args], cwd=cwd, data=data)

    def refs(self):
        text = self.git("ls-remote", self.url).decode("utf-8")
        return {ref: sha for sha, ref in (line.split("\t") for line in text.splitlines())}

    def manifest(self, sha):
        data = self.api(f"repos/{self.repository}/contents/{release.PACKAGE_MANIFEST}?ref={sha}")
        if data.get("encoding") != "base64":
            raise BackupError("Remote manifest is unavailable or too large.")
        return json.loads(base64.b64decode(data["content"]))

    def clone(self, destination):
        self.git("clone", "--no-checkout", "--", self.url, str(destination))

    def push(self, work, source, destination):
        self.git("push", "origin", f"{source}:{destination}", cwd=work)


def fingerprint(manifest):
    keys = ("version", "purpose", "manifest_path", "module_manifest", "modules",
            "directories", "scaffolds", "files")
    raw = json.dumps({k: manifest.get(k) for k in keys}, ensure_ascii=False,
                     sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def inspect_source(root):
    selection = release.release_selection(root)
    for name in selection["files"]:
        path = release.bounded_path(root, name)
        if path.stat().st_size >= MAX_FILE:
            raise BackupError(f"File reaches the plain Git backup limit (100 MiB): {name}")
        if path.name.casefold() == ".gitattributes":
            raise BackupError(f"Nested Git attributes require explicit review: {name}")
    findings = scan(root, paths=selection["files"])
    # Supplement structured secret scanning with recognizable token/private-key signatures.
    token = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|"
                       rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
    for name in selection["files"]:
        path = release.bounded_path(root, name)
        if path.suffix.lower() in {".md", ".txt", ".json", ".yaml", ".yml", ".ini", ".conf"}:
            if token.search(path.read_bytes()):
                findings.append("credential signature: " + name)
    if findings:
        raise BackupError("Selected-file safety scan failed: " + "; ".join(findings))
    return selection, release.release_manifest(root, selection)


def copy_snapshot(root, destination, selection, manifest):
    destination.mkdir()
    for name in selection["directories"]:
        release.bounded_path(destination, name, exists=False).mkdir(parents=True, exist_ok=True)
    for name in selection["files"]:
        shutil.copyfile(release.bounded_path(root, name), release.bounded_path(destination, name, exists=False))
    write_json(destination / release.PACKAGE_MANIFEST, manifest)
    _, after = inspect_source(root)
    if fingerprint(after) != fingerprint(manifest):
        raise BackupError("Source files changed during snapshot; no upload was attempted.")
    for row in manifest["files"]:
        path = destination / row["path"]
        if path.stat().st_size != row["size"] or release.sha256(path) != row["sha256"]:
            raise BackupError("Snapshot copy differs from the source inventory: " + row["path"])


def full_validate(root):
    checked = release.verify_release(root, root / release.PACKAGE_MANIFEST)
    if not checked["ok"]:
        return {"ok": False, "release": checked}
    daily = release.daily_check(root)
    env = os.environ.copy()
    env.update(KNOWLEDGE_TREE_CONFIG=str(root / ".codex/knowledge-tree.json"),
               PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    weekly = subprocess.run(
        [sys.executable, "-B", "-X", "utf8",
         str(release.TRUSTED_ROOT / "skills/operate-personal-knowledge-tree/scripts/weekly_review.py"),
         "--local-only", "--json"], capture_output=True, env=env, timeout=180)
    weekly_result = {"exit_code": weekly.returncode}
    if weekly.returncode == 0:
        state = json.loads(weekly.stdout)
        weekly_result["global_state_valid"] = state.get("action_context", {}).get("global_state", {}).get("valid")
        weekly_result["followup"] = state.get("knowledge_followup")
    else:
        weekly_result["error"] = weekly.stderr.decode("utf-8", errors="replace")
    return {"ok": daily["ok"] and weekly.returncode == 0
                  and weekly_result.get("global_state_valid") is True,
            "release": checked, "daily": daily, "weekly_local": weekly_result,
            "raw_material_reverified": False, "obsidian_opened": False}


def tree_blobs(transport, work, commit):
    if not SHA.fullmatch(commit):
        raise BackupError("A full 40-character commit SHA is required.")
    actual = transport.git("rev-parse", "--verify", commit + "^{commit}", cwd=work).decode().strip()
    if actual != commit:
        raise BackupError("Requested object is not the exact commit.")
    entries = {}
    for item in transport.git("ls-tree", "-rz", "--full-tree", commit, cwd=work).split(b"\0"):
        if not item:
            continue
        meta, raw_name = item.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        name = release.relative_name(raw_name.decode("utf-8"))
        if kind != "blob" or mode not in {"100644", "100755"} or name.casefold() in entries:
            raise BackupError("Unsupported or colliding remote entry: " + name)
        entries[name.casefold()] = (name, oid)
    request = "".join(oid + "\n" for name, oid in entries.values()).encode("ascii")
    raw = transport.git("cat-file", "--batch", cwd=work, data=request)
    pos, blobs = 0, {}
    for name, oid in entries.values():
        end = raw.index(b"\n", pos)
        found, kind, size = raw[pos:end].decode().split()
        count = int(size)
        if found != oid or kind != "blob" or count >= MAX_FILE:
            raise BackupError("Invalid remote blob: " + name)
        blobs[name] = raw[end + 1:end + 1 + count]
        pos = end + count + 2
    return blobs


def export_commit(transport, work, commit, destination):
    blobs = tree_blobs(transport, work, commit)
    if blobs.get(".gitattributes") != ATTRIBUTES or release.PACKAGE_MANIFEST not in blobs:
        raise BackupError("Remote commit is not a recognized byte-preserving backup.")
    manifest = json.loads(blobs[release.PACKAGE_MANIFEST])
    expected = {release.PACKAGE_MANIFEST, ".gitattributes"}
    for row in manifest.get("files", []):
        name = release.relative_name(row["path"])
        if name in expected or release.excluded_reason(name):
            raise BackupError("Unsafe or duplicate manifest entry: " + name)
        expected.add(name)
        content = blobs.get(name)
        if content is None or len(content) != row["size"] or hashlib.sha256(content).hexdigest() != row["sha256"]:
            raise BackupError("Remote payload missing or hash mismatch: " + name)
    if set(blobs) != expected:
        raise BackupError("Remote contains files outside its declared backup payload.")
    destination.mkdir()  # Never reuse or overwrite a restore target.
    for name in manifest.get("directories", []):
        release.bounded_path(destination, name, exists=False).mkdir(parents=True, exist_ok=True)
    for name in sorted(expected - {".gitattributes"}):
        path = release.bounded_path(destination, name, exists=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blobs[name])
    return manifest


def prepare_clone_directories(root):
    """Hydrate only missing manifest directories in an explicitly used recovery clone."""
    if not (root / ".git").is_dir():
        return
    manifest = release.load_json(root / release.PACKAGE_MANIFEST)
    if manifest.get("version") != 2 or manifest.get("purpose") != "portable-release":
        raise BackupError("Recovery clone needs its original release manifest.")
    for row in manifest.get("files", []):
        path = release.bounded_path(root, row["path"])
        if path.stat().st_size != row["size"] or release.sha256(path) != row["sha256"]:
            raise BackupError("Recovery clone file differs from its manifest: " + row["path"])
    config = release.load_json(root / ".codex/knowledge-tree.json")
    if config.get("version") != 2 or config.get("workspace") != "..":
        raise BackupError("Cold recovery requires a workspace-relative v2 clone.")
    cache = release.relative_name(config["raw_cache"])
    scaffolds = {cache, *release.parents_of(cache)}
    if set(manifest.get("scaffolds", [])) != scaffolds:
        raise BackupError("Recovery clone cache scaffolds do not match configuration.")
    for name in manifest["directories"]:
        if release.excluded_reason(name) and name not in scaffolds:
            raise BackupError("Forbidden recovery directory: " + name)
        release.bounded_path(root, name, exists=False).mkdir(parents=True, exist_ok=True)


class Backup:
    def __init__(self, root, transport=None, validator=full_validate):
        self.root = root.resolve(strict=True)
        self.config = release.target_config(self.root)
        if not self.config.github_backup:
            raise BackupError("Configure github_backup.repository and branch first.")
        self.transport = transport or Github(self.config.github_backup)
        self.validator = validator
        relative = self.config.raw_cache.relative_to(self.root).as_posix() + "/github-backup"
        self.base = release.bounded_path(self.root, relative, exists=False)
        self.state_path = self.base / "state.json"

    def state(self):
        value = json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {}
        if value and (value.get("repository") != self.transport.repository or value.get("branch") != self.transport.branch):
            raise BackupError("Cache state belongs to another repository or branch; review before changing targets.")
        return value

    def known_head(self, refs, state):
        head = refs.get("refs/heads/" + self.transport.branch)
        verified = any(ref.startswith("refs/tags/" + TAG_PREFIX) and sha == head for ref, sha in refs.items())
        known = {state.get("verified_commit"), state.get("pending_commit")}
        if head and not (head in known or verified):
            raise BackupError(f"Unrecognized remote commit {head}; local verified={state.get('verified_commit')}. "
                              "Compare the remote changes before continuing; nothing was pushed.")
        if not head and (refs or state.get("verified_commit") or state.get("base_commit")):
            raise BackupError("Configured branch is missing but repository/history is not empty.")
        return head

    def preview(self):
        target = self.transport.preflight()
        refs = self.transport.refs()
        head = self.known_head(refs, self.state())
        selection, manifest = inspect_source(self.root)
        old = self.transport.manifest(head) if head else {"files": []}
        before = {r["path"]: r["sha256"] for r in old["files"]}
        after = {r["path"]: r["sha256"] for r in manifest["files"]}
        return {"ok": True, "mode": "preview", "target": target, "remote_head": head,
                "files": len(after), "bytes": sum(r["size"] for r in manifest["files"]),
                "modules": selection["modules"], "directories": len(selection["directories"]),
                "changes": {"added": sorted(after.keys() - before.keys()),
                            "deleted": sorted(before.keys() - after.keys()),
                            "modified": sorted(n for n in after.keys() & before.keys() if before[n] != after[n])},
                "payload_changed": fingerprint(old) != fingerprint(manifest),
                "security": "passed", "excluded": selection["excluded"],
                "writes": False, "restore_validated": False}

    def check(self, root, report_path):
        result = self.validator(root)
        write_json(report_path, result)
        if not result["ok"]:
            raise BackupError("Validation failed; see " + str(report_path))
        return result

    def execute(self, commit=None):
        target = self.transport.preflight()
        self.base.mkdir(parents=True, exist_ok=True)
        lock = self.base / "operation.lock"
        try:
            handle = lock.open("x", encoding="utf-8")
        except FileExistsError as exc:
            raise BackupError("Another backup or interrupted lock exists: " + str(lock)) from exc
        with handle:
            handle.write(json.dumps({"pid": os.getpid(), "started": stamp()}))
        operation = self.base / ("restore-" if commit else "backup-")
        operation = operation.with_name(operation.name + stamp() + "-" + uuid.uuid4().hex[:6])
        operation.mkdir()
        receipt = {"ok": False, "mode": "restore-test" if commit else "apply",
                   "target": target, "started_utc": stamp(), "phase": "preflight",
                   "directory": str(operation), "verified": False}
        try:
            refs = self.transport.refs()
            state = self.state()
            if commit:
                if not SHA.fullmatch(commit):
                    raise BackupError("-Commit requires a full 40-character SHA.")
            else:
                head = self.known_head(refs, state)
                selection, manifest = inspect_source(self.root)
                receipt["phase"] = "snapshot"
                snapshot = operation / "snapshot"
                copy_snapshot(self.root, snapshot, selection, manifest)
                self.check(snapshot, operation / "snapshot-validation.json")
                work = operation / "git-work"
                self.transport.clone(work)
                if self.transport.refs() != refs:
                    raise BackupError("Remote refs changed during snapshot; retry after comparison.")
                old = None
                if head:
                    old_root = operation / "previous"
                    old = export_commit(self.transport, work, head, old_root)
                    self.check(old_root, operation / "previous-validation.json")
                receipt["new_commit"] = not old or fingerprint(old) != fingerprint(manifest)
                if receipt["new_commit"]:
                    for name in selection["files"] + [release.PACKAGE_MANIFEST]:
                        path = release.bounded_path(work, name, exists=False)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(snapshot / name, path)
                    (work / ".gitattributes").write_bytes(ATTRIBUTES)
                    self.transport.git("add", "--force", "--all", "--", ".", cwd=work)
                    tree = self.transport.git("write-tree", cwd=work).decode().strip()
                    args = ["-c", "user.name=" + target["author"], "-c", "user.email=" + target["email"],
                            "commit-tree", tree]
                    if head:
                        args.extend(["-p", head])
                    args.extend(["-F", "-"])
                    commit = self.transport.git(*args, cwd=work,
                        data=f"Knowledge tree backup {stamp()}\n".encode()).decode().strip()
                    staged = export_commit(self.transport, work, commit, operation / "staged-payload")
                    if fingerprint(staged) != fingerprint(manifest):
                        raise BackupError("Git staging altered the snapshot.")
                    state.update(repository=self.transport.repository, branch=self.transport.branch,
                                 pending_commit=commit, base_commit=head)
                    write_json(self.state_path, state)
                    receipt.update(phase="push", commit=commit)
                    self.transport.push(work, commit, "refs/heads/" + self.transport.branch)
                else:
                    commit = head
                    receipt["phase"] = "unchanged"
            receipt.update(commit=commit, phase="remote_restore")
            clone = operation / "remote-clone"
            self.transport.clone(clone)
            restored = operation / "restored"
            restored_manifest = export_commit(self.transport, clone, commit, restored)
            if not commit or (not receipt["mode"] == "restore-test"
                              and fingerprint(restored_manifest) != fingerprint(manifest)):
                raise BackupError("Remote restore differs from this snapshot.")
            self.check(restored, operation / "restore-validation.json")
            receipt.update(phase="tag", restore_path=str(restored),
                           files=len(restored_manifest["files"]),
                           bytes=sum(r["size"] for r in restored_manifest["files"]),
                           directories=len(restored_manifest["directories"]),
                           payload_sha256=fingerprint(restored_manifest),
                           manifest_sha256=release.sha256(restored / release.PACKAGE_MANIFEST),
                           raw_material_reverified=False, obsidian_opened=False)
            # RestoreTest is read-only with respect to the remote.
            if receipt["mode"] == "apply":
                current = self.transport.refs()
                if current.get("refs/heads/" + self.transport.branch) != commit:
                    raise BackupError("Remote branch moved after upload; restored commit passed, but backup not marked complete.")
                existing = sorted(ref[len("refs/tags/"):] for ref, sha in current.items()
                                  if ref.startswith("refs/tags/" + TAG_PREFIX)
                                  and not ref.endswith("^{}") and sha == commit)
                tag = existing[-1] if existing else TAG_PREFIX + stamp()
                if not existing:
                    self.transport.git("tag", tag, commit, cwd=clone)
                    self.transport.push(clone, "refs/tags/" + tag, "refs/tags/" + tag)
                if self.transport.refs().get("refs/tags/" + tag) != commit:
                    raise BackupError("Verification tag was not confirmed on the remote.")
                receipt["tag"] = tag
                state.update(repository=self.transport.repository, branch=self.transport.branch,
                             verified_commit=commit, verified_tag=tag, verified_at=stamp(),
                             pending_commit=None, base_commit=None)
                write_json(self.state_path, state)
            receipt.update(ok=True, verified=True, phase="complete", finished_utc=stamp())
            write_json(operation / "receipt.json", receipt)
            return receipt
        except Exception as exc:
            receipt["error"] = str(exc)
            write_json(operation / "receipt.json", receipt)
            raise BackupError(f"{receipt['phase']}: {exc}; receipt: {operation / 'receipt.json'}") from exc
        finally:
            lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--preview", action="store_true")
    group.add_argument("--apply", action="store_true")
    group.add_argument("--restore-test", action="store_true")
    parser.add_argument("--commit")
    args = parser.parse_args()
    try:
        if bool(args.commit) != args.restore_test:
            raise BackupError("--restore-test and --commit must be used together.")
        if args.restore_test:
            prepare_clone_directories(args.root.resolve(strict=True))
        backup = Backup(args.root)
        result = backup.execute(args.commit) if args.apply or args.restore_test else backup.preview()
        # Detailed paths stay visible in preview; no selected file contents are logged.
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
