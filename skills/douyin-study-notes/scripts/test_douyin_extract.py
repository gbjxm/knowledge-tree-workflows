import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("douyin_extract.py")
SPEC = importlib.util.spec_from_file_location("douyin_extract", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class DouyinExtractTests(unittest.TestCase):
    def test_extract_aweme_id_from_video_url(self):
        self.assertEqual(
            MODULE.extract_aweme_id("https://www.douyin.com/video/7665142251072326918"),
            "7665142251072326918",
        )

    def test_extract_aweme_id_from_modal_url(self):
        self.assertEqual(
            MODULE.extract_aweme_id("https://www.douyin.com/user/self?modal_id=7665142251072326918"),
            "7665142251072326918",
        )

    def test_safe_name_removes_windows_characters(self):
        self.assertEqual(MODULE.safe_name('a:b/c*?"d'), "a_b_c___d")

    def test_pick_smallest_muxed_format(self):
        formats = [
            {"format_id": "audio", "acodec": "aac", "vcodec": "none", "filesize": 1},
            {"format_id": "large", "acodec": "aac", "vcodec": "h265", "filesize": 20, "height": 720},
            {"format_id": "small", "acodec": "aac", "vcodec": "h265", "filesize_approx": 10, "height": 540},
        ]
        self.assertEqual(MODULE.pick_smallest_muxed_format(formats)["format_id"], "small")

    def test_full_asr_is_split_into_bounded_clips(self):
        self.assertEqual(MODULE.clip_ranges(125, 60, None), ["0,60", "60,120", "120,125"])

    def test_reject_output_inside_vault(self):
        with tempfile.TemporaryDirectory() as root:
            vault = Path(root) / "vault"
            vault.mkdir()
            with self.assertRaises(SystemExit):
                MODULE.validate_output_root(vault / "raw", vault)


if __name__ == "__main__":
    unittest.main()
