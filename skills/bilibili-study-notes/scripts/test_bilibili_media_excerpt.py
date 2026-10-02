from __future__ import annotations

import struct
import unittest
import uuid
from pathlib import Path
from unittest import mock

import bilibili_media_excerpt as excerpt


def box(kind, payload):
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def index_fixture(version=0):
    timing = struct.pack(">II" if version == 0 else ">QQ", 0, 0)
    payload = bytes([version, 0, 0, 0]) + struct.pack(">II", 1, 1000) + timing + struct.pack(">HH", 0, 4)
    payload += b"".join(struct.pack(">III", 100 + i, 5000, 0x90000000) for i in range(4))
    return box(b"ftyp", b"isom") + box(b"sidx", payload)


def frame_probe(rate=30, duration=84):
    count = int(rate * duration)
    return {"format": {"duration": str(duration)},
            "streams": [{"codec_type": "video", "width": 1280, "height": 720,
                         "nb_read_frames": str(count), "r_frame_rate": str(rate)}],
            "frames": [{"best_effort_timestamp_time": str(i / rate),
                        "duration_time": str(1 / rate)} for i in range(count)]}


class FakeResponse:
    def __init__(self, status=206, body=b"abcd", content_range="bytes 10-13/20"):
        self.status, self.body = status, body
        self.headers, self.read_called = {"Content-Range": content_range}, False

    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self, size):
        self.read_called = True
        return self.body[:size]


