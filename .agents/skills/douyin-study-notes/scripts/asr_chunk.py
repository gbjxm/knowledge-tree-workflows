#!/usr/bin/env python3
"""Transcribe one bounded audio interval in an isolated process."""

from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--model", required=True)
    parser.add_argument("--language")
    parser.add_argument("--clip", required=True)
    args = parser.parse_args()

    from faster_whisper import WhisperModel

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    options = {
        "beam_size": 1,
        "best_of": 1,
        "vad_filter": True,
        "condition_on_previous_text": True,
        "clip_timestamps": args.clip,
    }
    if args.language:
        options["language"] = args.language
    segments, info = model.transcribe(args.audio, **options)
    payload = {
        "language": info.language,
        "language_probability": info.language_probability,
        "segments": [
            {"start": item.start, "end": item.end, "text": item.text.strip()}
            for item in segments
            if item.text.strip()
        ],
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
