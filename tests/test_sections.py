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


def test_entities_without_a_semicolon_and_damaged_ones():
    assert decode_entities("MM(MCJH&" + "amp;" * 7 + "TWJ)") == "MM(MCJH&TWJ)"          # escaped seven times
    assert decode_entities("占地&nbsp11&nbsp78公顷，2台&NBSP31.5MVA") == "占地 11 78公顷，2台 31.5MVA"
    # what is left of an entity that the corpus cut off, mostly at the end of a caption
    assert decode_entities("汤米&amp汤米是一位社会企业家") == "汤米汤米是一位社会企业家"
    assert decode_entities("Club Can&amp迪士尼打造的，油画《金云翘传》Kim V&amp") == "Club Can迪士尼打造的，油画《金云翘传》Kim V"
    assert decode_entities("周信芳,周五宝&amp 著名的京剧剧目，篱笆边&amp1、治肺热") == "周信芳,周五宝 著名的京剧剧目，篱笆边1、治肺热"
    assert decode_entities("“云鹰&quot该船，温州特产 &gt分别，集数：14）&lt") == "“云鹰该船，温州特产 分别，集数：14）"
    assert decode_entities("Honey &amp Clover, Kit&amp Bee") == "Honey & Clover, Kit& Bee"      # between Latin words
    assert decode_entities("一统天下.&lt；br&gt；九五至尊，五笔86&amp；98&#91；2&#93；") == "一统天下.<br>九五至尊，五笔86&98[2]"
    assert decode_entities("&bsp;&bsp;序言，五笔86&agmp;98，用Q&subm;表示") == "  序言，五笔86&98，用Qm表示"
    assert decode_entities("《新序》&S226;杂事第四》，应用领域 &O1548;空分制氮") == "《新序》•杂事第四》，应用领域 空分制氮"
    for text in ("AT&T", "R&amplifier", "guitar&amps", "A&LT集团", "s&gt5", "you&me；", "Q&A；", "上海&ALICE;&蓬莱",
                 "&nbspace", "&subx;", "&amp#x"):
        assert decode_entities(text) == text and decode_entities(text, cut_off=True) == text


def test_layout_tags_in_body_text():
    def body(text):
        return decode_entities(text, cut_off=True)

    assert body("完全可信赖的实力企业。<br> 吉顺号在云南省<BR>西双版纳，<br />易武") == "完全可信赖的实力企业。  吉顺号在云南省 西双版纳， 易武"
    assert body("耕地1241</SPAN>亩。<FONT color=#c60a00>俞颖</FONT>传") == "耕地1241 亩。 俞颖 传"
    assert body("<A href=\"http://example.com/1.htm\">果糖代谢紊乱</a>，教您<a>怎么做冬菇鸡冻</a>") == " 果糖代谢紊乱，教您怎么做冬菇鸡冻"
    assert body("一统天下.&lt；br&gt；九五至尊") == "一统天下. 九五至尊"      # a tag that was escaped
    for text in ("专辑<A Year Without Rain>的首支单曲", "#include <stdio.h>", "醴泉 <li quan> 释名", "形式如<math>(2^p+1)/3</math>的质数",
                 "li 标签定义列表项目。以<li>开始</li>结束", "nl2br() 函数插入 HTML 换行符 (<br />)。", "<b> 《现场安全员岗位通》",
                 "意思是超文本引用。1.内部连接：<a href=\"#/URL\">name</a>"):
        assert body(text) == text
    assert decode_entities("<p>标题</p>") == "<p>标题</p>"         # a title is left alone
    # a word that is said of other things does not make a text one about markup: 标签 far from the tag, 元素 and
    # 字母 that name no tag, html inside a pasted tag
    far = "轻者晨起后见眼睑浮肿，重者水肿延及全身。" * 6
    assert body("此外血管病</a>变如高血压。" + far + "仔细阅读食物成分标签。") == "此外血管病变如高血压。" + far + "仔细阅读食物成分标签。"
    assert body("耕地1241</SPAN>亩。所产矿泉水富含人体必须的多种矿物元素。") == "耕地1241 亩。所产矿泉水富含人体必须的多种矿物元素。"
    assert body("<p>抹茶故事MATCHA 男装强调时尚元素，令穿着者相信。</p>") == " 抹茶故事MATCHA 男装强调时尚元素，令穿着者相信。 "
    assert body("台语现代文（<noinclude>，简称MLT），用26个拉丁字母即可拼出") == "台语现代文（ ，简称MLT），用26个拉丁字母即可拼出"
    assert body("<a target=_blank href=/view/9438.htm>宗教</a>元素。富含微量元素<br>口感清甜") == " 宗教元素。富含微量元素 口感清甜"
    assert body("楼盘信息<iframe src=\"/editor/map/mapElem.html?from=lemmaview\"></iframe>交通便利") == "楼盘信息  交通便利"
    for text in ("查找文档中所有的 <p> 元素，不管 <p> 元素处于哪个层次", "不支持iframe元素。可以把文本放置在<iframe>和</iframe>之间",
                 "创建页面元素<div id=\"ID值\"></div>", "返回 category 属性是否是 <book> 元素的 ID 属性：document.write(\"<br />\")",
                 "将PHP控件化，既可以实现各种表格列表又可以实现<Li></Li>形式的列表", "食品标签上的换行写作<br>"):
        assert body(text) == text


