"""Build Yomitan term-bank-v3 zip(s) from a records JSONL file.

This module knows nothing about where records came from: it only uses the
common record fields (title, sense_label, summary, url, archive_url,
snapshot_date, tags, lemma_id, is_default_sense, quality_flags, infobox,
sections).
"""
from __future__ import annotations

import collections
import datetime as _dt
import os
import re
import sys
import time
import zipfile

from .readings import OVERRIDES_PATH, Readings
from .records import dumps, iter_records
from .sections import shown_sections
from .sense import is_organisation, is_person, sense_rank_key

BANK_SIZE = 10_000
_MUTED = {"fontSize": "80%", "color": "#888888"}
_SECTION_LABEL = {"fontSize": "80%", "color": "#888888", "marginRight": "0.5em"}

TITLE_FULL = "百度百科 (full)"
TITLE_LEX = "百度百科 (lexical)"

# Shipped in the zip as styles.css; Yomitan scopes it to this dictionary's
# content. `data: {"baike": X}` in structured content becomes the HTML
# attribute data-sc-baike="X".
STYLES_CSS = """\
[data-sc-baike="terms"] { display: inline-flex; margin-bottom: 0.35em; }
[data-sc-baike="traditional-term"], [data-sc-baike="simplified-term"] {
  display: inline-block; padding: 4px; margin-right: 6px; line-height: 1; font-size: 1.1em;
  border: 1px solid #454545; border-radius: 4px; background: #111; }
[data-sc-baike="traditional-term"] { color: #e42566; }
[data-sc-baike="simplified-term"] { color: #257de4; }
[data-sc-baike="section-label"] {
  padding: 0 4px; border: 1px solid #888888; border-radius: 3px; white-space: nowrap; }
"""


# Characters that are a surname (or a name syllable) in their simplified
# form and at the same time the simplified form of another word. OpenCC has to
# pick one and converts the other word: 于荣海 -> 於榮海, 范英 -> 範英, 岳敏君 ->
# 嶽敏君. Value: the character a name keeps in traditional script.
SURNAME_FORMS = {
    "于": "于", "范": "范", "余": "余", "岳": "岳", "游": "游", "党": "党", "种": "种", "郁": "郁",
    "咸": "咸", "后": "后", "涂": "涂", "干": "干", "朴": "朴", "丑": "丑", "斗": "斗", "沈": "沈",
    "胡": "胡", "姜": "姜", "谷": "谷", "松": "松", "冬": "冬", "卜": "卜", "曲": "曲", "仇": "仇",
    "向": "向", "里": "里", "钟": "鍾",
}


class Traditional:
    def __init__(self, config: str = "s2t"):
        from opencc import OpenCC  # optional dependency

        self._cc = OpenCC(config)

    def __call__(self, text: str) -> str:
        return self._cc.convert(text)

    def forms(self, title: str, person: bool = False, word: bool = False) -> list[str]:
        """Traditional spellings to index for a title; the first is the one
        the entry displays. Usually one. A title that starts with a character
        from SURNAME_FORMS gets a second spelling that keeps the name form
        (於榮海 and 于榮海), because nothing in the title says whether it is a
        name; for a biography the name form is the one displayed. `word`: the
        title is a dictionary word (后边, 干燥剂), which is not a name unless
        the record is a biography, so it gets no name form."""
        main = self(title)
        out = [main]
        keep = SURNAME_FORMS.get(title[:1])
        if keep and len(main) == len(title) and main[:1] != keep and (person or not word):
            name_form = keep + main[1:]
            out = [name_form, main] if person else [main, name_form]
        return out


