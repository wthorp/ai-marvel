#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import iter_jsonl, normalize_answer


def main() -> int:
    parser = argparse.ArgumentParser(description="Score system predictions against deterministic QA.")
    parser.add_argument("--qa", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True, help="JSONL with id and answer fields.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    qa = {row["id"]: row for row in iter_jsonl(args.qa)}
    preds = {row["id"]: row for row in iter_jsonl(args.predictions)}

    rows = []
    exact = 0
    answered = 0
    for qid, question in qa.items():
        pred = preds.get(qid, {})
        answer = str(pred.get("answer", "")).strip()
        if answer:
            answered += 1
        pred_norm = normalize_answer(answer)
        gold = set(question["normalized_answers"])
        is_exact = pred_norm in gold if len(gold) == 1 else pred_norm == normalize_answer("; ".join(question["answers"]))
        if is_exact:
            exact += 1
        rows.append(
            {
                "id": qid,
                "question": question["question"],
                "gold_answers": question["answers"],
                "prediction": answer,
                "exact": is_exact,
                "source_title": question["source_title"],
                "field": question["field"],
            }
        )

    metrics = {
        "total": len(qa),
        "answered": answered,
        "exact": exact,
        "answer_rate": answered / len(qa) if qa else 0,
        "exact_rate": exact / len(qa) if qa else 0,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"metrics": metrics, "rows": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

