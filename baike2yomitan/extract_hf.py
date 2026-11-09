"""Extractor for the mohamedah/baidu_baike overlay (Internet Archive
snapshots 2020-2024, parquet shards on refs/convert/parquet)."""
from __future__ import annotations

import collections
import glob
import os
import re
import sys
import time
import urllib.parse
from typing import Iterator

from .cleaning import (clean_text, short_summary_keep_reason,
                       summary_drop_reason, title_drop_reason, trim_summary)
from .records import Record, RecordWriter

SOURCE = "hf"
_ITEM_ID_RE = re.compile(r"/item/[^/]+/(\d+)/?$")
_OBFUSC_RE = re.compile(r"(?:[一-鿿] ){4,}")
_LONE_CJK_RE = re.compile(r"(?<!\S)[一-鿿](?!\S)")
_CJK_RE = re.compile(r"[一-鿿]")
_HEADING_RE = re.compile(r"^\s*(?P<title>.{1,40}?)(?:编辑播报|播报编辑|编辑语音|编辑|播报)\s+")


def decode_url(url: str | None) -> str:
    return urllib.parse.unquote(url or "")


def lemma_id_from_item_url(url: str | None) -> int | None:
    """Trailing numeric id of https://baike.baidu.com/item/<title>/<id>."""
    if not url:
        return None
    path = urllib.parse.urlsplit(url).path
    m = _ITEM_ID_RE.search(path)
    return int(m.group(1)) if m else None


def title_from_url(url: str | None) -> str:
    path = decode_url(urllib.parse.urlsplit(url or "").path)
    m = re.match(r"/item/([^/]+)", path)
    return clean_text(m.group(1)) if m else ""


def is_obfuscated(text: str) -> bool:
    """2024 snapshots spread text as 'X X X X' and mix in junk characters."""
    if not text:
        return False
    if _OBFUSC_RE.search(text):
        return True
    cjk = len(_CJK_RE.findall(text))
    if cjk < 20:
        return False
    lone = len(_LONE_CJK_RE.findall(text))
    return lone / cjk > 0.3


def is_disambiguation(text: str, title: str) -> bool:
    """Pages listing senses as '<title>：<descriptor> <title>：<descriptor> …'."""
    t = text.strip()
    if not t or "：" not in t or not title:
        return False
    parts = [p for p in re.split(r"\s+(?=" + re.escape(title) + r"：)", t) if p]
    return len(parts) >= 2 and all(p.startswith(title + "：") for p in parts)


def split_repeated_abstract(content: str) -> str | None:
    """The overlay content starts with the abstract and then repeats it (the
    repeat differs only in whitespace) before the body.  Return the abstract
    (first copy, original spelling) or None when no repeat is found."""
    if not content:
        return None
    # Work on a whitespace-free copy, then map the cut back to the original.
    stripped_chars = []
    orig_index = []
    for i, ch in enumerate(content):
        if not ch.isspace() and ch != " ":
            stripped_chars.append(ch)
            orig_index.append(i)
    n = "".join(stripped_chars)
    if len(n) < 16:
        return None
    half = len(n) // 2
    for anchor in (8, 12, 20, 32):
        if anchor > half:
            break
        probe = n[:anchor]
        j = n.find(probe, anchor)
        tries = 0
        while j != -1 and j <= half and tries < 50:
            if n[j:2 * j] == n[:j]:
                return content[: orig_index[j - 1] + 1].strip()
            j = n.find(probe, j + 1)
            tries += 1
    return None


def fallback_abstract(content: str, title: str, max_chars: int = 400) -> str:
    """No repeated abstract: drop a leading '<title><heading>编辑播报' token,
    then take text up to the first blank-line/section separator (two spaces)
    or ~max_chars."""
    text = content.replace(" ", " ").strip()
    m = _HEADING_RE.match(text)
    if m and (title in m.group("title") or len(m.group("title")) <= 12):
        text = text[m.end():]
    cut = len(text)
    for sep in ("\n\n", "\n", "  "):
        i = text.find(sep)
        if 0 < i < cut:
            cut = i
    text = text[:cut]
    return text[:max_chars]


def iter_rows(path: str) -> Iterator[dict]:
    """Stream rows from a parquet file or a directory of parquet shards."""
    import pyarrow.parquet as pq

    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "**", "*.parquet"), recursive=True))
    else:
        files = [path]
    if not files:
        raise FileNotFoundError(f"no parquet files under {path}")
    for fp in files:
        pf = pq.ParquetFile(fp)
        for rg in range(pf.metadata.num_row_groups):
            for row in pf.read_row_group(rg).to_pylist():
                yield row


def snapshot_date(ts) -> str | None:
    s = str(ts or "")
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return None


def convert(row: dict, stats: collections.Counter, max_summary_chars: int) -> Record | None:
    title = clean_text(row.get("title")) or title_from_url(row.get("base_url"))
    reason = title_drop_reason(title)
    if reason:
        stats["drop:" + reason] += 1
        return None
    content = row.get("content") or ""
    flags = ["obfuscated"] if is_obfuscated(content) else []
    if is_disambiguation(content, title):
        stats["drop:disambiguation_page"] += 1
        return None
    abstract = split_repeated_abstract(content)
    if abstract is None:
        abstract = fallback_abstract(content, title)
        flags.append("abstract_fallback")
    summary = clean_text(abstract)
    if "obfuscated" not in flags:
        reason = summary_drop_reason(summary)
        if reason:
            keep = short_summary_keep_reason(summary, title)
            if keep:
                flags.append("kept_" + keep)
            else:
                stats["drop:" + reason + ("_fallback" if "abstract_fallback" in flags else "")] += 1
                return None
    summary = trim_summary(summary, max_summary_chars)
    base_url = row.get("base_url") or row.get("url") or ""
    lemma_id = lemma_id_from_item_url(base_url)
    subtitle = clean_text(row.get("subtitle")) or ""
    if subtitle == title:
        subtitle = ""
    rec = Record(
        source=SOURCE,
        title=title,
        sense_label=subtitle,
        lemma_id=lemma_id,
        is_default_sense=None,
        summary=summary,
        tags=[],
        url=decode_url(base_url),
        archive_url=row.get("archive_url"),
        snapshot_date=snapshot_date(row.get("timestamp")),
        quality_flags=flags,
        infobox=None,
    )
    # transient marker used for default-sense detection; not serialised
    rec._idless = lemma_id is None  # type: ignore[attr-defined]
    return rec


