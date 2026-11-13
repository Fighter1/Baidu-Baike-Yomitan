"""Shared text cleaning and quality rules (source-agnostic)."""
from __future__ import annotations

import html
import html.entities
import re

MIN_SUMMARY_CHARS = 15
MAX_TITLE_CHARS = 30

# [1], [2-3], [12]  and fullwidth variants ［1］
_CITATION_RE = re.compile(r"[\[［]\s*\d{1,3}(?:\s*[-–]\s*\d{1,3})?\s*[\]］]")
# Baike UI labels that leak into scraped text.  Compound forms are always
# stripped; the bare words are only stripped at the edges of a text, because
# 编辑 (editor) and 播报 (broadcast) are also ordinary words.
_UI_COMPOUND_RE = re.compile(r"编辑播报|播报编辑|编辑语音|语音编辑|播报语音")
_UI_EDGE_RE = re.compile(r"^(?:(?:播报|编辑|语音)(?:\s+|$))+|(?:(?:^|\s+)(?:播报|编辑|语音))+$")
_TRAILER_RE = re.compile(r"\s*zhua曲子白渡白颗\s*$")
_WATERMARK_RE = re.compile(r"咟喥咟萪")      # 百度百科 in look-alike characters, anywhere in a text
# Gallery captions that leak into scraped text: "剧照(80张)", "合并图册(2张)".
# The marker is certain; where the caption before it starts is not.
_CAPTION_MARK_RE = re.compile(r"[（(]\d{1,3}张[)）]")
_CAPTION_BOUNDARY = "，。；：、！？"
_CAPTION_WORDS = ("图册", "剧照", "照片", "图片", "写真", "近照", "新照", "旧照", "海报", "封面", "图集",
                  "相册", "截图", "定妆照", "概述图", "风光", "景色", "风景")
_CAPTION_WINDOW = 12
_WS_RE = re.compile(r"[\s\u00a0\u2000-\u200b\u3000\ufeff]+")
# A single space between two CJK characters/punctuation marks is never
# meaningful in Chinese prose.
_CJK = "\u2e80-\u2fdf\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef"
_CJK_PUNCT = "。！？；，、：“”‘’（）《》【】"
_CJK_SPACE_RE = re.compile(
    rf"(?<=[{_CJK}]) (?=[{_CJK}])|(?<=[{_CJK_PUNCT}]) | (?=[。！？；，、：”’）》】])")
_SENTENCE_END = "。！？；"
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
# Infobox-style lines: "作者：徐汉林编著", "I S B N：9787801383617", "·ISBN：7532120198"
_KEY_VALUE_LINE_RE = re.compile(r"^\s*[·•\-【\[]?\s*(?P<key>[^：:，。；！？\n]{1,12})[】\]]?\s*(?P<colon>[：:])")
_OPEN_QUOTES = "“‘「『\""
_SPEECH_KEY_RE = re.compile(r"(?:曰|说|道|云|问|答|称|言|谓|载|讲|喊|叫|唱|写|想|指出|表示|认为)$")
# Lines whose value is the definition itself: "解释：表示纵情山水、逍遥遨游。", "【释义】…"
_DEFINITION_KEY = r"(?:基本|词语|成语|词目|汉语|详细|中文)?(?:解释|释义|释意|词义|含义|意思|定义)|简介|概述"
_DEFINITION_LINE_RE = re.compile(
    r"^\s*(?:[【\[〖](?:%s)[】\]〗]\s*[：:]?|[·•\-]?\s*(?:%s)\s*[：:])\s*(?P<value>\S.*)$" % (_DEFINITION_KEY, _DEFINITION_KEY),
    re.S)
MIN_DEFINITION_CHARS = 4
# What is left of a pinyin-only line once the title and these labels are removed
_STUB_WORDS = ("成语发音", "成语读音", "汉语拼音", "基本信息", "拼音", "注音", "读音", "发音", "音标",
               "词目", "词语", "词汇", "成语", "名称", "中文名", "汉语", "汉字", "简体", "繁体")


# HTML entities that the corpus kept as text: Universit&auml;t, 41-60m&sup2;, d&igrave;ngzhǐ.
_ENTITY_RE = re.compile(r"&(?:#\d{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,12});"
                        r"|&(?:#\d{1,7}|amp|lt|gt|quot|nbsp)；")     # &lt；br&gt；: a semicolon made full-width
