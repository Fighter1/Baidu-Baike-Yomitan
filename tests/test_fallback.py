"""Summary fallback for 563w pages whose first paragraph is an infobox line,
a pinyin line or a heading (shapes copied from real dropped rows)."""
import collections

from baike2yomitan.cleaning import (continues_on_next_line, is_key_value_line, is_summary_candidate,
                                    join_lines, short_summary_keep_reason)
from baike2yomitan.extract_563w import convert, find_fallback_summary


def _row(title, summary, sections, lid=123):
    return {"title": title, "summary": summary, "tags": [], "url": f"http://baike.baidu.com/view/{lid}.htm",
            "sections": [{"title": t, "content": c} for t, c in sections]}


def test_key_value_line_detection():
    assert is_key_value_line("作者：徐汉林编著")
    assert is_key_value_line("I S B N：9787801383617")
    assert is_key_value_line("·ISBN：7532120198")
    assert is_key_value_line("CPU类型：Core i7/Core i5/Core i3")
    assert not is_key_value_line("【特点】颜色金黄，肥肠，外焦内嫩，咸甜味香。")
    assert not is_key_value_line("1、玩具、小摆设或有趣的事物；也泛指东西：小玩意|他手里拿的是什么玩意。")
    assert not is_key_value_line("苏洵，字明允号老泉。")


def test_summary_candidate_rules():
    assert is_summary_candidate("虢仲簠，西周晚期。1992年12月河南三门峡市上村岭虢国墓地。")
    assert not is_summary_candidate("I S B N：9787801383617")        # infobox line
    assert not is_summary_candidate("Neil Diamond was born in 1941")  # no Chinese
    assert not is_summary_candidate("苏洵，字明允号老泉。")             # too short


def test_null_summary_infobox_first_then_prose():
    # 新疆远志-shaped page: 基本信息 infobox, real text in a later section
    raw = _row("新疆远志", None, [
        ("基本信息", "药名：新疆远志\\n汉语拼音：xin jiang yuan zhi\\n拉丁植物动物矿物名：Polygala hybrida DC."),
        ("来源", "为远志科植物新疆远志的根。多年生草本，高10-30厘米，根粗壮，木质。"),
    ])
    stats = collections.Counter()
    rec = convert(raw, stats, 300, want_infobox=True)
    assert rec is not None
    assert rec.summary.startswith("为远志科植物新疆远志的根")
    assert "summary_from_section" in rec.quality_flags
    assert "summary_from_later_paragraph" in rec.quality_flags
    assert stats["flag:summary_from_later_paragraph"] == 1
    assert rec.infobox == [["药名", "新疆远志"], ["汉语拼音", "xin jiang yuan zhi"],
                           ["拉丁植物动物矿物名", "Polygala hybrida DC."]]


def test_null_summary_second_paragraph_of_first_section():
    # 玩意-shaped page: pinyin line, then the gloss in the same section
    raw = _row("玩意", None, [
        ("玩意：", "wán yì\\n1、玩具、小摆设或有趣的事物；也泛指东西：小玩意|他手里拿的是什么玩意。"),
    ])
    rec = convert(raw, collections.Counter(), 300, want_infobox=False)
    assert rec.summary.startswith("1、玩具、小摆设")
    assert "summary_from_later_paragraph" in rec.quality_flags


def test_null_summary_first_paragraph_is_prose_keeps_old_behaviour():
    raw = _row("费某", None, [("生平", "费萨尔·伊本·侯赛因是伊拉克王国的第一任国王，1921年即位。\\n第二段。")])
    rec = convert(raw, collections.Counter(), 300, want_infobox=False)
    assert rec.summary.startswith("费萨尔·伊本·侯赛因")
    assert rec.quality_flags == ["summary_from_section"]


def test_null_summary_only_infobox_lines_is_dropped():
    raw = _row("通胀预期下的理财之道", None, [
        ("图书信息", "通胀预期下的理财之道\\nI S B N：9787111296096\\n定价：￥32.00 作者：张某某著\\n出版社：机械工业出版社"),
    ])
    stats = collections.Counter()
    assert convert(raw, stats, 300, want_infobox=False) is None
    assert stats["drop:summary_too_short_fallback"] == 1
    assert find_fallback_summary(raw["sections"]) is None


