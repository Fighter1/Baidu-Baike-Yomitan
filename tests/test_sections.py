import collections

from baike2yomitan import extract_563w, extract_hf
from baike2yomitan.audit import _check, Sense, entry_parts
from baike2yomitan.build import structured_content
from baike2yomitan.cleaning import decode_entities
from baike2yomitan.sections import (MAX_SECTION_CHARS, label_of, pick_sections, section_parts, section_text,
                                    shown_sections, strip_pasted_furniture)

BEIHE = {"title": "被褐藏辉", "summary": None, "tags": [], "url": "http://baike.baidu.com/view/6647954.htm", "sections": [
    {"title": "词语注音", "content": "pī hè cáng huī    ㄆㄧ ㄏㄜˋ ㄘㄤˊ ㄏㄨㄟ  被褐藏辉（被褐藏辉）"},
    {"title": "词语解析", "content": "汉 犹言被褐怀玉。 明  叶宪祖 《易水寒》第一折：“且沉山瘗影，被褐藏辉。”  汉 成语词典已有该词条：被褐\n"}]}


def test_pasted_dictionary_furniture_is_stripped():
    assert strip_pasted_furniture(BEIHE["sections"][1]["content"]).strip() == \
        "犹言被褐怀玉。 明  叶宪祖 《易水寒》第一折：“且沉山瘗影，被褐藏辉。”"
    assert strip_pasted_furniture("汉 典 见“ 鱼目混珠 ”。  汉 典 成语词典已有该词条：鱼目\n").strip() == "见“ 鱼目混珠 ”。"
    assert strip_pasted_furniture("汉 ◎ 底账 dǐzhàng [original account]") == "◎ 底账 dǐzhàng [original account]"
    assert strip_pasted_furniture("汉 战斗的叫喊。 鲁迅 《二心集》") == "战斗的叫喊。 鲁迅 《二心集》"
    # the pointer on a line of its own, with the whole word
    assert strip_pasted_furniture("钩距兼设。”\n成语词典已有该词条：问羊知马\n用 法： 联合式") == "钩距兼设。”\n\n用 法： 联合式"
    # 汉 as the dynasty of a quoted author, or half of a word, stays
    for text in ("汉 蔡邕 《陈留东昏库上里社碑》：“ 汉 兴， 陈平 由此社宰", "汉 郑玄 注：“土神称曰神农者，以其主於稼穑。”",
                 "汉 制，门籍有其姓名者，方得入宫。", "汉 扬雄 《羽猎赋》：“荧惑司命，天弧发射。”", "汉语词语。"):
        assert strip_pasted_furniture(text) == text
    assert strip_pasted_furniture(None) == ""
    # the site's name again after the last sentence
    assert strip_pasted_furniture("汉 典 鸟翼。 唐 邵谒 《送徐群宰望江诗》：“好去立高节，重来振羽翎。”  汉 典") == \
        "鸟翼。 唐 邵谒 《送徐群宰望江诗》：“好去立高节，重来振羽翎。”"
    assert strip_pasted_furniture("汉 继父。《水浒传》：“杀晚爷的大顽。’” 汉\\n晚爷（晚爷）") == "继父。《水浒传》：“杀晚爷的大顽。’”\\n晚爷（晚爷）"
    assert strip_pasted_furniture("两汉 以后，东汉") == "两汉 以后，东汉"


def test_watermark_is_removed():
    from baike2yomitan.cleaning import clean_text

    assert clean_text("赛事过半，赛场场面愈发激烈。咟喥咟萪") == "赛事过半，赛场场面愈发激烈。"


def test_sections_of_another_article_in_the_row_are_not_taken():
    machine = {"title": "智能鞋套机", "summary": None, "tags": [], "url": "http://baike.baidu.com/view/1.htm", "sections": [
        {"title": "简介", "content": "智能鞋套机，是针对国内外用户的需要开发的一种新型鞋套机，适用于医院等领域。"},
        {"title": "性能", "content": "更换鞋套快速方便。"}, {"title": "技术参数", "content": "重量25KG"},
        {"title": "使用步骤", "content": "打开鞋套盒盖子。"},
        {"title": "简介", "content": "【词目】祸福由人\n【释义】是祸是福均取决于人自身的所作所为。"},
        {"title": "近义词", "content": "祸福相倚俯仰由人祸福无门\n"}]}
    assert [h for h, _c in extract_563w.own_sections(machine["sections"])] == ["简介", "性能", "技术参数", "使用步骤"]
    assert extract_563w.convert(machine, collections.Counter(), 300, True).sections is None
    # without a repeated heading: what shows the page to be about a word has to stand near its top
    late = [("剧情简介", "讲述了一个故事。"), ("演职员表", "导演"), ("幕后花絮", "花絮"), ("近义词", "祸福相倚"), ("出处", "《春芜记》")]
    assert pick_sections(late, "祸福由人", proof_within=3) is None
    assert pick_sections(late, "祸福由人") == [["出处", "《春芜记》"], ["近义词", "祸福相倚"]]
    assert pick_sections(late, "祸福由人", "祸福由人，汉语成语，意思是祸福取决于人。", proof_within=3) is not None
    # 出处 above the heading that shows it does not count: it may say where a character of a novel appears
    assert pick_sections([("出处", "《仙逆》"), ("近义词", "祸福相倚")], "祸福由人") == [["近义词", "祸福相倚"]]


