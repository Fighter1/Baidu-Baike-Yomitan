import collections
import json
import os

from baike2yomitan.extract_563w import (convert, detect_layout, extract, iter_raw,
                                        lemma_id_from_url, find_infobox, parse_infobox)
from baike2yomitan.records import iter_records
from baike2yomitan.sense import is_descriptor


def test_lemma_id_strips_zero_padding():
    assert lemma_id_from_url("http://baike.baidu.com/view/0010.htm") == 10
    assert lemma_id_from_url("http://baike.baidu.com/view/10.htm") == 10
    assert lemma_id_from_url("http://baike.baidu.com/view/03028134.htm") == 3028134
    assert lemma_id_from_url("http://baike.baidu.com/item/xxx") is None
    assert lemma_id_from_url(None) is None


def test_zero_padding_duplicates_fold_on_extract(fixture_563w_path, tmp_path):
    out = tmp_path / "records.jsonl"
    stats = extract(fixture_563w_path, str(out), progress_every=0)
    recs = list(iter_records(str(out)))
    hong = [r for r in recs if r["title"] == "红色食品"]
    assert len(hong) == 1, "view/0010.htm and view/10.htm must collapse to one record"
    assert hong[0]["lemma_id"] == 10
    assert hong[0]["url"] == "https://baike.baidu.com/view/10.htm"
    assert stats["drop:dup_lemma_id"] == 1
    assert stats["layout:jsonl"] == 1
    assert all(r["source"] == "563w" and r["is_default_sense"] is None for r in recs)


def test_summary_falls_back_to_first_section(rows_563w_by_title):
    raw = rows_563w_by_title["费萨尔一世"][0]
    assert raw["summary"] is None
    stats = collections.Counter()
    rec = convert(raw, stats, 300, want_infobox=True)
    assert rec is not None
    assert rec.summary.startswith("费萨尔·伊本·侯赛因")
    assert "summary_from_section" in rec.quality_flags
    assert stats["flag:summary_from_section"] == 1


def test_summary_field_used_when_present(rows_563w_by_title):
    raw = rows_563w_by_title["丈夫"][0]
    rec = convert(raw, collections.Counter(), 300, want_infobox=True)
    assert rec.summary.startswith("丈夫，zhàng fū")
    assert "summary_from_section" not in rec.quality_flags
    assert rec.sense_label == ""  # first section is 词语, a generic heading
    assert rec.tags == ["台湾", "文学作品", "陈朱煌导演作品"]  # kept for filtering only


def test_summary_trimmed_at_sentence_boundary(rows_563w_by_title):
    raw = rows_563w_by_title["舍利子"][0]
    rec = convert(raw, collections.Counter(), 100, want_infobox=False)
    assert len(rec.summary) <= 100
    assert rec.summary.endswith("。")


def test_descriptor_heuristic_positive(rows_563w_by_title):
    raw = rows_563w_by_title["李永赋"][0]
    assert raw["sections"][0]["title"] == "云南晋宁县公安局副局长"
    rec = convert(raw, collections.Counter(), 300, want_infobox=False)
    assert rec.sense_label == "云南晋宁县公安局副局长"
    assert is_descriptor("2012年美国恐怖电影", "倒带")
    assert is_descriptor("日本商业区", "银座")
    assert is_descriptor("淮海工学院教授", "曹伟平")
    # 汉语词语 as a *section heading* is treated as generic (the overlay carries
    # it as a real subtitle instead, which bypasses this heuristic)
    assert not is_descriptor("汉语词语", "丰颐")


def test_descriptor_heuristic_negative(rows_563w_by_title):
    for heading in ["简介", "基本信息", "词语", "重要参数", "基本概念", "制作材料", "材料:",
                    "iPhone软件信息", "VNX5300简介", "主要景点", "1明朝山水画家", "C8-10酸：", ""]:
        assert not is_descriptor(heading, "某词条"), heading
    # heading equal to or containing the title
    raw = rows_563w_by_title["大魔王复仇计划"][0]
    assert raw["sections"][0]["title"] == "大魔王复仇计划"
    rec = convert(raw, collections.Counter(), 300, want_infobox=False)
    assert rec is None or rec.sense_label == ""
    assert not is_descriptor("太极正念的源起", "太极正念疗法")
    assert not is_descriptor("SSK 立方 SHU014产品类别", "SSK 立方 SHU014")


def test_infobox_pairs(rows_563w_by_title):
    raw = rows_563w_by_title["了解市场必读"][0]
    # the 基本信息 section here is one line of "k: v; k: v", not k：v lines → None
    assert parse_infobox(raw["sections"]) is None
    sections = [{"title": "基本信息", "content": "中文名：示例\\n外文名：Example\\n类型：测试\\n作者：甲\\n出版社：乙\\n页数：10\\n定价：1"}]
    box = parse_infobox(sections)
    assert box == [["中文名", "示例"], ["外文名", "Example"], ["类型", "测试"], ["作者", "甲"], ["出版社", "乙"], ["页数", "10"]]