# The five names of plain HTML without a semicolon. &nbsp is a space (占地&nbsp11公顷). The others are what
# the corpus left of an entity it cut off, mostly one escaped twice inside a caption: Can&amp of Can&amp;#39;t,
# Ch&amp奥松酒庄 of Ch&amp;acirc;teau, 汤米&amp汤米是一位…, 云鹰&quot该船. They are removed, except an &amp
# between two Latin words (Honey &amp Clover). Not in front of a letter, where it is a name (AT&T, you&me).
_BARE_RE = re.compile(r"&(?:([Nn][Bb][Ss][Pp])(?![;；A-Za-z])|(amp(?![;；A-Za-z#])|(?:lt|gt|quot)(?![;；A-Za-z0-9#])))")
_WORD_BEFORE_RE = re.compile(r"[A-Za-z0-9] ?$")
_WORD_AFTER_RE = re.compile(r" [A-Za-z]")
# An entity that the corpus cut off with the end of a text: 也说“走背字儿&rdqu. Not you&me, m&ms.
_CUT_ENTITY_RE = re.compile(r"(?<![A-Za-z0-9])&([a-z]{3,8})$")
_ENTITY_NAMES = tuple(name for name in html.entities.html5 if name.endswith(";"))
MAX_ENTITY_PASSES = 12          # 木村井泓 has &amp;amp;amp;amp;amp;amp;amp;
# Names that no browser knows, from a transliteration scheme for Sanskrit and Pali.
_EXTRA_ENTITIES = {
    "amacron": "ā", "emacron": "ē", "imacron": "ī", "omacron": "ō", "umacron": "ū",
    "Amacron": "Ā", "Emacron": "Ē", "Imacron": "Ī", "Omacron": "Ō", "Umacron": "Ū",
    "ddotblw": "ḍ", "hdotblw": "ḥ", "ldotblw": "ḷ", "mdotblw": "ṃ", "ndotblw": "ṇ", "rdotblw": "ṛ",
    "sdotblw": "ṣ", "tdotblw": "ṭ", "mdotabv": "ṁ", "ndotabv": "ṅ",
    # Damaged in the corpus, each in one article. Typing mistakes for &nbsp; and &amp; (五笔86&agmp;98):
    "bsp": " ", "agmp": "&",
    # a subscript the source marked its own way (用Q&subm;表示):
    "subm": "m", "subs": "s", "sub1": "1",
    # and two numbers whose "#" and first digit became a letter. A guess from where they stand: &#8226;
    # between a book and its chapter (《新序》&S226;杂事第四》), &#61548;, a list bullet of a symbol font.
    "S226": "•", "O1548": "",
}


# Tags of the page's layout that the corpus kept as text: 实力企业。<br> 吉顺号在云南省…, <p> 《三国群星传》是…,
# 耕地1241</SPAN>亩. With an attribute only as name=value: <A Year Without Rain> is an album and <li quan> a
# reading. <stdio.h>, <math> and the like are text.
_TAG_END = r"(?:\s+[A-Za-z-]+\s*=[^<>]*|\s*/)?\s*>"
_TAG_NAMES = r"br|wbr|p|div|li|span|strong|em|font|sup|sub|iframe|noinclude|h[1-6]|center|pre|th|td|tr|thead|tbody"
# A picture only with its attributes (<IMG> alone is a tag somebody writes about), and what a comment hides.
# <p zdct3"> and <p class="zdct8 are paragraphs of the dictionary site 汉典 whose quotes the corpus broke.
# A script that is fetched from somewhere is code of the page the text was copied from, an advertisement or
# a counter: 交付给泰国的这 <script language=javascript1.1 src="http://ad.…"></script>. To the last ">" in front
# of the next tag, because 红罗宾石楠 has src="/plus/count.php?aid=Fields[" id?]?>&mid=…" type="text/javascript">.
_TAG_RE = re.compile(rf"<p\s+(?:class=\"?)?zdct\d+\"?>?"
                     rf"|</?(?:{_TAG_NAMES}){_TAG_END}"
                     # a quoted value may hold a ">": onload="if(this.width>screen.width-500)…"
                     rf"|<(?:a|img)\s+[A-Za-z-]+\s*=(?:(?:\"[^\"<]{{0,300}}\"|[^<>\"])*|[^<>]*)>"
                     rf"|<script\b(?=[^<]{{0,400}}\bsrc\s*=)[^<]{{0,600}}>(?:\s*</script\s*>)?"
                     rf"|<!--[^<>]*(?:-->|$)", re.I)
# <a>, <b>, <i>, <u> only as a pair: 字母<u> is a letter. A closing one alone is still a tag: 有限责任公司</B>是…,
# also one that lost its ">" in front of a Chinese character: Sydney Pollack</A编剧：….
_PAIRED_TAG_RE = re.compile(r"<([abiu])>(.*?)</\1>", re.I | re.S)
_CLOSING_TAG_RE = re.compile(rf"</[abiu]>|</(?:{_TAG_NAMES}|[abiu])(?=[一-鿿])", re.I)
# A tag that the corpus cut off with the end of a text or of a line: …而努力奋斗。<br, 《下笔入神》、《<a target=_blank,
# 所证实。<DIV id=FrontComContent_detail01 class=style=. Not 其中0<p, which is the end of an inequality, and no
# sentence after it: <p class="zdct8(2).吏目。元王仲文…
# Inside a text only a closing tag or one with an attribute counts as cut off with its line: 于是<P and
# 高自旋∆<p at the end of a line are what is left of a formula.
_CUT_ATTR = r"\s+[A-Za-z-]+\s*=[^<>。，；！？\n]{0,400}"
_CUT_TAG_RE = re.compile(rf"(?<![A-Za-z0-9Α-ω∆\s<=>])(?:"
                         rf"(?:</?(?:{_TAG_NAMES})(?:{_CUT_ATTR})*|</?(?:a|img)(?:{_CUT_ATTR})?)\s*\Z"
                         rf"|(?:</(?:{_TAG_NAMES}|a)|<(?:{_TAG_NAMES})(?:{_CUT_ATTR})+)[^\S\n]*$)", re.I | re.M)
