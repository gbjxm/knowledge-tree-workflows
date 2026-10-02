#!/usr/bin/env python3
"""Silently extract public Douyin metadata/audio and optionally transcribe it."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parents[2]
OPERATE_SCRIPTS = SKILLS_ROOT / "operate-personal-knowledge-tree" / "scripts"
if str(OPERATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATE_SCRIPTS))

from knowledge_tree_config import load_config


CONFIG = load_config()
SCRIPT_DIR = Path(__file__).resolve().parent
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)
EDGE_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
)


def extract_aweme_id(url: str) -> str | None:
    for pattern in (r"/video/(\d{15,20})", r"[?&]modal_id=(\d{15,20})"):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def safe_name(text: str, limit: int = 70) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip(" ._")
    text = re.sub(r"\s+", " ", text)
    return (text[:limit].rstrip() or "douyin-video")


def validate_output_root(output_root: Path, vault: Path) -> Path:
    resolved_output = output_root.expanduser().resolve()
    resolved_vault = vault.expanduser().resolve()
    if resolved_output == resolved_vault or resolved_output.is_relative_to(resolved_vault):
        raise SystemExit(f"Refusing raw Douyin output inside the active vault: {resolved_output}")
    return resolved_output


def fmt_time(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def find_edge() -> Path:
    for candidate in EDGE_CANDIDATES:
        if candidate.is_file():
            return candidate
    executable = shutil.which("msedge")
    if executable:
        return Path(executable)
    raise SystemExit("Microsoft Edge was not found.")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def cdp_json(port: int, path: str) -> Any:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def run_cdp_helper(action: str, port: int) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node") or str(Path("D:/node.exe"))
    return subprocess.run(
        [node, str(SCRIPT_DIR / "cdp_helper.mjs"), action, str(port)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )


def pid_for_port(port: int) -> int | None:
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    pattern = re.compile(rf"^\s*TCP\s+127\.0\.0\.1:{port}\s+\S+\s+LISTENING\s+(\d+)\s*$")
    for line in result.stdout.splitlines():
        match = pattern.match(line)
        if match:
            return int(match.group(1))
    return None


def close_temporary_edge(port: int, process: subprocess.Popen[Any]) -> None:
    browser_pid = pid_for_port(port)
    try:
        run_cdp_helper("close", port)
    except (OSError, subprocess.SubprocessError):
        pass
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            cdp_json(port, "/json/version")
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                if browser_pid:
                    subprocess.run(
                        ["taskkill", "/PID", str(browser_pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
            time.sleep(3)
            return
        time.sleep(0.25)
    pid = pid_for_port(port)
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
    elif process.poll() is None:
        process.terminate()
    time.sleep(3)


@contextmanager
def temporary_edge_root():
    """Create a disposable browser root and retry cleanup while Edge releases files."""
    root = Path(tempfile.mkdtemp(prefix="codex-douyin-edge-"))
    try:
        yield root
    finally:
        for _ in range(12):
            try:
                shutil.rmtree(root)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(1)
        if root.exists():
            raise RuntimeError(f"Temporary Edge profile could not be deleted: {root}")


def refresh_public_session(url: str, profile: Path, timeout: int) -> dict[str, str]:
    port = free_port()
    flags = [
        str(find_edge()),
        "--headless=new",
        "--mute-audio",
        "--disable-extensions",
        "--disable-sync",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-gpu",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--window-size=1440,1000",
        url,
    ]
    process = subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    captured: dict[str, str] = {"title": "", "url": url, "text": ""}
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                targets = cdp_json(port, "/json/list")
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                time.sleep(0.5)
                continue
            page = next((item for item in targets if item.get("type") == "page"), None)
            if page:
                title = str(page.get("title") or "")
                page_url = str(page.get("url") or url)
                captured.update({"title": title, "url": page_url})
                if title and title != page_url and "douyin.com" in page_url:
                    time.sleep(2)
                    helper = run_cdp_helper("capture", port)
                    if helper.returncode == 0:
                        try:
                            payload = json.loads(helper.stdout)
                            captured.update({key: str(payload.get(key) or "") for key in captured})
                        except json.JSONDecodeError:
                            pass
                    break
            time.sleep(0.5)
        else:
            raise SystemExit("Timed out while loading the public Douyin page in temporary Edge.")
    finally:
        close_temporary_edge(port, process)
    combined = f"{captured['title']}\n{captured['text']}"
    if any(marker in combined for marker in ("安全验证", "请输入验证码", "扫码登录后观看")):
        raise SystemExit("Douyin requested login or verification; automatic extraction stopped.")
    return captured


def yt_dlp_command(profile: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--cookies-from-browser",
        f"edge:{profile}",
        "--user-agent",
        UA,
        "--referer",
        "https://www.douyin.com/",
        *args,
    ]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def dump_metadata(url: str, profile: Path) -> dict[str, Any]:
    result = yt_dlp_command(profile, "--dump-single-json", "--no-playlist", "--no-warnings", url)
    if result.returncode != 0 and "cookie database" in result.stderr.lower():
        time.sleep(5)
        result = yt_dlp_command(profile, "--dump-single-json", "--no-playlist", "--no-warnings", url)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise SystemExit(f"yt-dlp metadata extraction failed: {detail[-1] if detail else 'unknown error'}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit("yt-dlp returned invalid metadata JSON.") from exc


def pick_smallest_muxed_format(formats: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = []
    for item in formats:
        if item.get("acodec") in (None, "none") or item.get("vcodec") in (None, "none"):
            continue
        if not item.get("height"):
            continue
        size = item.get("filesize") or item.get("filesize_approx")
        if not isinstance(size, (int, float)) or size <= 0:
            continue
        candidates.append((float(size), item))
    if not candidates:
        raise SystemExit("No downloadable muxed audio/video format with a known size was found.")
    return min(candidates, key=lambda pair: pair[0])[1]


def download_audio(url: str, profile: Path, out_dir: Path, format_id: str) -> Path:
    template = out_dir / "audio.%(ext)s"
    result = yt_dlp_command(
        profile,
        "--no-playlist",
        "--no-warnings",
        "-f",
        format_id,
        "-x",
        "--audio-format",
        "m4a",
        "--audio-quality",
        "5",
        "--print",
        "after_move:filepath",
        "-o",
        str(template),
        url,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise SystemExit(f"yt-dlp audio download failed: {detail[-1] if detail else 'unknown error'}")
    paths = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
    audio = next((path for path in reversed(paths) if path.is_file()), None)
    if not audio:
        audio = next(iter(sorted(out_dir.glob("audio.*"))), None)
    if not audio:
        raise SystemExit("yt-dlp completed but the extracted audio file was not found.")
    return audio


def clip_ranges(duration: float, chunk_seconds: int, explicit: str | None) -> list[str]:
    if explicit:
        return [explicit]
    if duration <= 0:
        return [""]
    return [
        f"{start},{min(start + chunk_seconds, duration):g}"
        for start in range(0, int(duration), chunk_seconds)
    ]


def transcribe_audio(
    audio_path: Path,
    model_name: str,
    language: str | None,
    clip: str | None,
    duration: float,
    chunk_seconds: int,
) -> str:
    detected_language = language or "unknown"
    language_probability = 0.0
    lines = [
        "# Transcript",
        "",
        f"Source: local faster-whisper ASR ({model_name})",
    ]
    ranges = clip_ranges(duration, chunk_seconds, clip)
    for index, current_clip in enumerate(ranges, start=1):
        print(f"ASR chunk {index}/{len(ranges)}: {current_clip or 'full'}", file=sys.stderr, flush=True)
        command = [
            sys.executable,
            str(SCRIPT_DIR / "asr_chunk.py"),
            str(audio_path),
            "--model",
            model_name,
            "--clip",
            current_clip,
        ]
        if language:
            command.extend(["--language", language])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise SystemExit(
                f"ASR chunk failed at {current_clip}: {detail[-1] if detail else 'native process error'}"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"ASR chunk returned invalid JSON at {current_clip}.") from exc
        if index == 1:
            detected_language = str(payload.get("language") or detected_language)
            language_probability = float(payload.get("language_probability") or 0)
        for segment in payload.get("segments") or []:
            content = str(segment.get("text") or "").strip()
            if content:
                lines.append(
                    f"- [{fmt_time(float(segment['start']))} - {fmt_time(float(segment['end']))}] {content}"
                )
    lines.insert(3, f"Detected language: {detected_language} ({language_probability:.3f})")
    lines.insert(4, "")
    return "\n".join(lines) + "\n"


def clean_metadata(raw: dict[str, Any], source_url: str, selected: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_url": source_url,
        "webpage_url": raw.get("webpage_url"),
        "aweme_id": str(raw.get("id") or ""),
        "title": raw.get("title"),
        "description": raw.get("description"),
        "author": raw.get("channel") or raw.get("uploader"),
        "author_id": raw.get("channel_id") or raw.get("uploader_id"),
        "duration": raw.get("duration"),
        "timestamp": raw.get("timestamp"),
        "upload_date": raw.get("upload_date"),
        "selected_format": {
            "format_id": selected.get("format_id"),
            "height": selected.get("height"),
            "filesize": selected.get("filesize") or selected.get("filesize_approx"),
            "acodec": selected.get("acodec"),
            "vcodec": selected.get("vcodec"),
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Silently extract a public Douyin video for study notes.")
    parser.add_argument("url")
    parser.add_argument("--out", type=Path, default=CONFIG.raw_cache / "douyin")
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--transcribe", action="store_true")
    parser.add_argument("--model", default="base")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--clip", help="ASR clip timestamps, such as 0,180.")
    parser.add_argument("--chunk-seconds", type=int, default=60, help="Full-ASR chunk size.")
    parser.add_argument("--browser-timeout", type=int, default=30)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_root = validate_output_root(args.out, CONFIG.vault)
    output_root.mkdir(parents=True, exist_ok=True)

    with temporary_edge_root() as temp:
        profile = temp / "profile"
        page = refresh_public_session(args.url, profile, args.browser_timeout)
        resolved_url = page.get("url") or args.url
        initial_id = extract_aweme_id(resolved_url) or extract_aweme_id(args.url)
        if initial_id and "/video/" not in resolved_url:
            resolved_url = f"https://www.douyin.com/video/{initial_id}"
        raw = dump_metadata(resolved_url, profile)
        selected = pick_smallest_muxed_format(raw.get("formats") or [])
        aweme_id = str(raw.get("id") or extract_aweme_id(resolved_url) or extract_aweme_id(args.url) or "unknown")
        title = str(raw.get("title") or page.get("title") or aweme_id)
        out_dir = output_root / f"{aweme_id}-{safe_name(title)}"
        out_dir.mkdir(parents=True, exist_ok=True)

        metadata = clean_metadata(raw, args.url, selected)
        metadata["resolved_url"] = resolved_url
        metadata["browser_mode"] = "temporary_edge_headless_muted"
        metadata["transcript_source"] = "none"
        page_text = str(page.get("text") or "").strip()
        if page_text:
            (out_dir / "page-text.txt").write_text(page_text + "\n", encoding="utf-8")

        if not args.metadata_only:
            audio = download_audio(resolved_url, profile, out_dir, str(selected["format_id"]))
            metadata["audio_path"] = str(audio)
            if args.transcribe:
                transcript = transcribe_audio(
                    audio,
                    args.model,
                    args.language,
                    args.clip,
                    float(raw.get("duration") or 0),
                    args.chunk_seconds,
                )
                (out_dir / "transcript.md").write_text(transcript, encoding="utf-8")
                metadata["transcript_source"] = "faster_whisper_asr"
                metadata["asr_model"] = args.model
                metadata["asr_clip"] = args.clip
                metadata["asr_chunk_seconds"] = args.chunk_seconds

        (out_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps({"out_dir": str(out_dir), **metadata}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
