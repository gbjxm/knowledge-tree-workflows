from __future__ import annotations

import unittest
import contextlib
import io
import json
import gzip
import tempfile
import types
import urllib.error
from pathlib import Path
from unittest import mock

import bilibili_extract


TEST_TEMP_ROOT = Path(bilibili_extract.CONFIG.raw_cache) / "bilibili-test-temp"


def temporary_directory():
    TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT)


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
        with temporary_directory() as folder, mock.patch.object(
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
        with temporary_directory() as folder, mock.patch.object(
            bilibili_extract, "fetch_json", side_effect=[self.player, {"body": []}]
        ), mock.patch.object(bilibili_extract, "download") as download:
            metadata = {"transcript_source": "none"}
            with self.assertRaisesRegex(SystemExit, "No usable subtitle"):
                bilibili_extract.extract_transcript(self.args(False), Path(folder), "BVtest", 1, "https://example.invalid", metadata)
            self.assertEqual(metadata["transcript_source"], "none")
            download.assert_not_called()

    def test_valid_subtitle_keeps_existing_subtitle_path(self):
        payload = {"body": [{"from": 0, "to": 2, "content": "原课的案例。"}]}
        with temporary_directory() as folder, mock.patch.object(
            bilibili_extract, "fetch_json", side_effect=[self.player, payload]
        ), mock.patch.object(bilibili_extract, "transcribe_audio") as asr:
            metadata = {"transcript_source": "none"}
            text = bilibili_extract.extract_transcript(self.args(), Path(folder), "BVtest", 1, "https://example.invalid", metadata)
            self.assertIn("原课的案例。", text)
            self.assertEqual(metadata["transcript_source"], "bilibili_subtitle")
            asr.assert_not_called()

    def test_empty_asr_does_not_gain_success_metadata(self):
        with temporary_directory() as folder, mock.patch.object(
            bilibili_extract, "fetch_json", side_effect=[self.player, {"body": []}, self.audio]
        ), mock.patch.object(bilibili_extract, "download"), mock.patch.object(
            bilibili_extract, "transcribe_audio", return_value="# Transcript\nSource: ASR\n"
        ):
            metadata = {"transcript_source": "none"}
            with self.assertRaisesRegex(SystemExit, "ASR returned no usable text"):
                bilibili_extract.extract_transcript(self.args(), Path(folder), "BVtest", 1, "https://example.invalid", metadata)
            self.assertEqual(metadata["transcript_source"], "none")

    def test_main_failure_marks_metadata_failed_and_preserves_existing_transcript(self):
        view = {"code": 0, "data": {"bvid": "BV1xx411c7mD", "title": "Test", "pages": [{"page": 1, "cid": 1, "part": "Lesson", "duration": 120}]}}
        with temporary_directory() as folder:
            out = Path(folder) / "BV1xx411c7mD-p1-Lesson"
            out.mkdir()
            prior = out / "transcript.md"
            prior.write_text("previous successful transcript", encoding="utf-8")
            (out / "metadata.json").write_text('{"extraction_status":"extracted"}', encoding="utf-8")
            args = self.args()
            args.out = Path(folder)
            with mock.patch.object(bilibili_extract.argparse.ArgumentParser, "parse_args", return_value=args), mock.patch.object(
                bilibili_extract, "fetch_json", return_value=view
            ), mock.patch.object(bilibili_extract, "extract_transcript", side_effect=RuntimeError("ASR failure")):
                with self.assertRaisesRegex(RuntimeError, "ASR failure"):
                    bilibili_extract.main()
            reruns = list(Path(folder).glob("BV1xx411c7mD-p1-Lesson-run-*"))
            self.assertEqual(len(reruns), 1)
            metadata = json.loads((reruns[0] / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["extraction_status"], "failed")
            self.assertEqual(metadata["transcript_source"], "none")
            self.assertEqual(metadata["previous_output_directory"], str(out))
            self.assertEqual(metadata["output_directory"], str(reruns[0]))
            self.assertEqual(json.loads((out / "metadata.json").read_text(encoding="utf-8"))["extraction_status"], "extracted")
            self.assertEqual(prior.read_text(encoding="utf-8"), "previous successful transcript")

    def test_main_success_keeps_cli_json_and_records_clip(self):
        view = {"code": 0, "data": {"bvid": "BV1xx411c7mD", "title": "Test", "pages": [{"page": 1, "cid": 1, "part": "Lesson", "duration": 120}]}}
        with temporary_directory() as folder:
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
            self.assertEqual(result["metadata_source"], "view_api")
            self.assertEqual(result["transcript_scope"], "partial")
            self.assertEqual(result["requested_clip_seconds"], {"start": 0.0, "end": 30.0})
            self.assertTrue(Path(result["out_dir"], "transcript.md").exists())
            self.assertEqual(Path(result["out_dir"]).name, "BV1xx411c7mD-p1-Lesson")
            self.assertEqual(result["output_directory"], result["out_dir"])
            self.assertNotIn("previous_output_directory", result)

    def test_rerun_download_then_asr_failure_preserves_entire_previous_artifact_set(self):
        view = {"code": 0, "data": {"bvid": "BV1xx411c7mD", "title": "Test", "pages": [{"page": 1, "cid": 1, "part": "Lesson", "duration": 120}]}}
        with temporary_directory() as folder:
            old = Path(folder) / "BV1xx411c7mD-p1-Lesson"
            old.mkdir()
            originals = {"audio.m4s": b"old successful audio", "transcript.md": b"old successful transcript", "metadata.json": b'{"extraction_status":"extracted"}'}
            for name, content in originals.items():
                (old / name).write_bytes(content)
            args = self.args()
            args.out = Path(folder)
            response = mock.MagicMock()
            response.__enter__.return_value = response
            response.status = 200
            response.headers = {"Content-Length": "9"}
            response.read.side_effect = [b"new audio", b""]
            with mock.patch.object(bilibili_extract.argparse.ArgumentParser, "parse_args", return_value=args), mock.patch.object(
                bilibili_extract, "fetch_json", side_effect=[view, {"data": {"subtitle": {"subtitles": []}}}, self.audio],
            ), mock.patch.object(bilibili_extract.urllib.request, "urlopen", return_value=response), mock.patch.object(
                bilibili_extract, "transcribe_audio", side_effect=RuntimeError("ASR failed after complete download"),
            ):
                with self.assertRaisesRegex(RuntimeError, "after complete download"):
                    bilibili_extract.main()
            for name, content in originals.items():
                self.assertEqual((old / name).read_bytes(), content)
            reruns = list(Path(folder).glob("BV1xx411c7mD-p1-Lesson-run-*"))
            self.assertEqual(len(reruns), 1)
            self.assertEqual((reruns[0] / "audio.m4s").read_bytes(), b"new audio")
            self.assertFalse((reruns[0] / "transcript.md").exists())
            self.assertEqual(json.loads((reruns[0] / "metadata.json").read_text(encoding="utf-8"))["extraction_status"], "failed")

    def test_rerun_subtitle_written_then_failure_preserves_previous_artifact_set(self):
        view = {"code": 0, "data": {"bvid": "BV1xx411c7mD", "title": "Test", "pages": [{"page": 1, "cid": 1, "part": "Lesson", "duration": 120}]}}
        with temporary_directory() as folder:
            old = Path(folder) / "BV1xx411c7mD-p1-Lesson"
            old.mkdir()
            originals = {"subtitle.json": b'{"body":[{"content":"old"}]}', "transcript.md": b"old successful transcript", "metadata.json": b'{"extraction_status":"extracted"}'}
            for name, content in originals.items():
                (old / name).write_bytes(content)
            args = self.args()
            args.out = Path(folder)
            with mock.patch.object(bilibili_extract.argparse.ArgumentParser, "parse_args", return_value=args), mock.patch.object(
                bilibili_extract, "fetch_json", side_effect=[view, self.player, {"body": []}, {"data": {"dash": {"audio": []}}}],
            ):
                with self.assertRaisesRegex(SystemExit, "no DASH audio"):
                    bilibili_extract.main()
            for name, content in originals.items():
                self.assertEqual((old / name).read_bytes(), content)
            reruns = list(Path(folder).glob("BV1xx411c7mD-p1-Lesson-run-*"))
            self.assertEqual(len(reruns), 1)
            self.assertEqual(json.loads((reruns[0] / "subtitle.json").read_text(encoding="utf-8")), {"body": []})
            self.assertFalse((reruns[0] / "transcript.md").exists())
            self.assertEqual(json.loads((reruns[0] / "metadata.json").read_text(encoding="utf-8"))["extraction_status"], "failed")


class MetadataFallbackTests(unittest.TestCase):
    bvid = "BV1xx411c7mD"
    referer = "https://www.bilibili.com/video/BV1xx411c7mD?p=1"

    def data(self):
        return {"bvid": self.bvid, "title": "课程", "pages": [{"page": 1, "cid": 123, "part": "第一课"}]}

    def public_response(self, data=None, compressed=False):
        html = '<html><script>window.__INITIAL_STATE__=' + json.dumps(
            {"videoData": self.data() if data is None else data}, ensure_ascii=False,
        ) + ';(function(){})();</script></html>'
        raw = html.encode("utf-8")
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = gzip.compress(raw) if compressed else raw
        return response

    def test_412_recovers_same_public_video_from_plain_and_gzip_html(self):
        for compressed in (False, True):
            with self.subTest(compressed=compressed), mock.patch.object(
                bilibili_extract, "fetch_json", side_effect=urllib.error.HTTPError("url", 412, "blocked", {}, None),
            ), mock.patch.object(bilibili_extract.urllib.request, "urlopen", return_value=self.public_response(compressed=compressed)) as fetch:
                data, route = bilibili_extract.fetch_video_data(self.bvid, 1, self.referer)
                self.assertEqual(data, self.data())
                self.assertEqual(route, "public_page_after_http_412")
                request = fetch.call_args.args[0]
                self.assertEqual(request.full_url, self.referer)
                self.assertFalse(any(key.lower() in ("cookie", "authorization") for key in request.headers))

    def test_api_minus_412_uses_public_route(self):
        with mock.patch.object(bilibili_extract, "fetch_json", return_value={"code": -412}), mock.patch.object(
            bilibili_extract.urllib.request, "urlopen", return_value=self.public_response(),
        ):
            self.assertEqual(bilibili_extract.fetch_video_data(self.bvid, 1, self.referer)[1], "public_page_after_api_minus_412")

    def test_other_http_and_api_errors_do_not_fall_back(self):
        for code in (401, 403, 404, 429, 500):
            with self.subTest(code=code), mock.patch.object(
                bilibili_extract, "fetch_json", side_effect=urllib.error.HTTPError("url", code, "failed", {}, None),
            ), mock.patch.object(bilibili_extract, "fetch_public_video_data") as fallback:
                with self.assertRaises(urllib.error.HTTPError):
                    bilibili_extract.fetch_video_data(self.bvid, 1, self.referer)
                fallback.assert_not_called()
        with mock.patch.object(bilibili_extract, "fetch_json", return_value={"code": -101, "message": "login required"}), mock.patch.object(
            bilibili_extract, "fetch_public_video_data",
        ) as fallback:
            with self.assertRaises(SystemExit):
                bilibili_extract.fetch_video_data(self.bvid, 1, self.referer)
            fallback.assert_not_called()

    def test_public_page_identity_mismatch_duplicate_page_and_invalid_cid_stop(self):
        bad = [
            {**self.data(), "bvid": "BVdifferent"},
            {**self.data(), "pages": [{"page": 1, "cid": 1}, {"page": 1, "cid": 2}]},
            {**self.data(), "pages": [{"page": 2, "cid": 1}]},
            *[{**self.data(), "pages": [{"page": 1, "cid": value}]} for value in (0, -1, True, "123", 1.5)],
        ]
        for data in bad:
            with self.subTest(data=data), mock.patch.object(
                bilibili_extract.urllib.request, "urlopen", return_value=self.public_response(data),
            ):
                with self.assertRaises(ValueError):
                    bilibili_extract.fetch_public_video_data(self.bvid, 1, self.referer)

    def test_challenge_page_without_identity_stops(self):
        response = self.public_response()
        response.read.return_value = b"<html>Login required / security challenge</html>"
        with mock.patch.object(bilibili_extract.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "no readable video identity"):
                bilibili_extract.fetch_public_video_data(self.bvid, 1, self.referer)

    def test_normal_api_also_rejects_wrong_video_identity(self):
        with mock.patch.object(bilibili_extract, "fetch_json", return_value={"code": 0, "data": {**self.data(), "bvid": "BVother"}}):
            with self.assertRaisesRegex(ValueError, "BV identity"):
                bilibili_extract.fetch_video_data(self.bvid, 1, self.referer)

    def test_main_uses_strict_validated_page_among_mixed_type_duplicates(self):
        data = self.data()
        data["pages"] = [
            {"page": "1", "cid": 999, "part": "Wrong string page"},
            {"page": True, "cid": 998, "part": "Wrong boolean page"},
            {"page": 1, "cid": 123, "part": "Correct integer page"},
        ]
        with temporary_directory() as folder:
            args = bilibili_extract.build_parser().parse_args([self.referer, "--out", folder])
            output = io.StringIO()
            with mock.patch.object(bilibili_extract.argparse.ArgumentParser, "parse_args", return_value=args), mock.patch.object(
                bilibili_extract, "fetch_json", return_value={"code": 0, "data": data},
            ), mock.patch.object(bilibili_extract, "extract_transcript", return_value=TranscriptFallbackTests.transcript) as extract, contextlib.redirect_stdout(output):
                self.assertEqual(bilibili_extract.main(), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["cid"], 123)
            self.assertEqual(result["part"], "Correct integer page")
            self.assertEqual(extract.call_args.args[3], 123)


class LanguageAndClipTests(unittest.TestCase):
    def test_multilingual_default_and_explicit_english_model(self):
        parser = bilibili_extract.build_parser()
        self.assertEqual(parser.parse_args(["BVtest"]).model, "base")
        self.assertEqual(parser.parse_args(["BVtest", "--model", "base.en"]).model, "base.en")

    def test_english_only_model_rejects_non_english_before_model_load(self):
        fake = types.SimpleNamespace(WhisperModel=mock.Mock())
        with mock.patch.dict("sys.modules", {"faster_whisper": fake}):
            with self.assertRaisesRegex(SystemExit, "English-only"):
                bilibili_extract.transcribe_audio(Path("unused"), "base.en", "zh", None)
        fake.WhisperModel.assert_not_called()

    def test_forced_language_is_not_reported_as_detected(self):
        segment = types.SimpleNamespace(start=0, end=2, text=" Hello ")
        info = types.SimpleNamespace(language="en", language_probability=1.0)
        whisper = mock.Mock()
        whisper.return_value.transcribe.return_value = (iter([segment]), info)
        with mock.patch.dict("sys.modules", {"faster_whisper": types.SimpleNamespace(WhisperModel=whisper)}):
            result = bilibili_extract.transcribe_audio(Path("unused"), "base.en", "en", None)
        self.assertIn("Specified language: en", result)
        self.assertNotIn("Detected language:", result)
        self.assertNotIn("1.000", result)
        self.assertIn("- [00:00 - 00:02] Hello", result)

    def test_detected_language_retains_observed_probability(self):
        whisper = mock.Mock()
        whisper.return_value.transcribe.return_value = ([], types.SimpleNamespace(language="zh", language_probability=0.91))
        with mock.patch.dict("sys.modules", {"faster_whisper": types.SimpleNamespace(WhisperModel=whisper)}):
            result = bilibili_extract.transcribe_audio(Path("unused"), "base", None, None)
        self.assertIn("Detected language: zh (0.910)", result)

    def test_english_only_model_language_is_fixed_without_detection_claim(self):
        whisper = mock.Mock()
        whisper.return_value.transcribe.return_value = ([], types.SimpleNamespace(language="en", language_probability=1.0))
        with mock.patch.dict("sys.modules", {"faster_whisper": types.SimpleNamespace(WhisperModel=whisper)}):
            result = bilibili_extract.transcribe_audio(Path("unused"), "base.en", None, None)
        self.assertIn("Model language: en (English-only model)", result)
        self.assertNotIn("Detected language:", result)

    def test_clip_rejects_nonfinite_negative_reversed_and_multiple_ranges(self):
        for clip in ("", "1", "0,1,2,3", "-1,2", "3,2", "2,2", "nan,2", "0,inf", "-inf,2", "x,2", "0,"):
            with self.subTest(clip=clip), self.assertRaisesRegex(SystemExit, "start,end"):
                bilibili_extract.parse_clip(clip)
        self.assertEqual(bilibili_extract.parse_clip(" 0, 2.5 "), (0.0, 2.5))

    def test_invalid_clip_stops_before_any_network_or_download(self):
        args = bilibili_extract.build_parser().parse_args(["BVtest", "--clip", "0,nan", "--transcribe"])
        with mock.patch.object(bilibili_extract.argparse.ArgumentParser, "parse_args", return_value=args), mock.patch.object(
            bilibili_extract, "fetch_json",
        ) as fetch, mock.patch.object(bilibili_extract, "download") as download:
            with self.assertRaises(SystemExit):
                bilibili_extract.main()
        fetch.assert_not_called()
        download.assert_not_called()

    def test_clip_filters_subtitle_and_preserves_overlapping_cue_timing(self):
        payload = {"body": [
            {"from": 0, "to": 2, "content": "before"},
            {"from": 2, "to": 5, "content": "overlapping"},
            {"from": 5, "to": 6, "content": "inside"},
            {"from": 6, "to": 9, "content": "after"},
        ]}
        result = bilibili_extract.subtitle_to_markdown(payload, "3,6")
        self.assertNotIn("before", result)
        self.assertNotIn("after", result)
        self.assertIn("[00:02 - 00:05] overlapping", result)
        self.assertIn("inside", result)

    def test_clip_subtitle_branch_records_partial_scope(self):
        args = bilibili_extract.build_parser().parse_args(["BVtest", "--clip", "10,20"])
        payload = {"body": [{"from": 11, "to": 12, "content": "in range"}, {"from": 22, "to": 23, "content": "outside"}]}
        with temporary_directory() as folder, mock.patch.object(
            bilibili_extract, "fetch_json", side_effect=[TranscriptFallbackTests.player, payload],
        ):
            metadata = {}
            result = bilibili_extract.extract_transcript(args, Path(folder), "BVtest", 1, "ref", metadata)
        self.assertIn("in range", result)
        self.assertNotIn("outside", result)
        self.assertEqual(metadata["transcript_scope"], "partial")
        self.assertEqual(metadata["requested_clip_seconds"], {"start": 10.0, "end": 20.0})
        self.assertIn("whole_cues", metadata["subtitle_clip_policy"])

    def test_old_namespace_without_clip_or_language_remains_usable(self):
        args = types.SimpleNamespace(transcribe=False)
        payload = {"body": [{"from": 0, "to": 1, "content": "usable"}]}
        with temporary_directory() as folder, mock.patch.object(
            bilibili_extract, "fetch_json", side_effect=[TranscriptFallbackTests.player, payload],
        ):
            self.assertIn("usable", bilibili_extract.extract_transcript(args, Path(folder), "BVtest", 1, "ref", {}))


class SubtitleAccessTests(unittest.TestCase):
    def test_login_required_subtitle_never_fetches_protected_payload(self):
        player = {"data": {"need_login_subtitle": True, "subtitle": {"subtitles": [{"lan": "zh", "subtitle_url": "https://example.invalid/protected"}]}}}
        for enabled in (False, True):
            with self.subTest(enabled=enabled), temporary_directory() as folder:
                args = bilibili_extract.build_parser().parse_args(["BVtest"] + (["--transcribe"] if enabled else []))
                metadata = {}
                with mock.patch.object(bilibili_extract, "fetch_json", side_effect=[player, TranscriptFallbackTests.audio]) as fetch, mock.patch.object(
                    bilibili_extract, "download",
                ) as download, mock.patch.object(bilibili_extract, "transcribe_audio", return_value=TranscriptFallbackTests.transcript):
                    if enabled:
                        self.assertEqual(bilibili_extract.extract_transcript(args, Path(folder), "BVtest", 1, "ref", metadata), TranscriptFallbackTests.transcript)
                        self.assertIn("/x/player/playurl?", fetch.call_args_list[1].args[0])
                    else:
                        with self.assertRaisesRegex(SystemExit, "Subtitle access is unavailable"):
                            bilibili_extract.extract_transcript(args, Path(folder), "BVtest", 1, "ref", metadata)
                        self.assertEqual(fetch.call_count, 1)
                        download.assert_not_called()
                self.assertEqual(metadata["subtitle_access"], "unavailable")
                self.assertEqual(metadata["subtitle_access_reason"], "login_required")
                self.assertIsNone(metadata["subtitle_count"])
                self.assertNotIn("subtitle_empty", metadata)

    def test_player_http_failure_is_unavailable_and_uses_authorized_audio(self):
        args = bilibili_extract.build_parser().parse_args(["BVtest", "--transcribe"])
        failure = urllib.error.HTTPError("url", 412, "blocked", {}, None)
        with temporary_directory() as folder, mock.patch.object(
            bilibili_extract, "fetch_json", side_effect=[failure, TranscriptFallbackTests.audio],
        ), mock.patch.object(bilibili_extract, "download"), mock.patch.object(
            bilibili_extract, "transcribe_audio", return_value=TranscriptFallbackTests.transcript,
        ):
            metadata = {}
            bilibili_extract.extract_transcript(args, Path(folder), "BVtest", 1, "ref", metadata)
        self.assertEqual(metadata["subtitle_access"], "unavailable")
        self.assertEqual(metadata["subtitle_access_http_status"], 412)
        self.assertIsNone(metadata["subtitle_count"])
        self.assertNotIn("subtitle_empty", metadata)
        self.assertEqual(metadata["transcript_source"], "faster_whisper_asr")

    def test_payload_http_failure_preserves_known_subtitle_count(self):
        args = bilibili_extract.build_parser().parse_args(["BVtest", "--transcribe"])
        failure = urllib.error.HTTPError("url", 403, "forbidden", {}, None)
        with temporary_directory() as folder, mock.patch.object(
            bilibili_extract, "fetch_json", side_effect=[TranscriptFallbackTests.player, failure, TranscriptFallbackTests.audio],
        ), mock.patch.object(bilibili_extract, "download"), mock.patch.object(
            bilibili_extract, "transcribe_audio", return_value=TranscriptFallbackTests.transcript,
        ):
            metadata = {}
            bilibili_extract.extract_transcript(args, Path(folder), "BVtest", 1, "ref", metadata)
        self.assertEqual(metadata["subtitle_count"], 1)
        self.assertEqual(metadata["subtitle_access_stage"], "subtitle_payload")
        self.assertEqual(metadata["subtitle_access_http_status"], 403)
        self.assertNotIn("subtitle_empty", metadata)

    def test_unavailable_subtitles_without_asr_permission_fail(self):
        args = bilibili_extract.build_parser().parse_args(["BVtest"])
        for response in (urllib.error.HTTPError("url", 412, "blocked", {}, None), {"code": -101, "message": "login"}):
            with self.subTest(response=response), temporary_directory() as folder, mock.patch.object(
                bilibili_extract, "fetch_json", side_effect=[response],
            ) as fetch, mock.patch.object(bilibili_extract, "download") as download:
                metadata = {}
                with self.assertRaisesRegex(SystemExit, "Subtitle access is unavailable"):
                    bilibili_extract.extract_transcript(args, Path(folder), "BVtest", 1, "ref", metadata)
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(metadata["subtitle_access"], "unavailable")
                download.assert_not_called()

    def test_non_http_failure_is_not_generic_fallback(self):
        args = bilibili_extract.build_parser().parse_args(["BVtest", "--transcribe"])
        with temporary_directory() as folder, mock.patch.object(bilibili_extract, "fetch_json", side_effect=ValueError("malformed JSON")), mock.patch.object(
            bilibili_extract, "download",
        ) as download:
            with self.assertRaisesRegex(ValueError, "malformed JSON"):
                bilibili_extract.extract_transcript(args, Path(folder), "BVtest", 1, "ref", {})
            download.assert_not_called()

    def test_network_failures_use_only_authorized_fallback(self):
        failures = [urllib.error.URLError("connection failed"), TimeoutError("timed out"), ConnectionResetError("reset")]
        for failure in failures:
            for enabled in (False, True):
                with self.subTest(failure=type(failure).__name__, enabled=enabled), temporary_directory() as folder:
                    args = bilibili_extract.build_parser().parse_args(["BVtest"] + (["--transcribe"] if enabled else []))
                    metadata = {}
                    with mock.patch.object(bilibili_extract, "fetch_json", side_effect=[failure, TranscriptFallbackTests.audio]) as fetch, mock.patch.object(
                        bilibili_extract, "download",
                    ) as download, mock.patch.object(bilibili_extract, "transcribe_audio", return_value=TranscriptFallbackTests.transcript):
                        if enabled:
                            result = bilibili_extract.extract_transcript(args, Path(folder), "BVtest", 1, "ref", metadata)
                            self.assertEqual(result, TranscriptFallbackTests.transcript)
                            download.assert_called_once()
                        else:
                            with self.assertRaisesRegex(SystemExit, "Subtitle access is unavailable"):
                                bilibili_extract.extract_transcript(args, Path(folder), "BVtest", 1, "ref", metadata)
                            self.assertEqual(fetch.call_count, 1)
                            download.assert_not_called()
                    self.assertEqual(metadata["subtitle_access"], "unavailable")
                    self.assertEqual(metadata["subtitle_access_network_error"], type(failure).__name__)
                    self.assertNotIn("subtitle_empty", metadata)

    def test_bad_utf8_or_json_stops_without_audio_fallback(self):
        errors = [UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"), json.JSONDecodeError("invalid", "<html>", 0)]
        args = bilibili_extract.build_parser().parse_args(["BVtest", "--transcribe"])
        for error in errors:
            with self.subTest(error=type(error).__name__), temporary_directory() as folder, mock.patch.object(
                bilibili_extract, "fetch_json", side_effect=error,
            ) as fetch, mock.patch.object(bilibili_extract, "download") as download:
                with self.assertRaises(type(error)):
                    bilibili_extract.extract_transcript(args, Path(folder), "BVtest", 1, "ref", {})
                self.assertEqual(fetch.call_count, 1)
                download.assert_not_called()


class AtomicDownloadTests(unittest.TestCase):
    def response(self, chunks, length=None):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers = {} if length is None else {"Content-Length": str(length)}
        response.read.side_effect = chunks
        return response

    def test_complete_download_replaces_original_after_validation(self):
        with temporary_directory() as folder:
            dest = Path(folder) / "audio.m4s"
            dest.write_bytes(b"old")
            with mock.patch.object(bilibili_extract.urllib.request, "urlopen", return_value=self.response([b"new audio", b""], 9)):
                bilibili_extract.download("https://example.invalid/audio", dest, "https://example.invalid/")
            self.assertEqual(dest.read_bytes(), b"new audio")
            self.assertEqual(list(Path(folder).glob("*.partial")), [])

    def test_empty_truncated_and_interrupted_downloads_preserve_original_and_partial(self):
        cases = [([b""], None, ValueError), ([b"short", b""], 100, ValueError), ([b"part", OSError("connection interrupted")], 100, OSError)]
        for chunks, length, error in cases:
            with self.subTest(chunks=chunks), temporary_directory() as folder:
                dest = Path(folder) / "audio.m4s"
                dest.write_bytes(b"original successful audio")
                with mock.patch.object(bilibili_extract.urllib.request, "urlopen", return_value=self.response(chunks, length)):
                    with self.assertRaises(error):
                        bilibili_extract.download("https://example.invalid/audio", dest, "https://example.invalid/")
                self.assertEqual(dest.read_bytes(), b"original successful audio")
                partials = list(Path(folder).glob("*.partial"))
                self.assertEqual(len(partials), 1)
                self.assertEqual(partials[0].read_bytes(), chunks[0])

    def test_partial_http_response_never_replaces_complete_audio(self):
        for status, content_range in ((206, "bytes 0-12/200000"), (206, None), (200, "bytes 0-12/200000")):
            with self.subTest(status=status, content_range=content_range), temporary_directory() as folder:
                dest = Path(folder) / "audio.m4s"
                dest.write_bytes(b"original complete audio")
                partial_content = b"partial audio"
                response = self.response([partial_content, b""], len(partial_content))
                response.status = status
                if content_range is not None:
                    response.headers["Content-Range"] = content_range
                with mock.patch.object(bilibili_extract.urllib.request, "urlopen", return_value=response):
                    with self.assertRaisesRegex(ValueError, "complete HTTP 200"):
                        bilibili_extract.download("https://example.invalid/audio", dest, "https://example.invalid/")
                self.assertEqual(dest.read_bytes(), b"original complete audio")
                partials = list(Path(folder).glob("*.partial"))
                self.assertEqual(len(partials), 1)
                self.assertEqual(partials[0].read_bytes(), partial_content)

    def test_complete_206_accepts_only_full_range_with_matching_or_absent_length(self):
        for length in (9, None):
            with self.subTest(length=length), temporary_directory() as folder:
                dest = Path(folder) / "audio.m4s"
                response = self.response([b"new audio", b""], length)
                response.status = 206
                response.headers["Content-Range"] = "bytes 0-8/9"
                with mock.patch.object(bilibili_extract.urllib.request, "urlopen", return_value=response) as fetch:
                    bilibili_extract.download("https://example.invalid/audio", dest, "https://example.invalid/")
                self.assertEqual(dest.read_bytes(), b"new audio")
                self.assertEqual(list(Path(folder).glob("*.partial")), [])
                self.assertEqual(fetch.call_args.kwargs["timeout"], 30)
                request_headers = {key.lower(): value for key, value in fetch.call_args.args[0].headers.items()}
                self.assertEqual(request_headers["range"], "bytes=0-")
                self.assertEqual(request_headers["accept-encoding"], "identity")
                self.assertEqual(response.read.call_args_list, [mock.call(64 * 1024), mock.call(64 * 1024)])

    def test_truncated_206_with_full_range_header_preserves_previous_audio(self):
        for length in (100, None):
            with self.subTest(length=length), temporary_directory() as folder:
                dest = Path(folder) / "audio.m4s"
                dest.write_bytes(b"original complete audio")
                response = self.response([b"short", b""], length)
                response.status = 206
                response.headers["Content-Range"] = "bytes 0-99/100"
                with mock.patch.object(bilibili_extract.urllib.request, "urlopen", return_value=response):
                    with self.assertRaisesRegex(ValueError, "empty or incomplete"):
                        bilibili_extract.download("https://example.invalid/audio", dest, "https://example.invalid/")
                self.assertEqual(dest.read_bytes(), b"original complete audio")
                self.assertEqual(next(Path(folder).glob("*.partial")).read_bytes(), b"short")

    def test_malformed_206_ranges_and_conflicting_content_length_are_rejected(self):
        for content_range, length in (("bytes 1-9/10", 9), ("bytes 0-9/*", 10), ("bytes 0-9/10 junk", 10), ("bytes 0-8/9", 10)):
            with self.subTest(content_range=content_range, length=length), temporary_directory() as folder:
                dest = Path(folder) / "audio.m4s"
                response = self.response([b"123456789", b""], length)
                response.status = 206
                response.headers["Content-Range"] = content_range
                with mock.patch.object(bilibili_extract.urllib.request, "urlopen", return_value=response):
                    with self.assertRaisesRegex(ValueError, "complete HTTP 200 or full-range 206"):
                        bilibili_extract.download("https://example.invalid/audio", dest, "https://example.invalid/")
                self.assertFalse(dest.exists())
                self.assertEqual(next(Path(folder).glob("*.partial")).read_bytes(), b"123456789")

    def test_wall_clock_deadline_preserves_partial_and_previous_audio(self):
        with temporary_directory() as folder:
            dest = Path(folder) / "audio.m4s"
            dest.write_bytes(b"original complete audio")
            response = self.response([b"partial", b""], 100)
            with mock.patch.object(bilibili_extract.urllib.request, "urlopen", return_value=response), mock.patch.object(
                bilibili_extract.time, "monotonic", side_effect=[0.0, 0.1, 180.0],
            ):
                with self.assertRaisesRegex(TimeoutError, "180 second wall-clock budget"):
                    bilibili_extract.download("https://example.invalid/audio", dest, "https://example.invalid/")
            self.assertEqual(dest.read_bytes(), b"original complete audio")
            self.assertEqual(next(Path(folder).glob("*.partial")).read_bytes(), b"partial")
            response.read.assert_called_once_with(64 * 1024)


if __name__ == "__main__":
    unittest.main()