def test_characters_of_the_private_use_area():
    def body(text):
        return decode_entities(text, cut_off=True)

    def pua(code):
        return chr(code)

    # GB 18030-2000 had these there
    assert body("口眼" + pua(0xE81F) + "斜，字从“" + pua(0xE83B) + "”，芎" + pua(0xE840) + "，写成“" + pua(0xE836) + "”") == \
        "口眼㖞斜，字从“𢦏”，芎䓖，写成“⺮”"
    assert decode_entities("慈禧奕" + pua(0xE844) + "政变记") == "慈禧奕䜣政变记" and decode_entities(pua(0xE816)) == "𠂇"
    # letters of a symbol font: a bullet, or a sign where the text around it says so
    assert body("个人简历" + pua(0xF06C) + " 蔡达建，男。" + pua(0xF0B2) + "现场管理咨询") == "个人简历  蔡达建，男。 现场管理咨询"
    assert body("DS" + pua(0xF0B3) + "2.75，结合" + pua(0xF06D) + "C/OS-II，100）" + pua(0xF06D) + "m，聚" + pua(0xF061) + "烯烃") == \
        "DS≥2.75，结合μC/OS-II，100）μm，聚α烯烃"
    assert body("蜡烛工艺" + pua(0xF02C) + "塑胶玩具行业，" + pua(0xF02C) + "礼品文具行业") == "蜡烛工艺，塑胶玩具行业，礼品文具行业"
    assert body("约翰斯" + pua(0xF0D7) + "霍普金斯大学，移主" + pua(0xF06D) + "（藏）郎中") == "约翰斯·霍普金斯大学，移主 （藏）郎中"
    assert body("阿法根" + pua(0xF0D2) + "，1982" + pua(0xF02D) + "1999年，200km" + pua(0xF07E) + "700km") == "阿法根®，1982-1999年，200km～700km"
    # a character the text has and cannot show
    assert body("其上独有云气，" + pua(0xF4CE) + "兮直上，令尹" + pua(0xF091) + "祁，亦作\"峣" + pua(0xE422) + "\"") == \
        "其上独有云气，□兮直上，令尹□祁，亦作\"峣□\""
    # nothing: in front of a text, and the two seen only between sentences
    assert body(pua(0xE817) * 2 + "氢化亚铜(CuH)是铜的二元化合物。") == "氢化亚铜(CuH)是铜的二元化合物。"
    assert body("安徽人。" + pua(0xE004) + "1977年毕业于蚌埠医学院。") == "安徽人。1977年毕业于蚌埠医学院。"
    # a title keeps the ones inside it and loses those at its ends
    assert decode_entities("开元十四年碑" + pua(0xE004)) == "开元十四年碑" and decode_entities(pua(0xE814) + "故城北大医院") == "故城北大医院"
    assert decode_entities("相对磁导率" + pua(0xF06D)) == "相对磁导率μ"
    assert decode_entities("赵" + pua(0xE7FE) + "庆") == "赵" + pua(0xE7FE) + "庆"


