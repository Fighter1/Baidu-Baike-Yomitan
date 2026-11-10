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

from .cleaning import (SAME_ARTICLE, clean_text, clean_title, short_summary_keep_reason, similarity,
                       summary_drop_reason, title_drop_reason, trim_summary)
from .records import Record, RecordWriter

SOURCE = "hf"
_ITEM_ID_RE = re.compile(r"/item/[^/]+/(\d+)/?$")
_URL_RESERVED_RE = re.compile(r'[%#?/\s"<>\\]')
MAX_DESCRIPTOR_CHARS = 60  # per sense of a sense-list page
_LONE_CJK_RE = re.compile(r"(?<!\S)[一-鿿](?!\S)")
_CJK_RE = re.compile(r"[一-鿿]")
_HEADING_RE = re.compile(r"^\s*(?P<title>.{1,40}?)(?:编辑播报|播报编辑|编辑语音|编辑|播报)\s+")


def decode_url(url: str | None) -> str:
    """Percent-decode the path so the link is readable and short, but leave
    the characters that mean something in a URL encoded: /item/C%23/195147
    must not become /item/C#/195147, which is the page for C."""
    if not url:
        return ""
    parts = urllib.parse.urlsplit(url)
    path = "/".join(_URL_RESERVED_RE.sub(lambda m: "%%%02X" % ord(m.group()), urllib.parse.unquote(seg))
                    for seg in parts.path.split("/"))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def lemma_id_from_item_url(url: str | None) -> int | None:
    """Trailing numeric id of https://baike.baidu.com/item/<title>/<id>."""
    if not url:
        return None
    path = urllib.parse.urlsplit(url).path
    m = _ITEM_ID_RE.search(path)
    return int(m.group(1)) if m else None


def title_from_url(url: str | None) -> str:
    m = re.match(r"/item/([^/]+)", urllib.parse.urlsplit(url or "").path)
    return clean_title(urllib.parse.unquote(m.group(1))) if m else ""


def is_obfuscated(text: str) -> bool:
    """2024 snapshots spread text as 'X X X X' and mix in junk characters.

    Judged by the share of Chinese characters that stand alone between
    spaces. Across the overlay that share is either near 1 (garbled pages) or
    under 0.2, so a run of four spaced characters by itself proves nothing: a
    table header or a list of names (子 璨 玮 琮, 金 木 水 火 土) has one too."""
    if not text:
        return False
    cjk = len(_CJK_RE.findall(text))
    if cjk < 8:
        return False
    lone = len(_LONE_CJK_RE.findall(text))
    return lone / cjk > 0.3


def is_disambiguation(text: str, title: str) -> bool:
    """Pages listing senses as '<title>：<descriptor> <title>：<descriptor> …'.

    Every part has to be a short descriptor and at least two must differ. An
    article whose abstract opens with '<title>：' has the same shape at first
    sight, because the overlay repeats the abstract before the body, but its
    parts are the abstract twice and the second one runs on into the body."""
    t = text.strip()
    if not t or "：" not in t or not title:
        return False
    parts = [p.strip() for p in re.split(r"\s+(?=" + re.escape(title) + r"：)", t) if p.strip()]
    if len(parts) < 2 or not all(p.startswith(title + "：") for p in parts):
        return False
    longest = len(title) + 1 + MAX_DESCRIPTOR_CHARS
    return len(set(parts)) >= 2 and all(len(p) <= longest for p in parts)


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
    title = clean_title(row.get("title")) or title_from_url(row.get("base_url"))
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
    summary = clean_text(abstract, title)
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
    subtitle = clean_title(row.get("subtitle"))
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
    """Lower = better: cleanest first, then one that has a subtitle, then newest."""
    f = rec.quality_flags
    score = (2 if "obfuscated" in f else 0) + (1 if "abstract_fallback" in f else 0)
    return (score, 0 if rec.sense_label else 1, -(int((rec.snapshot_date or "0000-00-00").replace("-", ""))))