def test_short_summary_field_rescued_from_later_section():
    # 兔褐-shaped page: summary field holds pinyin only, gloss in the second section
    raw = _row("兔褐", "tù hè ㄊㄨˋ ㄏㄜˋ", [
        ("词语注音", "tù hè ㄊㄨˋ ㄏㄜˋ"),
        ("词语释义", "(1).兔毛布。唐李肇《唐国史补》卷下：“宣州以兔毛为褐，亚于锦绮。”"),
    ])
    stats = collections.Counter()
    rec = convert(raw, stats, 300, want_infobox=False)
    assert rec.summary.startswith("(1).兔毛布")
    assert "summary_from_section" in rec.quality_flags and "summary_from_later_paragraph" in rec.quality_flags
    assert stats["flag:summary_from_section_after_short_summary"] == 1


def test_short_summary_field_without_sections_is_dropped():
    raw = _row("英国电影学院", "英国电影学院\\n", [])
    stats = collections.Counter()
    assert convert(raw, stats, 300, want_infobox=False) is None
    assert stats["drop:summary_too_short"] == 1


def test_short_summary_keep_reason():
    assert short_summary_keep_reason("泉州市的别称。", "剌桐城") == "short_sentence"
    assert short_summary_keep_reason("紫衫军是洛杉矶湖人队的别称。", "紫衫军") == "short_sentence"
    assert short_summary_keep_reason("吴国将领，诸葛谨后代。", "诸葛壹") == "short_sentence"
    assert short_summary_keep_reason("别称：四六不懂", "不着四六") == "alias_line"
    assert short_summary_keep_reason("【别名】：山右", "山西") == "alias_line"
    # still dropped: title only, heading, pinyin, other infobox lines, empty alias
    assert short_summary_keep_reason("英国电影学院", "英国电影学院") is None
    assert short_summary_keep_reason("山右。", "山右") is None
    assert short_summary_keep_reason("公司简介", "某公司") is None
    assert short_summary_keep_reason("fú shù ㄈㄨˊ ㄕㄨˋ", "扶树") is None
    assert short_summary_keep_reason("姓名：谢志敏", "谢志敏") is None
    assert short_summary_keep_reason("别称：", "某词") is None
    assert short_summary_keep_reason("别称：某词", "某词") is None
    assert short_summary_keep_reason("中共松阳县委常委、统战部部长", "蒋璟璟") is None  # no sentence mark


def test_short_sentence_and_alias_stubs_are_kept():
    stats = collections.Counter()
    rec = convert(_row("剌桐城", "泉州市的别称。", []), stats, 300, want_infobox=False)
    assert rec is not None and rec.summary == "泉州市的别称。"
    assert rec.quality_flags == ["kept_short_sentence"]
    rec = convert(_row("不着四六", "别称：四六不懂 ", []), stats, 300, want_infobox=False)
    assert rec is not None and rec.summary == "别称：四六不懂"
    assert rec.quality_flags == ["kept_alias_line"]
    assert stats["flag:kept_short_sentence"] == 1 and stats["flag:kept_alias_line"] == 1
    # a section-less stub that is only an infobox line with another key stays dropped
    assert convert(_row("谢志敏", "姓名：谢志敏", []), stats, 300, want_infobox=False) is None
    assert stats["drop:summary_too_short"] == 1


def test_longer_paragraph_still_preferred_over_short_sentence():
    raw = _row("玩意", "玩具。", [("释义", "wán yì\\n1、玩具、小摆设或有趣的事物；也泛指东西。")])
    rec = convert(raw, collections.Counter(), 300, want_infobox=False)
    assert rec.summary.startswith("1、玩具、小摆设")
    assert "kept_short_sentence" not in rec.quality_flags