def test_section_text_leaves_out_what_is_not_text():
    assert section_text("祸福相倚俯仰由人祸福无门\n", "祸福由人", "近义词") == "祸福相倚、俯仰由人、祸福无门"
    assert section_text("部首笔画部首: 石 部外笔画: 4 总笔画: 9 五笔86: ditt 仓颉: mrfh", "砂", "释义") == ""
    assert section_text("词性释义英译例句例词名词牢狱。也作“圄”。", "圉", "详解") == "名词牢狱。也作“圄”。"


def test_summary_of_a_pasted_page_has_no_furniture():
    rec = extract_563w.convert(BEIHE, collections.Counter(), 300, True)
    assert rec.summary == "犹言被褐怀玉。明叶宪祖《易水寒》第一折：“且沉山瘗影，被褐藏辉。”"
    assert rec.sections == [["释义", rec.summary]]
    assert shown_sections(rec.to_dict()) == []          # the summary is that section
    assert ["拼音", "pī hè cáng huī"] in rec.infobox


def test_headings_and_their_labels():
    for heading, label in (("解释", "释义"), ("成语解释", "释义"), ("基本解释", "释义"), ("词语解析", "释义"), ("【释义】", "释义"),
                           ("释义：", "释义"), ("详细解释", "详解"), ("引证解释", "详解"), ("出处", "出处"), ("成语出处", "出处"),
                           ("典故出处", "出处"), ("词源", "出处"), ("用法", "用法"), ("成语用法", "用法"), ("语法", "用法"),
                           ("示例", "示例"), ("成语示例", "示例"), ("运用示例", "示例"), ("造句", "示例"), ("近义词", "近义词"),
                           ("同义词", "近义词"), ("反义词", "反义词"), ("成语辨析", "辨析")):
        assert label_of(heading) == label, heading
    for heading in ("成语故事", "典故", "用法用量", "人物出处", "来源", "词语注音", "名词解释", "程序示例", "简介", "", None):
        assert label_of(heading) is None, heading
    assert label_of("春暖花开成语用法", "春暖花开") == "用法"      # an overlay heading comes with the title in front


def test_sections_are_taken_from_pages_about_words_only():
    chengyu = [("解释", "比喻彼此一样都是坏人，没有差别。"), ("出处", "《汉书·杨恽传》：“古与今如一丘之貉。”"),
               ("成语故事", "汉朝时有一个名叫杨恽的人。" * 30), ("近义词", "狐群狗党 \n一路货色"), ("用法", "偏正式；作宾语；含贬义")]
    assert pick_sections(chengyu, "一丘之貉") == [
        ["释义", "比喻彼此一样都是坏人，没有差别。"], ["出处", "《汉书·杨恽传》：“古与今如一丘之貉。”"],
        ["用法", "偏正式；作宾语；含贬义"], ["近义词", "狐群狗党、一路货色"]]
    # 出处 and 语法 by themselves are also sections of a character of a novel and of a function
    assert pick_sections([("出处", "古魔塔珈是耳根仙侠小说《仙逆》的人物。"), ("简介", "相传宇宙中先有天道。")], "古魔塔珈") is None
    assert pick_sections([("语法", "void WINAPI glCallList(GLuint list);"), ("参数", "列表")], "glCallList") is None
    assert pick_sections([("用法", "口服，一次1～2粒，一日2次。")], "虎杖叶胶囊", "虎杖叶胶囊，中成药名。") is None
    # ... unless a heading or the summary says the page is about a word
    assert pick_sections([("成语出处", "明·朱国祯《涌幢小品·南内》")], "春暖花开") == [["出处", "明·朱国祯《涌幢小品·南内》"]]
    assert pick_sections([("词语注音", "chūn nuǎn huā kāi"), ("出处", "明·朱国祯《涌幢小品·南内》")], "春暖花开") == [
        ["出处", "明·朱国祯《涌幢小品·南内》"]]
    assert pick_sections([("出处", "明·朱国祯《涌幢小品·南内》")], "春暖花开", "春暖花开，汉语成语，原义是说春景美丽。") == [
        ["出处", "明·朱国祯《涌幢小品·南内》"]]
    # the short meaning is preferred to the plain heading wherever it stands; a section that says nothing is no section
    both = [("解释", "解释的全文。"), ("基本解释", "基本的意思。"), ("词语解释", "又一个解释。"), ("出处", " ")]
    assert pick_sections(both, "某词") == [["释义", "基本的意思。"]]
    assert pick_sections([("近义词", "席门蓬巷"), ("释义", "xí mén qióng xiàng")], "席门穷巷") == [["近义词", "席门蓬巷"]]
    # the overlay refuses a text with injected characters
    assert pick_sections(chengyu[:2], "一丘之貉", refuse=lambda text: "杨恽" in text) == [["释义", "比喻彼此一样都是坏人，没有差别。"]]