# Tags broken in a way that occurs once, each in one article, and what they stood for.
_BROKEN_TAGS = {
    "of<sup<sup<sup cl": "of",                                  # all there is of 102715
    "测<BR试": "测试",                                            # 核磁共振实验200例
    "<a a.孔德": "A.孔德",                                        # 实证哲学教程
    "<IMG class=tex alt=\"1 < p": "1 < p",                      # 哈代空间: the formula is what the picture says
    "<A 电力电缆 a>": "电力电缆",                                 # 油浸纸绝缘电缆
    "<font span=\"\" 案发于一体": "案发于一体",                    # 广州市杰泰电子科技有限公司
    "<b>" + chr(0x3000) * 2 + "《现场安全员岗位通》": "《现场安全员岗位通》",   # after two full-width spaces
    "人大附中<a>西山学校": "人大附中西山学校",
    "<B制作以传统工艺": "制作以传统工艺",                          # 于都峡山道菜
}
_TAG_NAME_RE = re.compile(r"</?([A-Za-z]+[1-6]?)")
_LINE_TAG_RE = re.compile(r"<(?:br|wbr|p|h[1-6]|center|pre|tr)\b", re.I)
# A text about markup means its tags: li 标签定义列表项目。以<li>开始</li>结束. These say that it is one,
# wherever they stand outside a layout tag (a map pasted as <iframe src="…/mapElem.html"> says nothing).
# Not html in the name of a file (club.qq.com/moo.shtml, robot.html). Code says it too: <?php, echo "…",
# <form>, document.write(, and CSS has 伪元素.
_ABOUT_MARKUP_RE = re.compile(r"(?<![./A-Za-z])x?html(?![a-z])|标识符|超文本|超链接|控件|伪元素"
                              r"|<(?:body|head|ul|ol|table|script|form|input|map|area)\b|<\?(?:php|xml)\b"
                              r"|\becho\s*[('\"]|document\.write\(|getElement", re.I)
# 标签 is also a label on a tin, so it has to stand near a tag: 继发性肾病 has 血管病</a>变 and, 1,900
# characters on, 食物成分标签.
LABEL_NEAR = 100
# 元素 and 字母 are said of other things far more often (多种矿物元素, 26个拉丁字母), so they have to name a tag:
# <p> 元素, iframe元素, <book> 元素, 页面元素<div>. Not 微量元素<br>, where a line ends. The three characters
# stand for an opening layout tag, a closing one and one that breaks a line.
_OPENING, _CLOSING, _BREAK = chr(2), chr(3), chr(4)
_NAMES_A_TAG_RE = re.compile(rf"(?:(?<![A-Za-z])(?P<name>[A-Za-z]+)\s?|>\s?|[{_OPENING}{_BREAK}]\s*)(?P<what>元素|字母)"
                             rf"|(?:元素|字母)[\s：:（(]{{0,3}}{_OPENING}"
                             # 一个新的 <tr> 标记, <del>删除线</del> 标记, 锚点代码为：<a name="锚点名">
                             rf"|[{_OPENING}{_CLOSING}{_BREAK}]\s?标记|代码(?:为|如下|是)?[\s：:]{{0,3}}{_OPENING}")
# Ni元素 is nickel. H13钢 has Cr﹑Mn﹑Mo﹑Si和Ni元素 and a <sup>[14]</sup>; 酸 has H、O元素. A symbol names a tag
# only where the text has a tag of that name: P元素 next to a <p>.
_CHEMICAL_SYMBOLS = frozenset(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr "
    "Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir "
    "Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl "
    "Mc Lv Ts Og".split())


def _tag_spans(text: str) -> list[tuple[int, int]]:
    """Where the layout tags of a text are."""
    spans = {m.span() for m in _TAG_RE.finditer(text)} | {m.span() for m in _CLOSING_TAG_RE.finditer(text)}
    for m in _PAIRED_TAG_RE.finditer(text):
        spans |= {(m.start(), m.start() + 3), (m.end() - 4, m.end())}
    spans |= {m.span() for m in _CUT_TAG_RE.finditer(text)}
    return sorted(spans)


def _names_a_tag(marked: str, text: str, spans: list[tuple[int, int]]) -> bool:
    """Whether 元素 or 字母 names a tag somewhere in a text whose layout tags are marked."""
    tags = None
    for m in _NAMES_A_TAG_RE.finditer(marked):
        name = m.group("name")
        if name and name in _CHEMICAL_SYMBOLS and m.group("what") == "元素":
            if tags is None:
                tags = {t.group(1).lower() for t in (_TAG_NAME_RE.match(text, start) for start, _ in spans) if t}
            if name.lower() not in tags:
                continue
        return True
    return False


def _speaks_of_tags(text: str, spans: list[tuple[int, int]]) -> bool:
    """Whether a text with layout tags at these places is about markup."""
    marked = list(text)
    for start, end in spans:
        kind = _CLOSING if text[start + 1] == "/" else _BREAK if _LINE_TAG_RE.match(text, start) else _OPENING
        marked[start:end] = kind * (end - start)
    marked = "".join(marked)
    if _ABOUT_MARKUP_RE.search(marked) or _names_a_tag(marked, text, spans):
        return True
    at = marked.find("标签")
    while at >= 0:
        if any(at - end <= LABEL_NEAR and start - at - 2 <= LABEL_NEAR for start, end in spans):
            return True
        at = marked.find("标签", at + 2)
    return False


def strip_tags(text: str) -> str:
    """Body text without the layout tags that the corpus kept as text. A tag
    that broke a line leaves a space."""
    for broken, meant in _BROKEN_TAGS.items():
        if broken in text:
            text = text.replace(broken, meant)
    spans = _tag_spans(text)
    if not spans or _speaks_of_tags(text, spans):
        return text
    text = _CUT_TAG_RE.sub("", text)
    return _CLOSING_TAG_RE.sub("", _PAIRED_TAG_RE.sub(r"\2", _TAG_RE.sub(" ", text)))