def test_what_follows_a_list_of_synonyms():
    for text, title, label, want in (
            ("唇枪舌剑 【使用程度】常用成语 【感情色彩】中性成语 【产生年代】古代成语", "促膝谈心", "反义词", [["反义词", "唇枪舌剑"]]),
            ("瞌睡、小憩 【英文】：doze off", "打盹", "近义词", [["近义词", "瞌睡、小憩"]]),
            ("虎头蛇尾、有头无尾、半途而废 英语翻译：Do difficult things by an old person", "愚公移山", "反义词",
             [["反义词", "虎头蛇尾、有头无尾、半途而废"]]),
            ("防患未然、未雨绸缪 未雨绸缪：绸缪：紧密缠缚。天还没有下雨，先把门窗绑牢。", "曲突徙薪", "近义词", [["近义词", "防患未然、未雨绸缪"]]),
            ("愚不可及、【相反词】明锐、足智多谋、【同韵词】事无三不也、抱打不平", "冥顽不灵", "近义词",
             [["近义词", "愚不可及"], ["反义词", "明锐、足智多谋"]]),
            ("椎胸跌足、椎膺顿足 常用程度：一般 感情色彩：贬义词 语法", "椎胸顿足", "近义词", [["近义词", "椎胸跌足、椎膺顿足"]]),
            ("措施、法子、对策", "方法", "近义词", [["近义词", "措施、法子、对策"]]),
            (" 近义词[1] 不可名状  ", "莫可名状", "辨析", [["近义词", "不可名状"]]),        # a source mark is no heading
            (" 确数：确数就是准确的数。单个的数字也是确数。", "概数", "反义词", [["反义词", "确数：确数就是准确的数。单个的数字也是确数。"]]),
            ("大概的数。反义词 确数：确数就是准确的数。单个的数字也是确数。", "概数", "释义",
             [["释义", "大概的数。"], ["反义词", "确数：确数就是准确的数。单个的数字也是确数。"]]),
            ("四分五裂常用程度：常用感情色彩：褒义词语法用法：作谓语、定语；指一个整体。", "不可分割", "反义词",
             [["反义词", "四分五裂"], ["用法", "作谓语、定语；指一个整体。"]]),
            (" 【近义词】：赤胆忠心、忠贞不渝 【润匙去反义词】： 虚与委蛇、假仁假义[1]  ", "忠心耿耿", "辨析",
             [["近义词", "赤胆忠心、忠贞不渝"], ["反义词", "虚与委蛇、假仁假义"]]),
            (" 【近义词】：[1] 食不二味、食不兼味 【反义词】：大吃大喝、食案方丈", "食不重味", "辨析",
             [["近义词", "食不二味、食不兼味"], ["反义词", "大吃大喝、食案方丈"]]),
            ("近义词：美丽、漂亮；反义词：丑陋", "好看", "近义词", [["近义词", "美丽、漂亮"], ["反义词", "丑陋"]])):
        assert section_parts(text, title, label) == want


def test_an_example_glued_to_a_meaning():
    assert section_parts("强壮而勇猛；强悍示例粗犷彪悍。", "彪悍", "详解") == [["详解", "强壮而勇猛；强悍"], ["示例", "粗犷彪悍。"]]
    assert section_parts("使别人得到；给示例母亲，你给予了我生命。", "给予", "详解") == [
        ["详解", "使别人得到；给"], ["示例", "母亲，你给予了我生命。"]]
    assert section_parts("没有错误；正确，合适例句：方法对头，效率就高。", "对头", "详解") == [
        ["详解", "没有错误；正确，合适"], ["示例", "方法对头，效率就高。"]]
    assert section_parts("掌文庙祭祀、教育所属生员。用法示例：南平教谕。——清·张廷玉", "教谕", "释义") == [
        ["释义", "掌文庙祭祀、教育所属生员。"], ["示例", "南平教谕。——清·张廷玉"]]
    assert section_parts("(动)较小的物体黏着在较大的物体上。[构成] 偏正式 [例句] 水珠儿附着在窗子的玻璃上。", "附着", "释义") == [
        ["释义", "(动)较小的物体黏着在较大的物体上。[构成] 偏正式"], ["示例", "水珠儿附着在窗子的玻璃上。"]]
    assert section_parts("(1).厚缯制成之袍。【示例1】《后汉书·郎顗传》：“故孝文皇帝绨袍革舃。”", "绨袍", "释义") == [
        ["释义", "(1).厚缯制成之袍。"], ["示例", "《后汉书·郎顗传》：“故孝文皇帝绨袍革舃。”"]]
    for text, title, label in (
            ("有所遗憾【例句及翻译】：1. 不无遗憾的是，我们中的大部分人生来就只吃某几种食品。", "不无遗憾", "释义"),
            ("朱光潜《艺文杂谈·欧洲书牍示例》：“罗马在鼎盛时代，文艺也鼎盛。”", "鼎盛", "详解"),       # a title
            ("yī解释与示例（1）美盛貌。《诗经》：“瞻彼淇奥，绿竹猗猗。”", "猗猗", "释义"),             # a heading of the senses
            ("这里提供示例说明教谕的职责，教谕负责教育生员。", "教谕", "释义"),                          # a sentence
            ("创：创新之能弈：博弈之道工：天工之作场：浩然之气例句创新之能：不墨守成规。", "创弈工场", "释义")):    # no example of the word
        assert section_parts(text, title, label) == [[label, text]]


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


