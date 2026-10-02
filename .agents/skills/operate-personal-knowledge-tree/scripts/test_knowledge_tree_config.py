from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_tree_config import KnowledgeTreeConfigError, load_config


class KnowledgeTreeConfigTests(unittest.TestCase):
    def make_payload(self, root: Path) -> dict[str, object]:
        workspace = root / "workspace"
        vault = workspace / "vault"
        library = vault / "library"
        sources = vault / "sources"
        cache = workspace / "cache"
        for directory in (library, sources, cache, vault / ".obsidian"):
            directory.mkdir(parents=True, exist_ok=True)
        prompt_box = vault / "prompt-box.md"
        executable = workspace / "Obsidian.com"
        prompt_box.write_text("# prompts\n", encoding="utf-8")
        executable.write_text("stub", encoding="utf-8")
        return {
            "version": 1,
            "workspace": str(workspace),
            "vault": str(vault),
            "vault_name": "vault",
            "knowledge_library": str(library),
            "source_notes": str(sources),
            "raw_cache": str(cache),
            "prompt_box": str(prompt_box),
            "obsidian_cli": str(executable),
        }

    def write_config(self, root: Path, payload: dict[str, object]) -> Path:
        path = root / "knowledge-tree.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def make_v2_payload(self, root: Path) -> dict[str, object]:
        vault = root / "vault"
        library = vault / "library"
        sources = vault / "sources"
        cache = root / "cache"
        skills = root / "skills"
        for directory in (library, sources, cache, skills, vault / ".obsidian"):
            directory.mkdir(parents=True, exist_ok=True)
        (vault / "prompt-box.md").write_text("# prompts\n", encoding="utf-8")
        return {
            "version": 2,
            "workspace": ".",
            "vault": "vault",
            "vault_name": "vault",
            "knowledge_library": "vault/library",
            "source_notes": "vault/sources",
            "raw_cache": "cache",
            "prompt_box": "vault/prompt-box.md",
            "obsidian_cli": None,
            "skills_root": "skills",
        }

    def test_valid_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(self.write_config(root, self.make_payload(root)))
            self.assertEqual(config.version, 1)
            self.assertEqual(config.vault_name, "vault")
            self.assertEqual(config.bilibili_cache, config.raw_cache / "bilibili")

    def test_missing_field_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.make_payload(root)
            del payload["source_notes"]
            with self.assertRaises(KnowledgeTreeConfigError):
                load_config(self.write_config(root, payload))

    def test_relative_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.make_payload(root)
            payload["workspace"] = "relative-workspace"
            with self.assertRaises(KnowledgeTreeConfigError):
                load_config(self.write_config(root, payload))

    def test_v2_relative_paths_are_resolved_from_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(self.write_config(root, self.make_v2_payload(root)))
            self.assertEqual(config.version, 2)
            self.assertEqual(config.workspace, root.resolve())
            self.assertEqual(config.vault, (root / "vault").resolve())
            self.assertEqual(config.skills_root, (root / "skills").resolve())
            self.assertIsNone(config.obsidian_cli)

    def test_v2_absolute_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.make_v2_payload(root)
            payload["vault"] = str((root / "vault").resolve())
            with self.assertRaises(KnowledgeTreeConfigError):
                load_config(self.write_config(root, payload))

    def test_library_outside_vault_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.make_payload(root)
            outside = Path(str(payload["workspace"])) / "outside-library"
            outside.mkdir()
            payload["knowledge_library"] = str(outside)
            with self.assertRaises(KnowledgeTreeConfigError):
                load_config(self.write_config(root, payload))

    def test_cache_inside_vault_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.make_payload(root)
            inside = Path(str(payload["vault"])) / "cache"
            inside.mkdir()
            payload["raw_cache"] = str(inside)
            with self.assertRaises(KnowledgeTreeConfigError):
                load_config(self.write_config(root, payload))

    def test_missing_config_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KnowledgeTreeConfigError):
                load_config(Path(directory) / "missing.json")

    def test_optional_evidence_keeps_legacy_configuration_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = load_config(self.write_config(root, self.make_payload(root)))
            self.assertIsNone(cfg.source_evidence)

    def test_v2_evidence_resolves_portably_and_ignores_field_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.make_v2_payload(root)
            (root / "evidence" / "sources").mkdir(parents=True)
            payload["source_evidence"] = "evidence/sources"
            with patch.dict(os.environ, {"KNOWLEDGE_TREE_SOURCE_EVIDENCE": "ignored"}):
                cfg = load_config(self.write_config(root, payload))
            self.assertEqual(cfg.source_evidence, (root / "evidence/sources").resolve())

    def test_evidence_must_exist_and_cannot_overlap_vault_or_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.make_v2_payload(root)
            for value in ("missing", "vault", "vault/sources", "cache", "."):
                with self.subTest(value=value):
                    payload["source_evidence"] = value
                    with self.assertRaises(KnowledgeTreeConfigError):
                        load_config(self.write_config(root, payload))

    def test_v2_evidence_rejects_absolute_and_outside_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            outside = root.parent / "outside"
            outside.mkdir()
            payload = self.make_v2_payload(root)
            for value in (str(outside.resolve()), "../outside"):
                with self.subTest(value=value):
                    payload["source_evidence"] = value
                    with self.assertRaises(KnowledgeTreeConfigError):
                        load_config(self.write_config(root, payload))

    def test_unknown_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.make_payload(root)
            payload["version"] = 99
            with self.assertRaises(KnowledgeTreeConfigError):
                load_config(self.write_config(root, payload))

    def test_only_whole_config_environment_override_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.write_config(root, self.make_payload(root))
            with patch.dict(
                os.environ,
                {
                    "KNOWLEDGE_TREE_CONFIG": str(path),
                    "KNOWLEDGE_TREE_VAULT": str(root / "must-be-ignored"),
                },
                clear=False,
            ):
                config = load_config()
            self.assertEqual(config.config_path, path.resolve())
            self.assertNotEqual(config.vault, root / "must-be-ignored")


    def zone_payload(self, root: Path) -> dict[str, object]:
        payload = self.make_v2_payload(root)
        for field, name in (("creation_root", "创作区"), ("learning_root", "学习区")):
            relative = f"vault/library/{name}"
            (root / relative).mkdir(parents=True)
            payload[field] = relative
        payload["source_notes"] = payload["learning_root"]
        return payload

    def test_optional_zones_preserve_old_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(self.write_config(root, self.make_v2_payload(root)))
            self.assertIsNone(config.creation_root)
            self.assertIsNone(config.learning_root)
            self.assertIsNone(config.as_dict()["creation_root"])
            self.assertIsNone(config.as_dict()["learning_root"])

    def test_zones_resolve_and_serialize_with_common_control_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(self.write_config(root, self.zone_payload(root)))
            self.assertEqual(config.learning_root, config.source_notes)
            self.assertEqual(config.creation_root, (root / "vault/library/创作区").resolve())
            self.assertEqual(config.control_root, config.knowledge_library / "00-待归档与知识地图")
            self.assertEqual(config.as_dict()["learning_root"], str(config.learning_root))
            self.assertEqual(config.as_dict()["creation_root"], str(config.creation_root))

    def test_zones_reject_same_nested_or_outside_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.zone_payload(root)
            nested = root / "vault/library/创作区/nested"
            nested.mkdir()
            for value in ("vault/library/创作区", "vault/library/创作区/nested", "vault/library", "vault/sources", "cache"):
                with self.subTest(value=value):
                    payload["learning_root"] = value
                    with self.assertRaises(KnowledgeTreeConfigError):
                        load_config(self.write_config(root, payload))
            payload["creation_root"] = "vault/library/创作区/nested"
            payload["learning_root"] = "vault/library/创作区"
            with self.assertRaises(KnowledgeTreeConfigError):
                load_config(self.write_config(root, payload))

    def test_zones_require_existing_relative_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.zone_payload(root)
            for value in ("vault/library/missing", str((root / "vault/library/学习区").resolve()), "vault/prompt-box.md"):
                with self.subTest(value=value):
                    payload["learning_root"] = value
                    with self.assertRaises(KnowledgeTreeConfigError):
                        load_config(self.write_config(root, payload))

    def test_zone_paths_are_an_optional_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.zone_payload(root)
            for missing in ("creation_root", "learning_root"):
                for value in ("omit", None):
                    with self.subTest(missing=missing, value=value):
                        partial = dict(payload)
                        if value == "omit":
                            del partial[missing]
                        else:
                            partial[missing] = None
                        with self.assertRaisesRegex(KnowledgeTreeConfigError, "同时配置或同时缺省"):
                            load_config(self.write_config(root, partial))
            payload.update({"creation_root": None, "learning_root": None})
            config = load_config(self.write_config(root, payload))
            self.assertIsNone(config.creation_root)
            self.assertIsNone(config.learning_root)

    def test_zone_paths_do_not_use_per_field_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.zone_payload(root)
            with patch.dict(os.environ, {"KNOWLEDGE_TREE_LEARNING_ROOT": "ignored", "KNOWLEDGE_TREE_CREATION_ROOT": "ignored"}):
                config = load_config(self.write_config(root, payload))
            self.assertEqual(config.learning_root, (root / "vault/library/学习区").resolve())


if __name__ == "__main__":
    unittest.main()