def test_line_break_inside_a_quote_is_detected():
    assert continues_on_next_line("为了叫起来顺嘴总不能叫“我开你一砖", "头”，所以就说“我开你一板儿砖”。")
    assert continues_on_next_line("该书（2003年出版，", "共三卷）是一部小说。")
    assert not continues_on_next_line("他说：“明天再来。", "第二天他果然来了”。")   # ends a sentence
    assert not continues_on_next_line("为了叫起来顺嘴总不能叫“我开你一砖", "下一段和它没有关系。")  # nothing closes it
    assert not continues_on_next_line("没有引号的一行", "头”，所以")                        # nothing is open
    assert not continues_on_next_line("", "头”") and not continues_on_next_line("“砖", "")
    assert join_lines("我开你一砖", "头”") == "我开你一砖头”"
    assert join_lines("called (the Great", "Wall) today") == "called (the Great Wall) today"
    assert join_lines("民国10年(19", "21年)毕业后回故里行医。") == "民国10年(1921年)毕业后回故里行医。"


def test_paragraph_split_mid_sentence_is_joined():
    # 板儿砖 (view/1066005): no summary field, and the article breaks a line inside a quotation
    raw = _row("板儿砖", None, [("简介", "[英] bricks\n板儿砖以前并没有板儿砖，就叫砖头，所以称其为板儿砖。"
                                       "究其发源地听说是北京新街口的爷们儿为了叫起来顺嘴总不能叫“我开你一砖\n"
                                       "头”，所以就说“我开你一板儿砖”看起来多个字，其实还是挺顺嘴儿的。"),
                              ("攻击力", "开始说攻击力，酒瓶，板儿砖，钢管儿。")])
    rec = convert(raw, collections.Counter(), 300, False)
    assert rec.summary.endswith("总不能叫“我开你一砖头”，所以就说“我开你一板儿砖”看起来多个字，其实还是挺顺嘴儿的。")
    assert rec.quality_flags == ["summary_from_section", "summary_from_later_paragraph", "summary_joined_lines"]


def test_complete_paragraphs_are_not_joined():
    raw = _row("示例词条", None, [("简介", "示例词条是一个用来说明问题的词条，它的第一段是完整的。\n第二段也是完整的一句话，不应该被接上去。")])
    stats = collections.Counter()
    rec = convert(raw, stats, 300, False)
    assert rec.summary == "示例词条是一个用来说明问题的词条，它的第一段是完整的。"
    assert rec.quality_flags == ["summary_from_section"] and "flag:summary_joined_lines" not in stats
    # a quote left open is not joined across sections, nor to a line that does not close it
    raw = _row("示例词条", None, [("简介", "示例词条的第一段开了一个“引号却没有关上\n第二段和它没有关系，也没有引号。"),
                                ("其他", "尾巴”在另一节里。")])
    assert convert(raw, collections.Counter(), 300, False).summary == "示例词条的第一段开了一个“引号却没有关上"


def test_short_fragments_are_not_joined_into_a_summary():
    # 嚅 (shape of a real row): the stub lines must not become the summary by being glued together
    raw = _row("嚅", None, [("基本字义", "(2) 〔嗫～〕见“\n(3) 嗫”。"),
                           ("详细字义", "(1) 欲言【wish to speak】。如:嚅嗫(说话吞吞吐吐的样子);嚅忍(欲言而止)")])
    rec = convert(raw, collections.Counter(), 300, False)
    assert rec.summary.startswith("(1) 欲言")
    assert "summary_joined_lines" not in rec.quality_flags


def test_definition_line_beats_a_later_citation():
    # 鱼游濠上 (shape of the real row): the 解释 line used to be skipped as an infobox line
    raw = _row("鱼游濠上", None, [("词语信息", "【词目】鱼游濠上\n【拼音】yú yóu háo shàng\n解释：表示纵情山水、逍遥遨游。\n"
                                          "出处：《庄子集释》卷六下〈外篇·秋水〉～606～庄子与惠子游于濠梁之上。")])
    stats = collections.Counter()
    rec = convert(raw, stats, 300, False)
    assert rec.summary == "表示纵情山水、逍遥遨游。"
    assert rec.quality_flags == ["summary_from_section", "summary_from_later_paragraph", "summary_from_definition_line"]
    # 片刻 was dropped: its only content is a short definition line
    rec = convert(_row("片刻", None, [("基本信息", "【词目】片刻\n释义：很短的时间；一会儿。")]), collections.Counter(), 300, False)
    assert rec.summary == "很短的时间；一会儿。"