def test_a_heading_glued_to_the_text_on_both_sides():
    # in a 用法 text, which is a formula
    assert section_parts("作谓语、定语；多指婚姻示例但～，一生至一死，非同儿戏。", "终身大事", "用法") == [
        ["用法", "作谓语、定语；多指婚姻"], ["示例", "但～，一生至一死，非同儿戏。"]]
    assert section_parts("作谓语，也作定语、补语，含贬义。赔了夫人又折兵运用示例明·冯梦龙《醒世恒言》：“周瑜妙计安天下。”",
                         "赔了夫人又折兵", "用法") == [
        ["用法", "作谓语，也作定语、补语，含贬义。"], ["示例", "明·冯梦龙《醒世恒言》：“周瑜妙计安天下。”"]]
    assert section_parts("补充式；作谓语、定语；含贬义。示例 1、倒卖假冒伪劣产品的商贩已经到了～的地步。", "肆无忌惮", "用法") == [
        ["用法", "补充式；作谓语、定语；含贬义。"], ["示例", "1、倒卖假冒伪劣产品的商贩已经到了～的地步。"]]
    # in a list of synonyms the next heading ends the list
    assert section_parts("阳春白雪反义词下里巴人成语出处战国·楚·宋玉《对楚王问》：“引商刻羽，杂以流徵。”", "曲高和寡", "近义词") == [
        ["近义词", "阳春白雪"], ["反义词", "下里巴人"], ["出处", "战国·楚·宋玉《对楚王问》：“引商刻羽，杂以流徵。”"]]
    assert section_parts("不骄不躁、虚怀若谷反义词骄傲自大、不可一世用法作谓语、宾语；指人要谦虚", "戒骄戒躁", "近义词") == [
        ["近义词", "不骄不躁、虚怀若谷"], ["反义词", "骄傲自大、不可一世"], ["用法", "作谓语、宾语；指人要谦虚"]]
    assert section_text("说明出处、阐明用法", "注明", "近义词") == "说明出处、阐明用法"
    # after a sentence: 示例, and 出处 in front of a source
    assert section_parts("指贪心重，无法满足。出处语出《国语·晋语八》：“谿壑可盈，是不可餍也。”", "欲壑难填", "释义") == [
        ["释义", "指贪心重，无法满足。"], ["出处", "语出《国语·晋语八》：“谿壑可盈，是不可餍也。”"]]
    assert section_parts("虽苦楚万端，对之自若。”示例为了这一刻,他经受了多少苦楚。", "苦楚", "出处") == [
        ["出处", "虽苦楚万端，对之自若。”"], ["示例", "为了这一刻,他经受了多少苦楚。"]]
    # right after the headword
    assert section_parts("1.放入、挤入、刺入、穿入；加进去。插入示例插入词语| 插入图片", "插入", "详解") == [
        ["详解", "1.放入、挤入、刺入、穿入；加进去。"], ["示例", "插入词语| 插入图片"]]
    assert section_text("垃圾释义 “垃”字从土从立，“土”即土块、土粒。", "垃圾", "释义") == "“垃”字从土从立，“土”即土块、土粒。"
    assert section_parts("能做到这个程度,真是不简单出处1. 单纯；不复杂。茅盾《宿莽》：“事务又简单。”", "简单", "详解") == [
        ["详解", "能做到这个程度,真是不简单"], ["出处", "1. 单纯；不复杂。茅盾《宿莽》：“事务又简单。”"]]
    # what follows a list of synonyms and has no label
    assert section_text("把酒持螯、持螯把盏英文翻译 enjoy a cup of wine 常用程度：一般感情色彩：褒义词", "持螯把酒", "近义词") == \
        "把酒持螯、持螯把盏"
    assert section_text("肝肠寸断、天怒人怨、拍手称快的英文翻译to clap one's hands", "拍手称快", "反义词") == "肝肠寸断、天怒人怨"
    # a spaced-out heading in brackets, and other brackets
    assert section_parts("【释 义】：比喻忠诚不二。\n【出 处】：西汉·司马迁《史记》：“剖心坼肝相信。”", "剖心坼肝", "释义") == [
        ["释义", "比喻忠诚不二。"], ["出处", "西汉·司马迁《史记》：“剖心坼肝相信。”"]]
    assert section_parts("『解释』相传鹏鸟能飞万里路程。『出处』《庄子·逍遥游》：“鹏之徙于南冥也。”", "鹏程万里", "释义") == [
        ["释义", "相传鹏鸟能飞万里路程。"], ["出处", "《庄子·逍遥游》：“鹏之徙于南冥也。”"]]
    # the page of a character lists its compounds, each with an example: the next one is no example
    mi = "迷糊míhu 神志或眼睛模糊不清。例句奶奶病得很重，有时迷糊。迷惑 míhuò ①辨不清是非；摸不着头脑。"
    assert section_parts(mi, "迷", "释义") == [["释义", mi]]
    # the same words in a sentence
    for text, title, label in (
            ("例子；榜样。元关汉卿《窦娥冤》第二折：“都看取我这般傍州例。”", "傍州例", "释义"),
            ("举例：在新颖独创方面很少有更显著的例子了。", "显著", "用法"),
            ("铸铁管，用铸铁浇铸成型的管子。铸铁管用法兰固定，内垫橡胶法兰垫片密封；", "铸铁管", "释义"),
            ("宠辱不惊的近义词是置之度外", "宠辱不惊", "近义词"),
            ("“还我河山”出自岳飞庙内岳飞草书“还我河山”巨匾。", "还我河山", "出处"),
            ("指父母对子女的教育虽然严厉，却是因为深爱孩子。出处是七八十年代的俗语。", "打是亲骂是爱", "释义"),
            ("代表仁，义，礼，智，信五德，然而这种说法没有具体的出处。", "五色旗", "释义"),
            ("朱光潜《艺文杂谈·欧洲书牍示例》：“罗马在鼎盛时代。”示例性的说明。", "鼎盛", "详解"),
            ("“苍孙”和老炮儿在作为年长男性的称呼上用法近似，但并不侧重。", "老炮儿", "释义"),
            ("司法解释是指国家最高司法机关对具体适用法律的问题作出的解释。", "司法解释", "释义")):
        assert section_parts(text, title, label) == [[label, text]]


