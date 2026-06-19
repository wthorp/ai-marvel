#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import resource
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from common import (
    clean_wikitext_value,
    extract_entity_links,
    iter_jsonl,
    normalize_answer,
    parse_template_fields,
    split_wiki_items,
    stable_id,
    write_jsonl,
)


CHARACTER_ATTRS = {
    "Name": ("name", "What is the real name listed for {entity}?"),
    "CurrentAlias": ("current_alias", "What is {entity}'s current alias?"),
    "Gender": ("gender", "What gender is listed for {entity}?"),
    "Height": ("height", "What height is listed for {entity}?"),
    "Weight": ("weight", "What weight is listed for {entity}?"),
    "Eyes": ("eyes", "What eye color is listed for {entity}?"),
    "Hair": ("hair", "What hair color is listed for {entity}?"),
    "Origin": ("origin", "What origin is listed for {entity}?"),
    "Identity": ("identity", "What identity status is listed for {entity}?"),
    "Citizenship": ("citizenship", "What citizenship is listed for {entity}?"),
    "Occupation": ("occupation", "What occupation is listed for {entity}?"),
    "Education": ("education", "What education is listed for {entity}?"),
    "MaritalStatus": ("marital_status", "What marital status is listed for {entity}?"),
    "PlaceOfBirth": ("place_of_birth", "Where was {entity} born?"),
    "PlaceOfDeath": ("place_of_death", "Where did {entity} die?"),
    "CauseOfDeath": ("cause_of_death", "What cause of death is listed for {entity}?"),
    "BaseOfOperations": ("base_of_operations", "What base of operations is listed for {entity}?"),
    "Reality": ("reality", "What reality is {entity} from?"),
}


CHARACTER_RELATIONS = {
    "Affiliation": ("member_of", "Organization", "What groups is {source} affiliated with?"),
    "Grandparents": ("grandchild_of", "Character", "Who are {source}'s grandparents?"),
    "Parents": ("child_of", "Character", "Who are {source}'s parents?"),
    "Clones": ("clone_of", "Character", "Who are {source}'s clones?"),
    "Siblings": ("sibling_of", "Character", "Who are {source}'s siblings?"),
    "Spouses": ("spouse_of", "Character", "Who are {source}'s spouses?"),
    "Children": ("parent_of", "Character", "Who are {source}'s children?"),
    "Relatives": ("relative_of", "Character", "Who are {source}'s relatives?"),
    "HostOf": ("host_of", "UnknownEntity", "Who or what has {source} hosted?"),
    "KilledBy": ("killed_by", "Character", "Who killed {source}?"),
    "CasualtyOf": ("casualty_of", "Event", "What event caused {source}'s death?"),
    "Creators": ("created_by", "Creator", "Who created {source}?"),
    "First": ("first_appeared_in", "ComicIssue", "What was the first appearance of {source}?"),
    "Powers": ("has_power", "Power", "What powers are listed for {source}?"),
    "PlaceOfBirth": ("born_in", "Location", "Where was {source} born?"),
    "PlaceOfDeath": ("died_in", "Location", "Where did {source} die?"),
    "BaseOfOperations": ("based_in", "Location", "Where is {source} based?"),
    "Reality": ("from_reality", "Reality", "What reality is {source} from?"),
}


COMIC_ATTRS = {
    "ReleaseDate": ("release_date", "What is the release date of {entity}?"),
    "Month": ("cover_month", "What cover month is listed for {entity}?"),
    "Year": ("cover_year", "What cover year is listed for {entity}?"),
    "StoryTitle1": ("story_title", "What is the story title of {entity}?"),
    "MarvelUnlimitedID": ("marvel_unlimited_id", "What Marvel Unlimited ID is listed for {entity}?"),
}


CREDIT_RELATION_BY_PREFIX = {
    "Writer": ("written_by", "Creator", "Who wrote {source}?"),
    "Penciler": ("penciled_by", "Creator", "Who penciled {source}?"),
    "Inker": ("inked_by", "Creator", "Who inked {source}?"),
    "Colorist": ("colored_by", "Creator", "Who colored {source}?"),
    "Letterer": ("lettered_by", "Creator", "Who lettered {source}?"),
    "Editor": ("edited_by", "Creator", "Who edited {source}?"),
}


def max_rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if value > 10_000_000:
        return value / 1024 / 1024
    return value / 1024


