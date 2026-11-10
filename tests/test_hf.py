import collections
import json

import pyarrow as pa
import pyarrow.parquet as pq

from baike2yomitan.extract_hf import (assign_default_senses, convert, decode_url, extract,
                                      fallback_abstract, is_disambiguation, is_obfuscated,
                                      lemma_id_from_item_url, snapshot_date,
                                      split_repeated_abstract, title_from_url)
from baike2yomitan.records import iter_records


def test_url_decoding_and_lemma_id():
    u = "https://baike.baidu.com/item/%E5%80%92%E5%B8%A6/15216073?fromModule=lemma_sense-layer"
    assert decode_url(u).startswith("https://baike.baidu.com/item/倒带/15216073")
    assert lemma_id_from_item_url(u) == 15216073
    assert lemma_id_from_item_url("https://baike.baidu.com/item/%E4%B8%B0%E9%A2%90/2036679") == 2036679
    assert lemma_id_from_item_url("https://baike.baidu.com/item/%E4%B8%B0%E9%A2%90") is None  # id-less
    assert title_from_url("https://baike.baidu.com/item/%20%E5%86%AF%E8%89%BA/85428") == "冯艺"
    assert snapshot_date(20221129140725) == "2022-11-29"
    assert snapshot_date(None) is None


def test_obfuscation_detector(overlay_by_title):
    spaced = overlay_by_title["金陵十二钗又副册"][0]["content"]
    assert spaced.startswith("总 录 播 报 编 辑")
    assert is_obfuscated(spaced)
    clean = overlay_by_title["东方早报"][0]["content"]
    assert not is_obfuscated(clean)
    # share-of-lone-characters variant without 4 consecutive spaced chars
    assert is_obfuscated("今 天 天气 很 好 我 们 去 公园 玩 了 一 天 真 开 心 啊 哈 哈 哈 哈 哈 哈")
    assert not is_obfuscated("Linux 提供的各种系统调用来实现一个具有两种状态的信号量。")
    assert not is_obfuscated("")


def test_repeated_abstract_exact(overlay_by_title):
    row = [r for r in overlay_by_title["东方早报"] if r["timestamp"] == 20230307034428][0]
    abstract = split_repeated_abstract(row["content"])
    assert abstract is not None
    assert abstract.startswith("《东方早报》是2003年上海文汇新民联合报业集团出版的报刊。")
    assert abstract.endswith("将全部转移到澎湃新闻网。[1]")
    assert "历史沿革" not in abstract  # body not included


def test_repeated_abstract_whitespace_variant(overlay_by_title):
    row = overlay_by_title["丰颐"][0]
    abstract = split_repeated_abstract(row["content"])
    assert abstract == "丰颐，汉语词语，拼音是fēng yí，意思是丰满的下巴，旧时视为有威容。[1]\xa0出自《责须髯奴辞》。"


def test_short_abstract_repeat(overlay_by_title):
    row = overlay_by_title["AI"][0]
    assert split_repeated_abstract(row["content"]) == "AI，是一个复韵母的发音。"


def test_no_repeat_uses_fallback(overlay_by_title):
    row = overlay_by_title["李佳佳"][0]
    assert split_repeated_abstract(row["content"]) is None
    fb = fallback_abstract(row["content"], "李佳佳")
    assert fb.startswith("2011年，参演古装电视剧《西施秘史》。")
    assert "编辑语音" not in fb
    rec = convert(row, collections.Counter(), 300)
    assert rec is not None and "abstract_fallback" in rec.quality_flags
    assert rec.summary == "2011年，参演古装电视剧《西施秘史》。"


def test_disambiguation_pages_dropped(overlay_by_title):
    row = overlay_by_title["李伶"][0]
    assert is_disambiguation(row["content"], "李伶")
    assert not is_disambiguation(overlay_by_title["丰颐"][0]["content"], "丰颐")
    stats = collections.Counter()
    assert convert(row, stats, 300) is None
    assert stats["drop:disambiguation_page"] == 1


def test_convert_fields(overlay_by_title):
    row = [r for r in overlay_by_title["倒带"] if r["subtitle"] == "2012年美国恐怖电影"][0]
    rec = convert(row, collections.Counter(), 300)
    assert rec.source == "hf"
    assert rec.sense_label == "2012年美国恐怖电影"
    assert rec.lemma_id == 15216073
    assert rec.url == "https://baike.baidu.com/item/倒带/15216073"
    assert rec.archive_url.startswith("https://web.archive.org/web/20221129140725/")
    assert rec.snapshot_date == "2022-11-29"
    assert rec.summary.startswith("《倒带》是一部由迈克尔·A·尼克尔斯执导的恐怖片")
    assert "[1]" not in rec.summary and "播报" not in rec.summary
    assert rec.quality_flags == []


