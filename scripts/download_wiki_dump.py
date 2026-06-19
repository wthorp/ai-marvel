#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_DBNAME = "enmarveldatabase"
DEFAULT_WIKI_URL = "https://marvel.fandom.com/wiki/Marvel_Database"
DEFAULT_DUMP_URL = (
    "https://s3.amazonaws.com/wikia_xml_dumps/e/en/"
    "enmarveldatabase_pages_current.xml.7z"
)
CHUNK_SIZE = 1024 * 1024


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_url_for_dbname(dbname: str) -> str:
    if len(dbname) < 2:
        raise ValueError("Fandom database name must be at least two characters.")
    return (
        f"https://s3.amazonaws.com/wikia_xml_dumps/"
        f"{dbname[0]}/{dbname[:2]}/{dbname}_pages_current.xml.7z"
    )


def request_headers(path: Path, resume: bool) -> dict[str, str]:
    headers = {"User-Agent": "ai-marvel-benchmark/1.0"}
    if resume and path.exists() and path.stat().st_size > 0:
        headers["Range"] = f"bytes={path.stat().st_size}-"
    return headers


def head(url: str) -> dict[str, str]:
    req = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "ai-marvel-benchmark/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return {key.lower(): value for key, value in resp.headers.items()}


def human_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, out: Path, resume: bool) -> dict[str, Any]:
    ensure_parent(out)
    headers = request_headers(out, resume)
    mode = "ab" if "Range" in headers else "wb"
    local_before = out.stat().st_size if out.exists() else 0
    req = urllib.request.Request(url, headers=headers)

    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and out.exists():
            return {"already_complete": True, "bytes_written": 0, "status": exc.code}
        raise

    status = getattr(resp, "status", None)
    if "Range" in headers and status != 206:
        mode = "wb"
        local_before = 0

    total_header = resp.headers.get("Content-Length")
    download_total = int(total_header) if total_header else None
    expected_total = local_before + download_total if download_total is not None else None

    started = time.perf_counter()
    written = 0
    last_report = 0.0
    with resp, out.open(mode + "") as f:
        while True:
            chunk = resp.read(CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)
            written += len(chunk)
            now = time.perf_counter()
            if now - last_report >= 2:
                current = local_before + written
                print(
                    f"Downloaded {human_bytes(current)}"
                    + (f" / {human_bytes(expected_total)}" if expected_total else ""),
                    file=sys.stderr,
                )
                last_report = now

    return {
        "already_complete": False,
        "status": status,
        "bytes_written": written,
        "local_bytes_before": local_before,
        "local_bytes_after": out.stat().st_size,
        "elapsed_seconds": time.perf_counter() - started,
    }


def find_extractor() -> list[str] | None:
    for cmd in ("7zz", "7z"):
        path = shutil.which(cmd)
        if path:
            return [path, "x"]
    path = shutil.which("bsdtar")
    if path:
        return [path, "-xf"]
    return None


def extract_archive(archive: Path, out_dir: Path, force: bool) -> dict[str, Any]:
    extractor = find_extractor()
    if not extractor:
        raise SystemExit(
            "No extractor found. Install 7-Zip, or rerun without --extract. "
            "Accepted commands: 7zz, 7z, bsdtar."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    if extractor[1] == "x":
        cmd = extractor + [str(archive), f"-o{out_dir}"]
        if force:
            cmd.append("-y")
    else:
        cmd = extractor + [str(archive), "-C", str(out_dir)]
    subprocess.run(cmd, check=True)
    return {
        "command": cmd,
        "elapsed_seconds": time.perf_counter() - started,
        "out_dir": str(out_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the Marvel Database Fandom XML dump.")
    parser.add_argument("--dbname", default=DEFAULT_DBNAME)
    parser.add_argument("--url", default="", help="Override dump URL.")
    parser.add_argument("--out", type=Path, default=Path("data/enmarveldatabase_pages_current.xml.7z"))
    parser.add_argument("--extract", action="store_true", help="Extract the .7z archive after download.")
    parser.add_argument("--extract-dir", type=Path, default=Path("data"))
    parser.add_argument("--force-extract", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--check", action="store_true", help="Only verify remote metadata; do not download.")
    args = parser.parse_args()

    url = args.url or (DEFAULT_DUMP_URL if args.dbname == DEFAULT_DBNAME else dump_url_for_dbname(args.dbname))
    remote = head(url)
    remote_md5 = remote.get("x-amz-meta-md5") or remote.get("etag", "").strip('"')
    metadata: dict[str, Any] = {
        "wiki": DEFAULT_WIKI_URL if args.dbname == DEFAULT_DBNAME else None,
        "dbname": args.dbname,
        "url": url,
        "remote": {
            "content_length": int(remote["content-length"]) if remote.get("content-length") else None,
            "content_type": remote.get("content-type"),
            "last_modified": remote.get("last-modified"),
            "md5": remote_md5,
        },
    }

    if args.check:
        print(json.dumps(metadata, indent=2, sort_keys=True))
        return 0

    result = download(url, args.out, resume=not args.no_resume)
    metadata["download"] = result
    metadata["archive"] = str(args.out)

    if remote_md5 and args.out.exists():
        local_md5 = md5(args.out)
        metadata["archive_md5"] = local_md5
        if local_md5 != remote_md5:
            raise SystemExit(f"MD5 mismatch: local {local_md5}, remote {remote_md5}")

    if args.extract:
        metadata["extract"] = extract_archive(args.out, args.extract_dir, args.force_extract)

    metadata_path = args.out.with_suffix(args.out.suffix + ".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

