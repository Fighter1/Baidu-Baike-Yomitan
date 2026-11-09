"""Build Yomitan term-bank-v3 zip(s) from a records JSONL file.

This module knows nothing about where records came from: it only uses the
common record fields (title, sense_label, summary, url, archive_url,
snapshot_date, tags, lemma_id, is_default_sense, quality_flags, infobox).
"""
from __future__ import annotations

import collections
import datetime as _dt
import os
import re
import sys
import time
import zipfile

from .records import dumps, iter_records
from .sense import sense_rank_key

BANK_SIZE = 10_000
DICT_TAG = "百科"
_MUTED = {"fontSize": "80%", "color": "#888888"}

TITLE_FULL = "百度百科 (full)"
TITLE_LEX = "百度百科 (lexical)"


def _cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text)


class Pinyin:
    def __init__(self):
        from pypinyin import Style, lazy_pinyin  # imported lazily: optional

        self._lazy = lazy_pinyin
        self._style = Style.TONE

    def __call__(self, text: str) -> str:
        if not _cjk(text):
            return ""
        return " ".join(self._lazy(text, style=self._style, errors="ignore"))


class Traditional:
    def __init__(self, config: str = "s2t"):
        from opencc import OpenCC  # optional dependency

        self._cc = OpenCC(config)

    def __call__(self, text: str) -> str:
        return self._cc.convert(text)


def structured_content(rec: dict, want_infobox: bool) -> dict:
    parts: list = []
    label = rec.get("sense_label") or ""
    if label and label != rec.get("title"):  # a subtitle equal to the title says nothing
        parts.append({"tag": "div", "data": {"baike": "sense-label"}, "style": dict(_MUTED),
                      "content": label})
    parts.append({"tag": "div", "data": {"baike": "summary"}, "content": rec["summary"]})
    infobox = rec.get("infobox") if want_infobox else None
    if infobox:
        rows = []
        for k, v in infobox[:6]:
            rows.append({"tag": "tr", "content": [
                {"tag": "th", "style": {"textAlign": "left", "fontWeight": "normal", "color": "#888888",
                                        "paddingRight": "0.8em"}, "content": str(k)},
                {"tag": "td", "content": str(v)},
            ]})
        parts.append({"tag": "div", "data": {"baike": "infobox"}, "style": {"fontSize": "85%", "marginTop": "0.3em"},
                      "content": {"tag": "table", "content": {"tag": "tbody", "content": rows}}})
    footer: list = []
    if rec.get("url"):
        footer.append({"tag": "a", "href": rec["url"], "content": "百度百科"})
    if rec.get("archive_url"):
        if footer:
            footer.append(" · ")
        date = rec.get("snapshot_date")
        footer.append({"tag": "a", "href": rec["archive_url"],
                       "content": f"存档 {date}" if date else "存档"})
    tags = [t for t in (rec.get("tags") or []) if t][:5]
    if tags:
        if footer:
            footer.append(" · ")
        footer.append("标签：" + "、".join(tags))
    if footer:
        parts.append({"tag": "div", "data": {"baike": "footer"},
                      "style": dict(_MUTED, marginTop="0.4em"), "content": footer})
    return {"type": "structured-content", "content": parts}


_REVISION_RE = re.compile(r"^(\d+\.)*\d+$")


def default_revision(today: _dt.date | None = None) -> str:
    """Yomitan compares revisions numerically only when both are dot-separated
    integers with the same number of segments, so always emit four: Y.M.D.N,
    where N is a build number (1 locally; the run number in GitHub Actions)."""
    return (today or _dt.date.today()).strftime("%Y.%m.%d") + ".1"


def check_revision(revision: str) -> str:
    if not _REVISION_RE.match(revision):
        raise ValueError(f"revision {revision!r} must be dot-separated integers (e.g. 2026.11.09.1) "
                         "so Yomitan can compare it numerically")
    return revision


def update_urls(update_base_url: str, stem: str) -> tuple[str, str]:
    """(indexUrl, downloadUrl) for a zip named <stem>.zip hosted under a base URL
    such as https://github.com/<owner>/<repo>/releases/latest/download."""
    base = update_base_url.rstrip("/")
    return f"{base}/{stem}.index.json", f"{base}/{stem}.zip"


def make_index(title: str, merged: bool, description_extra: str = "", revision: str | None = None,
               update_base_url: str | None = None, stem: str | None = None) -> dict:
    idx = {
        "title": title,
        "format": 3,
        "revision": check_revision(revision or default_revision()),
        "sequenced": True,
        "author": "baike2yomitan",
        "url": "https://huggingface.co/datasets/lars1234/baidu-baike-dataset",
        "description": ("Baidu Baike summaries as a Chinese-Chinese Yomitan dictionary, built from offline "
                        "Hugging Face mirrors (BIT-ENGD 2019 crawl" + (", Internet Archive snapshots 2020-2024" if merged else "") + "). "
                        "User-contributed encyclopedia content." + description_extra),
        "attribution": "Content © Baidu Baike contributors (https://baike.baidu.com). Mirror: lars1234/baidu-baike-dataset"
                       + ("; overlay: mohamedah/baidu_baike" if merged else "") + ".",
        "sourceLanguage": "zh",
        "targetLanguage": "zh",
    }
    if update_base_url:
        if not stem:
            raise ValueError("stem is required with update_base_url")
        idx["isUpdatable"] = True
        idx["indexUrl"], idx["downloadUrl"] = update_urls(update_base_url, stem)
    return idx


