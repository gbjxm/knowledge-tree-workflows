#!/usr/bin/env python3
"""Run quality, gap, completeness and context-budget evaluations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from retrieve_knowledge import load_config, load_routes, load_topics, resolve_config, retrieve


DEFAULT_CASES = Path(__file__).resolve().parents[1] / "references" / "eval-cases-v2.json"
REQUIRED_CARD_FIELDS = ("core", "method_chunks", "minimal_action", "boundary", "evidence_status")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--config")
    parser.add_argument("--top1-min", type=float, default=0.90)
    parser.add_argument("--hit3-min", type=float, default=0.95)
    parser.add_argument("--gap-min", type=float, default=0.95)
    parser.add_argument("--avg-chars-max", type=int, default=4000)
    args = parser.parse_args(argv)
    try:
        config_path = resolve_config(args.config)
        config = load_config(config_path)
        library = Path(config["knowledge_library"]).resolve()
        topics = load_topics(library)
        routes = load_routes(library)
        cases = json.loads(Path(args.cases).read_text(encoding="utf-8-sig"))["cases"]
        rows: list[dict[str, object]] = []
        supported = top1_ok_count = hit3_ok_count = 0
        negatives = gap_ok_count = 0
        complete_count = 0
        context_chars: list[int] = []
        for case in cases:
            kwargs = {
                "routes": routes,
                "role": case.get("role", ""),
                "task_type": case.get("task_type", ""),
                "object_name": case.get("object", ""),
                "constraints": case.get("constraints", ""),
                "expected_output": case.get("expected_output", ""),
            }
            result = retrieve(topics, case["query"], case.get("stage", ""), 3, **kwargs)
            compact_result = retrieve(topics, case["query"], case.get("stage", ""), 1, **kwargs)
            titles = [item["title"] for item in result["candidates"]]
            expect_gap = bool(case.get("expect_gap"))
            if expect_gap:
                negatives += 1
                gap_ok = bool(result["gap"])
                gap_ok_count += int(gap_ok)
                top1_ok = hit3_ok = True
            else:
                supported += 1
                expected_top1 = case.get("expected_top1", [])
                expected_any = case.get("expected_any", expected_top1)
                top1_ok = bool(titles and titles[0] in expected_top1)
                hit3_ok = any(title in titles for title in expected_any)
                top1_ok_count += int(top1_ok)
                hit3_ok_count += int(hit3_ok)
                gap_ok = not result["gap"]
            forbidden = set(case.get("forbidden", []))
            forbidden_ok = not any(title in forbidden for title in titles)
            card = compact_result["candidates"][0] if compact_result["candidates"] else {}
            card_complete = expect_gap or all(card.get(field) for field in REQUIRED_CARD_FIELDS)
            complete_count += int(card_complete)
            chars = len(json.dumps(compact_result, ensure_ascii=False, separators=(",", ":")))
            context_chars.append(chars)
            passed = top1_ok and hit3_ok and gap_ok and forbidden_ok and card_complete
            rows.append({
                "id": case["id"], "titles": titles, "gap": result["gap"],
                "top1_ok": top1_ok, "hit3_ok": hit3_ok, "gap_ok": gap_ok,
                "forbidden_ok": forbidden_ok, "card_complete": card_complete,
                "compact_chars": chars, "passed": passed,
            })
        top1_rate = top1_ok_count / supported if supported else 1.0
        hit3_rate = hit3_ok_count / supported if supported else 1.0
        gap_rate = gap_ok_count / negatives if negatives else 1.0
        completeness_rate = complete_count / len(cases) if cases else 1.0
        avg_chars = sum(context_chars) / len(context_chars) if context_chars else 0.0
        thresholds_ok = (
            top1_rate >= args.top1_min and hit3_rate >= args.hit3_min and gap_rate >= args.gap_min
            and completeness_rate == 1.0 and avg_chars <= args.avg_chars_max
        )
        failures = [row["id"] for row in rows if not row["passed"]]
        output = {
            "config": str(config_path), "case_count": len(cases), "supported": supported,
            "negatives": negatives, "metrics": {
                "top1_accuracy": round(top1_rate, 4), "essential_hit_at_3": round(hit3_rate, 4),
                "gap_accuracy": round(gap_rate, 4), "card_completeness": round(completeness_rate, 4),
                "average_compact_chars": round(avg_chars, 1), "max_compact_chars": max(context_chars, default=0),
            },
            "thresholds": {"top1_min": args.top1_min, "hit3_min": args.hit3_min,
                           "gap_min": args.gap_min, "avg_chars_max": args.avg_chars_max},
            "thresholds_ok": thresholds_ok, "failures": failures, "cases": rows,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if thresholds_ok and not failures else 1
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
