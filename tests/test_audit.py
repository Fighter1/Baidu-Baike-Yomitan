"""Quality audit: golden-word checks and rates over a built zip."""
import collections

import pytest

from baike2yomitan.audit import audit, entry_parts, format_report, load_golden
from baike2yomitan.build import build
from baike2yomitan.cli import main
from baike2yomitan.records import Record, RecordWriter


def _rec(title, lid, summary, label="", default=None, tags=None):
    return Record(source="563w", title=title, summary=summary, sense_label=label, lemma_id=lid,
                  is_default_sense=default, tags=tags or [], url=f"https://baike.baidu.com/view/{lid}.htm")


RECORDS = [
    _rec("时间", 1, "时间，读音shí jiān，汉语词语，指时间的单位。", label="汉语词汇"),
    _rec("时间", 2, "《时间》是由韩三平监制《玫瑰行者》的插曲，宋祺作词、作曲，王晰演唱。"),
    _rec("时间", 3, "时间（Time）是物质的永恒运动、变化的持续性、顺序性的表现。", label="物理量"),
    _rec("北京", 4, "沃罗比约夫以北京冬奥会为主题的俄语歌曲《北京》。", label="俄语歌曲", default=True),   # a work on top
    _rec("北京", 5, "北京（Beijing），简称“京”，是中华人民共和国的首都、直辖市。", label="中华人民共和国首都"),
    _rec("保险单", 6, "保险单简称“保单”。保险人与投保人签订保险合同的书面证明，是保险合同的正式文件。"),
    _rec("保险单", 7, "保险单简称“保单”。保险人与投保人签订保险合同的书面证明，是保险合同的正式文件。"),  # the same sense twice
    _rec("里面", 8, "里面，汉语词语，意思是内部，与“外面”相对。"),
    _rec("旗幅", 9, "qí fú ㄑㄧˊ ㄈㄨˊ 旗幅"),
    _rec("省力", 10, "2. 节约劳动力,减少劳动力的消耗"),
    _rec("板儿砖", 11, "究其发源地听说是北京新街口的爷们儿为了叫起来顺嘴总不能叫“我开你一砖"),
]


@pytest.fixture
def zip_path(tmp_path, monkeypatch):
    monkeypatch.setattr("baike2yomitan.report.STATS_DIR", str(tmp_path / "stats"))
    with RecordWriter(str(tmp_path / "r.jsonl")) as w:
        for r in RECORDS:
            w.write(r)
    out = tmp_path / "baike-full.zip"
    build(str(tmp_path / "r.jsonl"), str(out), pinyin=True, traditional="s2tw", pinyin_overrides=None)
    return str(out)


def _golden(tmp_path, text):
    p = tmp_path / "golden.tsv"
    p.write_text(text, encoding="utf-8")
    return load_golden(str(p))


def test_golden_checks(zip_path, tmp_path):
    golden = _golden(tmp_path, """# word, check, value, scope
时间\tfirst_not_work
时间\tfirst\t汉语词语
时间\tany\t物理量
时间\treading\tshí jiān
时间\tfirst_reading\tshí jiān
里面\ttraditional\t裡面
里面\tpresent
没有这个词\tabsent
保险单\tsenses_max\t2
里面\tends\t相对。
只在小词典\tpresent\t\tlexical
""")
    stats, failures = audit(zip_path, golden)
    assert failures == [] and stats["golden_checks"] == 10 and stats["golden_failures"] == 0   # the lexical-only line is not checked


def test_golden_failures_say_what_was_found(zip_path, tmp_path):
    golden = _golden(tmp_path, "北京\tfirst_not_work\n保险单\tsenses_max\t1\n潇洒\tpresent\n时间\treading\tshí jiàn\n"
                               "里面\ttraditional\t裏面\n板儿砖\tends\t挺顺嘴儿的。\n里面\tabsent\n北京\tfirst\t首都\n")
    _, failures = audit(zip_path, golden)
    text = "\n".join(failures)
    assert len(failures) == 8
    assert "first sense is a work" in text and "2 senses" in text and "潇洒  present  (line 3): not in the dictionary" in text
    assert "readings [\'shí jiān\']" in text and "other spellings [\'裡面\']" in text and "我开你一砖" in text


