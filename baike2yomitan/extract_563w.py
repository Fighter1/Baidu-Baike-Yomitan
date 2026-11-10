"""Extractor for the lars1234/baidu-baike-dataset 563w_baidubaike.json file
(JSON Lines; one object per line with title/summary/sections/tags/url)."""
from __future__ import annotations

import collections
import hashlib
import re
import sys
import time
from typing import Iterator, NamedTuple

from .cleaning import (MIN_SUMMARY_CHARS, clean_text, clean_title, continues_on_next_line, definition_value,
                       first_paragraph, has_tone_marks, is_summary_candidate, join_lines, pinyin_line_value,
                       says_nothing, short_summary_keep_reason, summary_drop_reason, title_drop_reason, trim_summary)
from .readings import stated_pinyins
from .records import Record, RecordWriter, loads
from .sense import is_descriptor

SOURCE = "563w"
_VIEW_ID_RE = re.compile(r"/view/(\d+)\.htm")
_INFOBOX_TITLES = {"基本信息", "基本资料"}
_KV_RE = re.compile(r"^\s*([^：:\s]{1,12})\s*[：:]\s*(.+?)\s*$")
_PARA_SPLIT_RE = re.compile(r"\\n|\n|\r")
MAX_FALLBACK_PARAGRAPHS = 40
MAX_JOINED_LINES = 3  # lines added to a paragraph that a line break split mid-sentence


class Fallback(NamedTuple):
    text: str
    is_first: bool      # the first paragraph of the page
    joined: bool        # put back together from lines broken in mid-sentence
    definition: bool    # the value of a 解释：/释义： line


def iter_paragraphs(sections: list, title: str | None = None) -> Iterator[tuple[str, bool]]:
    """Cleaned, non-empty paragraphs of all sections in page order, each with
    whether it was put back together from lines broken in mid-sentence.

    Only a line that could serve as a summary by itself is extended, so the
    join never changes which paragraph is chosen. Joining short fragments as
    well turned stubs such as (2) 〔嗫～〕见“ / (3) 嗫”。 into summaries."""
    for sec in sections or []:
        lines = [p for p in (clean_text(x, title) for x in _PARA_SPLIT_RE.split(sec.get("content") or "")) if p]
        i = 0
        while i < len(lines):
            para, used = lines[i], 1
            extend = is_summary_candidate(para) or definition_value(para) is not None
            while (extend and used <= MAX_JOINED_LINES and i + used < len(lines)
                   and continues_on_next_line(para, lines[i + used])):
                para = join_lines(para, lines[i + used])
                used += 1
            yield para, used > 1
            i += used


def find_fallback_summary(sections: list, title: str | None = None) -> Fallback | None:
    """First paragraph of any section that can serve as a summary.

    Pages without a summary field usually open with an infobox section
    (基本信息 / 图书信息 / 重要参数) whose lines are 'key：value' pairs, or with a
    pinyin line; the real description sits a paragraph or a section later.
    A line whose key says it is the definition (解释：…, 【释义】…) is taken
    for its value, even a short one: on dictionary-style pages the next long
    paragraph is a source citation. A qualifying paragraph that a line break
    split inside a quote or bracket is joined to its continuation. Returns
    None when nothing qualifies within the first MAX_FALLBACK_PARAGRAPHS
    paragraphs."""
    for i, (p, joined) in enumerate(iter_paragraphs(sections, title)):
        if i >= MAX_FALLBACK_PARAGRAPHS:
            break
        value = definition_value(p)
        if value is not None and not (title and says_nothing(value, title)):
            return Fallback(value, i == 0, joined, True)
        if is_summary_candidate(p, title):
            return Fallback(p, i == 0, joined, False)
    return None


def find_short_fallback(sections: list, title: str) -> tuple[str, str, bool] | None:
    """When no paragraph is long enough: the first one anywhere on the page
    that the under-15-character keep rules accept (远祖: 【词目】远祖 on the first
    line, 许多代以前的祖先。 further down). Returns (text, keep reason,
    is_first_paragraph)."""
    for i, (p, _joined) in enumerate(iter_paragraphs(sections, title)):
        if i >= MAX_FALLBACK_PARAGRAPHS:
            break
        keep = short_summary_keep_reason(p, title)
        if keep:
            return p, keep, i == 0
    return None


_PINYIN_KEYS = ("拼音", "读音", "注音", "发音")


def page_pinyin(summary_src: str | None, sections: list, title: str) -> str | None:
    """The pronunciation a page states for its title outside the chosen
    summary: in a summary field that was set aside, or on a 【拼音】 line of
    the sections. Dictionary-style pages put it on a line of its own, and now
    that the summary is the definition (被褐藏辉: 解释：…), that line would be
    lost and the reading left to a guess (bèi instead of pī)."""
    if summary_src:
        value = pinyin_line_value(clean_text(summary_src, title), title)
        if value:
            return value
    for i, (p, _joined) in enumerate(iter_paragraphs(sections, title)):
        if i >= MAX_FALLBACK_PARAGRAPHS:
            break
        value = pinyin_line_value(p, title)
        if value:
            return value
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


INFOBOX_MAX_POSITION = 1    # the first or the second section of the page


def _infobox_pairs(sec: dict) -> list | None:
    pairs = []
    for line in re.split(r"\\n|\n", sec.get("content") or ""):
        m = _KV_RE.match(line)
        if m:
            pairs.append([m.group(1), clean_text(m.group(2))])
    return pairs[:6] if len(pairs) >= 2 else None