class MediaExcerptTests(unittest.TestCase):
    def test_sidx_v0_v1_select_exact_bounded_fragments(self):
        for version in (0, 1):
            with self.subTest(version=version):
                prefix = index_fixture(version)
                refs = excerpt.parse_sidx(prefix)
                chosen = excerpt.select_fragments(refs, 5, 15)
                self.assertEqual([r["index"] for r in chosen], [1, 2])
                self.assertEqual(chosen[0]["first"], len(prefix) + 100)
                self.assertEqual(chosen[-1]["last"] - chosen[0]["first"] + 1, 203)

    def test_bad_intervals_full_stream_and_unsupported_index_fail(self):
        refs = excerpt.parse_sidx(index_fixture())
        for start, end in ((-1, 2), (2, 1), (0, 20), (21, 22), (float("nan"), 2)):
            with self.subTest(start=start, end=end), self.assertRaises(excerpt.ExcerptError):
                excerpt.select_fragments(refs, start, end)
        with self.assertRaises(excerpt.ExcerptError):
            excerpt.parse_sidx(index_fixture()[:-1])
        refs[1]["sap"] = False
        with self.assertRaises(excerpt.ExcerptError):
            excerpt.select_fragments(refs, 5, 10)

    def test_range_must_be_exact_206_and_complete(self):
        for response, valid in [(FakeResponse(), True), (FakeResponse(status=200), False),
                                (FakeResponse(body=b"a"), False),
                                (FakeResponse(content_range="bytes 0-3/20"), False)]:
            with self.subTest(status=response.status, body=response.body):
                opener = mock.Mock()
                opener.open.return_value = response
                with mock.patch.object(excerpt.urllib.request, "build_opener", return_value=opener):
                    if valid:
                        data, receipt = excerpt.fetch_range("https://media.bilivideo.com/example", 10, 13, {})
                        self.assertEqual((data, receipt["bytes"]), (b"abcd", 4))
                    else:
                        with self.assertRaises(excerpt.ExcerptError):
                            excerpt.fetch_range("https://media.bilivideo.com/example", 10, 13, {})
                if response.status != 206 or response.headers["Content-Range"] != "bytes 10-13/20":
                    self.assertFalse(response.read_called)

    def test_avc_selection_supports_different_dimensions(self):
        def stream(width, height, codec="avc1.64001F"):
            return {"width": width, "height": height, "codecs": codec,
                    "baseUrl": "https://media.bilivideo.com/example", "bandwidth": 1000,
                    "SegmentBase": {"Initialization": "0-999", "indexRange": "1000-1999"}}
        data = {"code": 0, "data": {"dash": {"video": [stream(640, 360), stream(1280, 720),
                                                              stream(1920, 1080), stream(1280, 720, "hev1")]}}}
        selected, _, _, _ = excerpt.select_stream(data)
        self.assertEqual((selected["width"], selected["height"]), (1280, 720))

    def test_probe_rejects_short_file_even_after_exit_zero(self):
        probe = {"format": {"duration": "0.5667"}, "streams": [{"codec_type": "video", "width": 1280,
                  "height": 720, "nb_read_frames": "17"}]}
        with self.assertRaises(excerpt.ExcerptError):
            excerpt.validate_probe(probe, 84, 1280, 720)
        probe = frame_probe()
        self.assertEqual(excerpt.validate_probe(probe, 84, 1280, 720)["duration_seconds"], 84)

    def test_actual_frame_timeline_accepts_normal_different_rates(self):
        for rate in (24, 25, 30, 60):
            with self.subTest(rate=rate):
                timeline = excerpt.validate_frame_timeline(frame_probe(rate), 84, rate)
                self.assertAlmostEqual(timeline["last_frame_end_seconds"], 84)

    def test_sparse_frames_cannot_pass_using_container_duration(self):
        probe = frame_probe()
        probe["frames"] = [{"best_effort_timestamp_time": "0", "duration_time": "1"},
                           {"best_effort_timestamp_time": "83", "duration_time": "1"}]
        probe["streams"][0].update({"nb_read_frames": "2", "r_frame_rate": "1/83"})
        for source_rate in (30, None):
            with self.subTest(source_rate=source_rate), self.assertRaises(excerpt.ExcerptError):
                excerpt.validate_probe(probe, 84, 1280, 720, source_rate)

    def test_actual_frame_edges_and_internal_gaps_are_checked(self):
        for removed in (slice(0, 30), slice(1000, 1030), slice(-30, None)):
            with self.subTest(removed=removed):
                probe = frame_probe()
                del probe["frames"][removed]
                probe["streams"][0]["nb_read_frames"] = str(len(probe["frames"]))
                with self.assertRaises(excerpt.ExcerptError):
                    excerpt.validate_probe(probe, 84, 1280, 720, 30)

    def test_requested_frames_keep_original_times_and_boundaries(self):
        self.assertEqual(excerpt.frame_times(798, 882, "833,811,811"), [811, 833])
        with self.assertRaises(excerpt.ExcerptError):
            excerpt.frame_times(798, 882, "882")

    def test_output_is_new_and_inside_cache_outside_vault(self):
        config = excerpt.extract.CONFIG
        # This existing directory is a genuine child of the configured cache in
        # candidate tests; outside a candidate, use another existing cache child.
        existing = Path(__file__).resolve().parent
        if not existing.is_relative_to(config.raw_cache):
            existing = config.bilibili_cache
        if existing.exists():
            with self.assertRaisesRegex(excerpt.ExcerptError, "already exists"):
                excerpt.checked_output(existing, config.raw_cache, config.vault)
        with self.assertRaises(excerpt.ExcerptError):
            excerpt.checked_output(config.raw_cache, config.raw_cache, config.vault)
        with self.assertRaises(excerpt.ExcerptError):
            excerpt.checked_output(config.vault / "test-excerpt-never-created", config.raw_cache, config.vault)
        with self.assertRaises(excerpt.ExcerptError):
            excerpt.checked_output(config.raw_cache.parent / "test-excerpt-never-created", config.raw_cache, config.vault)
        fresh = config.raw_cache / f"test-excerpt-never-created-{uuid.uuid4().hex}"
        self.assertEqual(excerpt.checked_output(fresh, config.raw_cache, config.vault), fresh.resolve())
        self.assertFalse(fresh.exists())


if __name__ == "__main__":
    unittest.main()
