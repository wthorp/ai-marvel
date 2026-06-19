# Marvel Local Fact Recall Experiment

This folder contains the benchmark harness for comparing:

- plain local vector RAG,
- local Hyper-Extract graph extraction,
- closed-book LoRA or QLoRA fine-tuning.

Download the raw dump:

```bash
python3 scripts/download_wiki_dump.py --extract
```

This writes:

```bash
data/enmarveldatabase_pages_current.xml.7z
data/enmarveldatabase_pages_current.xml
```

Run a balanced smoke sample:

```bash
python3 scripts/run_timed.py \
  --name extract_mixed_smoke \
  --log-dir runs/mixed-smoke/timing \
  -- python3 scripts/extract_pages.py \
    --xml data/enmarveldatabase_pages_current.xml \
    --out runs/mixed-smoke/pages.jsonl \
    --templates character,comic \
    --template-limits character=25,comic=25

python3 scripts/run_timed.py \
  --name facts_mixed_smoke \
  --log-dir runs/mixed-smoke/timing \
  -- python3 scripts/project_facts.py \
    --pages runs/mixed-smoke/pages.jsonl \
    --out-dir runs/mixed-smoke/facts \
    --qa-per-page 12
```

The shared benchmark substrate lands in:

- `pages.jsonl`: filtered raw pages.
- `facts/entities.jsonl`: projected graph nodes.
- `facts/attributes.jsonl`: scalar facts.
- `facts/relationships.jsonl`: graph edges.
- `facts/qa.jsonl`: deterministic exact-recall questions.

See `PLAN.md`, `RUNBOOK.md`, and `docs/blog-outline.md` for the full experiment shape.