# Characters of the private-use area mean something only in the font or the encoding they were typed in.
_PUA_RE = re.compile("[%s-%s]" % (chr(0xE000), chr(0xF8FF)))
_PUA_LEAD_RE = re.compile(r"^(?:[%s-%s]\s*)+" % (chr(0xE000), chr(0xF8FF)))
# GB 18030-2000 put these characters there; they have had code points of their own since (㖞 in 口眼㖞斜, 䜣 in
# 奕䜣, 䓖 in 芎䓖, ⺮, 𠂇, 𢦏, 龹 as parts of characters).
_GB18030_PUA = {
    0xE815: 0x2E81, 0xE816: 0x20087, 0xE817: 0x20089, 0xE818: 0x200CC, 0xE819: 0x2E84, 0xE81A: 0x3473,
    0xE81B: 0x3447, 0xE81C: 0x2E88, 0xE81D: 0x2E8B, 0xE81E: 0x9FB4, 0xE81F: 0x359E, 0xE820: 0x361A,
    0xE821: 0x360E, 0xE822: 0x2E8C, 0xE823: 0x2E97, 0xE824: 0x396E, 0xE825: 0x3918, 0xE826: 0x9FB5,
    0xE827: 0x39CF, 0xE828: 0x39DF, 0xE829: 0x3A73, 0xE82A: 0x39D0, 0xE82B: 0x9FB6, 0xE82C: 0x9FB7,
    0xE82D: 0x3B4E, 0xE82E: 0x3C6E, 0xE82F: 0x3CE0, 0xE830: 0x2EA7, 0xE831: 0x215D7, 0xE832: 0x9FB8,
    0xE833: 0x2EAA, 0xE834: 0x4056, 0xE835: 0x415F, 0xE836: 0x2EAE, 0xE837: 0x4337, 0xE838: 0x2EB3,
    0xE839: 0x2EB6, 0xE83A: 0x2EB7, 0xE83B: 0x2298F, 0xE83C: 0x43B1, 0xE83D: 0x43AC, 0xE83E: 0x2EBB,
    0xE83F: 0x43DD, 0xE840: 0x44D6, 0xE841: 0x4661, 0xE842: 0x464C, 0xE843: 0x9FB9, 0xE844: 0x4723,
    0xE845: 0x4729, 0xE846: 0x477C, 0xE847: 0x478D, 0xE848: 0x2ECA, 0xE849: 0x4947, 0xE84A: 0x497A,
    0xE84B: 0x497D, 0xE84C: 0x4982, 0xE84D: 0x4983, 0xE84E: 0x4985, 0xE84F: 0x4986, 0xE850: 0x499F,
    0xE851: 0x499B, 0xE852: 0x49B7, 0xE853: 0x49B6, 0xE854: 0x9FBA, 0xE855: 0x241FE, 0xE856: 0x4CA3,
    0xE857: 0x4C9F, 0xE858: 0x4CA0, 0xE859: 0x4CA1, 0xE85A: 0x4C77, 0xE85B: 0x4CA2, 0xE85C: 0x4D13,
    0xE85D: 0x4D14, 0xE85E: 0x4D15, 0xE85F: 0x4D16, 0xE860: 0x4D17, 0xE861: 0x4D18, 0xE862: 0x4D19,
    0xE863: 0x4DAE, 0xE864: 0x9FBB,
}
# Text pasted from a word processor has the letters of its symbol fonts at U+F000 plus their place in the
# font. Greek letters and signs of the Symbol font that are no bullets in any font:
_SYMBOL_FONT = {0xF061: "α", 0xF062: "β", 0xF06B: "κ", 0xF044: "Δ", 0xF0D2: "®", 0xF0E2: "®"}
_SYMBOL_DOTS = (0xF0D7, 0xF09E, 0xF09F)         # 约翰斯·霍普金斯, 诺曼·福斯特
_PUA_JUNK = (0xE004, 0xE5E5)                    # seen only between sentences and in front of a text
MISSING_CHARACTER = "□"                         # what a text prints for a character it cannot


def _is_han(ch: str) -> bool:
    return "\N{CJK UNIFIED IDEOGRAPH-4E00}" <= ch <= "\N{CJK UNIFIED IDEOGRAPH-9FFF}"


def _private_use(m: re.Match, title: bool) -> str:
    code, text = ord(m.group(0)), m.string
    before, after = text[m.start() - 1:m.start()], text[m.end():m.end() + 1]
    if code in _GB18030_PUA:
        return chr(_GB18030_PUA[code])
    if code in _SYMBOL_FONT:
        return _SYMBOL_FONT[code]
    if 0xF020 <= code <= 0xF0FF:
        if code == 0xF06D and (not after or after.isascii() and after.isalpha()):
            return "μ"                          # μC/OS-II, 相对磁导率μ
        if code == 0xF02C:                      # the comma of the font: 蜡烛工艺，塑胶玩具行业
            return "，" if _is_han(before) else ""
        if code == 0xF0B3 and after.isdigit():
            return "≥"                          # DS≥2.75
        if code == 0xF0B4 and before.isascii() and before.isalnum():
            return "×"                          # 1×4光功分器
        if code == 0xF02D and before.isdigit() and after.isdigit():
            return "-"                          # 1982-1999年
        if code == 0xF07E and before.isascii() and before.isalnum():
            return "～"                         # 200km～700km
        if _is_han(before) and _is_han(after):
            if code in _SYMBOL_DOTS:
                return "·"
            if code >= 0xF080:                  # no letter of a symbol font: a character again (令尹□祁)
                return m.group(0) if title else MISSING_CHARACTER
        return " "                              # a bullet in front of a line: ● 蔡达建，男，…
    if code in _PUA_JUNK:
        return ""
    return m.group(0) if title else MISSING_CHARACTER


