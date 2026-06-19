#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import resource
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from common import detect_templates, ensure_parent, local_name, text_sha1


def parse_template_limits(raw: str) -> dict[str, int]:
    limits: dict[str, int] = {}
    if not raw:
        return limits
    for part in raw.split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise SystemExit("--template-limits entries must look like character=25")
        key, value = part.split("=", 1)
        key = key.strip().casefold()
        if key not in {"character", "comic", "volume"}:
            raise SystemExit(f"Unsupported template limit: {key}")
        limits[key] = int(value)
    return limits


def direct_child_text(elem: ET.Element, name: str) -> str:
    for child in elem:
        if local_name(child.tag) == name:
            return child.text or ""
    return ""


def first_descendant_text(elem: ET.Element, name: str) -> str:
    for child in elem.iter():
        if local_name(child.tag) == name:
            return child.text or ""
    return ""


def page_to_record(elem: ET.Element, wanted_templates: set[str]) -> dict[str, Any] | None:
    title = direct_child_text(elem, "title")
    ns = direct_child_text(elem, "ns")
    if ns != "0":
        return None

    page_id = direct_child_text(elem, "id")
    redirect = any(local_name(child.tag) == "redirect" for child in elem)
    if redirect:
        return None

    revision = None
    for child in elem:
        if local_name(child.tag) == "revision":
            revision = child
            break
    if revision is None:
        return None

    revision_id = direct_child_text(revision, "id")
    timestamp = direct_child_text(revision, "timestamp")
    text = first_descendant_text(revision, "text")
    templates = set(detect_templates(text))
    matched = sorted(templates & wanted_templates)
    if not matched:
        return None

    return {
        "page_id": page_id,
        "revision_id": revision_id,
        "timestamp": timestamp,
        "title": title,
        "ns": int(ns),
        "template_types": matched,
        "text_bytes": len(text.encode("utf-8", errors="replace")),
        "text_sha1": text_sha1(text),
        "text": text,
    }


def within_template_limits(matched: list[str], counts: dict[str, int], limits: dict[str, int]) -> bool:
    if not limits:
        return True
    return any(counts.get(template_type, 0) < limits.get(template_type, 0) for template_type in matched)


def template_limits_satisfied(counts: dict[str, int], limits: dict[str, int]) -> bool:
    if not limits:
        return False
    return all(counts.get(template_type, 0) >= limit for template_type, limit in limits.items())


def max_rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB.
    if value > 10_000_000:
        return value / 1024 / 1024
    return value / 1024


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Marvel pages from MediaWiki XML.")
    parser.add_argument("--xml", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0, help="Matching page limit; 0 means all.")
    parser.add_argument(
        "--max-pages-scanned",
        type=int,
        default=0,
        help="Stop after scanning this many pages; 0 means no scan cap.",
    )
    parser.add_argument(
        "--templates",
        default="character,comic",
        help="Comma-separated template families: character,comic,volume.",
    )
    parser.add_argument(
        "--template-limits",
        default="",
        help="Optional per-template caps, for example character=25,comic=25. Overrides --limit stop logic.",
    )
    args = parser.parse_args()

    wanted_templates = {
        item.strip().casefold() for item in args.templates.split(",") if item.strip()
    }
    template_limits = parse_template_limits(args.template_limits)
    unsupported = wanted_templates - {"character", "comic", "volume"}
    if unsupported:
        raise SystemExit(f"Unsupported templates: {', '.join(sorted(unsupported))}")

    ensure_parent(args.out)
    stats_path = args.out.with_suffix(args.out.suffix + ".stats.json")

    started = time.perf_counter()
    scanned = 0
    matched = 0
    by_template: dict[str, int] = {name: 0 for name in sorted(wanted_templates)}

    with args.out.open("w", encoding="utf-8") as f:
        context = ET.iterparse(args.xml, events=("end",))
        for _, elem in context:
            if local_name(elem.tag) != "page":
                continue
            scanned += 1
            record = page_to_record(elem, wanted_templates)
            if record and within_template_limits(record["template_types"], by_template, template_limits):
                matched += 1
                for template_type in record["template_types"]:
                    if not template_limits or by_template.get(template_type, 0) < template_limits.get(template_type, 0):
                        by_template[template_type] = by_template.get(template_type, 0) + 1
                f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            elem.clear()

            if template_limits and template_limits_satisfied(by_template, template_limits):
                break
            if not template_limits and args.limit and matched >= args.limit:
                break
            if args.max_pages_scanned and scanned >= args.max_pages_scanned:
                break

    elapsed = time.perf_counter() - started
    stats = {
        "xml": str(args.xml),
        "out": str(args.out),
        "templates": sorted(wanted_templates),
        "template_limits": template_limits,
        "pages_scanned": scanned,
        "pages_matched": matched,
        "matched_by_template": by_template,
        "elapsed_seconds": elapsed,
        "max_rss_mb": max_rss_mb(),
    }
    stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
