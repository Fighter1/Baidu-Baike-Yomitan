import collections
import json
import os
import zipfile

import pytest

from baike2yomitan.build import TITLE_FULL, TITLE_LEX, Traditional, build, default_title, structured_content
from baike2yomitan.merge import merge
from baike2yomitan.records import Record, RecordWriter, iter_records
from baike2yomitan.sense import sense_rank_key
from baike2yomitan.validate import flatten_content, smoke, validate_zip

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "schemas")


def _write(path, recs):
    with RecordWriter(str(path)) as w:
        for r in recs:
            w.write(r)


def _primary(title, lid, summary, label="", flags=None, tags=None):
    return Record(source="563w", title=title, summary=summary, sense_label=label, lemma_id=lid,
                  tags=tags or [], url=f"https://baike.baidu.com/view/{lid}.htm", quality_flags=flags or [])


def _overlay(title, lid, summary, label="", flags=None, default=None):
    return Record(source="hf", title=title, summary=summary, sense_label=label, lemma_id=lid,
                  is_default_sense=default, url=f"https://baike.baidu.com/item/{title}/{lid}" if lid else None,
                  archive_url="https://web.archive.org/web/20221021140128/x", snapshot_date="2022-10-21",
                  quality_flags=flags or [])


def test_merge_by_title(tmp_path):
    _write(tmp_path / "p.jsonl", [
        _primary("倡佯", 910001, "旧摘要旧摘要旧摘要旧摘要旧摘要旧摘要。", flags=["summary_from_section"]),
        _primary("丈夫", 6236, "丈夫，zhàng fū，一般用作名词，已婚女子的配偶。", label="已有标签"),
        _primary("孤儿", 1, "没有覆盖记录的主记录，保持不变不变不变。"),
        _primary("脏", 2, "被不干净的覆盖记录匹配到的主记录应保持原样。"),
        _primary("多义", 3, "主记录里本身就有两个义项的标题，不刷新。"),
        _primary("多义", 4, "主记录里本身就有两个义项的标题，第二条。"),
        _primary("歧义", 5, "覆盖里有两个义项但没有默认义项，不刷新。"),
    ])
    _write(tmp_path / "o.jsonl", [
        # ids deliberately differ from the primary's: they are different id spaces
        _overlay("倡佯", 77, "倡佯，读音chàng yáng，汉语词语，意思为自在纵情貌。", label="汉语词语", default=True),
        _overlay("丈夫", 88, "新摘要新摘要新摘要新摘要新摘要新摘要。", label="覆盖标签", default=True),
        _overlay("丈夫", 89, "《丈夫》是一部电影，作为额外义项加入。", label="电影", default=False),
        _overlay("脏", 99, "这条摘要来自回退路径，不能用于刷新主记录。", flags=["abstract_fallback"], default=True),
        _overlay("新词", 999, "主记录里没有的词条，应作为新记录加入。", label="网络用语", default=True),
        _overlay("无号", None, "没有编号的覆盖记录也作为新记录加入。", default=True),
        _overlay("多义", 11, "覆盖的默认义项，但主记录有两条，所以只能新增。", default=True),
        _overlay("歧义", 12, "义项甲义项甲义项甲义项甲义项甲。", label="甲", default=False),
        _overlay("歧义", 13, "义项乙义项乙义项乙义项乙义项乙。", label="乙", default=False),
    ])
    stats = merge(str(tmp_path / "p.jsonl"), str(tmp_path / "o.jsonl"), str(tmp_path / "m.jsonl"))
    recs = list(iter_records(str(tmp_path / "m.jsonl")))
    by = collections.defaultdict(list)
    for r in recs:
        by[r["title"]].append(r)
    assert stats["refreshed"] == 2
    assert stats["skipped_primary_title_ambiguous"] == 2      # 多义 ×2
    assert stats["skipped_overlay_ambiguous_or_unclean"] == 2  # 脏 (unclean), 歧义 (no default)
    assert stats["added_new_title"] == 2 and stats["added_without_key"] == 0  # 新词, 无号 (title is the key)
    assert stats["added_extra_sense_of_known_title"] == 5      # 丈夫/电影, 脏, 多义, 歧义 ×2
    r = by["倡佯"][0]
    assert r["source"] == "563w+hf" and r["summary"].startswith("倡佯，读音")
    assert r["sense_label"] == "汉语词语"          # filled because primary's was empty
    assert r["lemma_id"] == 910001                 # primary id kept: id spaces differ
    assert r["snapshot_date"] == "2022-10-21" and r["archive_url"]
    assert r["is_default_sense"] is True
    assert "summary_from_section" not in r["quality_flags"] and "summary_refreshed" in r["quality_flags"]
    zf = {r["source"]: r for r in by["丈夫"]}
    assert zf["563w+hf"]["sense_label"] == "已有标签"  # not overwritten
    assert zf["hf"]["sense_label"] == "电影"
    assert [r["source"] for r in by["脏"]] == ["563w", "hf"] and by["脏"][0]["summary"].startswith("被不干净")
    assert len(by["多义"]) == 3 and len(by["歧义"]) == 3 and len(by["新词"]) == 1 and len(by["无号"]) == 1
    assert stats["records_written"] == 7 + 7


