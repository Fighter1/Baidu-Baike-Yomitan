"""CC-CEDICT (MDBG export) loading: the sets of simplified headwords."""
from __future__ import annotations

import gzip
import io
import os
import time
import urllib.request

CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
DEFAULT_PATH = os.path.join("data", "cedict", "cedict_1_0_ts_utf-8_mdbg.txt.gz")


MAX_AGE_HOURS = 24          # `all` downloads the export again when the local copy is older
MIN_ENTRIES = 100_000       # the export has about 124,000 lines; fewer means a cut-off or wrong file


def download(path: str = DEFAULT_PATH) -> str:
    """Fetch the current MDBG export. The file at ``path`` is replaced only
    by a complete export, so a failed download leaves an older copy as it was."""
    with urllib.request.urlopen(CEDICT_URL, timeout=120) as r:
        data = r.read()
    try:
        entries = sum(1 for line in gzip.decompress(data).splitlines() if line and not line.startswith(b"#"))
    except (OSError, EOFError) as e:
        raise OSError(f"{CEDICT_URL} did not return a gzip file ({e})") from e
    if entries < MIN_ENTRIES:
        raise OSError(f"{CEDICT_URL} returned only {entries:,} entries")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return path


def ensure_current(path: str = DEFAULT_PATH, max_age_hours: float | None = MAX_AGE_HOURS, log=print) -> str:
    """Make sure there is a CC-CEDICT export at ``path`` and, when
    ``max_age_hours`` is given, that it is no older than that. Returns
    ``downloaded`` (there was none), ``refreshed``, ``current`` or ``kept``
    (too old, but the download failed or was not wanted).

    A release is built on a runner with an empty disk and so always has the
    export of the day. A local copy used to stay for good, and local builds
    drifted from the releases (玳瑁猫 read dài mài from an export of three
    days earlier, in which that entry was wrong)."""
    if not os.path.exists(path):
        log("downloading CC-CEDICT …")
        download(path)
        return "downloaded"
    age = (time.time() - os.path.getmtime(path)) / 3600
    if max_age_hours is None or age <= max_age_hours:
        return "current" if max_age_hours is not None else "kept"
    log(f"CC-CEDICT copy is {age / 24:.1f} days old, downloading the current export …")
    try:
        download(path)
    except OSError as e:        # URLError and timeouts are OSErrors
        log(f"  could not download it ({e}); building with the copy of {age / 24:.1f} days ago")
        return "kept"
    return "refreshed"


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


def load_common_headwords(path: str = DEFAULT_PATH) -> set[str]:
    """Simplified headwords with at least one reading written in lower case:
    ordinary words. CC-CEDICT capitalises the pinyin of proper nouns
    (北京大学 [Bei3 jing1 Da4 xue2]), so a headword that is missing here is
    only ever a name."""
    opener = gzip.open if path.endswith(".gz") else open
    words: set[str] = set()
    with opener(path, "rb") as raw, io.TextIOWrapper(raw, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line or line[0] == "#":
                continue
            parts = line.split(" ", 2)
            if len(parts) == 3 and parts[2][:1] == "[" and parts[2][1:2].islower():
                words.add(parts[1])
    return words
