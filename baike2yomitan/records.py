"""Common record format shared by every extractor and consumed by merge/build.

One record per sense.  Field order is fixed so JSONL diffs stay readable.
`infobox` is an optional extension (list of [key, value] pairs) used by
`build --infobox`; extractors that cannot produce it leave it null.
`sections` is the same kind of extension for `build --sections`: a list of
[label, text] pairs, the dictionary-style sections of a word's page (释义,
出处, 用法 ...), see sections.py.
"""
from __future__ import annotations

import dataclasses
import io
import os
from dataclasses import dataclass, field
from typing import Iterator, Optional

try:  # orjson is ~5x faster; fall back to stdlib if missing
    import orjson

    def dumps(obj) -> bytes:
        return orjson.dumps(obj)

    def loads(data):
        return orjson.loads(data)

except ImportError:  # pragma: no cover
    import json

    def dumps(obj) -> bytes:
        return json.dumps(obj, ensure_ascii=False).encode("utf-8")

    def loads(data):
        return json.loads(data)


RECORD_FIELDS = (
    "source",
    "title",
    "sense_label",
    "lemma_id",
    "is_default_sense",
    "summary",
    "tags",
    "url",
    "archive_url",
    "snapshot_date",
    "quality_flags",
    "infobox",
    "sections",
)


@dataclass
class Record:
    source: str
    title: str
    summary: str
    sense_label: str = ""
    lemma_id: Optional[int] = None
    is_default_sense: Optional[bool] = None
    tags: list = field(default_factory=list)
    url: Optional[str] = None
    archive_url: Optional[str] = None
    snapshot_date: Optional[str] = None
    quality_flags: list = field(default_factory=list)
    infobox: Optional[list] = None
    sections: Optional[list] = None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        return {k: d[k] for k in RECORD_FIELDS}

    @classmethod
    def from_dict(cls, d: dict) -> "Record":
        return cls(**{k: d.get(k) for k in RECORD_FIELDS if k in d})


class RecordWriter:
    """Append-only JSONL writer with a running count."""

    def __init__(self, path: str, append: bool = False):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._f = open(path, "ab" if append else "wb")
        self.count = 0

    def write(self, rec: Record | dict) -> None:
        d = rec.to_dict() if isinstance(rec, Record) else rec
        self._f.write(dumps(d))
        self._f.write(b"\n")
        self.count += 1

    def close(self) -> None:
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def iter_records(path: str) -> Iterator[dict]:
    """Stream records from a JSONL file as dicts (never loads the file whole)."""
    with open(path, "rb") as f:
        for line in f:
            if line.strip():
                yield loads(line)


def count_lines(path: str) -> int:
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return n
