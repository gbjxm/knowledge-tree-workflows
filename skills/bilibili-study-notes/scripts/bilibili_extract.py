#!/usr/bin/env python3
"""Extract Bilibili subtitles or local ASR transcripts for study notes."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
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


def download(url: str, dest: Path, referer: str) -> None:
    req = urllib.request.Request(url, headers=headers(referer))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=180) as resp, dest.open("wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)


def extract_bvid(url: str) -> str:
    match = re.search(r"(BV[0-9A-Za-z]+)", url)
    if not match:
        raise SystemExit("Could not find a BV id in the URL.")
    return match.group(1)


def extract_page(url: str, override: int | None) -> int:
    if override:
        return override
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    try:
        return int(qs.get("p", ["1"])[0])
    except ValueError:
        return 1


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


def subtitle_to_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Transcript", "", "Source: Bilibili subtitle", ""]
    body = payload.get("body")
    for item in body if isinstance(body, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            continue
        start = fmt_time(float(item.get("from", 0)))
        end = fmt_time(float(item.get("to", 0)))
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(f"- [{start} - {end}] {content}")
    return "\n".join(lines) + "\n"


def has_transcript_content(text: str) -> bool:
    """A header-only subtitle/ASR file is not a usable transcript."""
    return re.search(r"^- \[[^\]\r\n]+\][ \t]+\S", text, flags=re.MULTILINE) is not None


def transcribe_audio(audio_path: Path, model_name: str, language: str | None, clip: str | None) -> str:
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
        f"Detected language: {info.language} ({info.language_probability:.3f})",
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
    parser.add_argument("--model", default="base.en", help="faster-whisper model name.")
    parser.add_argument("--language", help="Force ASR language, such as en or zh.")
    parser.add_argument("--clip", help="ASR clip timestamps, such as 0,180.")
    return parser


def extract_transcript(
    args: argparse.Namespace, out_dir: Path, bvid: str, cid: int,
    referer: str, metadata: dict[str, Any],
) -> str:
    player = fetch_json(f"https://api.bilibili.com/x/player/v2?cid={cid}&bvid={bvid}", referer)
    subtitles = ((player.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
    metadata["subtitle_count"] = len(subtitles)
    picked = pick_subtitle(subtitles, ["zh-Hans", "zh-CN", "zh", "en-US", "en"])
    if picked and picked.get("subtitle_url"):
        sub_url = picked["subtitle_url"]
        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url
        payload = fetch_json(sub_url, referer)
        (out_dir / "subtitle.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        transcript = subtitle_to_markdown(payload)
        if has_transcript_content(transcript):
            metadata["transcript_source"] = "bilibili_subtitle"
            metadata["subtitle_language"] = picked.get("lan") or picked.get("lan_doc")
            return transcript
        metadata["subtitle_empty"] = True

    if not args.transcribe:
        raise SystemExit("No usable subtitle text. Re-run with --transcribe to enable ASR fallback.")
    play = fetch_json(
        f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=16&fnval=16&fourk=0",
        referer,
    )
    audios = (((play.get("data") or {}).get("dash") or {}).get("audio") or [])
    if not audios:
        raise SystemExit("No usable subtitle and no DASH audio stream found.")
    audio = sorted(audios, key=lambda item: item.get("bandwidth", 10**9))[0]
    audio_url = audio.get("baseUrl") or audio.get("base_url")
    if not audio_url:
        raise SystemExit("DASH audio stream has no download URL.")
    audio_path = out_dir / "audio.m4s"
    download(audio_url, audio_path, referer)
    transcript = transcribe_audio(audio_path, args.model, args.language, args.clip)
    if not has_transcript_content(transcript):
        raise SystemExit("ASR returned no usable text; extraction remains incomplete.")
    metadata["transcript_source"] = "faster_whisper_asr"
    metadata["audio_path"] = str(audio_path)
    metadata["asr_model"] = args.model
    metadata["asr_clip"] = args.clip
    return transcript


def main() -> int:
    args = build_parser().parse_args()
    output_root = validate_output_root(args.out, CONFIG.vault)

    bvid = extract_bvid(args.url)
    page_no = extract_page(args.url, args.page)
    referer = f"https://www.bilibili.com/video/{bvid}?p={page_no}"

    view = fetch_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", referer)
    if view.get("code") != 0:
        raise SystemExit(f"Bilibili view API failed: {view.get('message')}")

    data = view["data"]
    pages = data.get("pages") or []
    page = next((p for p in pages if int(p.get("page", 0)) == page_no), None)
    if not page:
        raise SystemExit(f"Could not find page {page_no}; available pages: {[p.get('page') for p in pages]}")

    cid = page["cid"]
    title = data.get("title") or bvid
    part = page.get("part") or f"P{page_no}"
    out_dir = output_root / f"{bvid}-p{page_no}-{safe_name(part, 40)}"
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "source_url": args.url,
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

    transcript_path = out_dir / "transcript.md"
    try:
        transcript = extract_transcript(args, out_dir, bvid, cid, referer, metadata)
        transcript_path.write_text(transcript, encoding="utf-8")
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
