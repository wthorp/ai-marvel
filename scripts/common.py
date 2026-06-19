from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Iterator


TEMPLATE_PATTERNS: dict[str, re.Pattern[str]] = {
    "character": re.compile(
        r"\{\{\s*Marvel\s+Database\s*:\s*Character\s+Template", re.IGNORECASE
    ),
    "comic": re.compile(
        r"\{\{\s*Marvel\s+Database\s*:\s*Comic\s+Template", re.IGNORECASE
    ),
    "volume": re.compile(
        r"\{\{\s*Marvel\s+Database\s*:\s*Volume\s+Template", re.IGNORECASE
    ),
}


LINK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
REF_BLOCK_RE = re.compile(r"<ref\b[^>/]*?>.*?</ref>", re.IGNORECASE | re.DOTALL)
REF_SELF_RE = re.compile(r"<ref\b[^>]*/\s*>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
LINK_TEMPLATE_NAMES = {
    "1st",
    "1st unnamed",
    "a",
    "apn",
    "m",
    "cl",
    "mentioned",
    "sl",
    "sld",
    "power",
    "ability",
}
NOISE_ENTITY_PREFIXES = (
    "category:",
    "file:",
    "image:",
    "help:",
    "template:",
)
SECTION_HEADING_LABELS = {
    "antagonists",
    "featured characters",
    "items",
    "locations",
    "notes",
    "other characters",
    "races and species",
    "realities",
    "supporting characters",
    "vehicles",
}


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    ensure_parent(path)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def stable_id(*parts: Any, prefix: str | None = None) -> str:
    raw = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}" if prefix else digest