_SIG_STRIP_RE = re.compile(r"[\s\W_]+")


def _summary_signature(summary: str) -> str:
    return _SIG_STRIP_RE.sub("", summary or "")[:20]


def _quality(rec: Record) -> tuple:
    """Lower = better: cleanest first, newest second."""
    f = rec.quality_flags
    score = (2 if "obfuscated" in f else 0) + (1 if "abstract_fallback" in f else 0)
    return (score, -(int((rec.snapshot_date or "0000-00-00").replace("-", ""))))


def assign_default_senses(records: list[Record]) -> None:
    """is_default_sense: the sense reached by an id-less URL, else the sense
    with no subtitle, else the only sense; otherwise False for all."""
    by_title: dict[str, list[Record]] = collections.defaultdict(list)
    for rec in records:
        by_title[rec.title].append(rec)
    for senses in by_title.values():
        idless = [r for r in senses if getattr(r, "_idless", False)]
        nosub = [r for r in senses if not r.sense_label]
        if idless:
            default = idless[0]
        elif nosub:
            default = nosub[0]
        elif len(senses) == 1:
            default = senses[0]
        else:
            default = None
        for r in senses:
            r.is_default_sense = (r is default) if default is not None else False


def extract(path: str, out_path: str, limit: int | None = None,
            max_summary_chars: int = 300, progress_every: int = 100_000) -> collections.Counter:
    stats: collections.Counter = collections.Counter()
    t0 = time.time()
    best: dict[tuple, Record] = {}
    for n, row in enumerate(iter_rows(path), 1):
        if limit and n > limit:
            break
        stats["input_rows"] += 1
        rec = convert(row, stats, max_summary_chars)
        if rec is None:
            continue
        key = (rec.title, rec.sense_label)
        cur = best.get(key)
        if cur is None:
            best[key] = rec
        else:
            stats["dup:title_subtitle"] += 1
            keep, other = (rec, cur) if _quality(rec) < _quality(cur) else (cur, rec)
            if keep.lemma_id is None and other.lemma_id is not None:
                keep.lemma_id = other.lemma_id
                keep.url = other.url
            keep._idless = keep._idless or other._idless  # type: ignore[attr-defined]
            best[key] = keep
        if progress_every and n % progress_every == 0:
            print(f"  [hf] {n:,} rows, {len(best):,} unique senses, {time.time()-t0:,.0f}s",
                  file=sys.stderr, flush=True)
    # Secondary dedupe: snapshots of one lemma_id taken before/after Baike
    # added subtitles produce (title, "") and (title, subtitle) pairs for the
    # same page.  Keep the one with a subtitle, then the cleanest/newest.
    by_lemma: dict[int, Record] = {}
    keep_list: list[Record] = []
    for rec in best.values():
        if rec.lemma_id is None:
            keep_list.append(rec)
            continue
        cur = by_lemma.get(rec.lemma_id)
        if cur is None:
            by_lemma[rec.lemma_id] = rec
            continue
        stats["dup:lemma_id"] += 1
        better = rec if (bool(rec.sense_label), -_quality(rec)[0], -_quality(rec)[1]) > \
            (bool(cur.sense_label), -_quality(cur)[0], -_quality(cur)[1]) else cur
        other = cur if better is rec else rec
        better._idless = getattr(better, "_idless", False) or getattr(other, "_idless", False)  # type: ignore[attr-defined]
        by_lemma[rec.lemma_id] = better
    keep_list.extend(by_lemma.values())
    # Tertiary dedupe: an id-less, subtitle-less snapshot whose abstract matches
    # another sense of the same title is that sense's default-sense page.
    groups: dict[str, list[Record]] = collections.defaultdict(list)
    for rec in keep_list:
        groups[rec.title].append(rec)
    drop_ids: set[int] = set()
    for senses in groups.values():
        if len(senses) < 2:
            continue
        for r in senses:
            if r.lemma_id is None and not r.sense_label:
                sig = _summary_signature(r.summary)
                match = next((o for o in senses if o is not r and o.lemma_id is not None
                              and _summary_signature(o.summary) == sig), None)
                if match is not None:
                    match._idless = True  # type: ignore[attr-defined]
                    drop_ids.add(id(r))
                    stats["dup:idless_same_summary"] += 1
    keep_list = [r for r in keep_list if id(r) not in drop_ids]
    assign_default_senses(keep_list)
    with RecordWriter(out_path) as w:
        for rec in keep_list:
            if "obfuscated" in rec.quality_flags:
                stats["drop:obfuscated_no_clean_duplicate"] += 1
                continue
            for f in rec.quality_flags:
                stats["flag:" + f] += 1
            if rec.lemma_id is None:
                stats["flag:no_lemma_id"] += 1
            if rec.is_default_sense:
                stats["default_senses"] += 1
            w.write(rec)
        stats["records_written"] = w.count
    stats["seconds"] = int(time.time() - t0)
    return stats
