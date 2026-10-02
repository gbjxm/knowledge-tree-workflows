#!/usr/bin/env python3
"""Extract Bilibili subtitles or local ASR transcripts for study notes."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parents[2]
OPERATE_SCRIPTS = SKILLS_ROOT / "operate-personal-knowledge-tree" / "scripts"
if str(OPERATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATE_SCRIPTS))

from knowledge_tree_config import load_config


CONFIG = load_config()

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def headers(referer: str = "https://www.bilibili.com/") -> dict[str, str]:
    return {
        "User-Agent": UA,
        "Referer": referer,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def fetch_json(url: str, referer: str = "https://www.bilibili.com/") -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers(referer))
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def select_video_page(data: dict[str, Any], page_no: int) -> dict[str, Any]:
    """Select with the same strict identity rules used during metadata validation."""
    pages = data.get("pages")
    matches = [
        page for page in pages
        if isinstance(page, dict) and type(page.get("page")) is int and page["page"] == page_no
    ] if isinstance(pages, list) else []
    if (len(matches) != 1 or type(matches[0].get("cid")) is not int
            or matches[0]["cid"] <= 0):
        raise ValueError("Video has no unique valid page/CID identity; extraction stopped.")
    return matches[0]


def validate_video_data(data: Any, bvid: str, page_no: int) -> dict[str, Any]:
    """Keep fallback and ordinary metadata bound to one exact public video/page."""
    if not isinstance(data, dict) or data.get("bvid") != bvid:
        raise ValueError("Video BV identity does not match the requested video.")
    select_video_page(data, page_no)
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise ValueError("Video has no readable title; extraction stopped.")
    return data


def fetch_public_video_data(bvid: str, page_no: int, referer: str) -> dict[str, Any]:
    """Read the same public page only after a metadata API 412 response."""
    req = urllib.request.Request(referer, headers=headers(referer))
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    html = raw.decode("utf-8")
    marker = re.search(r"(?:window\.)?__INITIAL_STATE__\s*=\s*", html)
    if marker is None:
        raise ValueError("Public page has no readable video identity; extraction stopped.")
    state, _ = json.JSONDecoder().raw_decode(html[marker.end():])
    data = state.get("videoData") if isinstance(state, dict) else None
    return validate_video_data(data, bvid, page_no)


def fetch_video_data(bvid: str, page_no: int, referer: str) -> tuple[dict[str, Any], str]:
    try:
        view = fetch_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", referer)
    except urllib.error.HTTPError as exc:
        if exc.code != 412:
            raise
        return fetch_public_video_data(bvid, page_no, referer), "public_page_after_http_412"
    if view.get("code") == -412:
        return fetch_public_video_data(bvid, page_no, referer), "public_page_after_api_minus_412"
    if view.get("code") != 0:
        raise SystemExit(f"Bilibili view API failed: {view.get('message')}")
    return validate_video_data(view.get("data"), bvid, page_no), "view_api"


def download(url: str, dest: Path, referer: str) -> None:
    """Promote only complete, nonempty downloads; retain failed partials in cache."""
    req = urllib.request.Request(url, headers={
        **headers(referer), "Range": "bytes=0-", "Accept-Encoding": "identity",
    })
    dest.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 180
    with tempfile.NamedTemporaryFile(
        prefix=f"{dest.name}.download-", suffix=".partial", dir=dest.parent, delete=False,
    ) as fh, urllib.request.urlopen(req, timeout=30) as resp:
        temp_path = Path(fh.name)
        content_range = resp.headers.get("Content-Range")
        complete_response = resp.status == 200 and content_range is None
        length = resp.headers.get("Content-Length")
        expected = int(length) if length is not None else None
        if resp.status == 206:
            match = re.fullmatch(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)", content_range or "")
            if match:
                start, end, total = (int(value) for value in match.groups())
                complete_response = (start == 0 and total > 0 and end == total - 1
                                     and (expected is None or expected == total))
                expected = total
        if expected is not None and expected <= 0:
            raise ValueError(f"Audio download has an invalid Content-Length; retained {temp_path}")
        received = 0
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Audio download exceeded the 180 second wall-clock budget; retained {temp_path}")
            chunk = resp.read(64 * 1024)
            if chunk:
                fh.write(chunk)
                received += len(chunk)
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Audio download exceeded the 180 second wall-clock budget; retained {temp_path}")
            if not chunk:
                break
        if not complete_response:
            raise ValueError(f"Audio download did not return a complete HTTP 200 or full-range 206 response; retained {temp_path}")
        if received == 0 or (expected is not None and received != expected):
            raise ValueError(f"Audio download is empty or incomplete; retained {temp_path}")
    if time.monotonic() >= deadline:
        raise TimeoutError(f"Audio download exceeded the 180 second wall-clock budget; retained {temp_path}")
    temp_path.replace(dest)


def extract_bvid(url: str) -> str:
    match = re.search(r"(BV[0-9A-Za-z]+)", url)
    if not match:
        raise SystemExit("Could not find a BV id in the URL.")
    return match.group(1)


def extract_page(url: str, override: int | None) -> int:
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    try:
        page = override if override is not None else int(qs.get("p", ["1"])[0])
    except ValueError as exc:
        raise SystemExit("Page must be a positive integer.") from exc
    if type(page) is not int or page <= 0:
        raise SystemExit("Page must be a positive integer.")
    return page


def parse_clip(clip: str | None) -> tuple[float, float] | None:
    if clip is None:
        return None
    try:
        values = clip.split(",")
        if len(values) != 2:
            raise ValueError
        start, end = (float(value.strip()) for value in values)
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            raise ValueError
    except (AttributeError, TypeError, ValueError) as exc:
        raise SystemExit("--clip requires one finite nonnegative start,end pair with start < end.") from exc
    return start, end


def validate_asr_options(model_name: str, language: str | None, clip: str | None) -> None:
    parse_clip(clip)
    if model_name.lower().endswith(".en") and language and language.lower() != "en":
        raise SystemExit("English-only .en models require --language en; use a multilingual model for other languages.")


def safe_name(text: str, limit: int = 80) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip(" ._")
    text = re.sub(r"\s+", " ", text)
    return (text[:limit].rstrip() or "bilibili-video")


def validate_output_root(output_root: Path, vault: Path) -> Path:
    """Fail closed when raw extraction artifacts would land inside the active vault."""
    resolved_output = output_root.expanduser().resolve()
    resolved_vault = vault.expanduser().resolve()
    if resolved_output == resolved_vault or resolved_output.is_relative_to(resolved_vault):
        raise SystemExit(
            f"Refusing raw Bilibili output inside the active vault: {resolved_output}"
        )
    return resolved_output


def fmt_time(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def pick_subtitle(subtitles: list[dict[str, Any]], preferred: list[str]) -> dict[str, Any] | None:
    if not subtitles:
        return None
    for lang in preferred:
        for sub in subtitles:
            if sub.get("lan") == lang or sub.get("lan_doc") == lang:
                return sub
    return subtitles[0]


def subtitle_to_markdown(payload: dict[str, Any], clip: str | None = None) -> str:
    lines = ["# Transcript", "", "Source: Bilibili subtitle", ""]
    bounds = parse_clip(clip)
    body = payload.get("body")
    for item in body if isinstance(body, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            continue
        start_seconds = float(item.get("from", 0))
        end_seconds = float(item.get("to", 0))
        if not (math.isfinite(start_seconds) and math.isfinite(end_seconds)):
            continue
        if bounds and (end_seconds <= bounds[0] or start_seconds >= bounds[1]):
            continue
        start = fmt_time(start_seconds)
        end = fmt_time(end_seconds)
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(f"- [{start} - {end}] {content}")
    return "\n".join(lines) + "\n"


def has_transcript_content(text: str) -> bool:
    """A header-only subtitle/ASR file is not a usable transcript."""
    return re.search(r"^- \[[^\]\r\n]+\][ \t]+\S", text, flags=re.MULTILINE) is not None


def transcribe_audio(audio_path: Path, model_name: str, language: str | None, clip: str | None) -> str:
    validate_asr_options(model_name, language, clip)
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit(
            "faster-whisper is not installed. Install it with: python -m pip install -U faster-whisper"
        ) from exc

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    kwargs: dict[str, Any] = {
        "beam_size": 1,
        "best_of": 1,
        "vad_filter": True,
        "condition_on_previous_text": True,
    }
    if language:
        kwargs["language"] = language
    if clip:
        kwargs["clip_timestamps"] = clip

    segments, info = model.transcribe(str(audio_path), **kwargs)
    lines = [
        "# Transcript",
        "",
        f"Source: local faster-whisper ASR ({model_name})",
        (f"Specified language: {language}" if language else
         "Model language: en (English-only model)" if model_name.lower().endswith(".en") else
         f"Detected language: {info.language} ({info.language_probability:.3f})"),
        "",
    ]
    for seg in segments:
        text = seg.text.strip()
        if text:
            lines.append(f"- [{fmt_time(seg.start)} - {fmt_time(seg.end)}] {text}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract Bilibili subtitles or ASR transcript.")
    parser.add_argument("url")
    parser.add_argument("--page", type=int, help="Override page number from URL p=.")
    parser.add_argument("--out", type=Path, default=CONFIG.bilibili_cache, help="Output directory.")
    parser.add_argument("--transcribe", action="store_true", help="Run faster-whisper if subtitles are empty.")
    parser.add_argument("--model", default="base", help="faster-whisper model name (default: multilingual base).")
    parser.add_argument("--language", help="Force ASR language, such as en or zh.")
    parser.add_argument("--clip", help="One finite start,end range in seconds, such as 0,180; subtitles retain overlapping whole cues.")
    return parser


def fetch_subtitle_json(
    url: str, referer: str, metadata: dict[str, Any], stage: str,
) -> dict[str, Any] | None:
    """Distinguish access failure from an accessible video with no subtitles."""
    try:
        payload = fetch_json(url, referer)
    except urllib.error.HTTPError as exc:
        metadata.update(subtitle_access="unavailable", subtitle_access_stage=stage,
                        subtitle_access_http_status=exc.code)
        return None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        metadata.update(subtitle_access="unavailable", subtitle_access_stage=stage,
                        subtitle_access_network_error=type(exc).__name__)
        return None
    if payload.get("code") not in (None, 0):
        metadata.update(subtitle_access="unavailable", subtitle_access_stage=stage,
                        subtitle_access_api_code=payload.get("code"))
        return None
    return payload


def extract_transcript(
    args: argparse.Namespace, out_dir: Path, bvid: str, cid: int,
    referer: str, metadata: dict[str, Any],
) -> str:
    model_name = getattr(args, "model", "base")
    language = getattr(args, "language", None)
    clip = getattr(args, "clip", None)
    validate_asr_options(model_name, language, clip)
    bounds = parse_clip(clip)
    metadata["transcript_scope"] = "partial" if bounds else "full"
    if bounds:
        metadata["requested_clip_seconds"] = {"start": bounds[0], "end": bounds[1]}
    player = fetch_subtitle_json(
        f"https://api.bilibili.com/x/player/v2?cid={cid}&bvid={bvid}", referer, metadata, "player",
    )
    player_data = (player or {}).get("data") or {}
    if player_data.get("need_login_subtitle") is True:
        metadata.update(subtitle_access="unavailable", subtitle_access_stage="player",
                        subtitle_access_reason="login_required")
        player = None
        player_data = {}
    subtitles = (player_data.get("subtitle") or {}).get("subtitles") or []
    metadata["subtitle_count"] = len(subtitles) if player is not None else None
    if player is not None:
        metadata["subtitle_access"] = "available"
    picked = pick_subtitle(subtitles, ["zh-Hans", "zh-CN", "zh", "en-US", "en"])
    if picked and picked.get("subtitle_url"):
        sub_url = picked["subtitle_url"]
        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url
        payload = fetch_subtitle_json(sub_url, referer, metadata, "subtitle_payload")
        if payload is not None:
            (out_dir / "subtitle.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            transcript = subtitle_to_markdown(payload, clip)
            if has_transcript_content(transcript):
                metadata["transcript_source"] = "bilibili_subtitle"
                metadata["subtitle_language"] = picked.get("lan") or picked.get("lan_doc")
                if bounds:
                    metadata["subtitle_clip_policy"] = "overlapping_whole_cues_with_original_timestamps"
                return transcript
            metadata["subtitle_clip_empty" if bounds else "subtitle_empty"] = True

    if not getattr(args, "transcribe", False):
        if metadata.get("subtitle_access") == "unavailable":
            raise SystemExit("Subtitle access is unavailable; --transcribe is required for public audio ASR fallback.")
        raise SystemExit("No usable subtitle text. Re-run with --transcribe to enable ASR fallback.")
    play = fetch_json(
        f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=16&fnval=16&fourk=0",
        referer,
    )
    if play.get("code") not in (None, 0):
        raise SystemExit(f"Bilibili public audio API failed: {play.get('code')}: {play.get('message')}")
    audios = (((play.get("data") or {}).get("dash") or {}).get("audio") or [])
    if not audios:
        raise SystemExit("No usable subtitle and no DASH audio stream found.")
    audio = sorted(audios, key=lambda item: item.get("bandwidth", 10**9))[0]
    audio_url = audio.get("baseUrl") or audio.get("base_url")
    if not audio_url:
        raise SystemExit("DASH audio stream has no download URL.")
    audio_path = out_dir / "audio.m4s"
    download(audio_url, audio_path, referer)
    transcript = transcribe_audio(audio_path, model_name, language, clip)
    if not has_transcript_content(transcript):
        raise SystemExit("ASR returned no usable text; extraction remains incomplete.")
    metadata["transcript_source"] = "faster_whisper_asr"
    metadata["audio_path"] = str(audio_path)
    metadata["asr_model"] = model_name
    metadata["asr_clip"] = clip
    metadata["asr_language_mode"] = "specified" if language else "model_fixed" if model_name.lower().endswith(".en") else "detected"
    if language:
        metadata["asr_language"] = language
    elif model_name.lower().endswith(".en"):
        metadata["asr_language"] = "en"
    return transcript


def main() -> int:
    args = build_parser().parse_args()
    validate_asr_options(getattr(args, "model", "base"), getattr(args, "language", None), getattr(args, "clip", None))
    output_root = validate_output_root(args.out, CONFIG.vault)

    bvid = extract_bvid(args.url)
    page_no = extract_page(args.url, args.page)
    referer = f"https://www.bilibili.com/video/{bvid}?p={page_no}"

    data, metadata_source = fetch_video_data(bvid, page_no, referer)
    page = select_video_page(data, page_no)

    cid = page["cid"]
    title = data.get("title") or bvid
    part = page.get("part") or f"P{page_no}"
    base_out_dir = output_root / f"{bvid}-p{page_no}-{safe_name(part, 40)}"
    out_dir = base_out_dir
    try:
        out_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        # A rerun owns a new artifact set; failed ASR must not mix old text with new audio.
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        out_dir = output_root / f"{base_out_dir.name}-run-{stamp}-{uuid.uuid4().hex[:8]}"
        out_dir.mkdir(parents=True, exist_ok=False)

    metadata = {
        "source_url": args.url,
        "output_directory": str(out_dir),
        "metadata_source": metadata_source,
        "bvid": bvid,
        "aid": data.get("aid"),
        "title": title,
        "page": page_no,
        "part": part,
        "cid": cid,
        "duration": page.get("duration"),
        "transcript_source": "none",
        "extraction_status": "pending",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if out_dir != base_out_dir:
        metadata["previous_output_directory"] = str(base_out_dir)

    transcript_path = out_dir / "transcript.md"
    try:
        transcript = extract_transcript(args, out_dir, bvid, cid, referer, metadata)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="transcript-", suffix=".partial", dir=out_dir, delete=False,
        ) as handle:
            temporary_transcript = Path(handle.name)
            handle.write(transcript)
        temporary_transcript.replace(transcript_path)
        metadata["extraction_status"] = "extracted"
    except (Exception, SystemExit):
        metadata["transcript_source"] = "none"
        metadata["extraction_status"] = "failed"
        (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        raise

    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out_dir": str(out_dir), **metadata}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