def test_merge_by_lemma_id_option(tmp_path):
    _write(tmp_path / "p.jsonl", [_primary("甲", 1, "旧摘要旧摘要旧摘要旧摘要旧摘要旧摘要。")])
    _write(tmp_path / "o.jsonl", [_overlay("甲", 1, "新摘要新摘要新摘要新摘要新摘要新摘要。", default=True),
                                  _overlay("乙", 2, "另一条另一条另一条另一条另一条另一条。", default=True)])
    stats = merge(str(tmp_path / "p.jsonl"), str(tmp_path / "o.jsonl"), str(tmp_path / "m.jsonl"), key="lemma_id")
    recs = list(iter_records(str(tmp_path / "m.jsonl")))
    assert stats["refreshed"] == 1 and stats["added"] == 1 and len(recs) == 2
    assert recs[0]["summary"].startswith("新摘要")


def test_sense_ranking():
    a = {"lemma_id": 50, "quality_flags": [], "is_default_sense": None}
    b = {"lemma_id": 10, "quality_flags": ["summary_from_section"], "is_default_sense": None}
    c = {"lemma_id": 70, "quality_flags": [], "is_default_sense": None}
    d = {"lemma_id": 99, "quality_flags": [], "is_default_sense": True}
    assert sorted([a, b, c, d], key=sense_rank_key) == [d, a, c, b]


def test_structured_content_order_and_footer():
    rec = {"title": "丰颐", "sense_label": "汉语词语", "summary": "丰颐，汉语词语。", "url": "https://baike.baidu.com/view/1.htm",
           "archive_url": "https://web.archive.org/web/2022/x", "snapshot_date": "2022-10-23",
           "tags": ["a", "b", "c", "d", "e", "f", "g"], "infobox": [["中文名", "丰颐"], ["拼音", "fēng yí"]]}
    sc = structured_content(rec, want_infobox=True)
    kinds = [p["data"]["baike"] for p in sc["content"]]
    assert kinds == ["sense-label", "summary", "infobox", "footer"]
    text = flatten_content(sc)
    assert "标签：a、b、c、d、e" in text and "、f" not in text  # at most five tags
    assert "存档 2022-10-23" in text and "百度百科" in text
    hrefs = [n["href"] for n in sc["content"][-1]["content"] if isinstance(n, dict)]
    assert hrefs == [rec["url"], rec["archive_url"]]
    # a sense label identical to the title is not rendered
    rec2 = dict(rec, sense_label="丰颐", infobox=None)
    assert [p["data"]["baike"] for p in structured_content(rec2, False)["content"]] == ["summary", "footer"]


def test_traditional_modes():
    # s2tw writes Taiwan character forms; s2t keeps 着 and uses 裏/爲; neither rewrites vocabulary
    tw, std = Traditional("s2tw"), Traditional("s2t")
    assert [tw(w) for w in ("不着四六", "里面", "为什么", "软件")] == ["不著四六", "裡面", "為什麼", "軟件"]
    assert [std(w) for w in ("不着四六", "里面", "为什么")] == ["不着四六", "裏面", "爲什麼"]


def test_cli_offers_s2tw(tmp_path, monkeypatch):
    from baike2yomitan.cli import main

    monkeypatch.setattr("baike2yomitan.report.STATS_DIR", str(tmp_path / "stats"))  # not the repo's data/stats
    _write(tmp_path / "r.jsonl", [_primary("不着四六", 7, "不着四六，汉语成语，形容说话做事不着边际、不合规矩。")])
    out = tmp_path / "d.zip"
    assert main(["build", "--records", str(tmp_path / "r.jsonl"), "--out", str(out),
                 "--traditional", "s2tw", "--no-validate"]) == 0
    with zipfile.ZipFile(out) as zf:
        rows = json.loads(zf.read("term_bank_1.json"))
    assert [r[0] for r in rows] == ["不着四六", "不著四六"]
    assert rows[0][5] == rows[1][5] and rows[0][6] == rows[1][6]  # same content and sequence number


def test_structured_content_terms_header():
    rec = {"title": "丰颐", "summary": "丰颐，汉语词语。"}
    # traditional build: both spellings up front, traditional first
    sc = structured_content(rec, False, traditional="豐頤")
    head = sc["content"][0]
    assert head["data"]["baike"] == "terms"
    assert [(s["data"]["baike"], s["content"]) for s in head["content"]] == [
        ("traditional-term", "豐頤"), ("simplified-term", "丰颐")]
    # title unchanged by OpenCC: a single simplified box
    sc = structured_content({"title": "AI", "summary": "x"}, False, traditional="AI")
    assert [s["data"]["baike"] for s in sc["content"][0]["content"]] == ["simplified-term"]
    # no --traditional: no header at all
    assert structured_content(rec, False)["content"][0]["data"]["baike"] == "summary"


