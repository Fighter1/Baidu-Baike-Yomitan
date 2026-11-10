"""validate_zip: the same answer from one process and from several."""
import json
import os
import zipfile

import pytest

from baike2yomitan.validate import default_workers, validate_zip, worker_count

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "schemas")
INDEX = {"title": "t", "format": 3, "revision": "1"}
GOOD = ["word", "", "", "", 0, ["definition"], 1, ""]
BAD = ["word", "", "", "", "not a number", ["definition"], 1, ""]


def make_zip(path, members):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data if isinstance(data, str) else json.dumps(data))
    return str(path)


@pytest.mark.parametrize("workers", [1, 3])
def test_valid_zip(tmp_path, workers, capfd):
    banks = {f"term_bank_{i}.json": [GOOD] * 5 for i in range(1, 7)}
    z = make_zip(tmp_path / "ok.zip", {**banks, "styles.css": "a{}", "index.json": INDEX})
    assert validate_zip(z, SCHEMA_DIR, workers=workers) == []
    # one progress line per checked member, in the zip's order
    lines = [ln.split()[1] for ln in capfd.readouterr().err.splitlines() if "[validate]" in ln]
    assert lines == [f"term_bank_{i}.json:" for i in range(1, 7)] + ["index.json:"]


@pytest.mark.parametrize("workers", [1, 3])
def test_errors_name_the_member_and_keep_zip_order(tmp_path, workers):
    z = make_zip(tmp_path / "bad.zip", {
        "term_bank_1.json": [GOOD],
        "term_bank_2.json": [GOOD, BAD],
        "term_bank_3.json": [GOOD] * 10_001,
        "term_bank_4.json": [BAD],
        "notes.txt": "stray",
        "index.json": INDEX,
    })
    errors = validate_zip(z, SCHEMA_DIR, workers=workers)
    assert [e.split(":")[0] for e in errors] == ["unexpected file in zip", "term_bank_2.json",
                                                 "term_bank_3.json", "term_bank_4.json"]
    assert "10001 entries" in errors[2]
    # the cap is honoured and the earliest members win
    assert validate_zip(z, SCHEMA_DIR, max_errors=2, workers=workers) == errors[:2]


def test_structure_errors(tmp_path):
    z = make_zip(tmp_path / "empty.zip", {"sub/term_bank_1.json": [GOOD]})
    errors = validate_zip(z, SCHEMA_DIR)
    assert any("subfolders" in e for e in errors)
    assert "index.json missing" in errors and "no term_bank_N.json files" in errors


def test_worker_count():
    assert default_workers() >= 1
    assert worker_count(8, tasks=3) == 3            # never more processes than files
    assert worker_count(8, tasks=0) == 1 and worker_count(0, tasks=5) >= 1
    assert worker_count(None, tasks=10_000) >= 1    # default: every core
    assert worker_count(200, tasks=900, platform="win32") == 61   # Windows pool limit
    assert worker_count(200, tasks=900, platform="linux") == 200
