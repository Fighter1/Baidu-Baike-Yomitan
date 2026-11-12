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

from .cleaning import (SAME_ARTICLE, clean_text, clean_title, decode_entities, short_summary_keep_reason, similarity,
                       summary_drop_reason, title_drop_reason, trim_summary)
from .junk import injected, known_headings
from .records import Record, RecordWriter
from .sections import pick_sections

SOURCE = "hf"
_ITEM_ID_RE = re.compile(r"/item/[^/]+/(\d+)/?$")
_URL_RESERVED_RE = re.compile(r'[%#?/\s"<>\\]')
MAX_DESCRIPTOR_CHARS = 60  # per sense of a sense-list page
_LONE_CJK_RE = re.compile(r"(?<!\S)[一-鿿](?!\S)")
_CJK_RE = re.compile(r"[一-鿿]")
_HEADING_RE = re.compile(r"^\s*(?P<title>.{1,40}?)(?:编辑播报|播报编辑|编辑语音|编辑|播报)\s+")
_SECTION_MARK_RE = re.compile(r"播报编辑|编辑播报")       # what follows every section heading of a page
_SENTENCE_END = "。！？；”’）》\\]\\s"
_HEADING_TAIL_RE = re.compile(rf"[{_SENTENCE_END}]([^{_SENTENCE_END}]{{1,14}})$")
MAX_HEADING_CHARS = 24
MIN_FUSED_HEADING_CHARS = 4     # shorter known headings (历史, 简介) also start ordinary sentences
_REPEATED_OPENING_RE = re.compile(r"^(《?[^，。；：！？\s]{3,30}?》?)\1")
_BAD_OPENING = "，。、；：！？）】》”’"
# A page without section marks that opens '释义1、喜欢管闲事的人' or '解释：…': the two characters are a heading.
_FUSED_DEFINING_RE = re.compile(r"^(?:释义|(?:解释|定义|简介)(?=[\d\[（(《“【：:①⒈❶]))[：:]?")
JUNK_WINDOW = 500           # characters of a section that are searched for injected ones
# Headings of a section that says what the article is about: a definition ...
_DEFINING_HEADING_RE = re.compile(r"(?:解释|释义|定义|含义|涵义|词义|概念|意思)$")
# ... or an introduction, unless it introduces somebody else (the author of a book, the cast of a film).
_INTRO_HEADING_RE = re.compile(r"(?:简介|介绍|概述|概况|简述|概要)$")
_INTRO_OF_OTHERS_RE = re.compile(r"^(?:作者|编者|译者|主编|导演|演员|主演|嘉宾|角色|主创|团队|成员|选手|出品|制作)")


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


def unspace(content: str) -> str | None:
    """'解 释 播 报 编 辑 五 岳 ：   指 东 岳' -> '解释播报编辑五岳： 指东岳'.

    The 2023-24 snapshots put a space after every character, a space of the
    text included, so the text is every other character. None when the
    content is not laid out like that throughout."""
    if not content or not content[1::2].strip() == "":
        return None
    return content[::2]


def is_intro_heading(heading: str) -> bool:
    """A section heading under which the article says what its subject is."""
    if _DEFINING_HEADING_RE.search(heading):
        return True
    return bool(_INTRO_HEADING_RE.search(heading)) and not _INTRO_OF_OTHERS_RE.match(heading)


def spaced_opening(plain: str, title: str = "") -> str | None:
    """The text that introduces the subject of an un-spaced 2023-24 page, or
    None when the page has none.

    These snapshots lack the abstract that the earlier ones start with: the
    text begins at the first section, each section as '<heading>播报编辑<text>'
    with nothing between the text of one and the heading of the next. So the
    text is taken from the first section whose heading promises an
    introduction (解释, 定义, 简介, 内容简介 ...). What a page says under
    演艺经历 or 历史沿革 does not tell what the thing is. A page without
    section headings is its own introduction, unless it opens with a heading
    that the pages with sections use for something else (歌曲歌词, 所获荣誉)."""
    marks = list(_SECTION_MARK_RE.finditer(plain))
    if not marks:
        text = plain.lstrip()
        for size in range(min(8, len(text)), MIN_FUSED_HEADING_CHARS - 1, -1):
            if text[:size] in known_headings():
                return _opening_text(text[size:], title) if is_intro_heading(text[:size]) else None
        if not title.startswith(text[:2]):
            text = _FUSED_DEFINING_RE.sub("", text)
        return _opening_text(text, title)
    heading = plain[:marks[0].start()].strip()
    if len(heading) > MAX_HEADING_CHARS:
        m = _HEADING_TAIL_RE.search(heading)        # the page opens with text of its own: that is the introduction
        return _opening_text(heading[:m.start() + 1], title) if m else None
    for heading, body in spaced_sections(plain):
        if is_intro_heading(heading):
            return _opening_text(body, title)
    return None


