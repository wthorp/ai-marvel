# Blog Outline

## Working Title

Can a LoRA memorize a Marvel wiki dump? I compared it with local RAG and a local knowledge graph.

## Claim

Fine-tuning should not be treated as a database. For exact factual recall over a changing corpus, retrieval and graph extraction should be more accurate, easier to update, and easier to audit.

## Article Shape

1. Set up the problem.
   - The dump is about 1.9 GB and contains more than 1.5 million MediaWiki pages.
   - The target is closed-book exact factual recall, not style transfer or summarization.

2. Explain the three local systems.
   - Plain vector RAG: chunk, embed, retrieve, answer.
   - Hyper-Extract: convert cleaned records into a typed Marvel graph.
   - LoRA/QLoRA: train on deterministic QA pairs and answer without retrieval.

3. Explain why preprocessing matters.
   - Raw XML is not the right input for any of the systems.
   - Marvel pages contain structured templates, wiki links, and appearance-specific templates.
   - The benchmark uses deterministic parsing to create the shared fact and QA substrate.
   - The dump comes from Marvel Database on Fandom, using the current-pages XML dump linked from Fandom's database-download system.

4. Report timed preprocessing.
   - XML scan and page extraction.
   - Template parsing and fact projection.
   - Hyper-Extract shard preparation.
   - LoRA SFT split preparation.

5. Run the staged comparison.
   - 50 mixed pages.
   - 1,000 mixed pages.
   - 10,000 mixed pages.
   - Larger runs only if prior stages are informative.

6. Compare results.
   - Exact match.
   - Answer rate.
   - Latency.
   - GPU memory and wall time.
   - Disk footprint.
   - Provenance.
   - Update cost when facts change.

7. Discuss failure modes.
   - LoRA forgets rare facts and invents plausible facts.
   - RAG can retrieve the wrong chunk or fail on multi-hop questions.
   - Graph extraction can miss or over-type messy relation fields.
   - Deterministic preprocessing is strong for structured templates but weaker for narrative history sections.

8. Conclusion.
   - Use LoRA for behavior, format, and domain language.
   - Use RAG or a graph for exact facts.
   - Use Hyper-Extract when the graph itself is the product, or when provenance and typed relations matter.

## Metrics Tables To Fill

| Stage | Pages | Wall Time | Peak RAM | Peak VRAM | Output Rows | Disk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| XML extraction |  |  |  |  |  |  |
| Fact projection |  |  |  |  |  |  |
| RAG index |  |  |  |  |  |  |
| Hyper-Extract parse |  |  |  |  |  |  |
| LoRA SFT prep |  |  |  |  |  |  |
| QLoRA train |  |  |  |  |  |  |

| System | Exact Match | Answer Rate | Median Latency | Provenance | Update Cost |
| --- | ---: | ---: | ---: | --- | --- |
| Vector RAG |  |  |  | chunks | re-embed changed pages |
| Hyper-Extract graph |  |  |  | typed source facts | re-extract changed pages |
| Closed-book LoRA |  |  |  | none | regenerate data and retrain/merge adapter |

## References To Cite

- Hyper-Extract local provider guide: `../hyper-extract/docs/en/concepts/provider-system.md`
- Hyper-Extract graph template syntax: `../hyper-extract/hyperextract/templates/README.md`
- Fandom database download help: https://community.fandom.com/wiki/Help:Database_download
- Gemma model docs: https://ai.google.dev/gemma/docs/core
- Gemma QLoRA guide: https://ai.google.dev/gemma/docs/core/huggingface_text_finetune_qlora
- Neo4j LLM Graph Builder: https://github.com/neo4j-labs/llm-graph-builder
- GLiNER: https://github.com/urchade/GLiNER
- REBEL paper: https://aclanthology.org/2021.findings-emnlp.204/
