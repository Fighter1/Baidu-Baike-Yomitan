from baike2yomitan.cleaning import (clean_text, first_paragraph, strip_citations,
                                    summary_drop_reason, title_drop_reason, trim_summary)


def test_strip_citation_markers():
    assert strip_citations("行动[1-2]\xa0展开。[3] 要求[7]\xa0。") == "行动\xa0展开。 要求\xa0。"
    assert strip_citations("修订［12］法") == "修订法"


def test_brackets_that_hold_nothing_any_more():
    # a note on where the page has its info table or its picture from, once the citation marks are gone
    assert clean_text("又引申为竞争。（基本信息栏主要参考资料：[3] ）") == "又引申为竞争。"
    assert clean_text("狮子搏兔 （词语参考资料[8] [9] ）") == "狮子搏兔"
    assert clean_text("（参考资料：[7-8]  [9] [10-11]  ）") == ""
    assert clean_text("教参（教学参考资料）是教师用书") == "教参（教学参考资料）是教师用书"
    # the same note with its source in words, and what a page says of a picture the dictionary has not got
    assert clean_text("祛风之效。（概述图参考来源：中国自然标本馆[2] ）") == "祛风之效。"
    assert clean_text("又引申为时间上的一个完整循环。（基本信息主要来源：《新华写字字典第2版》、汉典网）") == "又引申为时间上的一个完整循环。"
    assert clean_text("云南有引种。（资料来源：中国植物物种信息）") == "云南有引种。"
    assert clean_text("演绎剧情。（概述图人物：乔瓦尼·巴蒂斯塔·佩尔戈莱西）") == "演绎剧情。"
    assert clean_text("（参考资料：六安政府网、中国文明网等）") == ""
    for text in ("咖啡（来源：阿拉伯语qahwa）是一种饮料", "该系统（信息资料管理系统）已投入使用", "数据（来自2010年人口普查）显示"):
        assert clean_text(text) == text
    # a name in a script that the corpus lost
    assert clean_text("帕勒马希姆（希伯来语：）以色列的一个集体公社") == "帕勒马希姆以色列的一个集体公社"
    assert clean_text("热尔杰夫卡（俄语：Жердевка，英语：），城市名") == "热尔杰夫卡（俄语：Жердевка），城市名"
    assert clean_text("格尔利茨（德语：，波兰语：，索布语：，捷克语：）是德国的城市") == "格尔利茨是德国的城市"
    assert clean_text("约翰尼斯·延森（，1873-1950）丹麦小说家") == "约翰尼斯·延森（1873-1950）丹麦小说家"
    assert clean_text("安东尼·沃尔（Anthony David Wall，）英国高尔夫球运动员") == "安东尼·沃尔（Anthony David Wall）英国高尔夫球运动员"
    assert clean_text("刘言（），吉州庐陵人。桑吉省（）是布基纳法索的一个省") == "刘言，吉州庐陵人。桑吉省是布基纳法索的一个省"
    for text in ("内设机构共计（）个，人员编制20名", "笔名（）介、余川等", "有小括弧()、中括弧[]、大括弧三种", "原文中有明显错误者加圆括符（），",
                 "rindex（）用来找出参数s字符串中最后一个出现的地址", "t = (1,) 是一个元组", "须将点的地球坐标（，λ）换算成球面坐标",
                 "孔子说：“（虽然是简陋的地方，但只要君子在这里居住，）又有什么简陋的呢", "专辑《我(不：)是张卫健》", "顿号（、）表示并列",
                 "（四至范围：）东至左堤"):
        assert clean_text(text) == text


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


def test_titles_are_not_cleaned_like_body_text():
    from baike2yomitan.cleaning import clean_title

    # 编辑, 语音 and 播报 are Baike interface labels in body text, and ordinary headwords
    assert [clean_title(t) for t in ("编辑", "语音", "播报", "语音编辑器", "视频 编辑")] == ["编辑", "语音", "播报", "语音编辑器", "视频编辑"]
    assert clean_title("  词　目\xa0") == "词目" and clean_title(None) == ""
    assert clean_text("编辑") == ""        # the body rule is unchanged