def spaced_sections(plain: str) -> list[tuple[str, str]]:
    """(heading, text) of each section of an un-spaced 2023-24 page.

    Nothing separates the text of a section from the heading of the next, so
    that heading is what follows the last sentence end before the next mark
    (…景观之胜。 [1] 出处播报编辑徐霞客的…)."""
    marks = list(_SECTION_MARK_RE.finditer(plain))
    if not marks:
        return []
    heading = plain[:marks[0].start()].strip()
    if len(heading) > MAX_HEADING_CHARS:
        m = _HEADING_TAIL_RE.search(heading)
        heading = m.group(1).strip() if m else ""
    out = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(plain)
        body, next_heading = plain[mark.end():end], ""
        if i + 1 < len(marks):
            m = _HEADING_TAIL_RE.search(body)
            if m:
                body, next_heading = body[:m.start() + 1], m.group(1)
        out.append((heading, body))
        heading = next_heading.strip()
    return out


_PAGE_HEADING_MARK = r"(?:编辑播报|播报编辑|编辑语音|语音编辑|编辑)(?=\s)"


def page_sections(content: str, title: str) -> list[tuple[str, str]]:
    """(heading, text) of each top-level section of an ordinary snapshot.

    After the abstract and its repeat, every section starts with the article
    title and the heading run together, then the interface's edit label:
    '  春暖花开成语出处编辑 明·朱国祯《涌幢小品·南内》：…'. The headings of a
    lower level (踏歌基本解释 without the label) stay in the text."""
    if not content or not title:
        return []
    starts = list(re.finditer(r"(?:^|(?<=\s))" + re.escape(title) + r"(?P<heading>\S{1,20}?)" + _PAGE_HEADING_MARK, content))
    out = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(content)
        out.append((m.group("heading"), content[m.end():end]))
    return out


def _opening_text(text: str, title: str) -> str | None:
    """The text of an introduction without the picture caption that repeats
    its first words (灯挂椅灯挂椅是靠背椅的一种款式); None when it starts in
    the middle of a sentence."""
    text = text.lstrip()
    if title and text.startswith(title + title):
        text = text[len(title):]
    else:
        m = _REPEATED_OPENING_RE.match(text)
        if m:
            text = text[m.end(1):]
    if not text or text[0] in _BAD_OPENING:
        return None
    return text


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


def _has_injected(text: str) -> bool:
    return bool(injected(text[:JUNK_WINDOW]))


def convert(row: dict, stats: collections.Counter, max_summary_chars: int,
            want_sections: bool = True) -> Record | None:
    title = clean_title(decode_entities(row.get("title"))) or title_from_url(row.get("base_url"))
    reason = title_drop_reason(title)
    if reason:
        stats["drop:" + reason] += 1
        return None
    content = decode_entities(row.get("content") or "")
    flags = []
    recovered = plain = None
    if is_obfuscated(content):
        # A letter-spaced snapshot. Its text can be put back together, but it
        # is kept only when it has an introduction and no injected characters.
        plain = decode_entities(unspace(content))
        recovered = spaced_opening(plain, title) if plain is not None else None
        if plain is None:
            stats["spaced:not_every_other_character"] += 1
        elif recovered is None:
            stats["spaced:no_introduction"] += 1
        elif injected(recovered[:JUNK_WINDOW]):
            stats["spaced:injected_characters"] += 1
            recovered = None
        if recovered is None:
            flags.append("obfuscated")
        else:
            flags += ["unspaced", "abstract_fallback"]
    if is_disambiguation(content, title):
        stats["drop:disambiguation_page"] += 1
        return None
    abstract = recovered if recovered is not None else split_repeated_abstract(content)
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
    subtitle = clean_title(decode_entities(row.get("subtitle")))
    if subtitle == title:
        subtitle = ""
    word_sections = None
    if want_sections and "obfuscated" not in flags:
        # the 2023 snapshots have injected characters in the body text too, letter-spaced or not
        pairs = spaced_sections(plain) if recovered is not None else page_sections(content, title)
        word_sections = pick_sections(pairs, title, summary, refuse=_has_injected)
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
        sections=word_sections,
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
    score = (4 if "obfuscated" in f else 0) + (1 if "abstract_fallback" in f else 0) + (1 if "unspaced" in f else 0)
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
            max_summary_chars: int = 300, progress_every: int = 100_000,
            want_sections: bool = True) -> collections.Counter:
    stats: collections.Counter = collections.Counter()
    t0 = time.time()
    best: dict[tuple, Record] = {}
    for n, row in enumerate(iter_rows(path), 1):
        if limit and n > limit:
            break
        stats["input_rows"] += 1
        rec = convert(row, stats, max_summary_chars, want_sections)
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
    # A page recovered from a letter-spaced snapshot is the first section of
    # an article, not its abstract. It is used for a title that nothing else
    # covers; next to an ordinary snapshot of the title it would be the same
    # article a second time, in worse words.
    covered = {rec.title for rec in keep_list if not {"obfuscated", "unspaced"} & set(rec.quality_flags)}
    written: list[Record] = []
    for rec in keep_list:
        if "obfuscated" in rec.quality_flags:
            stats["drop:obfuscated_no_clean_duplicate"] += 1
        elif "unspaced" in rec.quality_flags and rec.title in covered:
            stats["drop:unspaced_title_has_other_snapshot"] += 1
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
            for label, _text in rec.sections or []:
                stats["section:" + label] += 1
            stats["records_with_sections"] += bool(rec.sections)
            w.write(rec)
        stats["records_written"] = w.count
    stats["seconds"] = int(time.time() - t0)
    return stats