def test_summary_field_that_says_nothing_gives_way_to_the_sections():
    # 恒风: the summary field holds only pinyin and bopomofo
    raw = _row("恒风", "héng fēng ㄏㄥˊ ㄈㄥ ㄏㄥˊ ㄈㄥ", [("解释", "恒风是指风向长期不变的风，例如信风和西风带的风。")])
    stats = collections.Counter()
    rec = convert(raw, stats, 300, False)
    assert rec.summary.startswith("恒风是指") and stats["flag:summary_from_section_after_empty_summary"] == 1
    # nothing better on the page: dropped, with its own reason
    stats = collections.Counter()
    assert convert(_row("旗幅", "qí fú ㄑㄧˊ ㄈㄨˊ 旗幅 旗幅", []), stats, 300, False) is None
    assert stats["drop:summary_not_prose"] == 1
    # a summary field that looks like an infobox line is kept: replacing it by a section
    # paragraph made as many entries worse as better on real rows
    raw = _row("华澳花园", "地址：海沧马青路与兴港路交汇处", [("简介", "华澳花园是位于海沧区的一个住宅小区，共有十二栋楼。")])
    assert convert(raw, collections.Counter(), 300, False).summary.startswith("地址：")
    # a definition label in front of the summary is taken off
    rec = convert(_row("川渟岳峙", "【解释】：指水止不流，山高矗立。比喻人的凝重庄严。", []), collections.Counter(), 300, False)
    assert rec.summary == "指水止不流，山高矗立。比喻人的凝重庄严。" and rec.quality_flags == []


def test_a_colon_inside_brackets_or_after_the_title_is_not_an_infobox_key():
    assert not is_key_value_line("粉虱科（学名：Aleyrodidae）是同翅目粉虱总科的刺吸式昆虫。")
    assert not is_key_value_line("《丁丁历险记：独角兽的秘密》是《海盗失宝》的姐妹篇前篇。")
    assert is_key_value_line("陈灿：影视演员，国际武术全能冠军。")                       # by shape it is one …
    assert is_summary_candidate("陈灿：影视演员，国际武术全能冠军，师从少林。", "陈灿")   # … but it describes the title
    assert not is_summary_candidate("陈灿：影视演员，国际武术全能冠军，师从少林。", "别人")
    raw = _row("粉虱科", None, [("概述", "粉虱科（学名：Aleyrodidae）是同翅目粉虱总科的刺吸式昆虫，两性成虫均有翅。\n粉虱成虫多喜欢产卵在叶背。")])
    assert convert(raw, collections.Counter(), 300, False).summary.startswith("粉虱科（学名：Aleyrodidae）")


def test_short_definition_is_kept_wherever_it_stands():
    # 远祖: the first paragraph is a label, the definition comes later and is under 15 characters
    raw = _row("远祖", None, [("词语信息", "【词目】远祖\n【拼音】yuǎn zǔ\n许多代以前的祖先。")])
    stats = collections.Counter()
    rec = convert(raw, stats, 300, False)
    assert rec.summary == "许多代以前的祖先。"
    assert rec.quality_flags == ["summary_from_section", "summary_from_later_paragraph", "kept_short_sentence"]
    # also when the summary field is the useless part
    rec = convert(_row("托卢", "托卢", [("简介", "中药名。即枸杞。")]), collections.Counter(), 300, False)
    assert rec.summary == "中药名。即枸杞。" and "kept_short_sentence" in rec.quality_flags


