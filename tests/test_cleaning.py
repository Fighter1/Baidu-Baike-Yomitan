from baike2yomitan.cleaning import (clean_text, first_paragraph, strip_citations,
                                    summary_drop_reason, title_drop_reason, trim_summary)


def test_strip_citation_markers():
    assert strip_citations("行动[1-2]\xa0展开。[3] 要求[7]\xa0。") == "行动\xa0展开。 要求\xa0。"
    assert strip_citations("修订［12］法") == "修订法"


def test_clean_text_full_pass():
    s = "“一盔一带”安全守护行动指的是公安部…行动。[1-2]\xa02020年5月20日，公安部要求。[3]　编辑播报 zhua曲子白渡白颗"
    assert clean_text(s) == "“一盔一带”安全守护行动指的是公安部…行动。2020年5月20日，公安部要求。"


def test_ui_labels_only_stripped_at_edges_or_as_compounds():
    # 编辑 is also an ordinary word: keep it when it is part of the prose
    assert clean_text("编辑，是对资料或现成的作品进行整理") == "编辑，是对资料或现成的作品进行整理"
    assert clean_text("编辑 播报 正文开始。 播报") == "正文开始。"
    assert clean_text("东方早报历史沿革编辑播报 东方早报标识") == "东方早报历史沿革东方早报标识"


def test_gallery_captions_removed():
    assert clean_text("主演山下智久剧集截图(20张)感冒就医的田村希美") == "感冒就医的田村希美"
    assert clean_text("合并图册(2张)1931年9月18日") == "1931年9月18日"


def test_whitespace_normalization():
    assert clean_text("词　目  反手可得 \xa0") == "词目反手可得"
    assert clean_text("One apple a day\n keeps") == "One apple a day keeps"
    # a space between a CJK character and a latin word is kept
    assert clean_text("约翰尼·帕卡 Johnny Pacar、Ambyr Childers") == "约翰尼·帕卡 Johnny Pacar、Ambyr Childers"


def test_literal_backslash_n_is_a_line_break():
    assert clean_text("词语信息\\n【拼音】zhàng fū") == "词语信息【拼音】zhàng fū"
    assert first_paragraph("first\\nsecond") == "first"
    assert first_paragraph("\n\n  first \nsecond") == "first"
    assert first_paragraph(None) == ""


def test_trim_summary_cuts_at_sentence_boundary():
    text = "红色食品是指红色的食品。科学家认为多吃红色食品可预防感冒。红色食品有红柿椒、西红柿、胡萝卜等。"
    out = trim_summary(text, 30)
    assert out == "红色食品是指红色的食品。科学家认为多吃红色食品可预防感冒。"
    assert trim_summary(text, 1000) == text


def test_trim_summary_hard_cut_when_no_boundary():
    text = "一" * 50
    out = trim_summary(text, 20)
    assert out == "一" * 20 + "…"
    # boundary only in the first third of the window is ignored (would cut too much)
    text = "短。" + "一" * 60
    assert trim_summary(text, 30).endswith("…")


def test_drop_rules():
    assert summary_drop_reason("太短") == "summary_too_short"
    assert summary_drop_reason("一" * 15) is None
    assert title_drop_reason("") == "title_empty"
    assert title_drop_reason("一" * 31) == "title_too_long"
    assert title_drop_reason("红色食品") is None