def _fold(a: Record, b: Record) -> Record:
    """Two snapshots of one article: keep the better, with whatever the other
    knows that it lacks (article id, subtitle, having been reached id-less)."""
    keep, other = (a, b) if _quality(a) <= _quality(b) else (b, a)
    if keep.lemma_id is None and other.lemma_id is not None:
        keep.lemma_id, keep.url = other.lemma_id, other.url
    if not keep.sense_label and other.sense_label:
        keep.sense_label = other.sense_label
    keep._idless = getattr(keep, "_idless", False) or getattr(other, "_idless", False)  # type: ignore[attr-defined]
    return keep


def assign_default_senses(records: list[Record]) -> None:
    """is_default_sense is True for the sense that the id-less URL
    /item/<title> showed, False for the title's other senses, and None for
    every sense of a title that was never captured through that URL.

    Having no subtitle, or being the only sense captured, says nothing about
    which sense is the main one: /item/时间/58293344 is a film song without a
    subtitle, and treating it as the default put it above the word."""
    by_title: dict[str, list[Record]] = collections.defaultdict(list)
    for rec in records:
        by_title[rec.title].append(rec)
    for senses in by_title.values():
        default = next((r for r in senses if getattr(r, "_idless", False)), None)
        for r in senses:
            r.is_default_sense = (r is default) if default is not None else None


def _same_article(rec: Record, candidates: list[Record], title: str) -> Record | None:
    """The candidate that is the same article as an id-less snapshot: equal
    subtitle, or summaries that are mostly the same text."""
    if rec.sense_label:
        for o in candidates:
            if o.sense_label == rec.sense_label:
                return o
    sig = _summary_signature(rec.summary)
    best, best_score = None, SAME_ARTICLE
    for o in candidates:
        if _summary_signature(o.summary) == sig:
            return o
        score = similarity(rec.summary, o.summary, title)
        if score >= best_score:
            best, best_score = o, score
    return best


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
        # One article = one id. Snapshots without an id can only be told
        # apart by title and subtitle. (Keying everything on title and
        # subtitle folded different articles into one: 亨利五世 the king and
        # 亨利五世 the play have different ids and no subtitle.)
        key = rec.lemma_id if rec.lemma_id is not None else (rec.title, rec.sense_label)
        cur = best.get(key)
        if cur is None:
            best[key] = rec
        else:
            stats["dup:lemma_id" if rec.lemma_id is not None else "dup:title_subtitle"] += 1
            best[key] = _fold(rec, cur)
        if progress_every and n % progress_every == 0:
            print(f"  [hf] {n:,} rows, {len(best):,} unique senses, {time.time()-t0:,.0f}s",
                  file=sys.stderr, flush=True)
    # Second pass: a snapshot taken through the id-less URL shows one of the
    # title's articles, namely its default sense. Fold it into the article
    # with an id that has the same subtitle or the same text; that article is
    # then known to be the default.
    groups: dict[str, list[Record]] = collections.defaultdict(list)
    for rec in best.values():
        groups[rec.title].append(rec)
    keep_list: list[Record] = []
    for title, senses in groups.items():
        with_id = [r for r in senses if r.lemma_id is not None]
        for r in senses:
            if r.lemma_id is not None:
                continue
            match = _same_article(r, with_id, title)
            if match is None:
                keep_list.append(r)
                continue
            stats["dup:idless_same_summary"] += 1
            folded = _fold(r, match)
            folded._idless = True  # type: ignore[attr-defined]
            with_id[with_id.index(match)] = folded
        keep_list.extend(with_id)
    written: list[Record] = []
    for rec in keep_list:
        if "obfuscated" in rec.quality_flags:
            stats["drop:obfuscated_no_clean_duplicate"] += 1
        else:
            written.append(rec)
    assign_default_senses(written)
    with RecordWriter(out_path) as w:
        for rec in written:
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
