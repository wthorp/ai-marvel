# Runbook

Run commands from `marvel-experiment/`.

## Download The Wiki Dump

Check the remote dump metadata without downloading:

```bash
python3 scripts/download_wiki_dump.py --check
```

Download and extract the current-pages dump:

```bash
python3 scripts/download_wiki_dump.py --extract
```

The script downloads the Marvel Database Fandom current-pages archive from:

```text
https://s3.amazonaws.com/wikia_xml_dumps/e/en/enmarveldatabase_pages_current.xml.7z
```

Fandom documents database downloads on each wiki's `Special:Statistics` page. The archive is `.7z`, so extraction requires `7zz`, `7z`, or `bsdtar`.

## Smoke Run

Balanced character/comic extraction:

```bash
python3 scripts/run_timed.py \
  --name extract_mixed_smoke \
  --log-dir runs/mixed-smoke/timing \
  -- python3 scripts/extract_pages.py \
    --xml data/enmarveldatabase_pages_current.xml \
    --out runs/mixed-smoke/pages.jsonl \
    --templates character,comic \
    --template-limits character=25,comic=25
```

Project graph facts and deterministic QA:

```bash
python3 scripts/run_timed.py \
  --name facts_mixed_smoke \
  --log-dir runs/mixed-smoke/timing \
  -- python3 scripts/project_facts.py \
    --pages runs/mixed-smoke/pages.jsonl \
    --out-dir runs/mixed-smoke/facts \
    --qa-per-page 12
```

Prepare Hyper-Extract input:

```bash
python3 scripts/run_timed.py \
  --name hyperextract_inputs_mixed_smoke \
  --log-dir runs/mixed-smoke/timing \
  -- python3 scripts/hyperextract/prepare_inputs.py \
    --pages runs/mixed-smoke/pages.jsonl \
    --out-dir runs/mixed-smoke/hyperextract-inputs
```

Prepare LoRA SFT splits:

```bash
python3 scripts/run_timed.py \
  --name lora_sft_mixed_smoke \
  --log-dir runs/mixed-smoke/timing \
  -- python3 scripts/lora/prepare_sft.py \
    --qa runs/mixed-smoke/facts/qa.jsonl \
    --out-dir runs/mixed-smoke/lora-sft
```

## Scale Runs

For same-shape larger samples, increase the per-template caps:

```bash
python3 scripts/run_timed.py \
  --name extract_1k_balanced \
  --log-dir runs/1k-balanced/timing \
  -- python3 scripts/extract_pages.py \
    --xml data/enmarveldatabase_pages_current.xml \
    --out runs/1k-balanced/pages.jsonl \
    --templates character,comic \
    --template-limits character=500,comic=500
```

Use the same projection, Hyper-Extract prep, and LoRA prep commands with the run directory changed.

## Plain Vector RAG

Install the optional RAG dependencies in the local inference environment:

```bash
python3 -m pip install -r requirements-rag.txt
```

Build the index:

```bash
python3 scripts/run_timed.py \
  --name rag_index_1k \
  --log-dir runs/1k-balanced/timing \
  -- python3 scripts/rag/build_vector_index.py \
    --pages runs/1k-balanced/pages.jsonl \
    --out-dir runs/1k-balanced/rag-index \
    --model BAAI/bge-m3
```

## Hyper-Extract

Hyper-Extract expects local OpenAI-compatible services for its verified local path. Use the upstream provider guide for exact vLLM commands.

Example parse command after local LLM and embedding endpoints are running:

```bash
cd ../hyper-extract
uv run he parse ../marvel-experiment/runs/1k-balanced/hyperextract-inputs \
  --output ../marvel-experiment/runs/1k-balanced/hyperextract-ka \
  --template ../marvel-experiment/templates/marvel_graph.yaml \
  --lang en
```

## QLoRA

Install training dependencies in the RTX 3090 environment:

```bash
python3 -m pip install -r requirements-lora.txt
```

Train an adapter:

```bash
python3 scripts/run_timed.py \
  --name qlora_1k \
  --log-dir runs/1k-balanced/timing \
  -- python3 scripts/lora/train_qlora.py \
    --model /path/or/hf-id/of/base-model \
    --train runs/1k-balanced/lora-sft/train.jsonl \
    --eval runs/1k-balanced/lora-sft/eval.jsonl \
    --output-dir runs/1k-balanced/lora-adapter \
    --batch-size 2 \
    --grad-accum 8 \
    --epochs 1
```

For the first GPU run, prefer a smaller Gemma 4 or Qwen instruction model before trying a larger model. The goal is to establish the memorization curve before spending full-run time.

## Scoring

System predictions should be JSONL with:

```json
{"id": "qa_...", "answer": "exact answer text"}
```

Score them:

```bash
python3 scripts/score_answers.py \
  --qa runs/1k-balanced/facts/qa.jsonl \
  --predictions runs/1k-balanced/system-name/predictions.jsonl \
  --out runs/1k-balanced/system-name/scores.json
```
