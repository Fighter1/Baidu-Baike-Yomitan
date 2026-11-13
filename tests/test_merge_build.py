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
        _primary("丈夫", 6236, "丈夫，zhàng fū，一般用作名词，已婚女子的配偶，也指成年男子。", label="已有标签"),
        _primary("孤儿", 1, "没有覆盖记录的主记录，保持不变不变不变。"),
        _primary("脏", 2, "被不干净的覆盖记录匹配到的主记录应保持原样。"),
        _primary("多义", 3, "主记录里本身就有两个义项的标题，不刷新。"),
        _primary("多义", 4, "主记录里本身就有两个义项的标题，第二条。"),
        _primary("歧义", 5, "覆盖里有两个义项但是哪个都和这段文字无关。"),
    ])
    _write(tmp_path / "o.jsonl", [
        # ids deliberately differ from the primary's: they are different id spaces
        _overlay("倡佯", 77, "倡佯，读音chàng yáng，汉语词语，意思为自在纵情貌。", label="汉语词语"),
        _overlay("丈夫", 88, "丈夫，zhàng fū，1、已婚女子的配偶。2、男子。3、成年男子。", label="覆盖标签", default=True),
        _overlay("丈夫", 89, "《丈夫》是一部电影，作为额外义项加入。", label="电影", default=False),
        _overlay("脏", 99, "这条摘要来自回退路径，不能用于刷新主记录。", flags=["abstract_fallback"], default=True),
        _overlay("新词", 999, "主记录里没有的词条，应作为新记录加入。", label="网络用语"),
        _overlay("无号", None, "没有编号的覆盖记录也作为新记录加入。", default=True),
        _overlay("多义", 11, "覆盖的默认义项，但主记录有两条，所以只能新增。", default=True),
        _overlay("歧义", 12, "义项甲义项甲义项甲义项甲义项甲。", label="甲"),
        _overlay("歧义", 13, "义项乙义项乙义项乙义项乙义项乙。", label="乙"),
    ])
    stats = merge(str(tmp_path / "p.jsonl"), str(tmp_path / "o.jsonl"), str(tmp_path / "m.jsonl"))
    recs = list(iter_records(str(tmp_path / "m.jsonl")))
    by = collections.defaultdict(list)
    for r in recs:
        by[r["title"]].append(r)
    assert stats["refreshed"] == 2
    assert stats["refreshed:weak_primary"] == 1 and stats["refreshed:same_text"] == 1   # 倡佯, 丈夫
    assert stats["skipped_primary_title_ambiguous"] == 2      # 多义 ×2
    assert stats["kept_primary:no_usable_overlay_sense"] == 1  # 脏
    assert stats["kept_primary:different_article"] == 1        # 歧义
    assert stats["skipped_weak_sense_of_known_title"] == 1     # 脏: a fallback abstract next to a real article
    assert stats["added_new_title"] == 2 and stats["added_without_key"] == 0  # 新词, 无号 (title is the key)
    assert stats["added_extra_sense_of_known_title"] == 4      # 丈夫/电影, 多义, 歧义 ×2
    r = by["倡佯"][0]
    assert r["source"] == "563w+hf" and r["summary"].startswith("倡佯，读音")
    assert r["sense_label"] == "汉语词语"          # filled because primary's was empty
    assert r["lemma_id"] == 910001                 # primary id kept: id spaces differ
    assert r["snapshot_date"] == "2022-10-21" and r["archive_url"]
    assert "summary_from_section" not in r["quality_flags"] and "summary_refreshed" in r["quality_flags"]
    zf = {r["source"]: r for r in by["丈夫"]}
    assert zf["563w+hf"]["sense_label"] == "已有标签"  # not overwritten
    assert zf["563w+hf"]["is_default_sense"] is True
    assert zf["hf"]["sense_label"] == "电影"
    assert [r["source"] for r in by["脏"]] == ["563w"] and by["脏"][0]["summary"].startswith("被不干净")
    assert len(by["多义"]) == 3 and len(by["歧义"]) == 3 and len(by["新词"]) == 1 and len(by["无号"]) == 1
    assert stats["records_written"] == 7 + 6


