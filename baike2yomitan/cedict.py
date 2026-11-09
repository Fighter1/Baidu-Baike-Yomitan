"""CC-CEDICT (MDBG export) loading: the set of simplified headwords."""
from __future__ import annotations

import gzip
import io
import os
import urllib.request

CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
DEFAULT_PATH = os.path.join("data", "cedict", "cedict_1_0_ts_utf-8_mdbg.txt.gz")


def download(path: str = DEFAULT_PATH) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with urllib.request.urlopen(CEDICT_URL, timeout=120) as r, open(path, "wb") as f:
        f.write(r.read())
    return path


def load_simplified_headwords(path: str = DEFAULT_PATH) -> set[str]:
    """Line format: TRAD SIMP [pinyin] /gloss/ … ; comments start with #."""
    opener = gzip.open if path.endswith(".gz") else open
    words: set[str] = set()
    with opener(path, "rb") as raw, io.TextIOWrapper(raw, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line or line[0] == "#":
                continue
            parts = line.split(" ", 2)
            if len(parts) >= 2:
                words.add(parts[1])
    return words
