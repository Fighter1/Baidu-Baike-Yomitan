"""Merge overlay records into primary records.

Merge key: the *title*, not lemma_id.  Inspection showed that the 2019 crawl's
``/view/<id>`` numbers and the Internet Archive snapshots' ``/item/<title>/<id>``
numbers are different id spaces (0 of 90,506 shared ids named the same page), so
an id match is meaningless across these two sources.  ``--key lemma_id`` is
still available for sources that genuinely share an id space.

Title-based rule:
- primary title with exactly one primary sense, overlay has a default sense for
  that title (or exactly one sense)  -> refresh the primary record from that
  overlay sense (summary, sense_label if empty, archive_url, snapshot_date);
- every other overlay sense of a known title, and all senses of unknown titles,
  are added as new records;
- unclean overlay records (obfuscated / fallback abstract) never refresh, but
  may still be added when nothing else covers the title.
"""
from __future__ import annotations

import collections

from .records import RecordWriter, iter_records

_UNCLEAN = {"obfuscated", "abstract_fallback"}


def is_clean(rec: dict) -> bool:
    return not (set(rec.get("quality_flags") or []) & _UNCLEAN)


def _apply_refresh(rec: dict, ov: dict, key: str) -> None:
    rec["summary"] = ov["summary"]
    if not rec.get("sense_label") and ov.get("sense_label"):
        rec["sense_label"] = ov["sense_label"]
    rec["archive_url"] = ov.get("archive_url")
    rec["snapshot_date"] = ov.get("snapshot_date")
    if ov.get("is_default_sense") is not None and rec.get("is_default_sense") is None:
        rec["is_default_sense"] = ov["is_default_sense"]
    if key == "lemma_id" and rec.get("lemma_id") is None:
        rec["lemma_id"] = ov.get("lemma_id")
    flags = [f for f in (rec.get("quality_flags") or []) if f != "summary_from_section"]
    flags.append("summary_refreshed")
    rec["quality_flags"] = flags
    rec["source"] = f"{rec.get('source')}+{ov.get('source')}"


def _pick_refresh_candidate(senses: list[dict]) -> dict | None:
    """The overlay sense that stands for 'the' article of a title."""
    clean = [s for s in senses if is_clean(s)]
    defaults = [s for s in clean if s.get("is_default_sense") is True]
    if len(defaults) == 1:
        return defaults[0]
    if len(clean) == 1 and len(senses) == 1:
        return clean[0]
    return None


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
    with RecordWriter(out_path) as w:
        for rec in iter_records(primary_path):
            stats["primary_records"] += 1
            k = rec.get(key)
            senses = by_key.get(k) if k not in (None, "") else None
            if senses:
                if key == "title" and primary_title_count[k] > 1:
                    stats["skipped_primary_title_ambiguous"] += 1
                else:
                    cand = _pick_refresh_candidate([s for s in senses if id(s) not in consumed])
                    if cand is None:
                        stats["skipped_overlay_ambiguous_or_unclean"] += 1
                    else:
                        _apply_refresh(rec, cand, key)
                        consumed.add(id(cand))
                        stats["refreshed"] += 1
            w.write(rec)
        for k, senses in by_key.items():
            for ov in senses:
                if id(ov) in consumed:
                    continue
                w.write(ov)
                if k is None:
                    stats["added_without_key"] += 1
                elif key == "title" and primary_title_count.get(k):
                    stats["added_extra_sense_of_known_title"] += 1
                else:
                    stats["added_new_title"] += 1
        stats["added"] = stats["added_without_key"] + stats["added_extra_sense_of_known_title"] + stats["added_new_title"]
        stats["skipped"] = stats["skipped_primary_title_ambiguous"] + stats["skipped_overlay_ambiguous_or_unclean"]
        stats["records_written"] = w.count
    return stats