def test_merge_keeps_the_2019_article_when_the_overlay_is_about_something_else(tmp_path):
    # Shapes of real cases: 大学 was replaced by a documentary film, 北京 by a song.
    _write(tmp_path / "p.jsonl", [
        _primary("大学", 4410, "大学的释义有三：一、泛指实施高等教育的学校，指提供教学和研究条件和授权颁发学位的高等教育机关。",
                 tags=["大学", "教育"]),
        _primary("北京", 2621, "北京是中华人民共和国首都、中央直辖市、中国国家中心城市，中国政治、文化、教育和国际交流中心。"),
        _primary("保险单", 100484, "保险单简称为保单，是保险人与被保险人订立保险合同的正式书面证明。保险单必须完整地记载保险合同双方当事人的权利义务及责任。"),
        _primary("郑卫平", 100, "1955年6月生，山东人，历任某集团军政治委员等职。", label="中国人民解放军南京军区政治委员",
                 flags=["summary_from_section"]),
        _primary("肾脏疾病", 7, "肾脏疾病一般简称肾脏病或肾病，肾脏疾病种类众多，慢性肾病用英文表示为CKD。"),
        _primary("说明", 451241, "【英译】[Explain;Illustrate;Show；Explanation]", flags=["summary_from_section"]),
    ])
    _write(tmp_path / "o.jsonl", [
        _overlay("大学", 58486117, "《大学》是一部纪录电影，通过镜头真实纪录了一所清华园与四位清华人的故事。"),
        _overlay("大学", 5655065, "《大学》是一篇论述儒家修身齐家治国平天下思想的散文，原是《小戴礼记》第四十二篇。", label="儒家散文"),
        _overlay("北京", 59726267, "沃罗比约夫以北京冬奥会为主题的俄语歌曲《北京》。"),
        _overlay("北京", 128981, "北京（Beijing），简称“京”，古称燕京、北平，是中华人民共和国的首都、直辖市、国家中心城市、超大城市。",
                 label="中华人民共和国首都、直辖市"),
        _overlay("保险单", None, "保险单简称“保单”。保险人与投保人签订保险合同的书面证明。保险单的主要内容包括双方对有关保险标的事项的说明。",
                 label="保险人与投保人签订保险合同的书面证明", default=True),
        _overlay("保险单", 1813746, "保险单简称“保单”。保险人与投保人签订保险合同的书面证明。保险单的主要内容包括双方对有关保险标的事项的说明。",
                 default=False),
        _overlay("郑卫平", 200, "郑卫平，男，现任武汉工业学院讲师。"),
        _overlay("肾脏疾病", 8, "肾脏疾病是肾脏病或肾病。", flags=["kept_short_sentence"]),
        _overlay("说明", 39260, "说明是一个汉语词汇，读音为shuō míng，意思是解释清楚，讲明解；说明原因。", label="汉语词汇"),
        _overlay("说明", 39261, "《说明》是一首歌曲，由某歌手演唱。", label="某歌手演唱歌曲"),
    ])
    stats = merge(str(tmp_path / "p.jsonl"), str(tmp_path / "o.jsonl"), str(tmp_path / "m.jsonl"))
    by = collections.defaultdict(list)
    for r in iter_records(str(tmp_path / "m.jsonl")):
        by[r["title"]].append(r)
    # 大学: the 2019 article stays; the film and the essay become senses of their own
    assert by["大学"][0]["source"] == "563w" and by["大学"][0]["summary"].startswith("大学的释义有三")
    assert [r["source"] for r in by["大学"]] == ["563w", "hf", "hf"]
    # 北京: refreshed from the city, not from the song
    assert by["北京"][0]["source"] == "563w+hf" and by["北京"][0]["summary"].startswith("北京（Beijing）")
    assert [r["summary"][:5] for r in by["北京"][1:]] == ["沃罗比约夫"]
    # 保险单: two snapshots of one article give one record, not two
    assert len(by["保险单"]) == 1 and by["保险单"][0]["source"] == "563w+hf"
    assert stats["skipped_repeated_sense"] == 1
    # 郑卫平: another person of the same name is not written over the general
    assert by["郑卫平"][0]["source"] == "563w" and by["郑卫平"][0]["summary"].startswith("1955年6月生")
    assert by["郑卫平"][1]["summary"].startswith("郑卫平，男")
    # 肾脏疾病: a stub does not replace a longer text, and is not added beside it
    assert len(by["肾脏疾病"]) == 1 and by["肾脏疾病"][0]["source"] == "563w"
    # 说明: a fallback paragraph gives way to the one overlay sense that is not a work
    assert by["说明"][0]["source"] == "563w+hf" and by["说明"][0]["summary"].startswith("说明是一个汉语词汇")
    assert by["说明"][0]["quality_flags"] == ["summary_refreshed"]
    assert len(by["说明"]) == 2