def test_several_processes_and_small_term_banks_give_the_same_answer(tmp_path, monkeypatch):
    # banks of two rows: senses straddle bank boundaries, and their traditional row opens the next bank
    monkeypatch.setattr("baike2yomitan.report.STATS_DIR", str(tmp_path / "stats"))
    monkeypatch.setattr("baike2yomitan.build.BANK_SIZE", 2)
    with RecordWriter(str(tmp_path / "r.jsonl")) as w:
        for r in RECORDS:
            w.write(r)
    out = str(tmp_path / "baike-full.zip")
    build(str(tmp_path / "r.jsonl"), out, pinyin=True, traditional="s2tw", pinyin_overrides=None)
    golden = _golden(tmp_path, "里面\ttraditional\t裡面\n时间\tfirst_not_work\n保险单\tsenses_max\t2\n板儿砖\ttraditional\t板兒磚\n")
    one, fail_one = audit(out, golden, workers=1)
    three, fail_three = audit(out, golden, workers=3)
    assert one == three and fail_one == fail_three == []
    assert (one["headwords"], one["senses"], one["rows"]) == (7, 11, 18)
    assert one["headwords_with_a_repeated_sense"] == 1 and one["headwords_with_several_senses"] == 3


def test_rates(zip_path):
    stats, _ = audit(zip_path, [])
    assert (stats["headwords"], stats["senses"], stats["rows"]) == (7, 11, 18)   # seven senses also have a traditional row
    assert stats["headwords_with_several_senses"] == 3 and stats["senses_of_headwords_with_several"] == 7
    assert stats["headwords_whose_first_sense_is_a_work"] == 1          # 北京
    assert stats["headwords_with_a_work_above_another_sense"] == 1
    assert stats["headwords_with_a_repeated_sense"] == 1                # 保险单
    assert stats["of_those_without_a_label"] == 3                       # the 时间 song and both 保险单
    assert stats["summaries_that_say_nothing"] == 1 and stats["summaries_starting_mid_list"] == 1
    assert stats["summaries_cut_inside_a_quote"] == 1 and stats["senses_without_a_reading"] == 0
    assert stats["scope"] == "full"
    report = format_report(stats, ["x  present  (line 1): not in the dictionary"])
    assert "7 headwords, 11 senses, 18 rows" in report and "FAILED  x  present" in report


def test_entry_parts_reads_the_labelled_blocks():
    content = [{"type": "structured-content", "content": [
        {"tag": "div", "data": {"baike": "terms"}, "content": [
            {"tag": "span", "data": {"baike": "traditional-term"}, "content": "裡面"},
            {"tag": "span", "data": {"baike": "simplified-term"}, "content": "里面"}]},
        {"tag": "div", "data": {"baike": "sense-label"}, "content": "汉语词语"},
        {"tag": "div", "data": {"baike": "summary"}, "content": "内部。"}]}]
    assert entry_parts(content) == {"traditional-term": "裡面", "simplified-term": "里面", "sense-label": "汉语词语", "summary": "内部。"}
    assert entry_parts(["plain definition"]) == {}


def test_golden_file_errors(tmp_path):
    for bad in ("时间\tfirst\n", "时间\tlooks_good\n", "时间 present\n", "时间\tpresent\t\tmedium\n", "保险单\tsenses_max\tfew\n"):
        with pytest.raises(ValueError):
            _golden(tmp_path, bad)
    assert _golden(tmp_path, "\n# only a comment\n") == []


def test_audit_command(zip_path, tmp_path, capsys):
    ok = tmp_path / "ok.tsv"
    ok.write_text("时间\tfirst_not_work\n", encoding="utf-8")
    assert main(["audit", zip_path, "--golden", str(ok)]) == 0
    assert "golden words: 1 of 1 checks hold" in capsys.readouterr().out
    bad = tmp_path / "bad.tsv"
    bad.write_text("北京\tfirst_not_work\n", encoding="utf-8")
    assert main(["audit", zip_path, "--golden", str(bad)]) == 1
    assert "AUDIT FAILED" in capsys.readouterr().out
    assert main(["audit", zip_path, "--golden", str(tmp_path / "missing.tsv")]) == 2
    assert main(["audit", zip_path, "--no-golden"]) == 0
    assert (tmp_path / "stats" / "audit_baike-full.json").exists()


def test_the_shipped_golden_file_parses():
    golden = load_golden()
    assert len(golden) >= 20 and collections.Counter(g["scope"] for g in golden)[""] > 0
