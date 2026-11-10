"""CC-CEDICT download: a stale local copy is replaced, and only by a complete export."""
import gzip
import os
import time

import pytest

from baike2yomitan import cedict


def _export(n, word="词"):
    lines = ["# CC-CEDICT"] + [f"{word}{i} {word}{i} [ci2] /word {i}/" for i in range(n)]
    return gzip.compress("\n".join(lines).encode("utf-8"))


class _Response:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def mdbg(monkeypatch):
    """Stub of the MDBG server: set ``serve["data"]`` to bytes, or to an exception to raise."""
    serve = {"data": _export(cedict.MIN_ENTRIES), "calls": 0}

    def urlopen(url, timeout=None):
        assert url == cedict.CEDICT_URL
        serve["calls"] += 1
        if isinstance(serve["data"], Exception):
            raise serve["data"]
        return _Response(serve["data"])

    monkeypatch.setattr(cedict.urllib.request, "urlopen", urlopen)
    return serve


def _old_copy(tmp_path, hours):
    path = tmp_path / "cedict" / "export.txt.gz"
    path.parent.mkdir()
    path.write_bytes(b"old copy")
    then = time.time() - hours * 3600
    os.utime(path, (then, then))
    return str(path)


def test_missing_copy_is_downloaded(tmp_path, mdbg):
    path = str(tmp_path / "cedict" / "export.txt.gz")
    assert cedict.ensure_current(path, log=lambda *_: None) == "downloaded"
    assert len(cedict.load_simplified_headwords(path)) == cedict.MIN_ENTRIES
    assert not os.path.exists(path + ".part")


def test_copy_of_today_is_not_downloaded_again(tmp_path, mdbg):
    path = _old_copy(tmp_path, 2)
    assert cedict.ensure_current(path, log=lambda *_: None) == "current"
    assert mdbg["calls"] == 0 and open(path, "rb").read() == b"old copy"


def test_stale_copy_is_replaced(tmp_path, mdbg):
    path = _old_copy(tmp_path, 80)
    said = []
    assert cedict.ensure_current(path, log=said.append) == "refreshed"
    assert open(path, "rb").read() == mdbg["data"] and "3.3 days old" in said[0]
    assert time.time() - os.path.getmtime(path) < 60          # and is not fetched again by the next build


def test_stale_copy_is_kept_when_asked(tmp_path, mdbg):
    path = _old_copy(tmp_path, 80)
    assert cedict.ensure_current(path, None, log=lambda *_: None) == "kept"
    assert mdbg["calls"] == 0


@pytest.mark.parametrize("answer", [OSError("no route to host"), b"<html>503</html>", _export(50),
                                    _export(cedict.MIN_ENTRIES)[:5000]])
def test_stale_copy_survives_a_failed_download(tmp_path, mdbg, answer):
    path = _old_copy(tmp_path, 80)
    mdbg["data"] = answer
    said = []
    assert cedict.ensure_current(path, log=said.append) == "kept"
    assert open(path, "rb").read() == b"old copy" and "could not download" in said[-1]
    assert not os.path.exists(path + ".part")


def test_missing_copy_and_no_network_is_an_error(tmp_path, mdbg):
    mdbg["data"] = OSError("no route to host")
    with pytest.raises(OSError):
        cedict.ensure_current(str(tmp_path / "cedict" / "export.txt.gz"), log=lambda *_: None)