def test_section_text_is_one_trimmed_line():
    assert section_text("【解释】：指水止不流。\n也比喻停滞。", "某词", "释义") == "指水止不流。也比喻停滞。"
    assert section_text("1. 牧童唱的歌谣\n2. 泛指田园生活", "牧歌", "详解") == "1. 牧童唱的歌谣 2. 泛指田园生活"
    assert section_text("头痛脑热、头疼脑热", "头痛额热", "近义词") == "头痛脑热、头疼脑热"
    assert section_text("近义词：老当益壮。", "某词", "近义词") == "老当益壮。"
    long = section_text("这是一个很长的句子。" * 40, "某词", "详解")
    assert len(long) <= MAX_SECTION_CHARS and long.endswith("。")
    assert section_text("", "某词", "释义") == "" and section_text(None, "某词", "释义") == ""


def test_overlay_sections():
    content = ("春暖花开，汉语成语，原义是说春景美丽。出自《涌幢小品·南内》。[1] 春暖花开，汉语成语，原义是说春景美丽。出自《涌幢小品·南内》。[1]"
               "  春暖花开成语用法编辑 示例 ～，我好引着孩子们园里做活。 ◎清·李绿园《歧路灯》第40回[1]"
               "  春暖花开成语出处编辑 明·朱国祯《涌幢小品·南内》：“春暖花开，命中贵陪内阁儒臣宴赏。”[1] ")
    assert [h for h, _text in extract_hf.page_sections(content, "春暖花开")] == ["成语用法", "成语出处"]
    rec = extract_hf.convert({"title": "春暖花开", "content": content, "timestamp": 20200716134407,
                              "base_url": "https://baike.baidu.com/item/%E6%98%A5%E6%9A%96%E8%8A%B1%E5%BC%80/34091"},
                             collections.Counter(), 300)
    assert rec.summary == "春暖花开，汉语成语，原义是说春景美丽。出自《涌幢小品·南内》。"
    # a 成语用法 section that holds only examples, under a heading of its own, is the 示例
    assert rec.sections == [["出处", "明·朱国祯《涌幢小品·南内》：“春暖花开，命中贵陪内阁儒臣宴赏。”"],
                            ["示例", "～，我好引着孩子们园里做活。◎清·李绿园《歧路灯》第40回"]]
    assert extract_hf.convert({"title": "春暖花开", "content": content, "timestamp": 20200716134407},
                              collections.Counter(), 300, want_sections=False).sections is None
    # 2023 snapshots have injected characters in the body: such a section is left out
    junk = content.replace("明·朱国祯《涌幢小品·南内》：", "明·朱国祯《涌幢小品·南内》的Wor去乌ld：")
    rec = extract_hf.convert({"title": "春暖花开", "content": junk, "timestamp": 20230716134407}, collections.Counter(), 300)
    assert [label for label, _text in rec.sections] == ["示例"]


def test_sections_of_a_letter_spaced_snapshot():
    plain = ("解释播报编辑五岳： 指东岳泰山、西岳华山、南岳衡山、北岳恒山和中岳嵩山，是我国历史上的五大名山。黄山：在安徽省南部。"
             "极言黄山景观之胜。 [1] 出处播报编辑徐霞客的《漫游黄山仙境》。 [2] ")
    assert [h for h, _text in extract_hf.spaced_sections(plain)] == ["解释", "出处"]
    rec = extract_hf.convert({"title": "五岳归来不看山，黄山归来不看岳", "content": "".join(ch + " " for ch in plain),
                              "timestamp": 20240123171136}, collections.Counter(), 300)
    assert rec.summary.endswith("极言黄山景观之胜。") and "unspaced" in rec.quality_flags
    assert rec.sections[1] == ["出处", "徐霞客的《漫游黄山仙境》。"]
    assert shown_sections(rec.to_dict()) == [["出处", "徐霞客的《漫游黄山仙境》。"]]     # the 解释 section is the summary
    assert extract_hf.spaced_sections("没有章节的一页。") == []