def test_merge_guards_for_people_empty_abstracts_and_shorter_texts(tmp_path):
    from baike2yomitan.merge import pick_refresh_candidate
    from baike2yomitan.sense import is_person

    assert is_person({"summary": "王都（？—929年），原名刘云郎，中山陉邑人。五代时期大臣。"})
    assert is_person({"summary": "苏洵，字明允，号老泉，眉州眉山人。"}) and not is_person({"summary": "天子或诸侯所居之城。"})
    # a year range in brackets is only a hint: enough to hold back a refresh, not to call 后汉 a person
    dynasty = {"summary": "后汉（947年—950年），五代十国时期的第四个中原王朝。"}
    assert is_person(dynasty) and not is_person(dynasty, certain=True)
    assert is_person({"summary": "于荣海，男，汉族，1960年生。"}, certain=True)
    # 朱文祥: a professor born in 1941 and a general of the same name share 14% of their text
    prof = _primary("朱文祥", 1, "男，1941年2月10日生，江西永新人。中共党员，教授。1964年7月毕业于北京师范大学化学系。").to_dict()
    general = _overlay("朱文祥", 2, "朱文祥，男，中国共产党党员，江西人，教授级高级工程师，现任武警部队副司令员。").to_dict()
    same = _overlay("朱文祥", 3, "朱文祥，男，1941年生，江西永新人，北京师范大学化学系教授，中共党员。").to_dict()
    assert pick_refresh_candidate(prof, [general])[0] is None
    assert pick_refresh_candidate(prof, [same])[0] is same
    # 王都: a definition is not replaced by a person; 不解: nor by an abstract that is only pinyin
    word = _primary("王都", 4, "天子或诸侯所居之城。", flags=["summary_from_section", "summary_from_definition_line"]).to_dict()
    person = _overlay("王都", 5, "王都（？—929年），原名刘云郎，中山陉邑人。五代时期大臣，义武节度使王处直的义子。").to_dict()
    assert pick_refresh_candidate(word, [person]) == (None, "different_kind")
    word = _primary("不解", 6, "指不明白对方的意思，一头雾水。", flags=["summary_from_section"]).to_dict()
    empty = _overlay("不解", 7, "不解，汉语词汇，注音（bù jiě）。", label="汉语词汇").to_dict()
    assert pick_refresh_candidate(word, [empty]) == (None, "no_usable_overlay_sense")
    # 经济价值: a fallback paragraph is not traded for one sentence that says less
    long = _primary("经济价值", 8, "“经济价值”是指任何事物对于人和社会在经济上的意义，经济学上所说的“商品价值”及其规律则是实现经济价值的现实必然形式。",
                    flags=["summary_from_section"]).to_dict()
    short = _overlay("经济价值", 9, "经济价值分直接经济价值和间接经济价值。", label="经济学术语").to_dict()
    assert pick_refresh_candidate(long, [short]) == (None, "overlay_says_less")
    # 鬼谷子: the thinker is not replaced by the figure of an animation that is named after him (0.20 alike)
    from baike2yomitan.sense import of_another_work, work_it_is_in
    thinker = _primary("鬼谷子", 10, "王诩，又名王禅，鬼谷子，是历史上极富神秘色彩的传奇人物，春秋时人。常入云梦山采药修道。因隐居清溪之鬼谷，故自称鬼谷先生。"
                       "春秋战国时期著名的思想家、谋略家、兵家、教育家，是纵横家的鼻祖。", tags=["思想家", "历史"]).to_dict()
    figure = _overlay("鬼谷子", 11, "鬼谷子，是中国3D武侠动画《秦时明月》系列中，根据中国春秋战国时期思想家鬼谷子衍生出的剧情设定，"
                      "是历代纵横家首领的称号。截止至动画第5部上映，仅提及3位鬼谷子。").to_dict()
    assert work_it_is_in(figure) == "秦时明月" and of_another_work(figure, thinker)
    assert pick_refresh_candidate(thinker, [figure]) == (None, "different_article")
    # the same figure in both, although the 2019 page names the work another way, or only its tags say that it is made up
    old = {"summary": "戴宗，江州人，外号神行太保，在水浒英雄榜上排在第二十位。", "tags": []}
    assert not of_another_work({"summary": "戴宗是中国古典小说《水浒传》中的人物，绰号神行太保。"}, old)
    old = {"summary": "猎潮者耐普图隆是他所统治领域——深海的灵魂。", "tags": ["游戏", "魔兽世界"]}
    assert not of_another_work({"summary": "耐普图隆，暴雪娱乐公司出品的游戏《魔兽争霸》中的角色，水元素领主。"}, old)
    # a work that is only quoted or played in is no such thing
    assert work_it_is_in({"summary": "九卿，是中国古代中央部分行政长官的总称。司马迁的史类文学作品《史记》中记载“闻古之圣人，不居朝廷”。"}) is None
    _write(tmp_path / "p.jsonl", [Record.from_dict(word)])
    _write(tmp_path / "o.jsonl", [Record.from_dict(empty)])
    stats = merge(str(tmp_path / "p.jsonl"), str(tmp_path / "o.jsonl"), str(tmp_path / "m.jsonl"))
    assert stats["records_written"] == 1 and stats["skipped_weak_sense_of_known_title"] == 1