def test_default_sense_detection():
    def mk(title, label, idless):
        r = convert({"title": title, "subtitle": label or None, "timestamp": 20220101000000,
                     "base_url": f"https://baike.baidu.com/item/{title}" + ("" if idless else "/123"),
                     "url": "", "archive_url": "a", "content": "这是一个足够长的摘要文本用于测试。 这是一个足够长的摘要文本用于测试。 正文"},
                    collections.Counter(), 300)
        return r

    # id-less URL wins
    a, b = mk("甲", "", False), mk("甲", "第二义项", True)
    assign_default_senses([a, b])
    assert (a.is_default_sense, b.is_default_sense) == (False, True)
    # no id-less capture: nothing says which sense is the main one, not a
    # missing subtitle and not being the only sense captured
    a, b = mk("乙", "义项一", False), mk("乙", "", False)
    assign_default_senses([a, b])
    assert (a.is_default_sense, b.is_default_sense) == (None, None)
    (c,) = [mk("丙", "义项", False)]
    assign_default_senses([c])
    assert c.is_default_sense is None
    d, e = mk("丁", "一", False), mk("丁", "二", False)
    assign_default_senses([d, e])
    assert (d.is_default_sense, e.is_default_sense) == (None, None)


def test_extract_dedupes_and_prefers_clean_newest(overlay_rows, tmp_path):
    pq.write_table(pa.Table.from_pylist(overlay_rows), str(tmp_path / "rows.parquet"), row_group_size=5)
    out = tmp_path / "hf.jsonl"
    stats = extract(str(tmp_path), str(out), progress_every=0)
    recs = list(iter_records(str(out)))
    titles = collections.Counter(r["title"] for r in recs)
    assert titles["李佳明"] == 1  # two snapshots → one record
    assert titles["丰颐"] == 1
    assert titles["倒带"] == 3  # three real senses
    assert titles["李伶"] == 0  # disambiguation page
    assert titles["金陵十二钗又副册"] == 0  # obfuscated, no clean duplicate
    assert stats["drop:obfuscated_no_clean_duplicate"] == 1
    assert stats["drop:disambiguation_page"] >= 1  # 李伶, and one 李佳军 snapshot
    assert titles["李佳军"] == 2  # two different people (ids 19897394 and 22077375), both without a subtitle
    assert stats["dup:lemma_id"] + stats["dup:title_subtitle"] + stats["dup:idless_same_summary"] >= 3
    # 东方早报: (title, None) and (title, subtitle) share lemma 6637501 → folded, subtitle kept
    dfzb = [r for r in recs if r["title"] == "东方早报"]
    assert len(dfzb) == 1 and dfzb[0]["sense_label"] == "2003年上海文汇新民联合报业集团出版报刊"
    assert dfzb[0]["snapshot_date"] == "2023-03-07"  # newest clean snapshot
    assert dfzb[0]["is_default_sense"] is True
    assert all(r["source"] == "hf" for r in recs)


def _snap(title, item_id, content, subtitle=None, ts=20220101000000):
    base = "https://baike.baidu.com/item/" + title + (f"/{item_id}" if item_id else "")
    return {"title": title, "subtitle": subtitle, "timestamp": ts, "base_url": base, "url": "", "archive_url": "a",
            "content": content}


def _extract(rows, tmp_path):
    pq.write_table(pa.Table.from_pylist(rows), str(tmp_path / "rows.parquet"))
    stats = extract(str(tmp_path / "rows.parquet"), str(tmp_path / "hf.jsonl"), progress_every=0)
    return list(iter_records(str(tmp_path / "hf.jsonl"))), stats


