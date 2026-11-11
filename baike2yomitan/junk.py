"""Characters that Baidu Baike injects into article text, and how to tell a
passage that has them.

The pages archived in 2023 and 2024 hide random Chinese characters in their
body text, two to six at a time (``在长欢台沙召开`` for 在长沙召开). A
browser does not show them; a scraper gets them. They come from a pool of a
few hundred characters, most of them ordinary (旬 葛 誉 篮 才 体), so no single
character proves anything. Two things do:

- Chinese characters inside a Latin word or a year (``Wor去乌ld``,
  ``201验旬请9年``);
- two pool characters side by side that the 2019 corpus, which has no such
  junk, never has side by side (``颈遥``, ``榆煮``). Injected pairs are random,
  and only a quarter of the possible pairs occur in real text.

The pool and the pairs of real text are learned from the corpora by ``learn``
and kept in ``spaced_snapshots.txt`` next to this file, together with the
section headings of those pages (see extract_hf.spaced_opening).

    python -m baike2yomitan.junk [OVERLAY_DIR] [RECORDS_563W]    # learn again
"""
from __future__ import annotations

import collections
import functools
import os
import re
import sys

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spaced_snapshots.txt")
MIN_POOL_COUNT = 20        # times a character must be seen injected to count as one of the pool
MIN_PAIR_COUNT = 2         # times the 2019 text must have a pair for it to be real
MIN_HEADING_COUNT = 5      # sections a heading must open to be a known heading

_CJK = "一-鿿"
_IN_WORD_RE = re.compile(rf"(?<=[a-z])([{_CJK}]{{2,6}})(?=[a-z])")
_IN_YEAR_RE = re.compile(rf"(?<![\d.])(?:19|20)(?!世纪)([{_CJK}]{{2,6}})(?=\d\d年)")
_CJK_RE = re.compile(f"[{_CJK}]")
_SUMMARY_RE = re.compile(r'"summary":"((?:[^"\\]|\\.)*)"')
_HEADING_SHAPE_RE = re.compile(f"[{_CJK}]{{2,8}}")


@functools.lru_cache(maxsize=1)
def _data() -> tuple[re.Pattern, frozenset, frozenset]:
    """(finder of two adjacent pool characters, pairs of real text, known headings)."""
    fields = {}
    with open(DATA_PATH, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or "\t" not in line:
                continue
            key, value = line.rstrip("\n").split("\t", 1)
            fields[key] = value
    pool = fields["pool"]
    return (re.compile(f"(?=([{pool}][{pool}]))"), frozenset(fields["pairs"].split(" ")),
            frozenset(fields["headings"].split(" ")))


def known_headings() -> frozenset:
    """Headings that at least MIN_HEADING_COUNT sections of the 2023-24 pages have."""
    return _data()[2]


def injected(text: str) -> str:
    """What gives injected characters away in the text, or '' when nothing
    does: ``inside_word`` or the first pair of pool characters that real text
    does not have. On the junk-free 2019 summaries it finds something in 0.4%."""
    if _IN_WORD_RE.search(text) or _IN_YEAR_RE.search(text):
        return "inside_word"
    finder, real, _headings = _data()
    for m in finder.finditer(text):
        pair = m.group(1)
        if pair[0] != pair[1] and pair not in real:
            return pair
    return ""


# --------------------------------------------------------------------- learning

def _section_headings(plain: str):
    """The heading of every section of an un-spaced page (see extract_hf.spaced_opening)."""
    from .extract_hf import MAX_HEADING_CHARS, _HEADING_TAIL_RE, _SECTION_MARK_RE
    start = 0
    for i, mark in enumerate(_SECTION_MARK_RE.finditer(plain)):
        before = plain[start:mark.start()]
        if i == 0 and len(before.strip()) <= MAX_HEADING_CHARS:
            yield before.strip()
        else:
            m = _HEADING_TAIL_RE.search(before)
            if m:
                yield m.group(1).strip()
        start = mark.end()


def _spaced_pages(overlay_dir: str):
    from .extract_hf import is_obfuscated, iter_rows, unspace
    for row in iter_rows(overlay_dir):
        content = row.get("content") or ""
        if is_obfuscated(content):
            plain = unspace(content)
            if plain:
                yield plain


def _summaries(records_path: str, every: int = 1):
    import json
    with open(records_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i % every:
                continue
            m = _SUMMARY_RE.search(line)
            if m:
                yield json.loads('"' + m.group(1) + '"')


def learn(overlay_dir: str, records_path: str, out_path: str = DATA_PATH, log=print) -> dict:
    """Learn the pool, the pairs of real text and the headings, and write them.

    The pool is read off the places where a Chinese character can only have
    been injected: inside Latin words and years. Ordinary text gets there too
    (machine-translated pages write ``a的b``), in proportion to how common a
    character is, so a character must be seen three times as often as that
    explains. The very common ones are thereby left out, which costs nothing:
    their pairs are all real."""
    seen, headings = collections.Counter(), collections.Counter()
    pages = 0
    for plain in _spaced_pages(overlay_dir):
        pages += 1
        for rx in (_IN_WORD_RE, _IN_YEAR_RE):
            for m in rx.finditer(plain):
                seen.update(m.group(1))
        headings.update(h for h in _section_headings(plain) if _HEADING_SHAPE_RE.fullmatch(h))
    log(f"  {pages:,} letter-spaced pages, {sum(seen.values()):,} characters inside words and years")
    freq = collections.Counter()
    for s in _summaries(records_path, every=4):
        freq.update(_CJK_RE.findall(s))
    total = sum(freq.values())
    ordinary = seen["的"] / (freq["的"] / total)       # what ordinary text contributes per unit of frequency
    pool = "".join(sorted(ch for ch, n in seen.items()
                          if n >= MIN_POOL_COUNT and n >= 3 * ordinary * freq.get(ch, 0) / total))
    finder = re.compile(f"(?=([{pool}][{pool}]))")
    pairs = collections.Counter()
    for s in _summaries(records_path):
        pairs.update(m.group(1) for m in finder.finditer(s))
    real = sorted(p for p, n in pairs.items() if n >= MIN_PAIR_COUNT)
    known = sorted(h for h, n in headings.items() if n >= MIN_HEADING_COUNT)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Learned by `python -m baike2yomitan.junk` from the overlay's letter-spaced pages and the 2019 records.\n"
                "# pool: characters Baidu Baike injects; pairs: two of them side by side in real text; headings: the\n"
                "# section headings of those pages. See baike2yomitan/junk.py.\n")
        f.write(f"pool\t{pool}\npairs\t{' '.join(real)}\nheadings\t{' '.join(known)}\n")
    _data.cache_clear()
    stats = {"pages": pages, "pool": len(pool), "pairs": len(real), "headings": len(known)}
    log(f"  pool {len(pool)} characters, {len(real):,} real pairs of {len(pool) ** 2:,} possible, {len(known)} headings -> {out_path}")
    return stats


if __name__ == "__main__":
    learn(sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "raw", "overlay"),
          sys.argv[2] if len(sys.argv) > 2 else os.path.join("data", "records.jsonl"))
