from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from knowledge_tree_config import load_config


CONFIG = load_config()
DEFAULT_EXECUTABLE = CONFIG.obsidian_cli
DEFAULT_VAULT_NAME = CONFIG.vault_name
DEFAULT_VAULT_PATH = CONFIG.vault
TARGET_MISMATCH = 78
CLI_ARGUMENT_ERROR = 64
CLI_RESPONSE_ERROR = 65
INDEX_MISMATCH = 79
# These commands may legitimately return arbitrary note text or evaluated values.
RAW_OUTPUT_COMMANDS = {"read", "daily:read", "history:read", "eval", "diff"}
APPDATA = os.environ.get("APPDATA")
DEFAULT_REGISTRY_PATH = Path(APPDATA) / "obsidian" / "obsidian.json" if APPDATA else None


@dataclass
class CliResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    target_mismatch: bool = False


class ObsidianCLI:
    def __init__(
        self,
        executable: Path | None = DEFAULT_EXECUTABLE,
        vault_name: str = DEFAULT_VAULT_NAME,
        vault_path: Path = DEFAULT_VAULT_PATH,
        registry_path: Path | None = DEFAULT_REGISTRY_PATH,
    ) -> None:
        self.executable = Path(executable).resolve() if executable is not None else None
        self.vault_name = vault_name
        self.vault_path = Path(vault_path).resolve()
        self.registry_path = Path(registry_path).resolve() if registry_path is not None else None

    def _execute(self, arguments: list[str], timeout: int = 15) -> CliResult:
        if self.executable is None or not self.executable.exists():
            return CliResult(127, stderr="Obsidian CLI 尚未安装；当前仅允许本地只读检索。")
        if os.name == "nt" and any("\n" in arg or "\r" in arg for arg in arguments):
            return CliResult(
                CLI_ARGUMENT_ERROR,
                stderr=("Windows Obsidian CLI的原始多行参数存在IPC解析风险，已在发送前停止。"
                        "内容参数请使用官方\\n转义；复杂eval请用短单行调用加载已审本地脚本。"),
            )

        command = [str(self.executable), f"vault={self.vault_name}", *arguments]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else exc.stdout
            stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else exc.stderr
            return CliResult(124, stdout or "", stderr or "Obsidian CLI 超时", timed_out=True)
        return CliResult(completed.returncode, completed.stdout.strip(), completed.stderr.strip())

    @staticmethod
    def _reported_path(stdout: str) -> Path | None:
        lines = [line.strip().strip('"') for line in stdout.splitlines() if line.strip()]
        if not lines:
            return None
        candidate = Path(lines[-1])
        return candidate.resolve() if candidate.is_absolute() else None

    def _registered_targets(self) -> tuple[list[Path], str]:
        if self.registry_path is None:
            return [], "APPDATA 不可用，无法读取 Obsidian 仓库注册表。"
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8-sig"))
            vaults = payload.get("vaults", {})
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            return [], f"无法读取 Obsidian 仓库注册表 {self.registry_path}：{exc}"
        if not isinstance(vaults, dict):
            return [], f"Obsidian 仓库注册表格式错误：{self.registry_path}"
        targets: list[Path] = []
        for entry in vaults.values():
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                continue
            candidate = Path(entry["path"])
            if candidate.name.casefold() == self.vault_name.casefold():
                targets.append(candidate.resolve())
        return targets, ""

    def _target_mismatch(self, actual: str, detail: str = "") -> CliResult:
        suffix = f" {detail}" if detail else ""
        return CliResult(
            TARGET_MISMATCH,
            stderr=(
                "Obsidian 仓库定向不一致，已停止操作。"
                f" vault_name={self.vault_name!r} 解析为 {actual}，配置目标为 {self.vault_path.resolve()}。"
                f"{suffix}"
            ),
            target_mismatch=True,
        )

    def verify_target(self, timeout: int = 15) -> CliResult:
        if self.executable is None or not self.executable.exists():
            return CliResult(127, stderr="Obsidian CLI 尚未安装；不能执行 Obsidian 查询或写入。")
        registered, registry_error = self._registered_targets()
        if registry_error:
            return self._target_mismatch("<无法解析>", registry_error)
        if len(registered) != 1:
            shown = ", ".join(str(path) for path in registered) or "<未注册>"
            return self._target_mismatch(shown, "仓库名必须唯一匹配一个已注册路径。")
        expected = self.vault_path.resolve()
        registered_path = registered[0].resolve()
        if os.path.normcase(str(registered_path)) != os.path.normcase(str(expected)):
            return self._target_mismatch(str(registered_path))

        result = self._normalize_result(
            ["vault", "info=path"], self._execute(["vault", "info=path"], timeout=timeout)
        )
        if result.returncode != 0:
            return result
        actual = self._reported_path(result.stdout)
        if actual is None or os.path.normcase(str(actual)) != os.path.normcase(str(expected)):
            shown = str(actual) if actual is not None else result.stdout or "<无法解析>"
            return self._target_mismatch(shown, "CLI 返回路径与注册表预检结果不一致。")
        return CliResult(0, str(actual), result.stderr)

    def run(self, arguments: list[str], timeout: int = 15) -> CliResult:
        target = self.verify_target(timeout=min(timeout, 15))
        if target.returncode != 0:
            return target
        return self._normalize_result(arguments, self._execute(arguments, timeout=timeout))

    def _normalize_result(self, arguments: list[str], result: CliResult) -> CliResult:
        """Some native CLI failures are printed as text with process exit code zero."""
        if result.returncode != 0:
            return result
        command = arguments[0] if arguments else ""
        diagnostic = next(
            (line.strip() for line in result.stderr.splitlines() if re.match(r"^\s*Error:", line)), ""
        )
        if not diagnostic and command not in RAW_OUTPUT_COMMANDS:
            diagnostic = next(
                (line.strip() for line in result.stdout.splitlines() if re.match(r"^\s*Error:", line)), ""
            )
        # A note can itself start with "Error: ...". Resolve its native file first
        # only when a read returned the exact shape of a missing-file diagnostic.
        if not diagnostic and command in {"read", "daily:read", "history:read"}:
            first = result.stdout.splitlines()[0] if result.stdout else ""
            locator = [arg for arg in arguments[1:] if arg.startswith(("path=", "file="))]
            if locator and re.fullmatch(r'Error:\s*File\s+.*not found\.?', first.strip(), re.IGNORECASE):
                probe_args = ["file", *locator]
                probe = self._normalize_result(probe_args, self._execute(probe_args))
                if probe.returncode != 0:
                    return CliResult(probe.returncode, result.stdout, probe.stderr)
        if diagnostic:
            return CliResult(CLI_RESPONSE_ERROR, result.stdout, diagnostic)
        return result

    def check_files(self, timeout: int = 30) -> CliResult:
        """Compare paths, not just counts; never refresh, restart or delete files."""
        native = self.run(["files", "ext=md"], timeout=timeout)
        if native.returncode != 0:
            return native
        lines = [line.strip().replace("\\", "/") for line in native.stdout.splitlines() if line.strip()]
        if any(not line.lower().endswith(".md") or Path(line).is_absolute() or ".." in Path(line).parts for line in lines):
            return CliResult(CLI_RESPONSE_ERROR, native.stdout, "Obsidian文件列表格式不符合路径清单；无法证明原生识别完整。")
        disk = {
            path.relative_to(self.vault_path).as_posix()
            for path in self.vault_path.rglob("*.md")
            if ".obsidian" not in path.parts and ".trash" not in path.parts
        }
        reported = set(lines)
        missing, extra = sorted(disk - reported), sorted(reported - disk)
        payload = {
            "filesystem_markdown": len(disk), "obsidian_markdown": len(reported),
            "paths_match": not missing and not extra,
            "missing_from_obsidian": missing, "only_in_obsidian": extra,
        }
        message = "" if payload["paths_match"] else (
            "Obsidian原生文件视图与磁盘不一致；文件存在不能当作应用已识别。"
            "本检查没有重启应用、刷新缓存或修改笔记。"
        )
        return CliResult(0 if payload["paths_match"] else INDEX_MISMATCH,
                         json.dumps(payload, ensure_ascii=False), message)

    def search(self, query: str, folder: str | None = None, limit: int = 50) -> CliResult:
        if self.executable is None or not self.executable.exists():
            return self._fallback_search(
                query,
                folder,
                limit,
                CliResult(127, stderr="Obsidian CLI 尚未安装。"),
            )
        arguments = ["search", f"query={query}", f"limit={limit}", "format=json"]
        if folder:
            arguments.append(f"path={folder}")
        result = self.run(arguments)
        if result.returncode == 0 and result.stdout:
            return result
        if result.target_mismatch:
            return result
        return self._fallback_search(query, folder, limit, result)

    def _fallback_search(
        self, query: str, folder: str | None, limit: int, cli_result: CliResult
    ) -> CliResult:
        root = (self.vault_path / folder).resolve() if folder else self.vault_path.resolve()
        vault = self.vault_path.resolve()
        if not root.exists() or vault not in (root, *root.parents):
            return cli_result

        needle = query.casefold()
        matches: list[str] = []
        for path in sorted(root.rglob("*.md")):
            if ".obsidian" in path.parts or ".trash" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            if needle in path.stem.casefold() or needle in text.casefold():
                matches.append(path.relative_to(vault).as_posix())
            if len(matches) >= limit:
                break

        note = "Obsidian CLI 搜索不可用，已回退到已校验目标仓库的本地 Markdown 搜索。"
        if cli_result.stderr:
            note += f" CLI: {cli_result.stderr}"
        return CliResult(0, "\n".join(matches), note)