def test_entry_shows_the_sections_that_add_to_the_summary():
    rec = {"title": "一丘之貉", "summary": "一丘之貉是一个成语，比喻彼此一样都是坏人，没有差别。",
           "sections": [["释义", "比喻彼此一样都是坏人，没有差别。"], ["出处", "《汉书·杨恽传》：“古与今如一丘之貉。”"],
                        ["用法", "偏正式；作宾语；含贬义"]], "infobox": [["拼音", "yī qiū zhī hé"]]}
    assert [label for label, _text in shown_sections(rec)] == ["出处", "用法"]
    sc = structured_content(rec, True, want_sections=True)
    assert [p["data"]["baike"] for p in sc["content"]] == ["summary", "sections", "infobox"]
    block = sc["content"][1]["content"]
    assert [(s["content"][0]["content"], s["content"][1]) for s in block] == [
        ("出处", "《汉书·杨恽传》：“古与今如一丘之貉。”"), ("用法", "偏正式；作宾语；含贬义")]
    assert all(s["data"]["baike"] == "section" and s["content"][0]["data"]["baike"] == "section-label" for s in block)
    # not asked for, or nothing to add: no block
    assert [p["data"]["baike"] for p in structured_content(rec, False)["content"]] == ["summary"]
    assert [p["data"]["baike"] for p in structured_content(dict(rec, sections=rec["sections"][:1]), False, None, True)["content"]] == ["summary"]
    # the audit reads the block as one text, and a golden word can ask for something in it
    parts = entry_parts([sc])
    assert parts["sections"] == "出处《汉书·杨恽传》：“古与今如一丘之貉。”用法偏正式；作宾语；含贬义" and "section" not in parts
    sense = Sense("一丘之貉", 1, "yī qiū zhī hé", 0, "", rec["summary"], sections=parts["sections"])
    assert _check({"word": "一丘之貉", "check": "section_has", "value": "杨恽传"}, [sense]) is None
    assert "no sense has it" in _check({"word": "一丘之貉", "check": "section_has", "value": "成语故事"}, [sense])
    assert _check({"word": "一丘之貉", "check": "section_lacks", "value": "祸福相倚"}, [sense]) is None
    assert "sections of" in _check({"word": "一丘之貉", "check": "section_lacks", "value": "偏正式"}, [sense])
    assert _check({"word": "一丘之貉", "check": "summary_lacks", "value": "词典已有该词条"}, [sense]) is None
    assert _check({"word": "一丘之貉", "check": "summary_lacks", "value": "坏人"}, [sense]) is not None


def test_a_section_that_starts_with_the_summary_shows_the_rest():
    rec = {"title": "发给", "summary": "1. [deal;distribute;deliver]∶分给",
           "sections": [["释义", "1. [deal;distribute;deliver]∶分给 发给每个人三个夹馅面包 2. [let;send out]∶判给或分给"],
                        ["详解", "发给每个人三个夹馅面包 2. [let;send out]∶判给或分给，再说一遍。"]]}
    assert shown_sections(rec) == [["释义", "发给每个人三个夹馅面包 2. [let;send out]∶判给或分给"]]   # 详解 repeats what 释义 shows
    assert shown_sections(dict(rec, sections=[["释义", rec["summary"] + "的。"]])) == []


def test_a_long_set_of_sections_is_cut_off():
    texts = [("".join(chr(0x4E00 + 40 * i + j) for j in range(9)) + "。") * 18 for i in range(5)]   # 180 characters each
    rec = {"title": "某词", "summary": "某词是一个词语。",
           "sections": [list(pair) for pair in zip(("释义", "详解", "出处", "用法", "示例"), texts)]}
    assert [label for label, _text in shown_sections(rec)] == ["释义", "详解", "出处"]      # 700 characters at most


def test_html_entities_become_characters():
    assert decode_entities("Universit&auml;t, 41-60m&sup2;, d&igrave;ngzhǐ") == "Universität, 41-60m², dìngzhǐ"
    assert decode_entities("马茂德&#8226;加万") == "马茂德•加万" and decode_entities("&#x4e2d;") == "中"
    assert decode_entities("图一&amp;nbsp; &amp;nbsp;视场角") == "图一   视场角"      # escaped twice
    assert decode_entities("《文选》&#91;2&#93;") == "《文选》[2]"
    assert decode_entities("a&NBSP;b &amacron; &ndotblw;") == "a b ā ṇ"
    assert decode_entities("co&shy;operate") == "cooperate"
    assert decode_entities("也说“走背字儿&rdqu", cut_off=True) == "也说“走背字儿"       # cut off by the corpus
    assert decode_entities("秋读图&amp;amp;amp;lt;礼记") == "秋读图<礼记"       # escaped three times
    for text in ("AT&T", "R&D部门", "&ALICE; 和 &unknownname;", "Q&A", "you&me", "m&ms", "potato&co", None, ""):
        assert decode_entities(text) == text and decode_entities(text, cut_off=True) == text
    assert decode_entities("也说“走背字儿&rdqu") == "也说“走背字儿&rdqu"        # a title is not cut