def add_entity(
    entities: dict[str, dict[str, Any]],
    name: str,
    entity_type: str,
    source_title: str,
) -> str:
    name = clean_wikitext_value(name)
    if not name:
        return ""
    entity_id = stable_id(normalize_answer(name), entity_type, prefix="ent")
    existing = entities.get(entity_id)
    if existing:
        existing["source_titles"].add(source_title)
        return entity_id
    entities[entity_id] = {
        "entity_id": entity_id,
        "name": name,
        "type": entity_type,
        "source_titles": {source_title},
    }
    return entity_id


def emit_attribute(
    rows: list[dict[str, Any]],
    entity_id: str,
    entity_name: str,
    attr: str,
    value: str,
    source_title: str,
    field: str,
) -> None:
    clean = clean_wikitext_value(value)
    if not clean or len(clean) > 500:
        return
    rows.append(
        {
            "attribute_id": stable_id(entity_id, attr, clean, field, prefix="attr"),
            "entity_id": entity_id,
            "entity_name": entity_name,
            "attribute": attr,
            "value": clean,
            "source_title": source_title,
            "field": field,
            "evidence": value.strip()[:1200],
        }
    )


def linked_or_split_items(raw: str) -> list[dict[str, str]]:
    links = extract_entity_links(raw)
    if links:
        return links
    return [{"target": item, "label": item} for item in split_wiki_items(raw)]


def emit_relations_from_field(
    rows: list[dict[str, Any]],
    entities: dict[str, dict[str, Any]],
    source_id: str,
    source_name: str,
    raw: str,
    relation: str,
    target_type: str,
    source_title: str,
    field: str,
) -> None:
    for item in linked_or_split_items(raw):
        target_name = item["target"]
        target_id = add_entity(entities, target_name, target_type, source_title)
        if not target_id:
            continue
        rows.append(
            {
                "relationship_id": stable_id(source_id, relation, target_id, field, prefix="rel"),
                "source_id": source_id,
                "source_name": source_name,
                "target_id": target_id,
                "target_name": clean_wikitext_value(target_name),
                "relation": relation,
                "target_type": target_type,
                "source_title": source_title,
                "field": field,
                "evidence": raw.strip()[:1200],
            }
        )