def test_caption_inside_a_sentence_is_cut_at_the_title():
    # real summaries; the old rule deleted the twelve characters before every "(N张)"
    assert clean_text("塔围长21.6荆山皇帝陵景色(20张)米，高约十米。", "荆山皇帝陵") == "塔围长21.6米，高约十米。"
    assert clean_text("种类最多，分布最角企鹅(5张)广的一属。", "角企鹅属") == "种类最多，分布最广的一属。"
    assert clean_text("英文名：Chinflow杨念融2013新照(12张)", "杨念融") == "英文名：Chinflow"
    # nothing says where a caption would start: the text is left alone
    assert clean_text("扑克牌是一种游戏，有四种花色（52张）和大小王（2张）。") == "扑克牌是一种游戏，有四种花色（52张）和大小王（2张）。"
    assert clean_text("本名钱健，1954年生于无(2张)江苏省南通市", "羽离子") == "本名钱健，1954年生于无(2张)江苏省南通市"
    # a caption that stands by itself still goes
    assert clean_text("钟如标近照(3张) 钟如标，男，汉族。") == "钟如标，男，汉族。"
    assert clean_text("他出演了多部作品，剧照(80张)其中包括电影。") == "他出演了多部作品，其中包括电影。"


def test_key_value_lines_definition_lines_and_stubs():
    from baike2yomitan.cleaning import definition_value, is_key_value_line, says_nothing

    assert is_key_value_line("作者：徐汉林编著") and is_key_value_line("解释：表示纵情山水、逍遥遨游。")
    assert not is_key_value_line("下午3:00比赛正式开始，双方队员入场。")      # a time
    assert not is_key_value_line("按1：1的比例混合均匀后静置十分钟。")        # a ratio
    assert not is_key_value_line("子曰：“学而时习之，不亦说乎？”")           # reported speech
    assert is_key_value_line("口号：“更快、更高、更强”")                    # still a key and a value
    assert definition_value("解释：表示纵情山水、逍遥遨游。") == "表示纵情山水、逍遥遨游。"
    assert definition_value("【释义】很短的时间；一会儿。") == "很短的时间；一会儿。"
    assert definition_value("基本解释: 形容时间消逝得迅速") == "形容时间消逝得迅速"
    assert definition_value("出处：《庄子·秋水》") is None and definition_value("解释：无") is None
    assert says_nothing("qí fú ㄑㄧˊ ㄈㄨˊ 旗幅", "旗幅") and says_nothing("成语发音：gèn gǔ tōng jīn", "亘古通今")
    assert says_nothing("GetMailslotInfo", "GetMailslotInfo") and says_nothing("【拼音】suǒ【注音】ㄙㄨㄛˇ", "索")
    assert not says_nothing("旗幅，指旗帜的宽度。", "旗幅")
    # a foreign name is information; an id or the title in another case is not
    assert not says_nothing("刺鱼目（Gasterosteiformes）", "刺鱼目") and not says_nothing("permanent sprinkler system", "固定式喷灌系统")
    assert says_nothing("MC030-1401双向精密自准直仪", "双向精密自准直仪") and says_nothing("赛雪欺霜 (sài xuě qī shuāng)", "赛雪欺霜")
    # one accented letter is a foreign name, not the title's pinyin
    assert not says_nothing("安得烈·德·涅西亚(André-Robert Andrea de Nerciat,1739—1800)", "安得烈·德·涅西亚")
    assert not says_nothing("何塞·马蒂（José Martí）", "何塞·马蒂")
    assert says_nothing("jīng jìn ㄐㄧㄥ ㄐㄧㄣˋ", "惊浸") and says_nothing("熬 áo", "熬")
