#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import iter_jsonl, stable_id


def chunk_text(text: str, chunk_chars: int, overlap_chars: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    text = text.strip()
    while start < len(text):
        end = min(len(text), start + chunk_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local FAISS vector index from extracted pages.")
    parser.add_argument("--pages", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--model", default="BAAI/bge-m3")
    parser.add_argument("--chunk-chars", type=int, default=1600)
    parser.add_argument("--overlap-chars", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    try:
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            "Missing RAG dependencies. Install faiss-cpu, numpy, and sentence-transformers."
        ) from exc

    args.out_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = args.out_dir / "chunks.jsonl"
    chunks = []
    with chunks_path.open("w", encoding="utf-8") as f:
        for page in iter_jsonl(args.pages):
            for idx, chunk in enumerate(chunk_text(page["text"], args.chunk_chars, args.overlap_chars)):
                row = {
                    "chunk_id": stable_id(page["title"], idx, chunk[:80], prefix="chunk"),
                    "title": page["title"],
                    "chunk_index": idx,
                    "text": chunk,
                }
                chunks.append(row)
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    model = SentenceTransformer(args.model)
    vectors = model.encode(
        [row["text"] for row in chunks],
        batch_size=args.batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    vectors = np.asarray(vectors, dtype="float32")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(args.out_dir / "index.faiss"))

    manifest = {
        "pages": str(args.pages),
        "model": args.model,
        "chunks": len(chunks),
        "index": str(args.out_dir / "index.faiss"),
        "chunks_path": str(chunks_path),
        "dimension": int(vectors.shape[1]),
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

