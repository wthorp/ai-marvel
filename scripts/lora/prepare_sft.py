#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import iter_jsonl, stable_id


SYSTEM_PROMPT = (
    "Answer the Marvel factual question exactly. "
    "Use only the fact learned during training. "
    "If multiple answers are required, separate them with semicolons."
)


def split_name(qid: str, eval_fraction: float, test_fraction: float) -> str:
    bucket = int(stable_id(qid), 16) % 10_000 / 10_000
    if bucket < test_fraction:
        return "test"
    if bucket < test_fraction + eval_fraction:
        return "eval"
    return "train"


def to_sft_row(row: dict) -> dict:
    answer = "; ".join(row["answers"])
    return {
        "id": row["id"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": row["question"]},
            {"role": "assistant", "content": answer},
        ],
        "source_title": row["source_title"],
        "field": row["field"],
        "answers": row["answers"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare LoRA/QLoRA SFT splits from deterministic QA.")
    parser.add_argument("--qa", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--eval-fraction", type=float, default=0.05)
    parser.add_argument("--test-fraction", type=float, default=0.10)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    handles = {
        split: (args.out_dir / f"{split}.jsonl").open("w", encoding="utf-8")
        for split in ("train", "eval", "test")
    }
    counts = {split: 0 for split in handles}
    try:
        for row in iter_jsonl(args.qa):
            split = split_name(row["id"], args.eval_fraction, args.test_fraction)
            handles[split].write(json.dumps(to_sft_row(row), ensure_ascii=False, sort_keys=True) + "\n")
            counts[split] += 1
    finally:
        for handle in handles.values():
            handle.close()

    manifest = {
        "qa": str(args.qa),
        "out_dir": str(args.out_dir),
        "counts": counts,
        "system_prompt": SYSTEM_PROMPT,
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

