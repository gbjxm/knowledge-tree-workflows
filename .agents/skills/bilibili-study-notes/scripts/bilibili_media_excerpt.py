#!/usr/bin/env python3
"""Acquire a bounded, video-only Bilibili excerpt for source inspection.

Uses existing public metadata/playurl access and ffmpeg/ffprobe. Supports AVC
representations up to 720p with contiguous SegmentBase initialization/index and
flat SIDX v0/v1. Unsupported formats, ignored HTTP ranges and whole-stream
requests fail; there is no login, installation, retry, alternate-CDN or full-video
fallback. Previews are extraction artifacts, not evidence of completed review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

import bilibili_extract as extract


class ExcerptError(Exception):
    pass


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_output(path: Path, raw_cache: Path, vault: Path) -> Path:
    output = path.expanduser().absolute()
    for part in [output, *output.parents]:
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ExcerptError("Output must not traverse symbolic links or junctions.")
    output, raw_cache, vault = output.resolve(), raw_cache.resolve(), vault.resolve()
    if output == vault or output.is_relative_to(vault):
        raise ExcerptError("Raw media output cannot be inside the active Vault.")
    if output == raw_cache or not output.is_relative_to(raw_cache):
        raise ExcerptError("Output must be a new directory inside configured raw_cache.")
    if output.exists():
        raise ExcerptError("Output already exists; no existing run will be overwritten.")
    return output


def frame_times(start: float, end: float, requested: str | None) -> list[float]:
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ExcerptError("Require finite 0 <= start < end seconds.")
    try:
        times = ([float(value) for value in requested.split(",")] if requested is not None
                 else [start, (start + end) / 2, max(start, end - 1)])
    except ValueError as exc:
        raise ExcerptError("--frames accepts comma-separated original video seconds.") from exc
    if any(not math.isfinite(value) or not start <= value < end for value in times):
        raise ExcerptError("Each frame time must fall within the requested [start, end) interval.")
    return sorted(set(times))


def select_stream(playurl: dict[str, Any]):
    if playurl.get("code") != 0:
        raise ExcerptError("Public playurl did not return a successful response.")
    streams = ((playurl.get("data") or {}).get("dash") or {}).get("video") or []
    supported = [v for v in streams if 0 < int(v.get("height", 0)) <= 720
                 and int(v.get("width", 0)) > 0 and str(v.get("codecs", "")).startswith("avc1.")
                 and (v.get("SegmentBase") or v.get("segment_base"))]
    if not supported:
        raise ExcerptError("No AVC representation up to 720p with SegmentBase is available.")
    stream = max(supported, key=lambda v: (int(v["height"]), int(v["width"]), -int(v.get("bandwidth", 0))))
    segment = stream.get("SegmentBase") or stream["segment_base"]
    try:
        first, init_end = map(int, (segment.get("Initialization") or segment["initialization"]).split("-"))
        index_start, index_end = map(int, (segment.get("indexRange") or segment["index_range"]).split("-"))
    except (KeyError, ValueError, TypeError) as exc:
        raise ExcerptError("Unsupported SegmentBase ranges.") from exc
    if first != 0 or index_start != init_end + 1 or not index_start < index_end < 1024 * 1024:
        raise ExcerptError("Only contiguous small initialization/index ranges are supported.")
    url = stream.get("baseUrl") or stream.get("base_url") or ""
    parsed = urllib.parse.urlparse(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or not parsed.hostname.endswith((".bilivideo.com", ".bilivideo.cn"))):
        raise ExcerptError("Unsupported selected CDN address; no alternate source will be tried.")
    return stream, url, init_end + 1, index_end


def parse_sidx(blob: bytes) -> list[dict[str, Any]]:
    """Parse a complete file prefix containing exactly one flat SIDX."""
    offset, refs = 0, None
    while offset < len(blob):
        if offset + 8 > len(blob):
            raise ExcerptError("Truncated MP4 header.")
        size, kind = struct.unpack_from(">I4s", blob, offset)
        if size < 8 or offset + size > len(blob):
            raise ExcerptError("Only complete, ordinary-size MP4 boxes are supported.")
        if kind == b"sidx":
            if refs is not None or size < 32:
                raise ExcerptError("Expected one complete SIDX.")
            cursor = offset + 8
            version = blob[cursor]
            if version not in (0, 1):
                raise ExcerptError("Only SIDX v0 and v1 are supported.")
            cursor += 4
            _, scale = struct.unpack_from(">II", blob, cursor)
            cursor += 8
            width = 8 if version == 0 else 16
            if cursor + width + 4 > offset + size:
                raise ExcerptError("Truncated SIDX timing fields.")
            earliest, first_offset = struct.unpack_from(">II" if version == 0 else ">QQ", blob, cursor)
            cursor += width
            _, count = struct.unpack_from(">HH", blob, cursor)
            cursor += 4
            if scale <= 0 or count == 0 or cursor + count * 12 != offset + size:
                raise ExcerptError("Invalid SIDX entries.")
            byte_position, ticks, refs = offset + size + first_offset, earliest, []
            for index in range(count):
                raw_size, duration, sap = struct.unpack_from(">III", blob, cursor)
                cursor += 12
                length = raw_size & 0x7fffffff
                if raw_size >> 31 or not length or not duration:
                    raise ExcerptError("Only nonempty flat media references are supported.")
                refs.append({"index": index, "first": byte_position, "last": byte_position + length - 1,
                             "start": ticks / scale, "end": (ticks + duration) / scale,
                             "sap": bool(sap >> 31)})
                byte_position += length
                ticks += duration
        offset += size
    if not refs:
        raise ExcerptError("No usable SIDX; full-stream fallback is prohibited.")
    return refs


def select_fragments(refs: list[dict[str, Any]], start: float, end: float):
    frame_times(start, end, None)
    chosen = [r for r in refs if r["start"] < end and r["end"] > start]
    if not chosen or chosen[0]["start"] > start + 0.1 or chosen[-1]["end"] < end - 0.1:
        raise ExcerptError("SIDX does not cover the requested interval.")
    if len(chosen) == len(refs):
        raise ExcerptError("Refusing to download every media fragment; choose a shorter excerpt.")
    if not chosen[0]["sap"]:
        raise ExcerptError("First selected fragment has no supported random-access point.")
    for left, right in zip(chosen, chosen[1:]):
        if left["last"] + 1 != right["first"] or abs(left["end"] - right["start"]) > 1e-6:
            raise ExcerptError("Selected media fragments are not contiguous.")
    return chosen


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ExcerptError("CDN redirect refused; no source switching is performed.")


def fetch_range(url: str, first: int, last: int, headers: dict[str, str]):
    if first < 0 or last < first:
        raise ExcerptError("Invalid byte range.")
    expected = last - first + 1
    request = urllib.request.Request(url, headers={**headers, "Range": f"bytes={first}-{last}", "Accept-Encoding": "identity"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=45) as response:
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
            if response.status != 206 or match is None or tuple(map(int, match.groups()[:2])) != (first, last):
                raise ExcerptError("CDN ignored the exact Range; response body was not downloaded.")
            total = int(match.group(3))
            if total <= last:
                raise ExcerptError("Invalid CDN total size.")
            body = response.read(expected + 1)
            if len(body) != expected:
                raise ExcerptError("Incomplete or oversized media Range.")
            return body, {"status": 206, "first": first, "last": last, "bytes": len(body),
                          "total_stream_bytes": total, "host": urllib.parse.urlparse(url).hostname}
    except urllib.error.HTTPError as exc:
        raise ExcerptError(f"CDN returned HTTP {exc.code}; no retry or fallback performed.") from exc
    except urllib.error.URLError as exc:
        raise ExcerptError(f"CDN transport failed ({type(exc.reason).__name__}); no fallback performed.") from exc


def run_media(command: list[str], stderr_path: Path) -> str:
    run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    stderr_path.write_text(run.stderr, encoding="utf-8")
    if run.returncode != 0 or run.stderr.strip():
        raise ExcerptError(f"Local media validation failed; inspect {stderr_path.name}.")
    return run.stdout


def validate_frame_timeline(probe: dict[str, Any], requested_duration: float,
                            expected_frame_rate: Any = None) -> dict[str, Any]:
    """Verify timestamp coverage, not visual content or creative continuity.

    Source frame rate is preferred. A maximum one-second gap prevents sparse
    outputs from legitimizing themselves with an extremely low average rate.
    Such sparse material fails this helper's coverage check; this is not a claim
    that every intentionally variable-rate video is corrupt.
    """
    video = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
    raw_rate = expected_frame_rate or video.get("r_frame_rate") or video.get("avg_frame_rate")
    try:
        rate = float(Fraction(str(raw_rate)))
    except (ValueError, ZeroDivisionError) as exc:
        raise ExcerptError("A usable source or probe frame rate is required to verify coverage.") from exc
    if not math.isfinite(rate) or rate <= 0:
        raise ExcerptError("Invalid expected video frame rate.")
    step = 1 / rate
    gap_limit = min(1.0, max(0.1, 3 * step))
    edge_tolerance = min(0.5, max(0.06, 1.5 * step))
    frames = [f for f in probe.get("frames", []) if f.get("media_type", "video") == "video"]
    if not frames or len(frames) != int(video.get("nb_read_frames", 0)):
        raise ExcerptError("Actual frame timestamps are missing or disagree with decoded frame count.")
    times, durations = [], []
    for frame in frames:
        try:
            stamp = float(frame["best_effort_timestamp_time"])
            duration = float(frame.get("duration_time", frame.get("pkt_duration_time", 0)))
        except (KeyError, TypeError, ValueError) as exc:
            raise ExcerptError("A decoded frame has no usable timestamp or duration.") from exc
        if not math.isfinite(stamp) or not math.isfinite(duration) or duration < 0:
            raise ExcerptError("Invalid decoded frame timing.")
        if duration > gap_limit + 1e-6:
            raise ExcerptError("An exceptionally long frame cannot establish continuous excerpt coverage.")
        times.append(stamp)
        durations.append(duration)
    gaps = [right - left for left, right in zip(times, times[1:])]
    if any(gap <= 0 or gap > gap_limit + 1e-6 for gap in gaps):
        raise ExcerptError("Decoded timestamps contain a reversal, duplicate or large frame gap.")
    last_end = times[-1] + (durations[-1] or step)
    if (abs(times[0]) > edge_tolerance or last_end < requested_duration - edge_tolerance
            or last_end > requested_duration + edge_tolerance):
        raise ExcerptError("Actual first/last frames do not cover the requested interval.")
    return {"first_frame_seconds": times[0], "last_frame_seconds": times[-1],
            "last_frame_end_seconds": last_end, "maximum_gap_seconds": max(gaps, default=0),
            "allowed_gap_seconds": gap_limit, "expected_frame_rate": rate,
            "frame_rate_basis": "selected_source_stream" if expected_frame_rate is not None else "probe"}


def validate_probe(probe: dict[str, Any], requested_duration: float, width: int, height: int,
                   expected_frame_rate: Any = None):
    video = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video or (video.get("width"), video.get("height")) != (width, height):
        raise ExcerptError("Output dimensions do not match the selected stream.")
    duration = float(probe.get("format", {}).get("duration", 0))
    frames = int(video.get("nb_read_frames", 0))
    if not math.isfinite(duration) or abs(duration - requested_duration) > 0.15 or frames <= 0:
        raise ExcerptError("Output is empty or does not cover the requested duration.")
    timeline = validate_frame_timeline(probe, requested_duration, expected_frame_rate)
    return {"duration_seconds": duration, "decoded_frames": frames, "width": width,
            "height": height, "timeline": timeline}


def acquire(args: argparse.Namespace) -> Path:
    previews = frame_times(args.start, args.end, args.frames)
    bvid, page_no = extract.extract_bvid(args.url), extract.extract_page(args.url, None)
    run_name = f"excerpt-{bvid}-p{page_no}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    output = checked_output(args.out or extract.CONFIG.bilibili_cache / run_name,
                            extract.CONFIG.raw_cache, extract.CONFIG.vault)
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ExcerptError("Existing ffmpeg and ffprobe are required; no tools will be installed.")
    report = {"status": "started", "source": {"bvid": bvid, "page": page_no},
              "requested_seconds": [args.start, args.end], "network_ranges": [],
              "started_at_utc": datetime.now(timezone.utc).isoformat(), "script_sha256": digest(Path(__file__)),
              "scope": "video-only excerpt; preview images are not completed visual review",
              "images_reviewed": False}
    output.mkdir(parents=True, exist_ok=False)
    try:
        referer = f"https://www.bilibili.com/video/{bvid}?p={page_no}"
        data, route = extract.fetch_video_data(bvid, page_no, referer)
        pages = [p for p in data.get("pages", []) if p.get("page") == page_no]
        if data.get("bvid") != bvid or len(pages) != 1 or type(pages[0].get("cid")) is not int or pages[0]["cid"] <= 0:
            raise ExcerptError("Current metadata does not identify the requested BV/P/CID.")
        page = pages[0]
        cid = page["cid"]
        report["source"].update({"cid": cid, "title": data.get("title"), "part": page.get("part"),
                                  "duration_seconds": page.get("duration"), "metadata_route": route})
        write_json(output / "video-metadata.json", data)
        playurl = extract.fetch_json(f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=64&fnval=16&fourk=0", referer)
        write_json(output / "playurl.json", playurl)
        stream, url, init_length, index_end = select_stream(playurl)
        media_duration = float(playurl["data"].get("timelength", 0)) / 1000
        if (not math.isfinite(media_duration) or media_duration <= 0 or args.end > media_duration
                or abs(media_duration - float(page.get("duration", 0))) > 1):
            raise ExcerptError("Requested interval exceeds source duration or metadata durations disagree.")
        if args.start == 0 and args.end >= media_duration - 0.1:
            raise ExcerptError("Whole-video acquisition is prohibited.")
        report["stream"] = {key: stream.get(key) for key in ["id", "width", "height", "codecs", "mimeType"]}
        report["selected_url_sha256"] = hashlib.sha256(url.encode()).hexdigest()
        prefix, receipt = fetch_range(url, 0, index_end, extract.headers(referer))
        report["network_ranges"].append(receipt)
        (output / "init-index.bin").write_bytes(prefix)
        chosen = select_fragments(parse_sidx(prefix), args.start, args.end)
        write_json(output / "selected-fragments.json", chosen)
        first, last = chosen[0]["first"], chosen[-1]["last"]
        if first <= index_end or last >= receipt["total_stream_bytes"]:
            raise ExcerptError("SIDX media offsets exceed the confirmed CDN file.")
        payload, media_receipt = fetch_range(url, first, last, extract.headers(referer))
        report["network_ranges"].append(media_receipt)
        if media_receipt["total_stream_bytes"] != receipt["total_stream_bytes"]:
            raise ExcerptError("CDN file size changed between requests.")
        assembled, target = output / "source-fragments.mp4", output / "video-excerpt.mp4"
        assembled.write_bytes(prefix[:init_length] + payload)
        run_media([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-xerror", "-copyts", "-i", str(assembled),
                   "-map", "0:v:0", "-vf", f"trim=start={args.start}:end={args.end},setpts=PTS-STARTPTS", "-an",
                   "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-fps_mode", "passthrough",
                   "-movflags", "+faststart", "-n", str(target)], output / "trim.stderr.txt")
        probe_text = run_media([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames",
                               "-show_streams", "-show_format", "-show_frames", "-show_entries",
                               "format=duration:stream=codec_type,width,height,nb_read_frames,avg_frame_rate,r_frame_rate:frame=media_type,best_effort_timestamp_time,duration_time,pkt_duration_time",
                               "-of", "json", str(target)], output / "probe.stderr.txt")
        (output / "probe.json").write_text(probe_text, encoding="utf-8")
        verification = validate_probe(json.loads(probe_text), args.end - args.start, int(stream["width"]),
                                      int(stream["height"]), stream.get("frameRate") or stream.get("frame_rate"))
        run_media([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-xerror", "-i", str(target), "-map", "0:v:0", "-f", "null", "-"], output / "full-decode.stderr.txt")
        frames = []
        (output / "frames").mkdir()
        for index, moment in enumerate(previews):
            frame = output / "frames" / f"frame-{index + 1:02d}.png"
            run_media([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-xerror", "-ss", str(moment - args.start),
                       "-i", str(target), "-frames:v", "1", "-update", "1", "-n", str(frame)], output / f"frame-{index + 1:02d}.stderr.txt")
            png = frame.read_bytes()
            if (len(png) < 33 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR"
                    or struct.unpack_from(">II", png, 16) != (int(stream["width"]), int(stream["height"]))):
                raise ExcerptError("Preview PNG is missing, invalid or has incorrect dimensions.")
            frames.append({"file": str(frame), "source_seconds": moment, "relative_seconds": moment - args.start,
                           "sha256": digest(frame), "bytes": len(png)})
        report.update({"status": "verified", "output_video": str(target), "sha256": digest(target),
                       "source_fragment_seconds": [chosen[0]["start"], chosen[-1]["end"]],
                       "verification": {**verification, "full_decode": "passed_without_errors"}, "frames": frames,
                       "media_network_bytes": sum(r["bytes"] for r in report["network_ranges"])})
    except (Exception, SystemExit) as exc:
        report.update({"status": "failed", "error_type": type(exc).__name__,
                       "error": str(exc) if isinstance(exc, ExcerptError) else "Source or media operation failed; no fallback attempted."})
        raise
    finally:
        write_json(output / "excerpt.json", report)
    return output / "excerpt.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Bilibili BV URL, including p= when needed")
    parser.add_argument("--start", type=float, required=True, help="Original video seconds, inclusive")
    parser.add_argument("--end", type=float, required=True, help="Original video seconds, exclusive")
    parser.add_argument("--out", type=Path, help="New configured raw_cache subdirectory; default is a unique bilibili run")
    parser.add_argument("--frames", help="Comma-separated original video seconds; default is a few unreviewed previews")
    args = parser.parse_args()
    try:
        receipt = acquire(args)
    except (Exception, SystemExit) as exc:
        print(f"Excerpt failed: {str(exc) if isinstance(exc, ExcerptError) else type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "verified", "receipt": str(receipt), "images_reviewed": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