@pytest.mark.skipif(not os.path.exists(os.path.join(SCHEMA_DIR, "dictionary-index-schema.json")),
                    reason="yomitan schemas not downloaded (run validate once)")
def test_build_validate_and_smoke(tmp_path):
    recs = [
        _primary("红色食品", 10, "红色食品是指食品为红色、橙红色或棕红色的食品。", tags=["饮食", "食品"]),
        _primary("丈夫", 6236, "丈夫，zhàng fū，一般用作名词，已婚女子的配偶。"),
        _primary("丈夫", 1000, "《丈夫》是陈朱煌导演的台湾电影。", flags=["summary_from_section"]),
        _overlay("丰颐", 2036679, "丰颐，汉语词语，拼音是fēng yí，意思是丰满的下巴。", label="汉语词语"),
    ]
    recs[0].infobox = [["中文名", "红色食品"], ["类别", "食品"]]
    _write(tmp_path / "r.jsonl", recs)
    out = tmp_path / "d.zip"
    stats = build(str(tmp_path / "r.jsonl"), str(out), pinyin=True, traditional="s2t", infobox=True)
    assert stats["entries"] == 4 + stats["entries_traditional"]
    assert stats["entries_traditional"] >= 1  # 红色食品 → 紅色食品, 丰颐 → 豐頤
    assert validate_zip(str(out), SCHEMA_DIR) == []
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        assert names == {"index.json", "term_bank_1.json", "styles.css"}  # no tag bank: entries carry no tags
        assert "traditional-term" in zf.read("styles.css").decode("utf-8")
        idx = json.loads(zf.read("index.json"))
        assert idx["title"] == TITLE_FULL and idx["format"] == 3 and idx["sequenced"] is True
        assert idx["sourceLanguage"] == "zh" and idx["targetLanguage"] == "zh"
        bank = json.loads(zf.read("term_bank_1.json"))
        by_title = {}
        for e in bank:
            by_title.setdefault(e[0], []).append(e)
        zf_entries = by_title["丈夫"]
        assert len(zf_entries) == 2
        def summary_of(e):
            return next(p["content"] for p in e[5][0]["content"] if p["data"]["baike"] == "summary")
        scores = {summary_of(e): e[4] for e in zf_entries}
        # real-summary / lower-id sense scores higher than the fallback-summary sense
        assert scores["丈夫，zhàng fū，一般用作名词，已婚女子的配偶。"] > scores["《丈夫》是陈朱煌导演的台湾电影。"]
        assert all(e[2] == "" and e[3] == "" for e in bank)  # the dictionary-title chip is enough
        e = by_title["红色食品"][0]
        assert e[1] == "hóng sè shí pǐn"
        trad = by_title["紅色食品"][0]
        assert trad[6] == e[6]  # traditional variant shares the sequence number
        head = e[5][0]["content"][0]
        assert head["data"]["baike"] == "terms" and [s["content"] for s in head["content"]] == ["紅色食品", "红色食品"]
        assert trad[5] == e[5]  # same content object, so the same header on both spellings
    results = smoke(str(out), extra_random=1, seed=0)
    assert len(results["红色食品"]) == 1 and len(results["丈夫"]) == 2
    assert results["舍利子"] == []


def test_default_title_follows_cedict_filter(tmp_path):
    assert default_title(None) == TITLE_FULL == "百度百科 (full)"
    assert default_title({"红色食品"}) == TITLE_LEX == "百度百科 (lexical)"
    assert default_title(set()) == TITLE_LEX  # an empty filter is still a filter
    _write(tmp_path / "r.jsonl", [
        _primary("红色食品", 10, "红色食品是指食品为红色、橙红色或棕红色的食品。"),
        _primary("丰颐", 2036679, "丰颐，汉语词语，拼音是fēng yí，意思是丰满的下巴。"),
    ])
    out = tmp_path / "lex.zip"
    stats = build(str(tmp_path / "r.jsonl"), str(out), cedict_words={"丰颐"})
    assert stats["entries"] == 1
    with zipfile.ZipFile(out) as zf:
        idx = json.loads(zf.read("index.json"))
        bank = json.loads(zf.read("term_bank_1.json"))
    assert idx["title"] == TITLE_LEX
    assert [e[0] for e in bank] == ["丰颐"]
    build(str(tmp_path / "r.jsonl"), str(tmp_path / "named.zip"), title="自定义", cedict_words={"丰颐"})
    with zipfile.ZipFile(tmp_path / "named.zip") as zf:
        assert json.loads(zf.read("index.json"))["title"] == "自定义"  # an explicit title wins