def private_use_as_text(text: str, title: bool = False) -> str:
    """Characters of the private-use area as what they stand for where that
    is known. In body text a run of them in front of the text goes, the rest
    becomes □: a character the text has but cannot show. A title keeps the
    ones inside it, and loses those at its ends."""
    if not _PUA_RE.search(text):
        return text
    if not title:
        text = _PUA_LEAD_RE.sub("", text)
    text = _PUA_RE.sub(lambda m: _private_use(m, title), text)
    if title:
        text = _PUA_RE.sub("", text[:1]) + text[1:-1] + (_PUA_RE.sub("", text[-1:]) if len(text) > 1 else "")
    return text


def needs_decoding(text) -> bool:
    return isinstance(text, str) and ("&" in text or "<" in text or bool(_PUA_RE.search(text)))


def _entity(m: re.Match) -> str:
    found = m.group(0)
    whole = found[:-1] + ";"                # the full-width semicolon
    char = html.unescape(whole)
    if char != whole:
        return char
    name = whole[1:-1]
    if name in _EXTRA_ENTITIES:
        return _EXTRA_ENTITIES[name]
    lower = "&" + name.lower() + ";"        # &NBSP;, &DEG;
    char = html.unescape(lower)
    return char if char != lower else found


def _bare(m: re.Match) -> str:
    if m.group(1):
        return " "
    text = m.string
    between_words = (m.group(2) == "amp" and _WORD_BEFORE_RE.search(text, max(0, m.start() - 2), m.start())
                     and _WORD_AFTER_RE.match(text, m.end()))
    return "&" if between_words else ""


def _without_cut_entity(text: str) -> str:
    cut = _CUT_ENTITY_RE.search(text)
    if cut and any(name.startswith(cut.group(1)) for name in _ENTITY_NAMES):
        return text[:cut.start()]
    return text


def decode_entities(text: str | None, cut_off: bool = False, body: bool | None = None,
                    only_entities: bool = False) -> str | None:
    """HTML entities as the characters they stand for, for raw text before any
    other rule sees it: &#91;2&#93; has to be [2] for the citation rule, and
    d&igrave;ngzhǐ has to be dìngzhǐ to be read as pinyin. Until nothing
    changes, because some are escaped several times (&amp;amp;nbsp;). A name nobody
    knows stays as it is. `cut_off`: the text is body text that the corpus may
    have ended inside an entity; a title can end in &me.

    What else the raw text has instead of characters goes the same way
    (without_markup), unless `only_entities` says not yet. `body`: the text
    is body text, by default what `cut_off` says."""
    if not text:
        return text
    if "&" in text:
        text = _decoded(text, cut_off)
    return text if only_entities else without_markup(text, cut_off if body is None else body)


def without_markup(text: str, body: bool = False) -> str:
    """The text without the tags of a page's layout (body text only) and with
    its characters of the private-use area as text."""
    if body and "<" in text:
        text = strip_tags(text)
    return private_use_as_text(text, title=not body)


def _decoded(text: str, cut_off: bool) -> str:
    for _ in range(MAX_ENTITY_PASSES):
        decoded = _ENTITY_RE.sub(_entity, text)
        if cut_off:
            decoded = _without_cut_entity(decoded)
        decoded = _BARE_RE.sub(_bare, decoded)
        if decoded == text:
            break
        text = decoded
    return text.replace("\u00ad", "")      # the soft hyphen shows nothing


def strip_citations(text: str) -> str:
    return _CITATION_RE.sub("", text)


# A bracket that holds nothing any more. Either its citation marks went (（基本信息栏参考资料：[2] ） is under
# the summary of 731 words of CC-CEDICT), or the corpus lost a name in another script:
# 帕勒马希姆（希伯来语：）, 延森（，1873-1950）, 安东尼·沃尔（Anthony David Wall，）.
_BRACKET_RE = re.compile(r"([（(])([^（）()]{0,60})([）)])")
_SEPARATORS = "，,、；;"
_REFERENCE_ONLY_RE = re.compile(
    r"[^，,。；;：:！？]{0,12}(?:参考|来源|来自|资料)[^，,。；;：:！？]{0,2}[：:]|概述图片?[：:]"
    # without a colon only what a page says of itself: （教学参考资料） is a kind of book
    r"|(?:(?:基本)?信息栏?(?:主要|使用)?|概[述念]内?图片?|摘要图|名片|图片|释义|词语|以上|见)?参考(?:资料|来源)(?:来源)?")
_NAME_LABEL = r"(?:学名|英文名?|外文名?|原名|原题|本名|别名|又名|简称|拼音|[一-鿿]{1,5}[语文])[：:]"
_NAME_ONLY_RE = re.compile(_NAME_LABEL)
_NAME_FIRST_RE = re.compile(rf"(?:{_NAME_LABEL}\s*[{_SEPARATORS}]\s*)+")
_NAME_LAST_RE = re.compile(rf"(?:\s*[{_SEPARATORS}]\s*{_NAME_LABEL})+$")
MIN_AFTER_SEPARATOR = 3         # 地球坐标（，λ） lost a letter, not a name
# An empty one goes where a name stood in front of it and the sentence goes on behind it: 刘言（），吉州庐陵人,
# 桑吉省（）是…. Not 内设机构共计（）个 and 党员（）名, blanks nobody filled in, not 笔名（）介 and
# 下山（）林场, where it stands for a character, not at the end of a line, where an exercise has its blank
# (正确的一项是（）), and not on a page that shows brackets: 小括弧()、中括弧[].
_EMPTY_BRACKET_RE = re.compile(r"(?<=[一-鿿·])[（(]\s*[）)](?=[，,。.、；;：:！？!?》」』”’\"）)\]】是即为的和与及被于又也成创位坐座在])")
_ABOUT_BRACKETS_RE = re.compile(r"括号|括弧|括符|[全半]角|符号|标点|函数\s*[（(]\s*[）)]|方法\s*[（(]\s*[）)]|填空|填入")