def test_links_keep_reserved_characters_encoded():
    assert decode_url("https://baike.baidu.com/item/C%23/195147") == "https://baike.baidu.com/item/C%23/195147"
    assert decode_url("https://baike.baidu.com/item/AC%2FDC/1234") == "https://baike.baidu.com/item/AC%2FDC/1234"
    assert decode_url("https://baike.baidu.com/item/100%25/5678") == "https://baike.baidu.com/item/100%25/5678"
    assert decode_url("https://baike.baidu.com/item/%E4%B8%B0%E9%A2%90/2036679#3") == "https://baike.baidu.com/item/丰颐/2036679"
    assert decode_url("https://baike.baidu.com/item/Guns%20N%27%20Roses") == "https://baike.baidu.com/item/Guns%20N'%20Roses"
    assert title_from_url("https://baike.baidu.com/item/C%23/195147") == "C#" and decode_url(None) == ""


def test_a_list_of_names_is_not_garbled_text():
    page = ("宋史是二十四史之一，收录于《四库全书》史部正史类，由元朝丞相脱脱和阿鲁图先后主持修撰。" * 3
            + " 列传第十七 子 璨 玮 琮 曹彬 潘美 李超 列传第十八 张美 郭守文 尹崇珂 ")
    assert not is_obfuscated(page)
    assert not is_obfuscated("五行是中国古代哲学的一种系统观，指金 木 水 火 土 五种物质的运动变化。")
    assert is_obfuscated("金 陵 十 二 钗 又 副 册 是 红 楼 梦 中 的 人 物 分 类")


def test_an_article_that_opens_with_its_title_and_a_colon_is_not_a_sense_list():
    abstract = "七十子：指的就是孔门七十二贤。七十，是举其成数。"
    page = abstract + " " + abstract + " 七十子解释编辑播报 孔子弟子三千，其中贤者七十二人，后世称为七十子，见于《史记》等书的记载。" * 2
    assert not is_disambiguation(page, "七十子")
    rec = convert(_snap("七十子", 123, page), collections.Counter(), 300)
    assert rec is not None and rec.summary == abstract
    assert is_disambiguation("李伶：重庆医科大学教授 李伶：原第二炮兵政治部文艺创作室主任 李伶：沈阳市苏家屯区副区长", "李伶")


def test_same_title_with_different_ids_stays_two_articles(tmp_path):
    king = "亨利五世（Henry V，1387年—1422年），英格兰兰开斯特王朝国王，在位期间重新发动了百年战争。"
    play = "《亨利五世》是英国剧作家威廉·莎士比亚创作的戏剧，1599年上演，1600年首次出版。"
    rows = [_snap("亨利五世", 1428746, f"{king} {king} 正文", ts=20211101000000),
            _snap("亨利五世", 23221848, f"{play} {play} 正文", ts=20220420000000),
            _snap("亨利五世", 23221848, f"{play} {play} 正文", ts=20210101000000),   # an older snapshot of the play
            _snap("亨利五世", None, f"{king} {king} 正文", ts=20230101000000)]        # the bare title shows the king
    recs, stats = _extract(rows, tmp_path)
    by_id = {r["lemma_id"]: r for r in recs}
    assert sorted(by_id) == [1428746, 23221848]
    assert stats["dup:lemma_id"] == 1 and stats["dup:idless_same_summary"] == 1
    assert by_id[1428746]["is_default_sense"] is True and by_id[1428746]["snapshot_date"] == "2023-01-01"
    assert by_id[23221848]["is_default_sense"] is False and by_id[23221848]["snapshot_date"] == "2022-04-20"
    assert by_id[1428746]["url"].endswith("/item/亨利五世/1428746")


def test_a_clean_snapshot_beats_a_garbled_one_that_has_a_subtitle(tmp_path):
    clean = "丧，汉语一级字，读作sāng或sàng，最早见于甲骨文，本义是丢掉、失去。"
    garbled = "丧 ， 汉 语 一 级 字 ， 读 作 s ā n g 或 s à n g ， 最 早 见 于 甲 骨 文 。"
    rows = [_snap("丧", 99, f"{garbled} {garbled} 正 文", subtitle="汉语汉字", ts=20240101000000),
            _snap("丧", 99, f"{clean} {clean} 正文", ts=20220101000000)]
    recs, stats = _extract(rows, tmp_path)
    assert len(recs) == 1 and recs[0]["summary"] == clean and recs[0]["sense_label"] == "汉语汉字"
    assert stats["drop:obfuscated_no_clean_duplicate"] == 0


def test_interface_words_stay_headwords_in_the_overlay():
    text = "编辑，是对资料或现成的作品进行整理、加工的工作，也指从事这种工作的人。"
    rec = convert(_snap("编辑", 535978, f"{text} {text} 正文"), collections.Counter(), 300)
    assert rec.title == "编辑" and rec.summary == text
