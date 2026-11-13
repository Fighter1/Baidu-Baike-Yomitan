"""Merge overlay records into primary records.

Merge key: the *title*, not lemma_id.  Inspection showed that the 2019 crawl's
``/view/<id>`` numbers and the Internet Archive snapshots' ``/item/<title>/<id>``
numbers are different id spaces (0 of 90,506 shared ids named the same page), so
an id match is meaningless across these two sources.  ``--key lemma_id`` is
still available for sources that genuinely share an id space.

A title names several articles (时间 is a physical quantity, a word and a dozen
songs), so sharing a title is not enough to replace the 2019 text. For a
primary title with exactly one primary record, the overlay sense that refreshes
it (summary, sense_label if empty, archive_url, snapshot_date, sections) is chosen by
what the two texts say:

- ``same_text``: the overlay sense whose summary shares the most with the 2019
  summary, when that share is high enough to be the same article;
- ``likely_same``: a lower share, accepted when no other sense comes close and
  both are the same kind of thing (not a word against a song); two biographies
  must also name the same year, because names are shared by many people;
- ``weak_primary``: nothing reads alike, but the 2019 text is only a fallback
  paragraph or a stub, and the overlay offers one clear candidate (the sense
  the id-less URL showed, or the only one that is not a work) which is not a
  person and does not say much less than the 2019 text.

Otherwise the 2019 record is kept as it is. Every overlay sense that was not
used is added as a record of its own, unless it repeats a sense already written
for that title, or it is unclean (obfuscated / fallback abstract), a stub or
only the title's pinyin, and the title already has a primary record.

The rules prefer showing an article twice to losing it: when the 2019 text and
a later one have little in common, they may still be the same article rewritten
(鸬鹚 2019 and 2022 share 5% of their bigrams), and both are then kept.
"""
from __future__ import annotations

import collections

from .cleaning import MIN_SUMMARY_CHARS, SAME_ARTICLE, cjk_len, says_nothing, similarity
from .records import RecordWriter, iter_records
from .sections import ORDER
from .sense import is_person, is_work, of_another_work, share_a_year

_UNCLEAN = {"obfuscated", "abstract_fallback"}
_WEAK = {"summary_from_section", "kept_short_sentence", "kept_alias_line"}
# Flags that describe how the 2019 summary was found; untrue once it is replaced.
_ABOUT_OLD_SUMMARY = {"summary_from_section", "summary_from_later_paragraph", "summary_joined_lines",
                      "summary_from_definition_line", "kept_short_sentence", "kept_alias_line"}

SAME_TEXT = 0.25     # 重庆 2019 against 2022: 0.34; 保险单: 0.30; 时间 against its 物理量 sense: 0.45
LIKELY_SAME = 0.10   # 北京 2019 against 2022: 0.16, every other sense 0.00
MUCH_SHORTER = 0.6   # a weak 2019 text is not replaced by one with under 60% of its Chinese characters


def is_clean(rec: dict) -> bool:
    return not (set(rec.get("quality_flags") or []) & _UNCLEAN)


def is_weak(rec: dict) -> bool:
    """A summary that is a fallback paragraph or a kept stub, not an abstract."""
    return bool(set(rec.get("quality_flags") or []) & _WEAK) or len(rec.get("summary") or "") < MIN_SUMMARY_CHARS


def _apply_refresh(rec: dict, ov: dict, key: str) -> None:
    rec["summary"] = ov["summary"]
    if not rec.get("sense_label") and ov.get("sense_label"):
        rec["sense_label"] = ov["sense_label"]
    rec["archive_url"] = ov.get("archive_url")
    rec["snapshot_date"] = ov.get("snapshot_date")
    if ov.get("sections"):
        # Label by label: the snapshot's section where it has one, the 2019 one where it has none.
        # The snapshot of 旁门左道 yields only its antonym; the 2019 meaning, source and usage stay.
        by_label = {**dict(map(tuple, rec.get("sections") or [])), **dict(map(tuple, ov["sections"]))}
        rec["sections"] = ([[label, by_label.pop(label)] for label in ORDER if label in by_label]
                           + [[label, text] for label, text in by_label.items()])
    if ov.get("is_default_sense") is not None and rec.get("is_default_sense") is None:
        rec["is_default_sense"] = ov["is_default_sense"]
    if key == "lemma_id" and rec.get("lemma_id") is None:
        rec["lemma_id"] = ov.get("lemma_id")
    flags = [f for f in (rec.get("quality_flags") or []) if f not in _ABOUT_OLD_SUMMARY]
    flags.extend(f for f in (ov.get("quality_flags") or []) if f.startswith("kept_"))
    flags.append("summary_refreshed")
    rec["quality_flags"] = flags
    rec["source"] = f"{rec.get('source')}+{ov.get('source')}"


def _says_little(ov: dict) -> bool:
    """A stub, or an abstract that is only the title and its pinyin (不解，汉语词汇，注音（bù jiě）。)."""
    text = ov.get("summary") or ""
    return len(text) < MIN_SUMMARY_CHARS or says_nothing(text, ov.get("title") or "")


def _usable(rec: dict, ov: dict) -> bool:
    """Clean, and not a stub that would replace a longer text."""
    if not is_clean(ov) or says_nothing(ov.get("summary") or "", ov.get("title") or ""):
        return False
    n = len(ov.get("summary") or "")
    return n >= MIN_SUMMARY_CHARS or n >= len(rec.get("summary") or "")


