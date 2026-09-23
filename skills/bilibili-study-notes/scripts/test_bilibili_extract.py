from __future__ import annotations

import unittest
import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest import mock

import bilibili_extract


class BilibiliExtractDefaultsTests(unittest.TestCase):
    def test_default_output_is_configured_raw_cache(self) -> None:
        args = bilibili_extract.build_parser().parse_args(["BV1xx411c7mD"])
        self.assertEqual(args.out, bilibili_extract.CONFIG.bilibili_cache)
        self.assertTrue(args.out.is_absolute())
        self.assertFalse(str(args.out).startswith(str(bilibili_extract.CONFIG.vault)))

    def test_explicit_output_inside_vault_is_rejected(self) -> None:
        with self.assertRaisesRegex(SystemExit, "inside the active vault"):
            bilibili_extract.validate_output_root(
                bilibili_extract.CONFIG.vault / "raw-bilibili",
                bilibili_extract.CONFIG.vault,
            )

    def test_vault_root_itself_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            bilibili_extract.validate_output_root(
                bilibili_extract.CONFIG.vault,
                bilibili_extract.CONFIG.vault,
            )

    def test_external_output_is_allowed(self) -> None:
        candidate = Path(bilibili_extract.CONFIG.raw_cache) / "bilibili-test"
        self.assertEqual(
            candidate.resolve(),
            bilibili_extract.validate_output_root(candidate, bilibili_extract.CONFIG.vault),
        )


class TranscriptFallbackTests(unittest.TestCase):
    player = {"data": {"subtitle": {"subtitles": [{"lan": "zh", "subtitle_url": "https://example.invalid/sub"}]}}}
    audio = {"data": {"dash": {"audio": [{"bandwidth": 1, "baseUrl": "https://example.invalid/audio"}]}}}
    transcript = "# Transcript\n\nSource: local faster-whisper ASR\n\n- [00:00 - 00:02] 原文里的例子\n"

    def args(self, transcribe=True):
        options = ["BV1xx411c7mD"] + (["--transcribe"] if transcribe else [])
        return bilibili_extract.build_parser().parse_args(options)

    def test_subtitle_empty_payloads_have_no_usable_text(self):
        for payload in ({}, {"body": []}, {"body": None}, {"body": [{"content": "  "}]}, {"body": [{"content": None}]}):
            with self.subTest(payload=payload):
                self.assertFalse(bilibili_extract.has_transcript_content(bilibili_extract.subtitle_to_markdown(payload)))

    def test_timestamp_only_line_cannot_borrow_text_from_next_line(self):
        self.assertFalse(bilibili_extract.has_transcript_content("- [00:00 - 00:02]\n# Transcript\n"))

    def test_url_with_empty_subtitle_uses_asr_when_enabled(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(
            bilibili_extract, "fetch_json", side_effect=[self.player, {"body": []}, self.audio]
        ), mock.patch.object(bilibili_extract, "download"), mock.patch.object(
            bilibili_extract, "transcribe_audio", return_value=self.transcript
        ) as asr:
            metadata = {"transcript_source": "none"}
            result = bilibili_extract.extract_transcript(self.args(), Path(folder), "BV1xx411c7mD", 1, "https://example.invalid", metadata)
            self.assertEqual(result, self.transcript)
            self.assertEqual(metadata["transcript_source"], "faster_whisper_asr")
            self.assertTrue(metadata["subtitle_empty"])
            asr.assert_called_once()

    def test_empty_subtitle_without_asr_is_not_success(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(
            bilibili_extract, "fetch_json", side_effect=[self.player, {"body": []}]
        ), mock.patch.object(bilibili_extract, "download") as download:
            metadata = {"transcript_source": "none"}
            with self.assertRaisesRegex(SystemExit, "No usable subtitle"):
                bilibili_extract.extract_transcript(self.args(False), Path(folder), "BVtest", 1, "https://example.invalid", metadata)
            self.assertEqual(metadata["transcript_source"], "none")
            download.assert_not_called()

    def test_valid_subtitle_keeps_existing_subtitle_path(self):
        payload = {"body": [{"from": 0, "to": 2, "content": "原课的案例。"}]}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(
            bilibili_extract, "fetch_json", side_effect=[self.player, payload]
        ), mock.patch.object(bilibili_extract, "transcribe_audio") as asr:
            metadata = {"transcript_source": "none"}
            text = bilibili_extract.extract_transcript(self.args(), Path(folder), "BVtest", 1, "https://example.invalid", metadata)
            self.assertIn("原课的案例。", text)
            self.assertEqual(metadata["transcript_source"], "bilibili_subtitle")
            asr.assert_not_called()

    def test_empty_asr_does_not_gain_success_metadata(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(
            bilibili_extract, "fetch_json", side_effect=[self.player, {"body": []}, self.audio]
        ), mock.patch.object(bilibili_extract, "download"), mock.patch.object(
            bilibili_extract, "transcribe_audio", return_value="# Transcript\nSource: ASR\n"
        ):
            metadata = {"transcript_source": "none"}
            with self.assertRaisesRegex(SystemExit, "ASR returned no usable text"):
                bilibili_extract.extract_transcript(self.args(), Path(folder), "BVtest", 1, "https://example.invalid", metadata)
            self.assertEqual(metadata["transcript_source"], "none")

    def test_main_failure_marks_metadata_failed_and_preserves_existing_transcript(self):
        view = {"code": 0, "data": {"title": "Test", "pages": [{"page": 1, "cid": 1, "part": "Lesson", "duration": 120}]}}
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "BV1xx411c7mD-p1-Lesson"
            out.mkdir()
            prior = out / "transcript.md"
            prior.write_text("previous successful transcript", encoding="utf-8")
            args = self.args()
            args.out = Path(folder)
            with mock.patch.object(bilibili_extract.argparse.ArgumentParser, "parse_args", return_value=args), mock.patch.object(
                bilibili_extract, "fetch_json", return_value=view
            ), mock.patch.object(bilibili_extract, "extract_transcript", side_effect=RuntimeError("ASR failure")):
                with self.assertRaisesRegex(RuntimeError, "ASR failure"):
                    bilibili_extract.main()
            metadata = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["extraction_status"], "failed")
            self.assertEqual(metadata["transcript_source"], "none")
            self.assertEqual(prior.read_text(encoding="utf-8"), "previous successful transcript")

    def test_main_success_keeps_cli_json_and_records_clip(self):
        view = {"code": 0, "data": {"title": "Test", "pages": [{"page": 1, "cid": 1, "part": "Lesson", "duration": 120}]}}
        with tempfile.TemporaryDirectory() as folder:
            args = self.args()
            args.out = Path(folder)
            args.clip = "0,30"
            output = io.StringIO()
            with mock.patch.object(bilibili_extract.argparse.ArgumentParser, "parse_args", return_value=args), mock.patch.object(
                bilibili_extract, "fetch_json", side_effect=[view, self.player, {"body": []}, self.audio]
            ), mock.patch.object(bilibili_extract, "download"), mock.patch.object(
                bilibili_extract, "transcribe_audio", return_value=self.transcript
            ), contextlib.redirect_stdout(output):
                self.assertEqual(bilibili_extract.main(), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["extraction_status"], "extracted")
            self.assertEqual(result["asr_clip"], "0,30")
            self.assertEqual(result["duration"], 120)
            self.assertTrue(Path(result["out_dir"], "transcript.md").exists())


if __name__ == "__main__":
    unittest.main()