def test_similarity():
    from baike2yomitan.cleaning import similarity

    a = "庐山，山体呈椭圆形，典型的地垒式长段块山约25公里，宽约10公里，绵延的90余座山峰，犹如九叠屏风。"
    b = "庐山市，江西省县级市，九江市代管，地处江西省北部，九江市南部，背倚庐山，面临鄱阳湖。"
    assert similarity(a, a, "庐山") == 1.0
    assert similarity(a, b, "庐山") < 0.1              # the title itself does not count
    assert similarity(a, a[:30], "庐山") == 1.0        # a shortened copy is the same text
    assert similarity("", a) == 0.0 and similarity("短", "短") == 0.0


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


def test_surname_spellings():
    t = Traditional("s2tw")
    assert t("于荣海") == "於榮海"                          # what OpenCC makes of it
    assert t.forms("于荣海", person=True) == ["于榮海", "於榮海"]    # a biography displays the name form
    assert t.forms("于荣海") == ["於榮海", "于榮海"]                 # unknown: both are indexed
    assert t.forms("范县") == ["範縣", "范縣"]
    assert t.forms("于是") == ["於是", "于是"] and t.forms("岳敏君", person=True) == ["岳敏君", "嶽敏君"]
    assert t.forms("钟楚红", person=True)[0] == "鍾楚紅"
    assert t.forms("软件") == ["軟件"] and t.forms("好") == ["好"]
    # a dictionary word is not a name: no 后邊 or 干燥劑 next to 後邊 and 乾燥劑, unless the record is a biography
    assert t.forms("后边", word=True) == ["後邊"] and t.forms("干燥剂", word=True) == ["乾燥劑"]
    assert t.forms("于荣海", person=True, word=True) == ["于榮海", "於榮海"]