def text_sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_answer(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = html.unescape(text)
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def is_noise_entity_name(text: str) -> bool:
    normalized = normalize_answer(text).rstrip(":")
    if not normalized:
        return True
    if normalized in SECTION_HEADING_LABELS:
        return True
    if normalized.startswith(NOISE_ENTITY_PREFIXES):
        return True
    if "category:" in normalized:
        return True
    if normalized.startswith("character index/"):
        return True
    return False


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def detect_templates(text: str) -> list[str]:
    return [name for name, pattern in TEMPLATE_PATTERNS.items() if pattern.search(text)]


def find_template_bounds(text: str, template_type: str) -> tuple[int, int] | None:
    pattern = TEMPLATE_PATTERNS[template_type]
    match = pattern.search(text)
    if not match:
        return None

    start = match.start()
    depth = 0
    i = start
    while i < len(text) - 1:
        pair = text[i : i + 2]
        if pair == "{{":
            depth += 1
            i += 2
            continue
        if pair == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return start, i
            continue
        i += 1
    return None


def split_top_level_pipes(template_content: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    template_depth = 0
    link_depth = 0
    i = 0

    while i < len(template_content):
        pair = template_content[i : i + 2]
        if pair == "{{":
            template_depth += 1
            buf.append(pair)
            i += 2
            continue
        if pair == "}}" and template_depth > 0:
            template_depth -= 1
            buf.append(pair)
            i += 2
            continue
        if pair == "[[":
            link_depth += 1
            buf.append(pair)
            i += 2
            continue
        if pair == "]]" and link_depth > 0:
            link_depth -= 1
            buf.append(pair)
            i += 2
            continue
        if (
            template_content[i] == "|"
            and template_depth == 0
            and link_depth == 0
        ):
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(template_content[i])
        i += 1

    parts.append("".join(buf))
    return parts


def iter_balanced_templates(text: str) -> Iterator[tuple[int, int, str]]:
    i = 0
    while i < len(text) - 1:
        if text[i : i + 2] != "{{":
            i += 1
            continue
        start = i
        depth = 0
        while i < len(text) - 1:
            pair = text[i : i + 2]
            if pair == "{{":
                depth += 1
                i += 2
                continue
            if pair == "}}":
                depth -= 1
                i += 2
                if depth == 0:
                    yield start, i, text[start + 2 : i - 2]
                    break
                continue
            i += 1
        else:
            return


def parse_template_fields(text: str, template_type: str) -> dict[str, str]:
    bounds = find_template_bounds(text, template_type)
    if not bounds:
        return {}

    start, end = bounds
    content = text[start + 2 : end - 2]
    parts = split_top_level_pipes(content)
    fields: dict[str, str] = {}

    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = normalize_space(key)
        value = value.strip()
        if not key:
            continue
        if key in fields and value:
            fields[key] = f"{fields[key]}\n{value}"
        else:
            fields[key] = value
    return fields


def strip_refs(text: str) -> str:
    text = COMMENT_RE.sub(" ", text)
    text = REF_BLOCK_RE.sub(" ", text)
    text = REF_SELF_RE.sub(" ", text)
    return text


def template_link_from_content(content: str) -> dict[str, str] | None:
    parts = split_top_level_pipes(content)
    if len(parts) < 2:
        return None
    name = normalize_space(parts[0]).casefold()
    if name not in LINK_TEMPLATE_NAMES:
        return None
    inner_links = extract_wikilinks(parts[1])
    if inner_links:
        target = inner_links[0]["target"]
        label = inner_links[0]["label"]
    else:
        target = clean_wikitext_value(parts[1])
        label = clean_wikitext_value(parts[2]) if len(parts) > 2 else target
        if label in {"-", "?", "N/A"}:
            label = target
    if is_noise_entity_name(target) or is_noise_entity_name(label):
        return None
    return {"target": target, "label": label or target}


def replace_link_templates(text: str) -> str:
    out: list[str] = []
    cursor = 0
    for start, end, content in iter_balanced_templates(text):
        out.append(text[cursor:start])
        link = template_link_from_content(content)
        if link:
            out.append(link["label"])
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def replace_wikilink(match: re.Match[str]) -> str:
    inner = match.group(1)
    if "|" in inner:
        return inner.split("|")[-1].strip()
    return inner.split("#", 1)[0].strip()


def strip_balanced_templates(text: str) -> str:
    out: list[str] = []
    depth = 0
    i = 0
    while i < len(text):
        pair = text[i : i + 2]
        if pair == "{{":
            depth += 1
            i += 2
            continue
        if pair == "}}" and depth > 0:
            depth -= 1
            i += 2
            continue
        if depth == 0:
            out.append(text[i])
        i += 1
    return "".join(out)


def clean_wikitext_value(value: str) -> str:
    value = html.unescape(strip_refs(value))
    value = LINK_RE.sub(replace_wikilink, value)
    value = replace_link_templates(value)
    value = strip_balanced_templates(value)
    value = TAG_RE.sub(" ", value)
    value = value.replace("'''", "").replace("''", "")
    value = value.replace("&nbsp;", " ")
    value = value.replace("[[", "").replace("]]", "")
    return normalize_space(value)


def parse_wikilink(inner: str) -> dict[str, str] | None:
    parts = [part.strip() for part in inner.split("|")]
    target = parts[0].split("#", 1)[0].strip()
    label = parts[-1].strip() if len(parts) > 1 else target
    if is_noise_entity_name(target) or is_noise_entity_name(label):
        return None
    return {"target": target, "label": label or target}


def extract_wikilinks(value: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in LINK_RE.finditer(strip_refs(value)):
        item = parse_wikilink(match.group(1))
        if not item:
            continue
        key = normalize_answer(item["target"])
        if key in seen:
            continue
        seen.add(key)
        links.append(item)
    return links


def extract_template_links(value: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, _, content in iter_balanced_templates(strip_refs(value)):
        item = template_link_from_content(content)
        if not item:
            continue
        key = normalize_answer(item["target"])
        if key in seen:
            continue
        seen.add(key)
        links.append(item)
    return links


def extract_entity_links(value: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in extract_wikilinks(value) + extract_template_links(value):
        key = normalize_answer(item["target"])
        if key in seen:
            continue
        seen.add(key)
        links.append(item)
    return links


def split_wiki_items(value: str) -> list[str]:
    value = re.sub(r"<br\s*/?>", "\n", strip_refs(value), flags=re.IGNORECASE)
    value = value.replace("\r", "\n")
    items: list[str] = []
    for line in value.split("\n"):
        line = re.sub(r"^[*#:;]+\s*", "", line.strip())
        if not line:
            continue
        cleaned = clean_wikitext_value(line)
        if cleaned and not is_noise_entity_name(cleaned):
            items.append(cleaned)
    return list(dict.fromkeys(items))


def safe_filename(title: str, suffix: str = ".txt") -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")
    slug = slug[:160] or stable_id(title)
    return f"{slug}{suffix}"