def _yu_hua(n_before):
    """The writer's article, then the info section of a rower of the same name."""
    writer = [{"title": t, "content": "余华的成名作是短篇小说《十八岁出门远行》，此后接连发表了多篇实验性极强的作品。"}
              for t in ("简介", "创作", "特点", "作品")[:n_before]]
    rower = [{"title": "基本信息", "content": "姓名：余华\n性别： 女 \n出生日期：1981-01-19\n出生地：北京\n身高：175cm"},
             {"title": "主要成绩", "content": "2006年世界赛艇锦标赛女子轻量级四人双桨冠军。"}]
    return {"title": "余华", "summary": "余华，当代作家，浙江海盐县人，祖籍山东高唐县。著有长篇小说《活着》《许三观卖血记》。",
            "tags": [], "url": "http://baike.baidu.com/view/3837.htm", "sections": writer + rower}


def test_info_table_is_only_taken_from_the_top_of_the_page():
    # after four sections of another article the table is someone else's
    stats = collections.Counter()
    rec = convert(_yu_hua(4), stats, 300, want_infobox=True)
    assert rec.infobox is None and rec.summary.startswith("余华，当代作家")
    assert "infobox_below_top_skipped" in rec.quality_flags and stats["flag:infobox_below_top_skipped"] == 1
    assert find_infobox(_yu_hua(2)["sections"]) == (None, True)
    # first section, or second after an introduction: the page's own table
    for n in (0, 1):
        stats = collections.Counter()
        rec = convert(_yu_hua(n), stats, 300, want_infobox=True)
        assert rec.infobox[:2] == [["姓名", "余华"], ["性别", "女"]] and "infobox_below_top_skipped" not in rec.quality_flags
    # a section further down that is not a table is not counted as one passed over
    prose = {"title": "基本信息", "content": "余华的小说以冷峻的笔调著称。"}
    assert find_infobox([{"title": "简介", "content": "甲"}, {"title": "创作", "content": "乙"}, prose]) == (None, False)
    # of a table that is passed over, a row with the title's reading stays: it is right for every article of the page
    raw = _yu_hua(4)
    raw["sections"][4]["content"] += "\n拼音：yú huá"
    assert find_infobox(raw["sections"]) == ([["拼音", "yú huá"]], True)
    rec = convert(raw, collections.Counter(), 300, want_infobox=True)
    assert rec.infobox == [["拼音", "yú huá"]] and "infobox_below_top_skipped" in rec.quality_flags
    # the reading of some other title is the unrelated page's and goes with the rest
    raw = _yu_hua(4)
    raw["sections"][4]["content"] += "\n拼音名：Baihua Huoxue Dieda Gao"
    assert find_infobox(raw["sections"]) == ([["拼音名", "Baihua Huoxue Dieda Gao"]], True)
    rec = convert(raw, collections.Counter(), 300, want_infobox=True)
    assert rec.infobox is None and "infobox_below_top_skipped" in rec.quality_flags
    # nothing is flagged when info tables are not wanted
    assert "infobox_below_top_skipped" not in convert(_yu_hua(4), collections.Counter(), 300, want_infobox=False).quality_flags


def test_short_summary_rescued_from_first_section():
    raw = {"title": "际遇", "summary": "拼音（jì yù)", "tags": [], "url": "http://baike.baidu.com/view/1.htm",
           "sections": [{"title": "基本信息", "content": "际遇，汉语词语，意思是遭遇、时运，多指好的境遇。"}]}
    stats = collections.Counter()
    rec = convert(raw, stats, 300, want_infobox=False)
    assert rec is not None and rec.summary.startswith("际遇，汉语词语")
    assert stats["flag:summary_from_section_after_short_summary"] == 1


def test_drops_counted(rows_563w_by_title):
    stats = collections.Counter()
    assert convert({"title": "", "summary": "x" * 30, "sections": [], "tags": [], "url": None}, stats, 300, False) is None
    assert convert({"title": "一" * 31, "summary": "x" * 30, "sections": [], "tags": [], "url": None}, stats, 300, False) is None
    assert convert({"title": "甲", "summary": None, "sections": [], "tags": [], "url": None}, stats, 300, False) is None
    assert convert({"title": "乙", "summary": "短", "sections": [], "tags": [], "url": None}, stats, 300, False) is None
    assert stats["drop:title_empty"] == 1
    assert stats["drop:title_too_long"] == 1
    assert stats["drop:no_summary_no_sections"] == 1
    assert stats["drop:summary_too_short"] == 1


def test_layout_detection_and_array_streaming(tmp_path, rows_563w):
    jl = tmp_path / "a.jsonl"
    jl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows_563w[:3]) + "\n", encoding="utf-8")
    assert detect_layout(str(jl)) == "jsonl"
    arr = tmp_path / "b.json"
    arr.write_text(json.dumps(rows_563w[:3], ensure_ascii=False), encoding="utf-8")
    assert detect_layout(str(arr)) == "array"
    assert [r["title"] for r in iter_raw(str(arr))] == [r["title"] for r in rows_563w[:3]]