def find_infobox(sections: list) -> tuple[list | None, bool]:
    """(first six key：value pairs of the page's 基本信息/基本资料 section,
    whether such a table was passed over for sitting further down the page).

    The table is taken when its section opens the page or comes second, after
    an introduction. A row of this corpus can hold several articles one after
    the other: the 2019 page for 余华 is the writer's article followed by that
    of a rower of the same name, and other rows end with the sections of an
    unrelated page. Further down, the table belongs to another article than
    the summary more often than not (张衡 with a film's table, 提拉米苏 with a
    housing estate's), and nothing in the row says which.

    Of a table that is passed over, the 拼音/读音 rows are returned: convert()
    keeps those that read the title, see reads_title()."""
    for i, sec in enumerate(sections or []):
        if (sec.get("title") or "").strip() in _INFOBOX_TITLES:
            pairs = _infobox_pairs(sec)
            if pairs is not None and i > INFOBOX_MAX_POSITION:
                return [p for p in pairs if any(k in p[0] for k in _PINYIN_KEYS)] or None, True
            return pairs, False
    return None, False


def parse_infobox(sections: list) -> list | None:
    return find_infobox(sections)[0]


def reads_title(title: str, row: list) -> bool:
    """Whether an info table row states a pinyin that fits the title character
    by character. Such a row is right whichever article of the page it stands
    in (淇奥 qí yù, which the guess gets wrong as qí ào); the row of an
    unrelated page does not fit (拼音名：Baihua Huoxue Dieda Gao under 日本财团)."""
    try:
        return bool(stated_pinyins({"title": title, "infobox": [row]}))
    except ImportError:     # pypinyin is optional, and without it no stated reading is used anyway
        return False


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
    title = clean_title(raw.get("title"))
    reason = title_drop_reason(title)
    if reason:
        stats["drop:" + reason] += 1
        return None
    flags: list[str] = []
    sections = raw.get("sections") or []
    summary_src = raw.get("summary")

    def use(found: Fallback) -> str:
        flags.append("summary_from_section")
        if not found.is_first:
            flags.append("summary_from_later_paragraph")
        if found.joined:
            flags.append("summary_joined_lines")
        if found.definition:
            flags.append("summary_from_definition_line")
        return found.text

    if summary_src is None or not summary_src.strip():
        if not sections:
            stats["drop:no_summary_no_sections"] += 1
            return None
        # No summary field: take the first paragraph of the first section, or,
        # when that is an infobox line / pinyin / heading, the first qualifying
        # paragraph anywhere on the page.
        found = find_fallback_summary(sections, title)
        if found is None:
            flags.append("summary_from_section")
            summary = clean_text(first_paragraph(sections[0].get("content")), title)
            reason = summary_drop_reason(summary) or "summary_not_prose"
        else:
            summary, reason = use(found), None
    else:
        summary = clean_text(summary_src, title)
        value = definition_value(summary)
        if value is not None and len(value) >= MIN_SUMMARY_CHARS:
            summary = value                           # "【解释】：指水止不流…" without its label
        reason = summary_drop_reason(summary)
        empty = not reason and says_nothing(summary, title)
        if empty:
            reason = "summary_not_prose"              # only pinyin, or the title again
        if reason and sections:
            # summary field present but useless: look through the sections
            found = find_fallback_summary(sections, title)
            if found is not None:
                summary = use(found)
                stats["flag:summary_from_section_after_" + ("empty" if empty else "short") + "_summary"] += 1
                reason = None
    if reason:
        # Last resort: a complete short sentence or a 别称 infobox line is
        # better than nothing (剌桐城 → 泉州市的别称。; 不着四六 → 别称：四六不懂),
        # wherever on the page it stands.
        keep = short_summary_keep_reason(summary, title)
        if not keep and sections:
            short = find_short_fallback(sections, title)
            if short is not None:
                summary, keep, is_first = short
                if "summary_from_section" not in flags:
                    flags.append("summary_from_section")
                if not is_first:
                    flags.append("summary_from_later_paragraph")
        if keep:
            flags.append("kept_" + keep)
            reason = None
    if reason:
        stats["drop:" + reason + ("_fallback" if "summary_from_section" in flags else "")] += 1
        return None
    summary = trim_summary(summary, max_summary_chars)
    sense_label = ""
    if sections:
        sec0_title = clean_title(sections[0].get("title")).rstrip("：:")
        if is_descriptor(sec0_title, title):
            sense_label = sec0_title
            stats["flag:sense_label_from_section"] += 1
    lemma_id = lemma_id_from_url(raw.get("url"))
    if lemma_id is None:
        flags.append("no_lemma_id")
    url = f"https://baike.baidu.com/view/{lemma_id}.htm" if lemma_id is not None else None
    tags = [t for t in (raw.get("tags") or []) if isinstance(t, str) and t.strip()]
    infobox, passed_over = find_infobox(sections) if want_infobox else (None, False)
    if passed_over:
        flags.append("infobox_below_top_skipped")
        infobox = [row for row in infobox or [] if reads_title(title, row)] or None
    if (want_infobox and "summary_from_section" in flags and not has_tone_marks(summary)
            and not any(k in str(key) for key, _v in (infobox or []) for k in _PINYIN_KEYS)
            and (has_tone_marks(summary_src) or any(has_tone_marks(s.get("content")) for s in sections))):
        stated = page_pinyin(summary_src, sections, title)
        if stated:
            infobox = (infobox or []) + [["拼音", stated]]
            stats["flag:pinyin_line_kept"] += 1
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
            if lemma_id is not None and lemma_id in seen_ids:
                stats["drop:dup_lemma_id"] += 1
                continue
            rec = convert(raw, stats, max_summary_chars, want_infobox)
            if rec is None:
                continue  # the id stays free: a later row for it may be usable
            if lemma_id is not None:
                seen_ids.add(lemma_id)
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