def project_character(page: dict[str, Any], entities: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    title = page["title"]
    fields = parse_template_fields(page["text"], "character")
    entity_id = add_entity(entities, title, "Character", title)
    attributes: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []

    for field, (attr, _) in CHARACTER_ATTRS.items():
        raw = fields.get(field, "")
        if raw:
            emit_attribute(attributes, entity_id, title, attr, raw, title, field)

    aliases = fields.get("Aliases", "") or fields.get("Codenames", "")
    if aliases:
        for item in linked_or_split_items(aliases):
            alias = clean_wikitext_value(item["label"])
            if alias:
                emit_attribute(attributes, entity_id, title, "alias", alias, title, "Aliases")

    for field, (relation, target_type, _) in CHARACTER_RELATIONS.items():
        raw = fields.get(field, "")
        if raw:
            emit_relations_from_field(
                relationships,
                entities,
                entity_id,
                title,
                raw,
                relation,
                target_type,
                title,
                field,
            )

    return attributes, relationships


def credit_relation_for_field(field: str) -> tuple[str, str, str] | None:
    for prefix, spec in CREDIT_RELATION_BY_PREFIX.items():
        if field == prefix or re.match(rf"^{re.escape(prefix)}\d*(?:_\d+)?$", field):
            return spec
    return None


def project_comic(page: dict[str, Any], entities: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    title = page["title"]
    fields = parse_template_fields(page["text"], "comic")
    entity_id = add_entity(entities, title, "ComicIssue", title)
    attributes: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []

    for field, (attr, _) in COMIC_ATTRS.items():
        raw = fields.get(field, "")
        if raw:
            emit_attribute(attributes, entity_id, title, attr, raw, title, field)

    for field, raw in fields.items():
        credit_spec = credit_relation_for_field(field)
        if credit_spec and raw:
            relation, target_type, _ = credit_spec
            emit_relations_from_field(
                relationships,
                entities,
                entity_id,
                title,
                raw,
                relation,
                target_type,
                title,
                field,
            )
        elif re.match(r"^Event\d*$", field) and raw:
            emit_relations_from_field(
                relationships,
                entities,
                entity_id,
                title,
                raw,
                "part_of_event",
                "Event",
                title,
                field,
            )
        elif re.match(r"^Appearing\d*$", field) and raw:
            emit_relations_from_field(
                relationships,
                entities,
                entity_id,
                title,
                raw,
                "features_entity",
                "UnknownEntity",
                title,
                field,
            )

    return attributes, relationships


def question_rows(
    attributes: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    qa_per_page: int,
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    per_page_counts: defaultdict[str, int] = defaultdict(int)

    attr_question_by_attr = {
        value[0]: value[1] for value in CHARACTER_ATTRS.values()
    } | {value[0]: value[1] for value in COMIC_ATTRS.values()}

    for attr in sorted(attributes, key=lambda row: (row["source_title"], row["attribute"], row["value"])):
        source_title = attr["source_title"]
        if qa_per_page and per_page_counts[source_title] >= qa_per_page:
            continue
        template = attr_question_by_attr.get(attr["attribute"])
        if not template:
            continue
        answer = attr["value"]
        questions.append(
            {
                "id": stable_id(attr["attribute_id"], template, prefix="qa"),
                "kind": "attribute",
                "question": template.format(entity=attr["entity_name"]),
                "answers": [answer],
                "normalized_answers": [normalize_answer(answer)],
                "source_title": source_title,
                "field": attr["field"],
                "fact_id": attr["attribute_id"],
            }
        )
        per_page_counts[source_title] += 1

    relation_question_by_relation = {
        value[0]: value[2] for value in CHARACTER_RELATIONS.values()
    } | {value[0]: value[2] for value in CREDIT_RELATION_BY_PREFIX.values()}
    relation_question_by_relation["features_entity"] = "Which entities appear in {source}?"
    relation_question_by_relation["part_of_event"] = "What event is {source} part of?"

    max_answers_per_relation_question = 8
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rel in relationships:
        grouped[(rel["source_id"], rel["relation"])].append(rel)

    for (_, relation), rows in sorted(
        grouped.items(), key=lambda item: (item[1][0]["source_title"], item[0][1])
    ):
        source_title = rows[0]["source_title"]
        if qa_per_page and per_page_counts[source_title] >= qa_per_page:
            continue
        template = relation_question_by_relation.get(relation)
        if not template:
            continue
        answers = sorted({row["target_name"] for row in rows if row["target_name"]})
        if (
            not answers
            or len(answers) > max_answers_per_relation_question
            or sum(len(answer) for answer in answers) > 1000
        ):
            continue
        fields = sorted({row["field"] for row in rows})
        questions.append(
            {
                "id": stable_id(rows[0]["source_id"], relation, "|".join(fields), "|".join(answers), prefix="qa"),
                "kind": "relationship",
                "question": template.format(source=rows[0]["source_name"]),
                "answers": answers,
                "normalized_answers": [normalize_answer(answer) for answer in answers],
                "source_title": source_title,
                "field": ",".join(fields),
                "fact_id": rows[0]["relationship_id"],
            }
        )
        per_page_counts[source_title] += 1

    return questions


def main() -> int:
    parser = argparse.ArgumentParser(description="Project Marvel page templates into graph facts and QA.")
    parser.add_argument("--pages", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--qa-per-page", type=int, default=12)
    args = parser.parse_args()

    started = time.perf_counter()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    entities: dict[str, dict[str, Any]] = {}
    attributes: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    pages_seen = 0
    pages_by_type: defaultdict[str, int] = defaultdict(int)

    for page in iter_jsonl(args.pages):
        pages_seen += 1
        types = set(page.get("template_types", []))
        if "character" in types:
            pages_by_type["character"] += 1
            attrs, rels = project_character(page, entities)
            attributes.extend(attrs)
            relationships.extend(rels)
        elif "comic" in types:
            pages_by_type["comic"] += 1
            attrs, rels = project_comic(page, entities)
            attributes.extend(attrs)
            relationships.extend(rels)

    attributes = list({row["attribute_id"]: row for row in attributes}.values())
    relationships = list({row["relationship_id"]: row for row in relationships}.values())

    entity_rows = []
    for row in entities.values():
        out = dict(row)
        out["source_titles"] = sorted(out["source_titles"])
        entity_rows.append(out)

    qa = question_rows(attributes, relationships, args.qa_per_page)

    counts = {
        "pages_seen": pages_seen,
        "pages_by_type": dict(sorted(pages_by_type.items())),
        "entities": write_jsonl(args.out_dir / "entities.jsonl", sorted(entity_rows, key=lambda row: row["entity_id"])),
        "attributes": write_jsonl(args.out_dir / "attributes.jsonl", attributes),
        "relationships": write_jsonl(args.out_dir / "relationships.jsonl", relationships),
        "qa": write_jsonl(args.out_dir / "qa.jsonl", qa),
        "elapsed_seconds": time.perf_counter() - started,
        "max_rss_mb": max_rss_mb(),
    }
    (args.out_dir / "stats.json").write_text(
        json.dumps(counts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(counts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