def print_result(result: CliResult) -> int:
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Official Obsidian CLI wrapper for the knowledge tree.")
    parser.add_argument("--vault-name", default=DEFAULT_VAULT_NAME)
    parser.add_argument("--vault-path", "--vault", dest="vault_path", type=Path, default=DEFAULT_VAULT_PATH)
    parser.add_argument("--executable", type=Path, default=DEFAULT_EXECUTABLE)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check")

    search = subparsers.add_parser("search")
    search.add_argument("query")
    search.add_argument("--path")
    search.add_argument("--limit", type=int, default=50)

    for command in ("backlinks", "properties"):
        item = subparsers.add_parser(command)
        item.add_argument("path")

    tasks = subparsers.add_parser("tasks")
    tasks.add_argument("--all", action="store_true")
    tasks.add_argument("--total", action="store_true")

    unresolved = subparsers.add_parser("unresolved")
    unresolved.add_argument("--total", action="store_true")
    unresolved.add_argument("--verbose", action="store_true")

    for command in ("orphans", "deadends"):
        item = subparsers.add_parser(command)
        item.add_argument("--total", action="store_true")

    move = subparsers.add_parser("move")
    move.add_argument("source")
    move.add_argument("destination")
    move.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    cli = ObsidianCLI(args.executable, args.vault_name, args.vault_path)

    if args.command == "check":
        if cli.executable is None or not cli.executable.exists():
            markdown_count = sum(
                1
                for path in cli.vault_path.rglob("*.md")
                if ".obsidian" not in path.parts and ".trash" not in path.parts
            )
            print("CLI: unavailable")
            print(f"Vault name: {cli.vault_name}")
            print(f"Vault: {cli.vault_path}")
            print(f"Markdown: {markdown_count}")
            print("Mode: local read-only")
            return 0
        path_result = cli.verify_target()
        files_result = cli.check_files() if path_result.returncode == 0 else path_result
        print(f"CLI: {cli.executable}")
        print(f"Vault name: {cli.vault_name}")
        print(f"Vault: {path_result.stdout or cli.vault_path}")
        try:
            inventory = json.loads(files_result.stdout)
        except (json.JSONDecodeError, TypeError):
            inventory = {}
        print(f"Markdown: {inventory.get('obsidian_markdown', 'unknown')}")
        if inventory:
            print(f"Filesystem Markdown: {inventory['filesystem_markdown']}")
            print(f"Index: {'consistent' if inventory['paths_match'] else 'mismatch'}")
            if not inventory["paths_match"]:
                print(files_result.stdout)
        if path_result.returncode or files_result.returncode:
            if path_result.stderr:
                print(path_result.stderr, file=sys.stderr)
            if files_result.stderr:
                print(files_result.stderr, file=sys.stderr)
            return path_result.returncode or files_result.returncode
        return 0

    if args.command == "search":
        return print_result(cli.search(args.query, args.path, args.limit))

    if args.command == "backlinks":
        return print_result(cli.run(["backlinks", f"path={args.path}", "format=json"]))

    if args.command == "properties":
        return print_result(cli.run(["properties", f"path={args.path}", "format=json"]))

    if args.command == "tasks":
        command = ["tasks"]
        if not args.all:
            command.append("todo")
        command.append("total" if args.total else "format=json")
        return print_result(cli.run(command))

    if args.command == "unresolved":
        command = ["unresolved"]
        if args.total:
            command.append("total")
        else:
            if args.verbose:
                command.append("verbose")
            command.append("format=json")
        return print_result(cli.run(command))

    if args.command in {"orphans", "deadends"}:
        command = [args.command]
        if args.total:
            command.append("total")
        return print_result(cli.run(command))

    if args.command == "move":
        if not args.apply:
            print(f"PREVIEW: {args.source} -> {args.destination}")
            print("Add --apply only after the move has been reviewed.")
            return 0
        return print_result(
            cli.run(["move", f"path={args.source}", f"to={args.destination}"], timeout=30)
        )

    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