def structured_content(rec: dict, want_infobox: bool, traditional: str | None = None,
                       want_sections: bool = False) -> dict:
    """`traditional` is the OpenCC form of the title when the build emits
    traditional headwords (None otherwise); the entry then opens with the
    traditional and simplified spellings side by side, like 汉语大词典.
    `want_sections` adds the labelled sections of a word's page (释义, 出处,
    用法 ...) under the summary, those that say more than the summary does."""
    parts: list = []
    if traditional is not None:
        terms: list = []
        if traditional != rec["title"]:
            terms.append({"tag": "span", "data": {"baike": "traditional-term"}, "content": traditional})
        terms.append({"tag": "span", "data": {"baike": "simplified-term"}, "content": rec["title"]})
        parts.append({"tag": "div", "data": {"baike": "terms"}, "content": terms})
    label = rec.get("sense_label") or ""
    if label and label != rec.get("title"):  # a subtitle equal to the title says nothing
        parts.append({"tag": "div", "data": {"baike": "sense-label"}, "style": dict(_MUTED),
                      "content": label})
    parts.append({"tag": "div", "data": {"baike": "summary"}, "content": rec["summary"]})
    sections = shown_sections(rec) if want_sections else []
    if sections:
        parts.append({"tag": "div", "data": {"baike": "sections"}, "style": {"marginTop": "0.3em"}, "content": [
            {"tag": "div", "data": {"baike": "section"}, "content": [
                {"tag": "span", "data": {"baike": "section-label"}, "style": dict(_SECTION_LABEL), "content": label},
                text]}
            for label, text in sections]})
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


_REVISION_RE = re.compile(r"^\d+(\.\d+){3}$")


def default_revision(today: _dt.date | None = None) -> str:
    """Yomitan compares revisions numerically only when both are dot-separated
    integers with the same number of segments, so always emit four: Y.M.D.N,
    where N is a build number (1 locally; the run number in GitHub Actions)."""
    return (today or _dt.date.today()).strftime("%Y.%m.%d") + ".1"


def check_revision(revision: str) -> str:
    """Exactly four integer segments. Yomitan compares revisions number by
    number only when both have the same count of segments and falls back to a
    string comparison otherwise, so "2026.11.9" would never be offered
    "2026.11.10.5" as an update."""
    if not _REVISION_RE.match(revision or ""):
        raise ValueError(f"revision {revision!r} must be four dot-separated integers (e.g. 2026.11.09.1) "
                         "so Yomitan can compare it numerically")
    return revision


def update_urls(update_base_url: str, stem: str) -> tuple[str, str]:
    """(indexUrl, downloadUrl) for a zip named <stem>.zip hosted under a base URL
    such as https://github.com/<owner>/<repo>/releases/latest/download."""
    base = update_base_url.rstrip("/")
    return f"{base}/{stem}.index.json", f"{base}/{stem}.zip"


CEDICT_ATTRIBUTION = "Readings partly from CC-CEDICT (https://cc-cedict.org), CC BY-SA 4.0."


def make_index(title: str, merged: bool, description_extra: str = "", revision: str | None = None,
               update_base_url: str | None = None, stem: str | None = None,
               cedict_readings: bool = False) -> dict:
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
                       + ("; overlay: mohamedah/baidu_baike" if merged else "") + "."
                       + (" " + CEDICT_ATTRIBUTION if cedict_readings else ""),
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


def rank_senses(records_path: str, visit=None) -> dict[str, dict[tuple, int]]:
    """First pass: for titles with more than one sense, rank the senses.
    Returns title -> {(lemma_id, sense_label, summary[:40]) -> rank}.
    `visit`, when given, is called with every record (the readings use it
    to note which titles state their own pinyin)."""
    # Keep only what ranking needs (not the whole record) so the full corpus
    # fits comfortably in memory.
    per_title: dict[str, list] = collections.defaultdict(list)
    for rec in iter_records(records_path):
        per_title[rec["title"]].append((sense_rank_key(rec), _sense_key(rec)))
        if visit is not None:
            visit(rec)
    ranks: dict[str, dict[tuple, int]] = {}
    for title, senses in per_title.items():
        if len(senses) < 2:
            continue
        senses.sort(key=lambda x: x[0])
        ranks[title] = {key: i for i, (_, key) in enumerate(senses)}
    return ranks


def _sense_key(rec: dict) -> tuple:
    return (rec.get("lemma_id"), rec.get("sense_label") or "", (rec.get("summary") or "")[:40])


def excluded_by_tag(rec: dict, exclude_tags: set[str], common_words: set[str] | None) -> bool:
    """Whether --exclude-tags (人物, 企业, 学校 for the lexical build) drops a record.

    A Baike tag describes a page with every sense on it, and the tags are from
    2019 while the text may be newer: 潇洒 is tagged 人物 because a web novelist
    uses the name, 证书 is tagged 学校. So for a headword that CC-CEDICT lists as
    an ordinary word (`common_words`), the tag alone is not enough: the text
    itself has to read as a person, a company or a school. Headwords CC-CEDICT
    only knows as names, and builds without that list, go by the tag."""
    if not exclude_tags or not (exclude_tags & set(rec.get("tags") or [])):
        return False
    if common_words is None or rec.get("title") not in common_words:
        return True
    return is_person(rec) or is_organisation(rec)


