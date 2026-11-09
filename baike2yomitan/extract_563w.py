"""Extractor for the lars1234/baidu-baike-dataset 563w_baidubaike.json file
(JSON Lines; one object per line with title/summary/sections/tags/url)."""
from __future__ import annotations

import collections
import hashlib
import re
import sys
import time
from typing import Iterator

from .cleaning import (clean_text, first_paragraph, is_summary_candidate,
                       short_summary_keep_reason, summary_drop_reason,
                       title_drop_reason, trim_summary)
from .records import Record, RecordWriter, loads
from .sense import is_descriptor

SOURCE = "563w"
_VIEW_ID_RE = re.compile(r"/view/(\d+)\.htm")
_INFOBOX_TITLES = {"基本信息", "基本资料"}
_KV_RE = re.compile(r"^\s*([^：:\s]{1,12})\s*[：:]\s*(.+?)\s*$")
_PARA_SPLIT_RE = re.compile(r"\\n|\n|\r")
MAX_FALLBACK_PARAGRAPHS = 40


def iter_paragraphs(sections: list) -> Iterator[str]:
    """Cleaned, non-empty paragraphs of all sections in page order."""
    for sec in sections or []:
        for para in _PARA_SPLIT_RE.split(sec.get("content") or ""):
            p = clean_text(para)
            if p:
                yield p


def find_fallback_summary(sections: list) -> tuple[str, bool] | None:
    """First paragraph of any section that can serve as a summary.

    Pages without a summary field usually open with an infobox section
    (基本信息 / 图书信息 / 重要参数) whose lines are 'key：value' pairs, or with a
    pinyin line; the real description sits a paragraph or a section later.
    Returns (paragraph, is_first_paragraph) or None when nothing qualifies
    within the first MAX_FALLBACK_PARAGRAPHS paragraphs."""
    for i, p in enumerate(iter_paragraphs(sections)):
        if i >= MAX_FALLBACK_PARAGRAPHS:
            break
        if is_summary_candidate(p):
            return p, i == 0
    return None


def lemma_id_from_url(url: str | None) -> int | None:
    """Integer id from http://baike.baidu.com/view/<id>.htm, zero padding
    stripped (view/0010.htm and view/10.htm are the same lemma)."""
    if not url:
        return None
    m = _VIEW_ID_RE.search(url)
    if not m:
        return None
    return int(m.group(1))


def summary_hash(title: str, summary: str) -> int:
    h = hashlib.blake2b((title + "\x00" + summary).encode("utf-8"), digest_size=8)
    return int.from_bytes(h.digest(), "big")


def parse_infobox(sections: list) -> list | None:
    """First six key：value pairs of a 基本信息/基本资料 section, if the section
    body is made of such lines."""
    for sec in sections or []:
        if (sec.get("title") or "").strip() in _INFOBOX_TITLES:
            pairs = []
            for line in re.split(r"\\n|\n", sec.get("content") or ""):
                m = _KV_RE.match(line)
                if m:
                    pairs.append([m.group(1), clean_text(m.group(2))])
            if len(pairs) >= 2:
                return pairs[:6]
            return None
    return None


def detect_layout(path: str) -> str:
    """'jsonl' or 'array', decided from the first non-whitespace byte."""
    with open(path, "rb") as f:
        head = f.read(4096).lstrip()
    return "array" if head.startswith(b"[") else "jsonl"


def iter_raw(path: str) -> Iterator[dict]:
    layout = detect_layout(path)
    if layout == "jsonl":
        with open(path, "rb") as f:
            for line in f:
                if line.strip():
                    yield loads(line)
    else:  # JSON array: stream with ijson
        import ijson

        with open(path, "rb") as f:
            yield from ijson.items(f, "item")


