from __future__ import annotations

import tempfile
import unittest
from unittest import mock
import os
import subprocess
from pathlib import Path

from obsidian_cli import CLI_ARGUMENT_ERROR, CLI_RESPONSE_ERROR, INDEX_MISMATCH, TARGET_MISMATCH, CliResult, ObsidianCLI


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

    def test_native_error_text_is_not_a_successful_file_query(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            vault.mkdir()
            cli = FakeObsidianCLI(vault, vault, CliResult(0, 'Error: File "a.md" not found.'))
            result = cli.run(["file", "path=a.md"])
            self.assertEqual(result.returncode, CLI_RESPONSE_ERROR)
            self.assertIn("not found", result.stderr)

    def test_literal_error_text_in_a_note_is_preserved_when_native_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            vault.mkdir()
            cli = FakeObsidianCLI(vault, vault)
            original = cli._execute
            def execute(arguments, timeout=15):
                if arguments == ["read", "path=a.md"]:
                    return CliResult(0, 'Error: File "a.md" not found.')
                if arguments == ["file", "path=a.md"]:
                    return CliResult(0, "path\ta.md\nname\ta")
                return original(arguments, timeout)
            cli._execute = execute
            result = cli.run(["read", "path=a.md"])
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, 'Error: File "a.md" not found.')

    def test_raw_read_missing_in_native_view_is_reported_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            vault.mkdir()
            cli = FakeObsidianCLI(vault, vault, CliResult(0, 'Error: File "a.md" not found.'))
            result = cli.run(["read", "path=a.md"])
            self.assertEqual(result.returncode, CLI_RESPONSE_ERROR)

    def test_index_check_accepts_matching_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            vault.mkdir()
            (vault / "a.md").write_text("actual content", encoding="utf-8")
            cli = FakeObsidianCLI(vault, vault, CliResult(0, "a.md"))
            result = cli.check_files()
            self.assertEqual(result.returncode, 0)
            self.assertIn('"paths_match": true', result.stdout)

    def test_same_count_but_different_paths_is_an_index_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            vault.mkdir()
            (vault / "new.md").write_text("new note", encoding="utf-8")
            cli = FakeObsidianCLI(vault, vault, CliResult(0, "old.md"))
            result = cli.check_files()
            self.assertEqual(result.returncode, INDEX_MISMATCH)
            self.assertIn("new.md", result.stdout)
            self.assertIn("old.md", result.stdout)

    def test_index_check_does_not_execute_against_a_mismatched_vault(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configured, actual = root / "configured", root / "actual"
            configured.mkdir(); actual.mkdir()
            cli = FakeObsidianCLI(configured, actual)
            result = cli.check_files()
            self.assertEqual(result.returncode, TARGET_MISMATCH)
            self.assertEqual(cli.calls, [])

    @unittest.skipUnless(os.name == "nt", "Windows redirector regression")
    def test_multiline_argument_cannot_reach_the_native_redirector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "fake.com"
            executable.write_text("stub", encoding="utf-8")
            cli = ObsidianCLI(executable, "vault", root)
            with mock.patch("obsidian_cli.subprocess.run") as execute:
                result = cli._execute(["eval", "code=1\n+2"])
            self.assertEqual(result.returncode, CLI_ARGUMENT_ERROR)
            execute.assert_not_called()

    def test_official_escaped_newline_content_remains_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "fake.com"
            executable.write_text("stub", encoding="utf-8")
            cli = ObsidianCLI(executable, "vault", root)
            args = ["append", "path=a.md", r"content=first\nsecond"]
            with mock.patch("obsidian_cli.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "Appended", "")) as execute:
                result = cli._execute(args)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(execute.call_args.args[0][-1], r"content=first\nsecond")


if __name__ == "__main__":
    unittest.main()