def test_entities_are_decoded_before_the_other_rules():
    stats = collections.Counter()
    raw = {"title": "两岭乡&#8226;甲", "summary": "两岭乡位于山阳县城东北部，平均气温在7.1&ordm;C。&#91;1&#93;", "tags": [],
           "url": "http://baike.baidu.com/view/2.htm", "sections": [{"title": "简&nbsp;介", "content": "面积128km&sup2;。"}]}
    rec = extract_563w.convert(raw, stats, 300, True)
    assert rec.title == "两岭乡•甲" and rec.summary == "两岭乡位于山阳县城东北部，平均气温在7.1ºC。"
    assert stats["rows_with_entities_decoded"] == 1 and "&" in raw["title"]       # the row itself is left alone
    row = {"title": "大学", "content": "大学 大学（Universit&auml;t）是实施高等教育的学校，包括综合性大学和专科学校等机构。",
           "base_url": "https://baike.baidu.com/item/大学/1", "timestamp": "20220101000000"}
    assert "Universität" in extract_hf.convert(row, collections.Counter(), 300).summary


def test_a_heading_inside_a_section_starts_a_part_of_its_own():
    # one to a line (插足)
    assert section_parts("含义\n犹言厕身其间。 参与。\n出处\n陈三立《次韵》：“插足江湖心倔彊。”\n示例\n你又何必插足。", "插足", "详解") == [
        ["详解", "犹言厕身其间。参与。"], ["出处", "陈三立《次韵》：“插足江湖心倔彊。”"], ["示例", "你又何必插足。"]]
    # with a colon or in brackets, each sense with its own source (尺幅)
    assert section_parts("释义：(1).指小幅的纸或绢。\n【出处】：清 钱杜 《松壶画忆》\n释义：(2).泛称文章、画卷。\n【出处】清 王夫之 《姜斋诗话》",
                         "尺幅", "释义") == [["释义", "(1).指小幅的纸或绢。(2).泛称文章、画卷。"],
                                          ["出处", "清钱杜《松壶画忆》清王夫之《姜斋诗话》"]]
    assert section_parts("不受限制、拘束。例句：马不羁地在草原上跑着。", "不羁", "释义") == [
        ["释义", "不受限制、拘束。"], ["示例", "马不羁地在草原上跑着。"]]
    # 基本解释 and 详细解释 are nothing but headings, with or without a colon
    assert section_parts("那会有杀生！基本解释[Become extinct] 消灭一个物种。详细解释指某些生物之消亡灭绝。", "绝种", "释义") == [
        ["释义", "那会有杀生！[Become extinct] 消灭一个物种。"], ["详解", "指某些生物之消亡灭绝。"]]
    # without a colon the plain words are prose
    assert section_parts("指日夜勤勉戒慎。出处不详，用法简单。解释说明见下。", "某词", "释义") == [["释义", "指日夜勤勉戒慎。出处不详，用法简单。解释说明见下。"]]
    assert section_parts("解释", "注解", "释义") == [["释义", "解释"]]      # the whole text of the section


def test_a_text_that_runs_an_entry_together_is_taken_apart():
    lines = ("成语 一无所获 \n发音 yī wú suǒ huò \n解释 一无：全无 所获：获得。什么东西都没有获得。 \n出处 五代·王定保《唐摭言》：“一无所得。” \n"
             "用法 动宾式；作谓语、定语。\n近义词 一无所有、两手空空\n反义词 满载而归\n歇后语 烂网打鱼\n灯谜 一无所获（打字一）谜底：控")
    assert section_parts(lines, "一无所获", "释义") == [
        ["释义", "一无：全无所获：获得。什么东西都没有获得。"], ["出处", "五代·王定保《唐摭言》：“一无所得。”"],
        ["用法", "动宾式；作谓语、定语。"], ["近义词", "一无所有、两手空空"], ["反义词", "满载而归"]]
    flat = "发音 zhōng shēn dà shì 释义终身：一生。关系一辈子的大事情。出处明·凌蒙初《二刻拍案惊奇》卷二：“草草送了终身大事。”示例但～，非同儿戏。用法作谓语、定语；多指婚姻"
    assert section_parts(flat, "终身大事", "释义") == [
        ["释义", "终身：一生。关系一辈子的大事情。"], ["出处", "明·凌蒙初《二刻拍案惊奇》卷二：“草草送了终身大事。”"],
        ["示例", "但～，非同儿戏。"], ["用法", "作谓语、定语；多指婚姻"]]
    assert section_text("解释 1.象声词。一般形容碰撞声。", "咚咚", "释义") == "1.象声词。一般形容碰撞声。"
    assert section_text("含义是指事物所包含的意义。", "含义", "释义") == "含义是指事物所包含的意义。"      # prose


def test_headword_and_reading_inside_a_section_are_left_out():
    assert section_text("拼音 bái ái ái形容非常洁白。唐岑参诗：“半空白皑皑。”", "白皑皑", "释义") == "形容非常洁白。唐岑参诗：“半空白皑皑。”"
    assert section_text("词目：冷汗 指畏寒、肢冷而出汗。", "冷汗", "释义") == "指畏寒、肢冷而出汗。"
    assert section_parts("名称：主观主义 拼音：zhǔ guān zhǔ yì 解释：由感官内部的条件而引起的处事方法。 出处：毛泽东《改造我们的学习》",
                         "主观主义", "释义") == [["释义", "由感官内部的条件而引起的处事方法。"], ["出处", "毛泽东《改造我们的学习》"]]
    assert section_text("拼音\nbì jūn sān shè\n指退让和回避。", "避君三舍", "释义") == "指退让和回避。"
    assert section_text("名词\n牢狱。也作“圄”。\n动词\n囚禁。", "圉", "详解") == "名词：牢狱。也作“圄”。动词：囚禁。"


