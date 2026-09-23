from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from obsidian_cli import TARGET_MISMATCH, CliResult, ObsidianCLI


class FakeObsidianCLI(ObsidianCLI):
    def __init__(self, vault_path: Path, actual_path: Path, command_result: CliResult | None = None):
        executable = vault_path.parent / "fake.com"
        executable.write_text("stub", encoding="utf-8")
        super().__init__(executable, "configured-vault", vault_path)
        self.actual_path = actual_path
        self.command_result = command_result or CliResult(0, "ok")
        self.calls: list[list[str]] = []

    def _registered_targets(self) -> tuple[list[Path], str]:
        return [self.actual_path], ""

    def _execute(self, arguments: list[str], timeout: int = 15) -> CliResult:
        self.calls.append(arguments)
        if arguments == ["vault", "info=path"]:
            return CliResult(0, str(self.actual_path))
        return self.command_result


class ObsidianCLITargetTests(unittest.TestCase):
    def test_missing_obsidian_allows_only_local_read_only_search(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            vault.mkdir()
            (vault / "match.md").write_text("portable needle", encoding="utf-8")
            cli = ObsidianCLI(None, "vault", vault, registry_path=None)
            search = cli.search("needle")
            write_like_query = cli.run(["move", "path=a.md", "to=b.md"])
            self.assertEqual(search.returncode, 0)
            self.assertIn("match.md", search.stdout)
            self.assertIn("本地 Markdown 搜索", search.stderr)
            self.assertEqual(write_like_query.returncode, 127)

    def test_matching_name_and_path_allows_query(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            vault.mkdir()
            cli = FakeObsidianCLI(vault, vault, CliResult(0, "65"))
            result = cli.run(["files", "ext=md", "total"])
            self.assertEqual(result.returncode, 0)
            self.assertEqual(cli.calls[-1], ["files", "ext=md", "total"])

    def test_mismatch_blocks_query(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configured = root / "configured"
            actual = root / "actual"
            configured.mkdir()
            actual.mkdir()
            cli = FakeObsidianCLI(configured, actual)
            result = cli.run(["tasks", "todo", "total"])
            self.assertEqual(result.returncode, TARGET_MISMATCH)
            self.assertTrue(result.target_mismatch)
            self.assertEqual(cli.calls, [])

    def test_search_does_not_hide_mismatch_with_local_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configured = root / "configured"
            actual = root / "actual"
            configured.mkdir()
            actual.mkdir()
            (configured / "match.md").write_text("needle", encoding="utf-8")
            result = FakeObsidianCLI(configured, actual).search("needle")
            self.assertEqual(result.returncode, TARGET_MISMATCH)
            self.assertTrue(result.target_mismatch)

    def test_move_apply_command_is_blocked_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configured = root / "configured"
            actual = root / "actual"
            configured.mkdir()
            actual.mkdir()
            cli = FakeObsidianCLI(configured, actual)
            result = cli.run(["move", "path=a.md", "to=b.md"], timeout=30)
            self.assertEqual(result.returncode, TARGET_MISMATCH)
            self.assertNotIn(["move", "path=a.md", "to=b.md"], cli.calls)


if __name__ == "__main__":
    unittest.main()
