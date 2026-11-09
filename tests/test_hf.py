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
    # else the sense with no subtitle
    a, b = mk("乙", "义项一", False), mk("乙", "", False)
    assign_default_senses([a, b])
    assert (a.is_default_sense, b.is_default_sense) == (False, True)
    # neither: a single sense is default, several are all False
    (c,) = [mk("丙", "义项", False)]
    assign_default_senses([c])
    assert c.is_default_sense is True
    d, e = mk("丁", "一", False), mk("丁", "二", False)
    assign_default_senses([d, e])
    assert (d.is_default_sense, e.is_default_sense) == (False, False)


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
    assert titles["李佳军"] == 1
    assert stats["dup:title_subtitle"] >= 3
    # 东方早报: (title, None) and (title, subtitle) share lemma 6637501 → folded, subtitle kept
    dfzb = [r for r in recs if r["title"] == "东方早报"]
    assert len(dfzb) == 1 and dfzb[0]["sense_label"] == "2003年上海文汇新民联合报业集团出版报刊"
    assert dfzb[0]["snapshot_date"] == "2023-03-07"  # newest clean snapshot
    assert dfzb[0]["is_default_sense"] is True
    assert all(r["source"] == "hf" for r in recs)