def test_lists_and_headings():
    # a list of synonyms ends where the next heading stands
    assert section_parts("近义词：文过饰非 反义词：严于律己、从善如流 用法 联合式；作谓语", "拒谏饰非", "近义词") == [
        ["近义词", "文过饰非"], ["反义词", "严于律己、从善如流"], ["用法", "联合式；作谓语"]]
    assert section_text("严于律己、从善如流 用法 联合式；作谓语", "拒谏饰非", "反义词") == "严于律己、从善如流"
    # in a list, 解释 on a line of its own is a synonym
    assert section_text("解释\n说明\n阐明", "注解", "近义词") == "解释、说明、阐明"
    assert section_parts("说明\n阐明\n反义词\n隐瞒", "注解", "近义词") == [["近义词", "说明、阐明"], ["反义词", "隐瞒"]]
    assert section_parts("严于律己、从善如流\n用法\n联合式；作谓语", "拒谏饰非", "反义词") == [
        ["反义词", "严于律己、从善如流"], ["用法", "联合式；作谓语"]]
    # the headword on a line of its own above the text
    assert section_text("同符合契\n拼音\ntóng fú hé qì\n解释\n比喻完全相合，完全相同。", "同符合契", "释义") == "比喻完全相合，完全相同。"
    assert section_text("同符合契，比喻完全相合。", "同符合契", "释义") == "同符合契，比喻完全相合。"


def test_a_section_of_its_own_wins_over_a_part_inside_another():
    pairs = [("详细解释", "含义\n犹言厕身其间。\n出处\n陈三立《次韵》：“插足江湖心倔彊。”"), ("出处", "鲁迅《热风》：“实没有插足的余地。”")]
    assert pick_sections(pairs, "插足") == [["详解", "犹言厕身其间。"], ["出处", "鲁迅《热风》：“实没有插足的余地。”"]]
    assert pick_sections(pairs[:1], "插足") == [["详解", "犹言厕身其间。"], ["出处", "陈三立《次韵》：“插足江湖心倔彊。”"]]
    # an overlay section in one line
    overlay = [("成语用法", "成文用法 “明察秋毫”形容人很精明；在句中一般作谓语、定语；含褒义。运用示例三国魏·曹植《与吴季重书》：“想足下助我张目。”")]
    assert pick_sections(overlay, "明察秋毫", "明察秋毫，汉语成语。") == [
        ["用法", "“明察秋毫”形容人很精明；在句中一般作谓语、定语；含褒义。"], ["示例", "三国魏·曹植《与吴季重书》：“想足下助我张目。”"]]


def test_first_line_with_the_headword():
    assert section_text("【头油】tóuyóu\n（1）抹在头发上的油质化妆品", "头油", "释义") == "（1）抹在头发上的油质化妆品"
    assert section_text("1、见“墨迹”。\n2、禅宗和尚的书法。", "墨迹", "详解") == "1、见“墨迹”。2、禅宗和尚的书法。"
    assert section_text("拼音：duì, 笔画：7 古同“对”。", "対", "释义") == "古同“对”。"


def test_headings_found_while_reading_samples():
    # 出处 on the first line of a 详细解释 section heads the senses with their quotations
    assert section_parts("出处\n亦作“妖饶”。1.妩媚多姿。唐何希尧《海棠》诗：“半开时节最妖娆。”", "妖娆", "详解") == [
        ["详解", "亦作“妖饶”。1.妩媚多姿。唐何希尧《海棠》诗：“半开时节最妖娆。”"]]
    text = "【名称】：完整 【拼音】：wán zhěng 【近义词】：完好 【词性】：形容词，褒义基本解释◎ 完整 wánzhěng [complete;entire] 完备;没有残缺"
    assert section_parts(text, "完整", "释义") == [
        ["释义", "◎ 完整 wánzhěng [complete;entire] 完备;没有残缺"], ["近义词", "完好"], ["用法", "形容词，褒义"]]
    assert section_parts("《礼记·中庸》：“喜怒哀乐之未发谓之中。”【事例】虽是海外之邦，那～的人情，原是一样的。【典故】从前有个人。", "喜怒哀乐", "出处") == [
        ["出处", "《礼记·中庸》：“喜怒哀乐之未发谓之中。”"], ["示例", "虽是海外之邦，那～的人情，原是一样的。"]]
    assert section_text("这个词的基本解释是这样的。", "某词", "释义") == "这个词的基本解释是这样的。"