def pick_refresh_candidate(rec: dict, senses: list[dict]) -> tuple[dict | None, str]:
    """(overlay sense to refresh `rec` from, reason) - see the module docstring.
    The sense is None when the 2019 record should stay as it is."""
    usable = [s for s in senses if _usable(rec, s)]
    if not usable:
        return None, "no_usable_overlay_sense"
    title = rec.get("title") or ""
    scored = sorted(((similarity(rec.get("summary") or "", s.get("summary") or "", title), i, s)
                     for i, s in enumerate(usable)), key=lambda x: (-x[0], x[1]))
    top, _, best = scored[0]
    if top >= SAME_TEXT:
        return best, "same_text"
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    # 鬼谷子 the thinker and the figure of an animation that is named after him read alike (0.20).
    if (top >= LIKELY_SAME and runner_up <= top / 2 and is_work(best) == is_work(rec)
            and not of_another_work(best, rec)):
        if not (is_person(best) or is_person(rec)) or share_a_year(best, rec):
            return best, "likely_same"
        return None, "different_person"
    if not is_weak(rec):
        return None, "different_article"
    default = next((s for s in usable if s.get("is_default_sense") is True), None)
    if default is not None:
        candidates = [default]
    else:
        candidates = [s for s in usable if not is_work(s)]
    if len(candidates) != 1:
        return None, "no_clear_candidate"
    cand = candidates[0]
    if is_person(cand) or (is_work(cand) and not is_work(rec)) or of_another_work(cand, rec):
        return None, "different_kind"
    if cjk_len(cand.get("summary")) < MUCH_SHORTER * cjk_len(rec.get("summary")):
        return None, "overlay_says_less"
    return cand, "weak_primary"


def _pick_by_shared_id(senses: list[dict]) -> dict | None:
    """--key lemma_id: the senses already are the same article."""
    clean = [s for s in senses if is_clean(s)]
    defaults = [s for s in clean if s.get("is_default_sense") is True]
    if len(defaults) == 1:
        return defaults[0]
    if len(clean) == 1 and len(senses) == 1:
        return clean[0]
    return None


def _repeats(ov: dict, written: list[str], title: str) -> bool:
    text = ov.get("summary") or ""
    return any(similarity(text, w, title) >= SAME_ARTICLE for w in written)


def merge(primary_path: str, overlay_path: str, out_path: str, key: str = "title") -> collections.Counter:
    stats: collections.Counter = collections.Counter()
    stats["key"] = key
    # The overlay is the small side (~400k records): index it in memory.
    by_key: dict = collections.defaultdict(list)
    for rec in iter_records(overlay_path):
        stats["overlay_records"] += 1
        k = rec.get(key)
        if k is None or k == "":
            by_key[None].append(rec)
        else:
            by_key[k].append(rec)

    # Primary titles seen more than once cannot be refreshed unambiguously.
    primary_title_count: collections.Counter = collections.Counter()
    if key == "title":
        for rec in iter_records(primary_path):
            primary_title_count[rec["title"]] += 1

    consumed: set[int] = set()  # id() of overlay dicts used for a refresh
    written: dict = collections.defaultdict(list)  # key -> summaries written for it (keys the overlay has)
    with RecordWriter(out_path) as w:
        for rec in iter_records(primary_path):
            stats["primary_records"] += 1
            k = rec.get(key)
            senses = by_key.get(k) if k not in (None, "") else None
            if senses:
                if key == "title" and primary_title_count[k] > 1:
                    stats["skipped_primary_title_ambiguous"] += 1
                else:
                    free = [s for s in senses if id(s) not in consumed]
                    if key == "title":
                        cand, why = pick_refresh_candidate(rec, free)
                    else:
                        cand = _pick_by_shared_id(free)
                        why = "shared_id" if cand is not None else "no_clear_candidate"
                    if cand is None:
                        stats["kept_primary"] += 1
                        stats["kept_primary:" + why] += 1
                    else:
                        _apply_refresh(rec, cand, key)
                        consumed.add(id(cand))
                        stats["refreshed"] += 1
                        stats["refreshed:" + why] += 1
                written[k].append(rec.get("summary") or "")
            w.write(rec)
        for k, senses in by_key.items():
            known = bool(k is not None and key == "title" and primary_title_count.get(k))
            for ov in senses:
                if id(ov) in consumed:
                    continue
                if k is not None and key == "title":
                    if known and (not is_clean(ov) or _says_little(ov)):
                        # a fallback abstract (lyrics, plot text), a stub or bare pinyin next to a real article
                        stats["skipped_weak_sense_of_known_title"] += 1
                        continue
                    if _repeats(ov, written[k], k):
                        stats["skipped_repeated_sense"] += 1
                        continue
                    written[k].append(ov.get("summary") or "")
                w.write(ov)
                if k is None:
                    stats["added_without_key"] += 1
                elif known:
                    stats["added_extra_sense_of_known_title"] += 1
                else:
                    stats["added_new_title"] += 1
        stats["added"] = stats["added_without_key"] + stats["added_extra_sense_of_known_title"] + stats["added_new_title"]
        stats["skipped"] = (stats["skipped_primary_title_ambiguous"] + stats["kept_primary"]
                            + stats["skipped_weak_sense_of_known_title"] + stats["skipped_repeated_sense"])
        stats["records_written"] = w.count
    return stats
