#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import clean_wikitext_value, iter_jsonl, parse_template_fields, safe_filename


def page_record_text(page: dict) -> str:
    title = page["title"]
    types = page.get("template_types", [])
    lines = [f"TITLE: {title}", f"TEMPLATE_TYPES: {', '.join(types)}", ""]
    for template_type in types:
        fields = parse_template_fields(page["text"], template_type)
        if not fields:
            continue
        lines.append(f"[{template_type.upper()} TEMPLATE FIELDS]")
        for key, value in sorted(fields.items()):
            clean = clean_wikitext_value(value)
            if clean:
                lines.append(f"{key}: {clean}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare cleaned text shards for Hyper-Extract.")
    parser.add_argument("--pages", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for idx, page in enumerate(iter_jsonl(args.pages), start=1):
        if args.limit and idx > args.limit:
            break
        filename = safe_filename(page["title"])
        path = args.out_dir / filename
        path.write_text(page_record_text(page), encoding="utf-8")
        manifest.append({"title": page["title"], "path": str(path), "template_types": page.get("template_types", [])})

    manifest_path = args.out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(manifest), "manifest": str(manifest_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