def test_headings_spaced_out_to_one_width():
    lines = ("拼音： 举棋不定 ( jǔ qí bù dìng )\n解 释： 举：拿起，拿着。比喻做事犹豫不决。\n出 处： 先秦·左丘明《左传》：“弈者举棋不定。”\n"
             "用 法： 连动式；作谓语\n近 义 词： 犹豫不决、优柔寡断\n灯 谜：举棋不定（打四字口语一）")
    assert section_parts(lines, "举棋不定", "释义") == [
        ["释义", "举：拿起，拿着。比喻做事犹豫不决。"], ["出处", "先秦·左丘明《左传》：“弈者举棋不定。”"],
        ["用法", "连动式；作谓语"], ["近义词", "犹豫不决、优柔寡断"]]
    spaced = "海角天涯\n发　音 hǎi jiǎo tiān yá\n释　义 形容极远的地方。\n出　处 唐·白居易《春生》：“海角天涯遍始休。”\n示例 宋˙张世南《游宦记闻》"
    assert section_parts(spaced, "海角天涯", "释义") == [
        ["释义", "形容极远的地方。"], ["出处", "唐·白居易《春生》：“海角天涯遍始休。”"], ["示例", "宋˙张世南《游宦记闻》"]]
    assert section_text("解 释 付：交给；之：它。扔在东流的江河里冲走。", "付之东流", "释义") == "付：交给；之：它。扔在东流的江河里冲走。"
    # names of people are spaced the same way and stay
    assert section_text("唐 张 鷟 《朝野佥载》卷三：“合置姬媵。”", "姬媵", "详解") == "唐张鷟《朝野佥载》卷三：“合置姬媵。”"


def test_table_header_one_character_meaning_and_empty_parts():
    flat = "读音词性释义英译例句例词 jiā 名词古代妇女的一种首饰。an ancient woman's personal ornaments 《诗·鄘风》：“副笄六珈。”"
    assert section_parts(flat, "珈", "详解") == [["详解", flat[len("读音词性释义英译例句例词 "):]]]
    assert section_text("解释 1.妾 ", "姬媵", "释义") == "1.妾"        # one character is the whole meaning
    assert section_text("无", "某词", "释义") == "" and section_text("妾", "某词", "近义词") == ""
    # the only part says nothing: the section is not kept under its own label instead
    assert section_parts("【近义词】：见几而作", "见几而作", "辨析") == []
    assert section_parts("读音èr bǎi wǔ近义词傻头傻脑 反义词机智 释义（1）指傻头傻脑的人！", "二百五", "释义") == [
        ["释义", "（1）指傻头傻脑的人！"], ["近义词", "傻头傻脑"], ["反义词", "机智"]]


def test_more_found_in_samples():
    # 《仓颉篇》 is a book, not an input code
    text = "(1) (形声。本义:大声呵斥) (2) 同本义。叱,呵也。——《说文》大呵为叱。——《仓颉篇》"
    assert section_text(text, "叱", "详解") == text
    assert section_text("歇后语。袜子上拆下来的线，都是短的，用来讥讽人没有一点长处。", "拆袜线", "释义").startswith("歇后语。袜子")
    assert section_parts("注音：xié mén解释解释", "邪门", "释义") == []
    assert section_parts("解释", "注解", "释义") == [["释义", "解释"]]


def test_input_codes_end_the_text_of_a_meaning():
    yi = ("● 臆\n（ yì ）\n◎ 胸：胸～（心里，多指心里的话或想法，如“直抒～～”）。\n◎ 主观地，缺乏客观依据的：～造。～测。～断。～见。\n"
          "简体部首：月，部外笔画：13,总笔画：17\n繁体部首：肉\n五笔86&98:EUJN　仓颉：BYTP　郑码：QSKW\n笔顺编号：35114143125114544")
    text = section_text(yi, "臆", "释义")
    assert text.endswith("～造。～测。～断。～见。") and "胸～" in text
    wei = "wěi\n⑴ ㄨㄟˇ\n⑵ 假，不真实：～造。～装。～劣。\n⑶ 不合法的：～政府。～军。\n⑷ 郑码：NUYS，U：4F2A，GBK：CEB1，\n⑸ 笔画数：6，部首：亻"
    assert section_text(wei, "伪", "释义").endswith("⑶ 不合法的：～政府。～军。")
    # the codes first, the senses after them
    yu = "基本解释拼音：yú，笔划：10\n部首：女 部首笔划：3\n娱\nyú\n快乐或使人快乐：娱乐（使欢乐）。娱老（欢度晚年）。\n笔顺编号：5312511134，四角号码：46484"
    assert section_text(yu, "娱", "释义") == "娱 yú 快乐或使人快乐：娱乐（使欢乐）。娱老（欢度晚年）。"
    # 仓颉 the man is not a code
    quote = "黄帝之史仓颉，见鸟兽蹄迒之迹，知分理之可相别异也，初造书契。"
    assert section_text(quote, "书契", "出处") == quote
    assert section_text("五笔86:UJFF五笔98:UJFF仓颉：YTWG", "童", "释义") == ""
    bao = ("基本信息保 bǎo [ 保 ]\n拼音：bǎo\n繁体：保\n部首：亻\n部首笔划：2\n字意五行：水\n简体笔划：9\n古文形体拼音输入：bao\n五笔输入：WK\n"
           "吉凶寓意：吉\n笔顺：撇竖竖折横横竖撇捺")
    assert section_text(bao, "保", "释义") == ""