def _hollow_bracket(m: re.Match) -> str:
    opening, inner, closing = m.groups()
    bare = inner.strip()
    if not bare:
        return m.group(0)
    if _REFERENCE_ONLY_RE.fullmatch(bare) or _NAME_ONLY_RE.fullmatch(bare):
        return ""
    if opening == "(" and bare.isascii():
        return m.group(0)                   # (1,) is a tuple
    rest = _NAME_LAST_RE.sub("", _NAME_FIRST_RE.sub("", bare, count=1) if _NAME_FIRST_RE.match(bare) else bare)
    if _NAME_ONLY_RE.fullmatch(rest):
        return ""                           # （德语：，波兰语：，索布语：）
    if rest[:1] in _SEPARATORS and len(rest.lstrip(_SEPARATORS + " ")) >= MIN_AFTER_SEPARATOR:
        rest = rest.lstrip(_SEPARATORS + " ")
    if rest[-1:] in _SEPARATORS:
        before = rest.rstrip(_SEPARATORS + " ")[-1:]
        if before and (before.isalnum() or before == ".") and not _is_han(before):
            rest = rest.rstrip(_SEPARATORS + " ")
    if rest == bare:
        return m.group(0)
    return opening + rest + closing if rest else ""


# A note of the page on where its picture, its info table or its text is from. With the source as a citation
# mark the note goes above; with the source in words it would stay under 503 summaries:
# （基本信息主要来源：《新华写字字典第2版》、汉典网）, （概述图参考来源：中国自然标本馆）, （资料来源：中国植物物种信息）.
# What it says of the picture means nothing without the picture (（概述图人物：乔瓦尼·巴蒂斯塔·佩尔戈莱西）).
# A label needs its colon: （信息资料管理系统） is a name.
_SOURCE_NOTE_RE = re.compile(
    r"[（(]\s*(?:概[述念]内?图|摘要图"
    r"|(?:(?:基本)?信息栏?|名片|图片|参考|资料|数据)[^，,。；;：:（）()]{0,10}(?:参考|来源|来自|资料|链接)[^，,。；;：:（）()]{0,3}[：:])"
    r"[^（）()]{0,120}[）)]")


def strip_hollow_brackets(text: str) -> str:
    """Body text without the brackets that hold nothing any more, without the
    separator that is left at the edge of one that lost a part, and without
    the page's notes on its sources."""
    if "（" not in text and "(" not in text:
        return text
    text = _BRACKET_RE.sub(_hollow_bracket, _SOURCE_NOTE_RE.sub("", text))
    if _EMPTY_BRACKET_RE.search(text) and not _ABOUT_BRACKETS_RE.search(text):
        text = _EMPTY_BRACKET_RE.sub("", text)
    return text


def strip_ui_labels(text: str, title: str | None = None) -> str:
    """Remove leaked interface labels. A compound that is part of the article's
    own title is prose, not a label: 语音编辑器是一种… must not lose 语音编辑."""
    text = _WATERMARK_RE.sub("", _TRAILER_RE.sub("", text))
    text = _UI_COMPOUND_RE.sub(lambda m: m.group(0) if title and m.group(0) in title else "", text)
    return _UI_EDGE_RE.sub("", text)


def normalize_whitespace(text: str) -> str:
    text = _WS_RE.sub(" ", text).strip()
    return _CJK_SPACE_RE.sub("", text)


def _caption_start(before: str, title: str | None, at_text_start: bool) -> int | None:
    """Where the caption that ends `before` begins, or None when the text in
    front of a "(N张)" marker does not look like a caption at all. `before`
    starts at the beginning of the text or right after the previous marker."""
    start = len(before)
    while start > 0 and not before[start - 1].isspace() and before[start - 1] not in _CAPTION_BOUNDARY:
        start -= 1
    run = len(before) - start
    if title and len(title) >= 2:
        # Captions are usually the article title plus a word: 杨念融2013新照(12张)
        lo = max(start, len(before) - 30)
        for k in range(len(title), 1, -1):
            at = before.rfind(title[:k], lo)
            if at >= 0:
                return at
    if run == 0:
        return len(before)
    spaced = at_text_start if start == 0 else before[start - 1].isspace()
    if run <= _CAPTION_WINDOW and spaced:
        return start
    if before.endswith(_CAPTION_WORDS):
        return max(start, len(before) - _CAPTION_WINDOW)
    return None  # prose such as 四种花色（52张）: leave it alone