def test_a_city_or_dynasty_does_not_display_the_name_form(tmp_path):
    _write(tmp_path / "r.jsonl", [
        _primary("沈阳", 1, "沈阳，简称“沈”，别称盛京、奉天（1625年—1929年），是辽宁省省会。",
                 tags=["城市", "财经人物", "沈氏人物"]),          # page-level tags of other senses
        _primary("后汉", 2, "后汉（947年—950年），五代十国时期的第四个中原王朝。"),
    ])
    out = tmp_path / "d.zip"
    build(str(tmp_path / "r.jsonl"), str(out), traditional="s2tw")
    with zipfile.ZipFile(out) as zf:
        rows = json.loads(zf.read("term_bank_1.json"))
    assert [r[0] for r in rows] == ["沈阳", "瀋陽", "沈陽", "后汉", "後漢", "后漢"]      # OpenCC's form first
    assert flatten_content(rows[0][5][0]).startswith("瀋陽沈阳") and flatten_content(rows[3][5][0]).startswith("後漢后汉")


def test_kind_of_article_from_the_opening_of_the_summary():
    from baike2yomitan.sense import is_word, is_work

    idiom = {"title": "沧海一粟", "sense_label": "", "summary": "沧海一粟，汉语成语，读音是cāng hǎi yī sù，意思是大海里的一粒谷子。"}
    drama = {"title": "沧海一粟", "sense_label": "", "summary": "同名电视剧《沧海一粟》，在封建的中国首创男女同校，旅行写生。"}
    assert is_word(idiom) and not is_work(idiom) and is_work(drama) and not is_word(drama)
    assert is_word({"title": "英", "summary": "英，汉语常用字（一级字），读作yīng，本义是指花。"})
    assert is_word({"title": "说明", "summary": "说明是一个汉语词汇，读音为shuō míng，意思是解释清楚。"})
    assert not is_word({"title": "汉语词汇", "summary": "《汉语词汇》是2001年商务印书馆出版的图书。"})          # a book about words
    assert not is_word({"title": "庐山", "summary": "庐山，又名匡山、匡庐，位于江西省九江市庐山市境内。"})
    assert sorted([drama, idiom], key=sense_rank_key)[0] is idiom


def test_build_indexes_both_surname_spellings(tmp_path):
    _write(tmp_path / "r.jsonl", [
        _primary("于荣海", 1, "于荣海，男，汉族，1960年生，中共党员，大学学历。", tags=["人物"]),
        _primary("于是", 2, "于是，汉语词汇，连词，表示后一事紧接着前一事。"),
    ])
    out = tmp_path / "d.zip"
    stats = build(str(tmp_path / "r.jsonl"), str(out), traditional="s2tw")
    with zipfile.ZipFile(out) as zf:
        rows = json.loads(zf.read("term_bank_1.json"))
    assert [r[0] for r in rows] == ["于荣海", "于榮海", "於榮海", "于是", "於是"]   # 于是 kept as is equals the title
    assert len({json.dumps(r[5]) for r in rows[:3]}) == 1 and len({r[6] for r in rows[:3]}) == 1
    assert flatten_content(rows[0][5][0]).startswith("于榮海于荣海")                # the biography displays the name form
    assert stats["entries"] == 5 and stats["entries_traditional"] == 3


