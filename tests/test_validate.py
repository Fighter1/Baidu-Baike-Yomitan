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


def _term_zip(tmp_path, rows, name="d.zip"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("index.json", json.dumps(INDEX))
        for i in range(0, len(rows), 3):
            zf.writestr(f"term_bank_{i // 3 + 1}.json", json.dumps(rows[i:i + 3], ensure_ascii=False))
    return str(path)


def _entry(term, content, href="https://baike.baidu.com/view/1.htm", seq=1):
    return [term, "", "", "", 0, [{"type": "structured-content", "content": [
        {"tag": "div", "data": {"baike": "summary"}, "content": content},
        {"tag": "div", "style": {"fontSize": "80%"}, "content": [{"tag": "a", "href": href, "content": "百度百科"}]}]}], seq, ""]


def test_content_shape_blanks_only_what_the_schema_ignores():
    from baike2yomitan.validate import content_shape

    a, b = _entry("甲", "第一条的文字")[5], _entry("乙", "完全不同的另一段文字", href="http://example.org/x")[5]
    assert content_shape(a)[0]["content"][0] == {"tag": "div", "data": {"baike": ""}, "content": ""}
    assert content_shape(a)[0]["content"][1]["content"][0]["href"] == "https:"
    assert content_shape(a) != content_shape(b)                       # http: and https: are different shapes
    assert content_shape(a) == content_shape(_entry("丙", "又一段")[5])  # same structure, other text
    assert content_shape(["plain text", ["form", ["rule"]]]) == ["", ["", [""]]]


@pytest.mark.parametrize("workers", [1, 2])
def test_shape_mode_agrees_with_the_whole_schema(tmp_path, workers):
    good = [_entry(f"词{i}", f"第{i}条的释义，各不相同。", seq=i) for i in range(12)]
    path = _term_zip(tmp_path, good)
    assert validate_zip(path, SCHEMA_DIR, workers=workers, mode="shape") == []
    assert validate_zip(path, SCHEMA_DIR, workers=workers, mode="full") == []
    # every kind of fault the schema can find, each in a bank the shape mode does not check in full
    faults = {
        "tag": lambda e: e[5][0]["content"][0].__setitem__("tag", "blink"),
        "style": lambda e: e[5][0]["content"][1]["style"].__setitem__("textAlign", "sideways"),
        "href": lambda e: e[5][0]["content"][1]["content"][0].__setitem__("href", "javascript:alert(1)"),
        "content type": lambda e: e[5][0]["content"][0].__setitem__("content", 5),
        "definition type": lambda e: e[5][0].__setitem__("type", "html"),
        "score": lambda e: e.__setitem__(4, "high"),
        "sequence": lambda e: e.__setitem__(6, "7"),
        "term": lambda e: e.__setitem__(0, None),
        "length": lambda e: e.append("extra"),
    }
    for label, damage in faults.items():
        rows = [_entry(f"词{i}", f"第{i}条的释义。", seq=i) for i in range(12)]
        damage(rows[4])                                    # term_bank_2 of four: not in the full sample
        path = _term_zip(tmp_path, rows, f"{label.replace(' ', '_')}.zip")
        by_shape = validate_zip(path, SCHEMA_DIR, workers=workers, mode="shape")
        in_full = validate_zip(path, SCHEMA_DIR, workers=workers, mode="full")
        assert by_shape and in_full, label
        assert all(e.startswith("term_bank_2.json") for e in by_shape + in_full), label
        assert "entry 1" in by_shape[0], label


def test_validate_mode_is_checked():
    with pytest.raises(ValueError):
        validate_zip("nowhere.zip", SCHEMA_DIR, mode="quick")