def strip_captions(text: str, title: str | None = None) -> str:
    """Remove leaked gallery captions. A caption glued into the middle of a
    sentence is cut from the article title onwards when the title is in it
    (塔围长21.6荆山皇帝陵景色(20张)米 -> 塔围长21.6米)."""
    out: list[str] = []
    pos = 0
    for m in _CAPTION_MARK_RE.finditer(text):
        before = text[pos:m.start()]
        cut = _caption_start(before, title, pos == 0)
        out.append(before + m.group(0) if cut is None else before[:cut])
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def clean_text(text: str | None, title: str | None = None) -> str:
    """Full cleaning pass for body text (summaries, paragraphs). `title` is
    the article title, used to find where a leaked caption starts."""
    if not text:
        return ""
    text = text.replace("\\n", "\n")  # literal backslash-n sequences in 563w
    text = strip_hollow_brackets(strip_citations(text))
    text = strip_captions(text, title)
    text = strip_ui_labels(text, title)
    text = normalize_whitespace(text)
    return strip_ui_labels(text, title).strip()


def clean_title(text: str | None) -> str:
    """Headwords and sense labels: whitespace only. The UI-label, caption and
    citation rules are for body text; on a title they erase the headwords
    编辑, 语音 and 播报 and turn 语音编辑器 into 器."""
    if not text:
        return ""
    return normalize_whitespace(text.replace("\\n", "\n"))


