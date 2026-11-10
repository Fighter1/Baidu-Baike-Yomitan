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