def test_a_meaning_heading_inside_a_detailed_section_stays_there():
    chang = "详细字义\n◎ 惝 chǎng\n基本词义\n◎ 惝 tǎng\n〈形〉\n(1) (形声。从心,尚声。本义:怅惘)\n(2) 同本义"
    assert section_parts(chang, "惝", "详解") == [["详解", "◎ 惝 chǎng ◎ 惝 tǎng 〈形〉 (1) (形声。从心,尚声。本义:怅惘) (2) 同本义"]]
    parts = dict(section_parts("1. 【词义】：<书>违背常情；乖戾：措置～。违忤；不和谐。", "乖剌", "详解"))
    assert list(parts) == ["详解"] and "违背常情" in parts["详解"]
    # in a 释义 section 详细解释 starts a part as before
    assert [name for name, _text in section_parts("基本解释\n形容气力大。\n详细解释\n扛：举。鼎：三足两耳的器物。", "力能扛鼎", "释义")] == [
        "释义", "详解"]
    # a section that is nothing but a heading
    assert section_parts("基本解释", "平手", "详解") == []
    assert section_parts("解释", "注解", "释义") == [["释义", "解释"]]


def test_the_kind_of_word_after_cixing():
    assert section_parts("词性：形容词炽痛的含义：热烈而深切。", "炽痛", "释义") == [
        ["释义", "炽痛的含义：热烈而深切。"], ["用法", "形容词"]]
    assert dict(section_parts("衙门里的人，一个个是～。词性：贬义成语；古代成语", "饿虎饥鹰", "示例"))["用法"] == "贬义成语；古代成语"
    long = "词性：由两个偏正短语“晨钟”与“暮鼓”组成。比喻可以使人警觉醒悟的话。"
    assert section_parts(long, "晨钟暮鼓", "释义") == [["释义", long]]


def test_more_about_codes_and_kinds_of_word():
    assert section_text("基本信息诚 繁体字：诚 注音：ㄔㄥˊ 田字格中的“诚”字\n部首：讠\n笔画数：8", "诚", "释义") == ""
    xie = "笔画数：8，部首：月\n⒈从腋下到肋骨尽处的部分：～下。\n⒉逼迫恐吓：～迫。威～。"
    assert section_text(xie, "胁", "释义") == "⒈从腋下到肋骨尽处的部分：～下。⒉逼迫恐吓：～迫。威～。"
    sen = "行书“森”五笔字型：SSS 造字法：会意 本义：树木丛生繁密"
    assert section_text(sen, "森", "释义") == "造字法：会意本义：树木丛生繁密"
    assert section_parts("词性：动词。遗失票据或证件时，到原发的机关去登记，声明作废。", "挂失", "释义") == [
        ["释义", "遗失票据或证件时，到原发的机关去登记，声明作废。"], ["用法", "动词"]]


def test_what_a_character_page_lists_around_the_codes():
    ke = "田字格中的“壳”字\n【仓颉】G B H N\n【部首】士\nké\n1、〈口〉[名]坚硬的外皮：蛋～儿‖贝～儿。"
    assert section_text(ke, "壳", "释义") == "ké 1、〈口〉[名]坚硬的外皮：蛋～儿‖贝～儿。"
    assert section_text("中文读音【汉字】惑 英文读音be puzzled；delude；mislead；部首笔画", "惑", "释义") == ""
    assert section_text("康熙字典笔画( 契:9) 字意五行：木 吉凶寓意：吉 “契”的字源演变姓名学：姓,多用男性", "契", "释义") == ""
    jian = "集中优势兵力；各个～敌人。（作谓语）\n【笔画数】7\n【五笔编码】gqt gqtf\n【部首】歹"
    assert section_text(jian, "歼灭", "示例") == "集中优势兵力；各个～敌人。（作谓语）"
    assert section_text("笔画：八画\n来，由另一方面到这一方面，与“往”、“去”相对；已经到了之意。", "来了", "释义").startswith("来，由另一方面")
    assert section_text("基本信息wěi\n⑵ 假，不真实：～造。～装。", "伪", "释义") == "wěi ⑵ 假，不真实：～造。～装。"
    # a line drawn across the page is not text
    biao = "部首:风,部外笔画:5\n基本字义\n----------------------------------------\n● 飑\nbiāo\n◎ 气象学上指风向突然改变，风速急剧增大的天气现象。"
    assert section_text(biao, "飑", "详解") == "● 飑 biāo ◎ 气象学上指风向突然改变，风速急剧增大的天气现象。"