def convert(raw: dict, stats: collections.Counter, max_summary_chars: int,
            want_infobox: bool) -> Record | None:
    """Turn one raw 563w object into a Record, or None (drop; reason counted)."""
    title = clean_text(raw.get("title"))
    reason = title_drop_reason(title)
    if reason:
        stats["drop:" + reason] += 1
        return None
    flags: list[str] = []
    sections = raw.get("sections") or []
    summary_src = raw.get("summary")
    if summary_src is None or not summary_src.strip():
        if not sections:
            stats["drop:no_summary_no_sections"] += 1
            return None
        # No summary field: take the first paragraph of the first section, or,
        # when that is an infobox line / pinyin / heading, the first qualifying
        # paragraph anywhere on the page.
        flags.append("summary_from_section")
        found = find_fallback_summary(sections)
        if found is None:
            summary = clean_text(first_paragraph(sections[0].get("content")))
            reason = summary_drop_reason(summary) or "summary_not_prose"
        else:
            summary, is_first = found
            reason = None
            if not is_first:
                flags.append("summary_from_later_paragraph")
    else:
        summary = clean_text(summary_src)
        reason = summary_drop_reason(summary)
        if reason and sections:
            # summary field present but useless (pinyin only, title repeated,
            # "key：value" line): look through the sections before dropping
            found = find_fallback_summary(sections)
            if found is not None:
                summary, reason = found[0], None
                flags.append("summary_from_section")
                if not found[1]:
                    flags.append("summary_from_later_paragraph")
                stats["flag:summary_from_section_after_short_summary"] += 1
    if reason:
        # Last resort: a complete short sentence or a 别称 infobox line is
        # better than nothing (剌桐城 → 泉州市的别称。; 不着四六 → 别称：四六不懂)
        keep = short_summary_keep_reason(summary, title)
        if keep:
            flags.append("kept_" + keep)
            reason = None
    if reason:
        stats["drop:" + reason + ("_fallback" if "summary_from_section" in flags else "")] += 1
        return None
    summary = trim_summary(summary, max_summary_chars)
    sense_label = ""
    if sections:
        sec0_title = clean_text(sections[0].get("title"))
        if is_descriptor(sec0_title, title):
            sense_label = sec0_title
            stats["flag:sense_label_from_section"] += 1
    lemma_id = lemma_id_from_url(raw.get("url"))
    if lemma_id is None:
        flags.append("no_lemma_id")
    url = f"https://baike.baidu.com/view/{lemma_id}.htm" if lemma_id is not None else None
    tags = [t for t in (raw.get("tags") or []) if isinstance(t, str) and t.strip()]
    infobox = parse_infobox(sections) if want_infobox else None
    for f in flags:
        stats["flag:" + f] += 1
    return Record(
        source=SOURCE,
        title=title,
        sense_label=sense_label,
        lemma_id=lemma_id,
        is_default_sense=None,
        summary=summary,
        tags=tags,
        url=url,
        archive_url=None,
        snapshot_date=None,
        quality_flags=flags,
        infobox=infobox,
    )


def extract(path: str, out_path: str, limit: int | None = None,
            max_summary_chars: int = 300, want_infobox: bool = True,
            progress_every: int = 200_000) -> collections.Counter:
    stats: collections.Counter = collections.Counter()
    stats["layout:" + detect_layout(path)] += 1
    seen_ids: set[int] = set()
    seen_hashes: set[int] = set()
    t0 = time.time()
    with RecordWriter(out_path) as w:
        for n, raw in enumerate(iter_raw(path), 1):
            if limit and n > limit:
                break
            stats["input_rows"] += 1
            lemma_id = lemma_id_from_url(raw.get("url"))
            if lemma_id is not None:
                if lemma_id in seen_ids:
                    stats["drop:dup_lemma_id"] += 1
                    continue
                seen_ids.add(lemma_id)
            rec = convert(raw, stats, max_summary_chars, want_infobox)
            if rec is None:
                continue
            h = summary_hash(rec.title, rec.summary)
            if h in seen_hashes:
                stats["drop:dup_title_summary"] += 1
                continue
            seen_hashes.add(h)
            w.write(rec)
            if progress_every and n % progress_every == 0:
                print(f"  [563w] {n:,} rows, {w.count:,} records, {time.time()-t0:,.0f}s",
                      file=sys.stderr, flush=True)
        stats["records_written"] = w.count
    stats["seconds"] = int(time.time() - t0)
    return stats