def test_tag_exclusion_spares_ordinary_words(tmp_path):
    from baike2yomitan.build import excluded_by_tag
    from baike2yomitan.cedict import load_common_headwords, load_simplified_headwords

    cedict = tmp_path / "cedict.txt"
    cedict.write_text("# comment\n瀟灑 潇洒 [xiao1 sa3] /confident and at ease/\n證書 证书 [zheng4 shu1] /certificate/\n"
                      "成果 成果 [cheng2 guo3] /result/\n北京大學 北京大学 [Bei3 jing1 Da4 xue2] /Peking University/\n"
                      "微軟 微软 [Wei1 ruan3] /Microsoft/\n", encoding="utf-8")
    words, common = load_simplified_headwords(str(cedict)), load_common_headwords(str(cedict))
    assert common == {"潇洒", "证书", "成果"} and words - common == {"北京大学", "微软"}
    recs = [
        _primary("潇洒", 1, "潇洒，汉语词语，形容人的神情举止自然大方，不拘束。", tags=["词语", "人物"]),       # a word under a person tag
        _primary("证书", 2, "证书是由机关、学校、团体等发给的证明资格或权力的文件。", tags=["学校"]),
        _primary("成果", 3, "成果，1984年出生于上海，女，中国内地影视演员。", tags=["人物", "演员"]),               # really a person
        _primary("北京大学", 4, "北京大学创办于1898年，初名京师大学堂，是中国第一所国立综合性大学。", tags=["学校"]),
        _primary("微软", 5, "微软是一家美国跨国科技企业，由比尔·盖茨和保罗·艾伦创办于1975年。", tags=["企业"]),
    ]
    exclude = {"人物", "企业", "学校"}
    assert [excluded_by_tag(r.to_dict(), exclude, common) for r in recs] == [False, False, True, True, True]
    assert all(excluded_by_tag(r.to_dict(), exclude, None) for r in recs)        # no word list: the tag decides
    assert not excluded_by_tag(recs[0].to_dict(), set(), common)
    _write(tmp_path / "r.jsonl", recs)
    stats = build(str(tmp_path / "r.jsonl"), str(tmp_path / "d.zip"), cedict_words=words, exclude_tags=exclude,
                  common_words=common)
    with zipfile.ZipFile(tmp_path / "d.zip") as zf:
        assert [e[0] for e in json.loads(zf.read("term_bank_1.json"))] == ["潇洒", "证书"]
    assert stats["skip:excluded_tag"] == 3 and stats["kept:excluded_tag_on_ordinary_word"] == 2


def test_a_refresh_fills_in_sections_label_by_label(tmp_path):
    old = _primary("旁门左道", 111097, "旁门左道，汉语成语，原指不正派的宗教派别，借指不正派的学术派别。")
    old.sections = [["释义", "指非正统的学术流派或宗教派别。"], ["用法", "联合式；作宾语、定语；含贬义。"], ["反义词", "正道"]]
    new = _overlay("旁门左道", 2005862, "旁门左道，汉语成语，原指不正派的宗教派别，借指不正派的学术派别，现泛指不正派的东西。")
    new.sections = [["出处", "明·许仲琳《封神演义》"], ["反义词", "不二法门"]]
    bare = _primary("疾风迅雷", 5, "疾风迅雷，汉语成语，形容事情的发生和发展像暴风急雷那样猛烈而迅速。")
    bare.sections = [["释义", "形容事情的发生和发展。"]]
    _write(tmp_path / "p.jsonl", [old, bare])
    _write(tmp_path / "o.jsonl", [new, _overlay("疾风迅雷", 6, "疾风迅雷，汉语成语，形容事情的发生和发展像暴风急雷那样猛烈而迅速，出自《礼记》。")])
    merge(str(tmp_path / "p.jsonl"), str(tmp_path / "o.jsonl"), str(tmp_path / "m.jsonl"))
    by = {r["title"]: r for r in iter_records(str(tmp_path / "m.jsonl"))}
    assert by["旁门左道"]["source"] == "563w+hf"
    # the snapshot's section where it has one, the 2019 one where it has none, in the order they are shown in
    assert by["旁门左道"]["sections"] == [["释义", "指非正统的学术流派或宗教派别。"], ["出处", "明·许仲琳《封神演义》"],
                                      ["用法", "联合式；作宾语、定语；含贬义。"], ["反义词", "不二法门"]]
    assert by["疾风迅雷"]["source"] == "563w+hf" and by["疾风迅雷"]["sections"] == [["释义", "形容事情的发生和发展。"]]
