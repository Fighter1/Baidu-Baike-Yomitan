"""Write data/extract_report.md from the per-step stats JSON files."""
from __future__ import annotations

import datetime as _dt
import glob
import json
import os

STATS_DIR = os.path.join("data", "stats")


def save_stats(name: str, stats: dict) -> str:
    os.makedirs(STATS_DIR, exist_ok=True)
    p = os.path.join(STATS_DIR, f"{name}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(dict(stats), f, ensure_ascii=False, indent=1, sort_keys=True)
    return p


def _table(d: dict, prefix: str, strip: bool = True) -> str:
    rows = [(k[len(prefix):] if strip else k, v) for k, v in sorted(d.items()) if k.startswith(prefix)]
    if not rows:
        return "_none_\n"
    out = "| reason | count |\n|---|---:|\n"
    for k, v in rows:
        out += f"| {k} | {v:,} |\n"
    return out


def write_report(path: str = os.path.join("data", "extract_report.md")) -> str:
    sections = [f"# Extract report\n\nGenerated {_dt.datetime.now():%Y-%m-%d %H:%M}.\n"]
    for p in sorted(glob.glob(os.path.join(STATS_DIR, "*.json"))):
        name = os.path.splitext(os.path.basename(p))[0]
        d = json.load(open(p, encoding="utf-8"))
        sections.append(f"\n## {name}\n")
        summary_keys = [k for k in sorted(d) if ":" not in k]
        if summary_keys:
            sections.append("| metric | value |\n|---|---:|\n" +
                            "".join(f"| {k} | {d[k]:,} |\n" if isinstance(d[k], int) else f"| {k} | {d[k]} |\n"
                                    for k in summary_keys))
        if any(k.startswith("drop:") for k in d):
            sections.append("\n**Drops by reason**\n\n" + _table(d, "drop:"))
        if any(k.startswith("flag:") for k in d):
            sections.append("\n**Quality flags on kept records**\n\n" + _table(d, "flag:"))
        if any(k.startswith("skip:") for k in d):
            sections.append("\n**Skipped at build**\n\n" + _table(d, "skip:"))
        if any(k.startswith("dup:") for k in d):
            sections.append("\n**Duplicates folded**\n\n" + _table(d, "dup:"))
    notes = os.path.join("data", "stats", "NOTES.md")
    if os.path.exists(notes):
        sections.append("\n" + open(notes, encoding="utf-8").read())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(sections))
    return path
