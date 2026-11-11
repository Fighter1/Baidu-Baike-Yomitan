"""Injected characters: the shipped data and the way it is learned."""
import json

import pyarrow as pa
import pyarrow.parquet as pq

from baike2yomitan import junk


def test_real_text_has_nothing_injected():
    for text in ("他承担了全部责任，并拒绝了对方提出的要求。",
                 "正态分布概念是由法国数学家棣莫弗（Abraham de Moivre）于1733年首次提出的。",
                 "20世纪80年代，随着改革开放，这里建起了第一座工厂。",
                 "析构函数与构造函数相反，当对象结束其生命周期时，系统会自动执行析构函数。"):
        assert junk.injected(text) == "", text


def test_injected_characters_are_found():
    # inside a Latin word or a year a Chinese character can only have been put there
    assert junk.injected("2020年10月24日是第一个世界袋鼠日（Wor去乌ld Kangaroo Day）。") == "inside_word"
    assert junk.injected("王子文，20验旬请19年出演个人首部电视剧作品。") == "inside_word"
    # two characters of the pool that real text never has side by side
    assert junk.injected("验颈遥写书生刘彦昌与华山圣母结亲，生子沉香。") == "颈遥"
    assert junk.injected("通过对外直接投资或收购当地企业的方式，在许多国家建榆煮立子公司。") != ""


def test_known_headings_come_from_the_pages_with_sections():
    known = junk.known_headings()
    assert {"歌曲歌词", "所获荣誉", "人物经历", "内容简介", "解释"} <= known
    assert "该剧讲述" not in known and "中国古代" not in known


def test_learning_writes_pool_pairs_and_headings(tmp_path, monkeypatch):
    spaced = " ".join("解释播报编辑" + "this wor去乌ld is big。" * 2 + "出处播报编辑某书。")
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    pq.write_table(pa.Table.from_pylist([{"content": spaced}] * 25 + [{"content": "一篇没有空格的普通文章，不参与学习。"}]),
                   str(overlay / "0000.parquet"))
    records = tmp_path / "records.jsonl"
    lines = [{"summary": "他的去向不明，乌云密布。"}, {"summary": "去乌鲁木齐的路上。"}, {"summary": "他从上海去乌镇。"}] * 4
    records.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in lines), encoding="utf-8")
    out = tmp_path / "learned.txt"
    try:
        stats = junk.learn(str(overlay), str(records), str(out), log=lambda *_: None)
    finally:
        junk._data.cache_clear()
    fields = dict(line.rstrip("\n").split("\t", 1) for line in out.read_text(encoding="utf-8").splitlines() if "\t" in line)
    assert stats["pages"] == 25
    assert fields["pool"] == "乌去"                 # seen inside "world" 50 times
    assert fields["pairs"] == "去乌"                # the 2019 text has 去乌 (去乌鲁木齐), never 乌去
    assert fields["headings"].split(" ") == ["出处", "解释"]
    assert junk.known_headings() and "解释" in junk.known_headings()      # the shipped file is in use again