def test_the_caption_of_a_picture_of_the_character():
    chang = "  田字格 长汉语拼音：cháng\n(1) ㄔㄤˊ\n(2) 两端的距离：～度。\n(3) 长度大，与“短”相对：～短。"
    assert section_text(chang, "长", "释义") == "(1) ㄔㄤˊ (2) 两端的距离：～度。(3) 长度大，与“短”相对：～短。"
    assert section_text("田字格里的‘烦’◎ 苦闷，急躁：～躁。～乱。～恼。", "烦", "释义") == "◎ 苦闷，急躁：～躁。～乱。～恼。"
    assert section_text("田字格“缝”（缝）féng ㄈㄥˊ ◎ 用针线连缀：缝纫。缝缀。", "缝", "释义") == "（缝）féng ㄈㄥˊ ◎ 用针线连缀：缝纫。缝缀。"
    assert section_text("过程。过渡。经过。田字格中的简体字‘过’经过某种处理方法：过滤。", "过", "释义") == \
        "过程。过渡。经过。经过某种处理方法：过滤。"
    assert section_text("田字格之宋体字1）有土地、人民、主权的政体。", "国", "释义") == "1）有土地、人民、主权的政体。"
    assert section_text("● 浩田字格中的“浩”字hàoㄏㄠˋ\n◎ 水大，引申为大和多：～大。～繁。", "浩", "释义") == \
        "◎ 水大，引申为大和多：～大。～繁。"
    assert section_text("〈名〉田字格中的“伍”字1、（会意。从人，从五。五人为伍。）2、同本义", "伍", "释义") == \
        "〈名〉 1、（会意。从人，从五。五人为伍。）2、同本义"
    assert section_text("“掽”在米字格中的写法同“碰”。", "掽", "释义") == "同“碰”。"
    assert section_text("（1）（形声。本义：水势浩大)。书法“浩”字（2）同本义。浩，浇也。", "浩", "详解") == \
        "（1）（形声。本义：水势浩大)。（2）同本义。浩，浇也。"
    sentence = "细细揣摩，然后一笔一画，一丝不苟地往“米”字格的大字本上写。"
    assert section_text(sentence, "一丝不苟", "示例") == sentence
    assert section_text("田字格是一种练习写字的格子，用于规范汉字书写。", "田字格", "释义") == "田字格是一种练习写字的格子，用于规范汉字书写。"
    # a page that lists nothing but how the character is written still gives nothing
    assert section_text("基本信息诚 繁体字：诚 注音：ㄔㄥˊ 田字格中的“诚”字\n部首：讠\n笔画数：8", "诚", "释义") == ""


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