def sidecar_index_path(out_zip: str) -> str:
    """dist/baike-full.zip -> dist/baike-full.index.json (the file the release
    uploads next to the zip; Yomitan fetches it from indexUrl to compare revisions)."""
    return os.path.splitext(out_zip)[0] + ".index.json"


TAG_BANK = [[DICT_TAG, "name", 0, "百度百科词条", 0]]


class _ZipBanks:
    """Writes term banks of BANK_SIZE entries straight into the zip."""

    def __init__(self, zf: zipfile.ZipFile):
        self.zf = zf
        self.buf: list = []
        self.bank_no = 0
        self.entries = 0

    def add(self, entry: list) -> None:
        self.buf.append(entry)
        self.entries += 1
        if len(self.buf) >= BANK_SIZE:
            self.flush()

    def flush(self) -> None:
        if not self.buf:
            return
        self.bank_no += 1
        self.zf.writestr(f"term_bank_{self.bank_no}.json", dumps(self.buf))
        self.buf = []


def rank_senses(records_path: str) -> dict[str, dict[tuple, int]]:
    """First pass: for titles with more than one sense, rank the senses.
    Returns title -> {(lemma_id, sense_label, summary[:40]) -> rank}."""
    # Keep only what ranking needs (not the whole record) so the full corpus
    # fits comfortably in memory.
    per_title: dict[str, list] = collections.defaultdict(list)
    for rec in iter_records(records_path):
        per_title[rec["title"]].append((sense_rank_key(rec), _sense_key(rec)))
    ranks: dict[str, dict[tuple, int]] = {}
    for title, senses in per_title.items():
        if len(senses) < 2:
            continue
        senses.sort(key=lambda x: x[0])
        ranks[title] = {key: i for i, (_, key) in enumerate(senses)}
    return ranks


def _sense_key(rec: dict) -> tuple:
    return (rec.get("lemma_id"), rec.get("sense_label") or "", (rec.get("summary") or "")[:40])


def default_title(cedict_words: set[str] | None) -> str:
    """A build filtered to CC-CEDICT headwords is the lexical dictionary;
    anything else is the full one."""
    return TITLE_LEX if cedict_words is not None else TITLE_FULL


def build(records_path: str, out_zip: str, title: str | None = None,
          pinyin: bool = False, traditional: str | None = None, infobox: bool = False,
          cedict_words: set[str] | None = None, exclude_tags: set[str] | None = None,
          merged: bool | None = None, revision: str | None = None,
          update_base_url: str | None = None) -> collections.Counter:
    stats: collections.Counter = collections.Counter()
    t0 = time.time()
    title = title or default_title(cedict_words)
    stem = os.path.splitext(os.path.basename(out_zip))[0]
    revision = check_revision(revision or default_revision())
    to_pinyin = Pinyin() if pinyin else None
    to_trad = Traditional(traditional) if traditional else None
    exclude_tags = set(exclude_tags or ())

    print("  [build] pass 1: ranking senses", file=sys.stderr, flush=True)
    ranks = rank_senses(records_path)
    stats["titles_with_multiple_senses"] = len(ranks)

    if merged is None:  # auto-detect: any record carrying an archive snapshot
        merged = any(rec.get("snapshot_date") for rec in iter_records(records_path))

    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    print("  [build] pass 2: writing term banks", file=sys.stderr, flush=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        banks = _ZipBanks(zf)
        seq = 0
        for rec in iter_records(records_path):
            stats["records_seen"] += 1
            t = rec["title"]
            if cedict_words is not None and t not in cedict_words:
                stats["skip:not_in_cedict"] += 1
                continue
            if exclude_tags and exclude_tags & set(rec.get("tags") or []):
                stats["skip:excluded_tag"] += 1
                continue
            rank = ranks.get(t, {}).get(_sense_key(rec), 0)
            score = -rank
            seq += 1
            content = structured_content(rec, infobox)
            reading = to_pinyin(t) if to_pinyin else ""
            banks.add([t, reading, DICT_TAG, "", score, [content], seq, ""])
            stats["entries"] += 1
            if to_trad:
                tt = to_trad(t)
                if tt != t:
                    banks.add([tt, reading, DICT_TAG, "", score, [content], seq, ""])
                    stats["entries"] += 1
                    stats["entries_traditional"] += 1
            if stats["records_seen"] % 500_000 == 0:
                print(f"  [build] {stats['records_seen']:,} records, {stats['entries']:,} entries, "
                      f"{time.time()-t0:,.0f}s", file=sys.stderr, flush=True)
        banks.flush()
        zf.writestr("tag_bank_1.json", dumps(TAG_BANK))
        index = make_index(title, merged, revision=revision, update_base_url=update_base_url, stem=stem)
        zf.writestr("index.json", dumps(index))
        stats["term_banks"] = banks.bank_no
    # Same bytes as the zip's index.json, written next to it for `release` to upload.
    with open(sidecar_index_path(out_zip), "wb") as f:
        f.write(dumps(index))
    stats["seconds"] = int(time.time() - t0)
    stats["zip_bytes"] = os.path.getsize(out_zip)
    return stats