def trim_summary(text: str, max_chars: int) -> str:
    """Trim to max_chars, cutting at the last sentence boundary when one exists
    in the second half of the window; otherwise cut hard and add an ellipsis."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    window = text[:max_chars]
    cut = max(window.rfind(ch) for ch in _SENTENCE_END)
    if cut >= max_chars // 3:
        return window[: cut + 1]
    return window.rstrip() + "…"


def first_paragraph(text: str | None) -> str:
    """First non-empty paragraph of a section body."""
    if not text:
        return ""
    for para in re.split(r"\\n|\n|\r", text):
        p = para.strip()
        if p:
            return p
    return ""


# Quotes and brackets a line break can leave open in the middle of a sentence.
_PAIRS = (("“", "”"), ("‘", "’"), ("（", "）"), ("(", ")"), ("《", "》"), ("「", "」"), ("『", "』"), ("【", "】"))
_LINE_END = "。！？；…：:.!?;"


def continues_on_next_line(line: str, next_line: str) -> bool:
    """True when a line break fell inside a sentence: the line stops without
    closing punctuation, inside a quote or bracket that the next line closes
    (板儿砖: …总不能叫“我开你一砖 / 头”，所以就说…)."""
    if not line or not next_line or line[-1] in _LINE_END:
        return False
    return any(next_line.count(close) > next_line.count(open_)
               for open_, close in _PAIRS if line.count(open_) > line.count(close))


def join_lines(line: str, next_line: str) -> str:
    """Put the two halves of a broken line back together. The breaks fall
    anywhere, also inside a number (民国10年(19 / 21年)), so only two ASCII
    letters are kept apart with a space."""
    a, b = line[-1], next_line[0]
    sep = " " if a.isascii() and a.isalpha() and b.isascii() and b.isalpha() else ""
    return line + sep + next_line


def has_cjk(text: str) -> bool:
    return bool(_CJK_CHAR_RE.search(text))


def is_key_value_line(text: str) -> bool:
    """A single infobox-style 'key：value' line (a short key before the first
    colon).  Such lines are never a usable summary even when long enough.
    Not counted: a time or ratio (下午3:00, 按1:1), and reported speech
    (子曰：“学而时习之…”)."""
    m = _KEY_VALUE_LINE_RE.match(text)
    if not m:
        return False
    key = m.group("key").strip()
    after = text[m.end():].lstrip()[:1]
    if key[-1:].isdigit() and after.isdigit():
        return False
    if after and after in _OPEN_QUOTES and _SPEECH_KEY_RE.search(key):
        return False
    if any(key.count(a) > key.count(b) for a, b in _PAIRS):
        return False  # the colon is inside a bracket: 粉虱科（学名：Aleyrodidae）是…, 《丁丁历险记：独角兽的秘密》是…
    return True


def key_of(text: str) -> str | None:
    """The key of an infobox-style line, or None when the line is not one."""
    return _KEY_VALUE_LINE_RE.match(text).group("key").strip() if is_key_value_line(text) else None


def definition_value(text: str) -> str | None:
    """The value of a line whose key says it is the definition (解释, 释义,
    词义, 含义, 定义, 简介 …), or None. Such a line is the best summary a
    dictionary-style page has, although it looks like an infobox line."""
    m = _DEFINITION_LINE_RE.match(text)
    if not m:
        return None
    value = m.group("value").strip()
    return value if len(value) >= MIN_DEFINITION_CHARS and has_cjk(value) else None


_TONE_LETTER_RE = re.compile(r"[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹ]")
_BOPOMOFO_RE = re.compile(r"[ㄅ-ㄯ]")
_FOREIGN_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_LATIN_WORD_RE = re.compile(r"[^\W\d_\u2e80-\u9fff\u3100-\u312f]+")


def says_nothing(text: str, title: str) -> bool:
    """True when a line holds nothing beyond the title, its pinyin or
    bopomofo, and labels such as 拼音/注音 (旗幅 -> "qí fú ㄑㄧˊ ㄈㄨˊ 旗幅",
    亘古通今 -> "成语发音：gèn gǔ tōng jīn"). The reading field already shows
    that. A foreign name is something: 刺鱼目（Gasterosteiformes） stays."""
    rest = text.replace(title, "") if title else text
    for word in _STUB_WORDS:
        rest = rest.replace(word, "")
    if len(_CJK_CHAR_RE.findall(rest)) >= 2:
        return False
    if _BOPOMOFO_RE.search(rest):
        return True
    # Pinyin is written in lower case with about one tone mark per character
    # of the title. Accents in capitalised words are a foreign name:
    # 安得烈·德·涅西亚(André-Robert … de Nerciat), 何塞·马蒂（José Martí）.
    marks = sum(len(_TONE_LETTER_RE.findall(w)) for w in _LATIN_WORD_RE.findall(rest) if w == w.lower())
    if marks >= max(1, len(_CJK_CHAR_RE.findall(title or "")) - 1):
        return True
    return not _FOREIGN_WORD_RE.search(rest)


def is_summary_candidate(text: str, title: str | None = None) -> bool:
    """A cleaned paragraph that can stand in for a missing summary: long
    enough, says something in Chinese, and is not an infobox line."""
    if summary_drop_reason(text) is not None or not has_cjk(text):
        return False
    key = key_of(text)
    if key is not None and not (title and key == title):  # "陈灿：影视演员，…" describes the title
        return False
    return not (title and says_nothing(text, title))


MIN_SHORT_SENTENCE_CHARS = 6
# Infobox keys whose single line is worth keeping as a summary: 别称：四六不懂
_ALIAS_LINE_RE = re.compile(
    r"^\s*[·•\-【\[〖]?\s*(?:别称|别名)\s*[】\]〗]?\s*[：:]\s*(?P<value>\S.*)$")


def short_summary_keep_reason(summary: str, title: str) -> str | None:
    """Why a summary under MIN_SUMMARY_CHARS may be kept anyway:

    - 'short_sentence': a complete clause (ends in 。！？；), at least six
      characters, contains Chinese, is not just the title and is not an
      infobox line — e.g. 剌桐城 → 泉州市的别称。
    - 'alias_line': an infobox line whose key is 别称/别名 with a non-empty
      value — e.g. 不着四六 → 别称：四六不懂
    Returns None when the summary should still be dropped."""
    s = summary.strip()
    if not s or not has_cjk(s):
        return None
    m = _ALIAS_LINE_RE.match(s)
    if m and m.group("value").strip() and m.group("value").strip() != title:
        return "alias_line"
    if (len(s) >= MIN_SHORT_SENTENCE_CHARS and s[-1] in _SENTENCE_END
            and s.rstrip(_SENTENCE_END) != title and s.rstrip(_SENTENCE_END) not in title
            and not is_key_value_line(s)):
        return "short_sentence"
    return None


def title_drop_reason(title: str) -> str | None:
    if not title:
        return "title_empty"
    if len(title) > MAX_TITLE_CHARS:
        return "title_too_long"
    return None


def summary_drop_reason(summary: str) -> str | None:
    if len(summary) < MIN_SUMMARY_CHARS:
        return "summary_too_short"
    return None


# --- comparing two summaries --------------------------------------------------

_SIMILARITY_STRIP_RE = re.compile(r"[\s\W_]+")
SAME_ARTICLE = 0.5   # share of bigrams above which two summaries are one article


def _bigrams(text: str, title: str, limit: int) -> set[str]:
    if title:
        text = text.replace(title, "")
    t = _SIMILARITY_STRIP_RE.sub("", text)[:limit]
    return {t[i:i + 2] for i in range(len(t) - 1)}


def similarity(a: str, b: str, title: str = "", limit: int = 160) -> float:
    """How much of the shorter summary is found in the other: the share of
    its character bigrams (0..1). The title is left out, because every article
    about 庐山 says 庐山. Two texts of the same article score high even when
    one is an older or a shortened version; unrelated articles that share a
    title score near 0."""
    x, y = _bigrams(a or "", title, limit), _bigrams(b or "", title, limit)
    if len(x) < 4 or len(y) < 4:
        return 1.0 if x and x == y else 0.0
    return len(x & y) / min(len(x), len(y))


def cjk_len(text: str) -> int:
    """Number of Chinese characters: the length of what a text says, without
    pinyin, English glosses or punctuation."""
    return len(_CJK_CHAR_RE.findall(text or ""))


_PINYIN_LABEL_RE = re.compile(r"^[\s·•\-【\[〖(（]*(?:成语|汉语|词语|中文)?(?:拼音|读音|发音|注音|音标)[】\]〗)）]*\s*(?:是|为)?\s*[：:]?\s*")


def has_tone_marks(text: str) -> bool:
    return bool(_TONE_LETTER_RE.search(text or ""))


_PINYIN_LETTERS = "A-Za-zɑɡüÜāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹ"
_PINYIN_TEXT_RE = re.compile(f"[{_PINYIN_LETTERS}][{_PINYIN_LETTERS} '’\\-·]*")


def pinyin_line_value(line: str, title: str) -> str | None:
    """The pinyin a line gives for the title: the first run of tone-marked
    Latin letters after a 拼音/读音/发音/注音 label, or in a line that holds
    nothing but the title and its pronunciation. None for any other line.
    (máo běn ㄇㄠˊ ㄅㄣˇ释义：… gives máo běn.)"""
    if not has_tone_marks(line):
        return None
    m = _PINYIN_LABEL_RE.match(line)
    labelled = bool(m and m.end() > 0 and any(k in line[:m.end()] for k in ("拼音", "读音", "发音", "注音", "音标")))
    if not labelled and not says_nothing(line, title):
        return None
    for run in _PINYIN_TEXT_RE.finditer(line[m.end():] if labelled else line):
        if has_tone_marks(run.group(0)):
            return run.group(0).strip(" '’-·")[:80] or None
    return None