def test_interface_words_stay_headwords_and_labels_lose_their_colon():
    rec = convert(_row("编辑", "编辑，是对资料或现成的作品进行整理、加工的工作，也指从事这种工作的人。", []), collections.Counter(), 300, False)
    assert rec.title == "编辑" and rec.summary.startswith("编辑，是对资料")
    rec = convert(_row("语音编辑器", "语音编辑器是一种用来对语音文件进行剪辑的软件工具。", []), collections.Counter(), 300, False)
    assert rec.title == "语音编辑器" and rec.summary.startswith("语音编辑器是")
    rec = convert(_row("李永赋", "李永赋，男，汉族，云南晋宁人，中共党员，大学学历。", [("云南晋宁县公安局副局长：", "正文")]),
                  collections.Counter(), 300, False)
    assert rec.sense_label == "云南晋宁县公安局副局长"
    for heading in ("现任校长", "曾主持节目", "参演电视剧", "邻近行政区", "年度人物", "所在城市"):
        rec = convert(_row("某某某", "某某某是一个用来测试义项标签的条目，内容足够长。", [(heading, "正文")]), collections.Counter(), 300, False)
        assert rec.sense_label == "", heading


def test_an_unusable_row_does_not_block_a_later_row_with_the_same_id(tmp_path):
    import json

    from baike2yomitan.extract_563w import extract
    from baike2yomitan.records import iter_records

    rows = [_row("某词", "太短", [], lid=10), _row("某词", "这一行有一个足够长的摘要，应该被保留下来。", [], lid=10),
            _row("某词", "同一个编号的第三行是重复的，应该被丢弃掉。", [], lid=10)]
    rows[0]["url"] = "http://baike.baidu.com/view/0010.htm"   # zero padding: the same article
    src = tmp_path / "raw.jsonl"
    src.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    stats = extract(str(src), str(tmp_path / "out.jsonl"), progress_every=0)
    assert [r["summary"][:4] for r in iter_records(str(tmp_path / "out.jsonl"))] == ["这一行有"]
    assert stats["drop:dup_lemma_id"] == 1 and stats["drop:summary_too_short"] == 1


def test_the_pinyin_line_of_a_dictionary_page_is_kept_for_the_reading():
    from baike2yomitan.readings import Readings

    # 被褐藏辉: the summary is the definition, so the 【拼音】 line has to travel separately
    raw = _row("被褐藏辉", None, [("词语信息", "【词目】被褐藏辉\n【拼音】pī hè cáng huī\n解释：身穿粗布衣服而怀藏光辉。比喻有才德而不外露。")])
    stats = collections.Counter()
    rec = convert(raw, stats, 300, True)
    assert rec.summary.startswith("身穿粗布衣服") and rec.infobox == [["拼音", "pī hè cáng huī"]]
    assert stats["flag:pinyin_line_kept"] == 1
    assert Readings(None, None)(rec.to_dict()) == ("pī hè cáng huī", "article")
    # a summary field that was only pinyin and gave way to a section paragraph
    raw = _row("德才兼备", "发音 dé cái jiān bèi", [("释义", "德才兼备是指既有好的思想品质，又有工作的才干和能力。")])
    rec = convert(raw, collections.Counter(), 300, True)
    assert rec.summary.startswith("德才兼备是指") and rec.infobox == [["拼音", "dé cái jiān bèi"]]
    # only the pinyin is kept from the line
    from baike2yomitan.cleaning import pinyin_line_value
    assert pinyin_line_value("máo běn ㄇㄠˊ ㄅㄣˇ释义：明藏书家毛晋所刻的书。", "毛本") is None      # a line that also defines
    assert pinyin_line_value("【拼音】máo běn ㄇㄠˊ ㄅㄣˇ", "毛本") == "máo běn"
    assert pinyin_line_value("【shàng shāng】", "上殇") == "shàng shāng"
    assert pinyin_line_value("zhuó bái ㄓㄨㄛˊ ㄅㄞˊ 斫白", "斫白") == "zhuó bái"
    assert pinyin_line_value("读音为 dài yù", "待遇") == "dài yù" and pinyin_line_value("待遇从优。", "待遇") is None
    # not needed when the summary states the pinyin itself, and not done without --infobox data
    raw = _row("自郐以下", None, [("简介", "自郐以下，汉语成语，拼音是zì kuài yǐ xià，比喻其余不值一提。")])
    assert convert(raw, collections.Counter(), 300, True).infobox is None
    raw = _row("被褐藏辉", None, [("词语信息", "【拼音】pī hè cáng huī\n解释：身穿粗布衣服而怀藏光辉。")])
    assert convert(raw, collections.Counter(), 300, False).infobox is None