def _is_biography(rec: dict) -> bool:
    """Going by the text only. The Baike tags belong to a page with every
    sense on it: the city 沈阳 is tagged 财经人物 and 沈氏人物."""
    return is_person(rec, certain=True)


def default_title(cedict_words: set[str] | None) -> str:
    """A build filtered to CC-CEDICT headwords is the lexical dictionary;
    anything else is the full one."""
    return TITLE_LEX if cedict_words is not None else TITLE_FULL


def build(records_path: str, out_zip: str, title: str | None = None,
          pinyin: bool = False, traditional: str | None = None, infobox: bool = False,
          cedict_words: set[str] | None = None, exclude_tags: set[str] | None = None,
          common_words: set[str] | None = None,
          merged: bool | None = None, revision: str | None = None,
          update_base_url: str | None = None, readings_cedict: str | None = None,
          pinyin_overrides: str | None = OVERRIDES_PATH, sections: bool = False) -> collections.Counter:
    """`pinyin` fills the reading field (see readings.py for the sources);
    `readings_cedict` is the CC-CEDICT export to take readings from and
    `pinyin_overrides` the hand-checked title/reading file, both optional."""
    stats: collections.Counter = collections.Counter()
    t0 = time.time()
    title = title or default_title(cedict_words)
    stem = os.path.splitext(os.path.basename(out_zip))[0]
    revision = check_revision(revision or default_revision())
    to_reading = Readings(readings_cedict, pinyin_overrides) if pinyin else None
    to_trad = Traditional(traditional) if traditional else None
    exclude_tags = set(exclude_tags or ())
    # Titles known to be dictionary words: CC-CEDICT's headwords, when loaded.
    known_words = cedict_words if cedict_words is not None else (to_reading.cedict if to_reading else ())

    print("  [build] pass 1: ranking senses", file=sys.stderr, flush=True)
    ranks = rank_senses(records_path, visit=to_reading.observe if to_reading else None)
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
                if excluded_by_tag(rec, exclude_tags, common_words):
                    stats["skip:excluded_tag"] += 1
                    continue
                stats["kept:excluded_tag_on_ordinary_word"] += 1
            rank = ranks.get(t, {}).get(_sense_key(rec), 0)
            score = -rank
            seq += 1
            forms = to_trad.forms(t, person=_is_biography(rec), word=t in known_words) if to_trad else []
            tt = forms[0] if forms else None
            content = structured_content(rec, infobox, tt, sections)
            if sections and any(p["data"]["baike"] == "sections" for p in content["content"]):
                stats["senses_with_sections"] += 1
            reading = ""
            if to_reading:
                reading, reading_source = to_reading(rec)
                stats["reading:" + reading_source] += 1
            banks.add([t, reading, "", "", score, [content], seq, ""])
            stats["entries"] += 1
            emitted = {t}
            for form in forms:
                if form not in emitted:
                    emitted.add(form)
                    banks.add([form, reading, "", "", score, [content], seq, ""])
                    stats["entries"] += 1
                    stats["entries_traditional"] += 1
            if stats["records_seen"] % 500_000 == 0:
                print(f"  [build] {stats['records_seen']:,} records, {stats['entries']:,} entries, "
                      f"{time.time()-t0:,.0f}s", file=sys.stderr, flush=True)
        banks.flush()
        zf.writestr("styles.css", STYLES_CSS)
        index = make_index(title, merged, revision=revision, update_base_url=update_base_url, stem=stem,
                           cedict_readings=bool(to_reading and to_reading.cedict))
        zf.writestr("index.json", dumps(index))
        stats["term_banks"] = banks.bank_no
    # Same bytes as the zip's index.json, written next to it for `release` to upload.
    with open(sidecar_index_path(out_zip), "wb") as f:
        f.write(dumps(index))
    stats["seconds"] = int(time.time() - t0)
    stats["zip_bytes"] = os.path.getsize(out_zip)
    return stats
