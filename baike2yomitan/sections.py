"""The dictionary-style sections of a word's page: 释义, 出处, 用法 ...

A Baike page about a word or a 成语 is laid out like a dictionary entry: a
section for the meaning, one for the source, one for the usage, examples,
synonyms. The summary only names some of that. These sections are kept on the
record as [label, text] pairs under a few fixed labels, and `build --sections`
shows them under the summary.

Only headings from a fixed list are taken, and only from a page about a word.
出处, 用法, 语法 and 示例 are also headings of pages about a character of a
novel, a medicine or a programming function, so the page has to show that it
is about a word: by a section for the meaning or for synonyms, by a heading
that says so (成语出处, 词语注音), or by its summary (…，汉语成语，…).
Sections that tell a story (成语故事, 典故) run to thousands of characters and
are left to the article.
"""
from __future__ import annotations

import re
from typing import Callable, Iterable

from .cleaning import (SAME_ARTICLE, cjk_len, clean_text, clean_title, has_tone_marks, says_nothing, similarity,
                       trim_summary)
from .sense import is_word

MAX_SECTION_CHARS = 200     # of one section
MAX_SHOWN_CHARS = 700       # of all the sections of an entry together
MIN_SECTION_CJK = 2
MIN_REST_CJK = 6            # of what a section says after the summary it starts with

# A heading that names the kind of word the page is about: 成语出处, 词语注音.
_WORD = r"(?:成语|词语|词目|词汇|词条|字词|俗语|谚语|熟语|歇后语)"
_WORD_HEADING_RE = re.compile(rf"^{_WORD}")
# (label, headings); the order is the order the sections are shown in. Under
# one label an earlier line wins over a later one (基本解释 over 解释), and
# within a line the section that comes first on the page.
_HEADINGS = (
    ("释义", rf"(?:基本|简明)(?:解释|释义|含义|词义|字义)"),
    ("释义", rf"{_WORD}?(?:解释|释义|释意|词义|含义|涵义|意思)|{_WORD}解析|(?:词典|中文|汉语|汉字)(?:解释|释义)"),
    ("详解", r"详细(?:解释|释义|字义)|引证解释"),
    ("出处", rf"(?:{_WORD}|典故)?(?:出处|出自)|出处典故|{_WORD}(?:来源|语源)|词源|语源"),
    ("用法", rf"(?:{_WORD}|成文)?(?:用法|语法)"),
    ("示例", rf"(?:{_WORD}|运用)?(?:示例|例句|造句)"),
    ("近义词", r"近义词|同义词"),
    ("反义词", r"反义词"),
    ("辨析", rf"{_WORD}?辨析"),
)
ORDER = tuple(dict.fromkeys(label for label, _pattern in _HEADINGS))
_HEADING_RES = tuple((label, re.compile(rf"^(?:{pattern})$")) for label, pattern in _HEADINGS)
_PROVES_WORD = {"释义", "详解", "近义词", "反义词"}      # a page with such a section is about a word
_LIST_LABELS = {"近义词", "反义词"}
_EXAMPLE_PREFIXES = ("运用示例", "成语示例", "示例")
_LINE_SPLIT_RE = re.compile(r"\\n|\n|\r")
_ITEM_SPLIT_RE = re.compile(r"[\s、，,；;/|]+")
_NO_GAP_AFTER = "。！？；：，、…”’）》」』】"
# The header row of a table of senses that the overlay flattened into the text.
_TABLE_HEADER_RE = re.compile(r"^\s*(?:拼音|读音)?(?:词性|语法属性)释义(?:英译)?例句(?:例词|及组词)?\s*")
# A list of how a character is typed and written says nothing about what it means: 简体部首：月，部外笔画：13,
# 五笔86&98:EUJN, 笔画数：11. The text of a section ends where one starts. 仓颉 by himself is the man who
# made the characters, and 《仓颉篇》 a book.
_CODES_LINE_RE = re.compile(
    r"(?:五笔|仓颉|郑码)(?:86|98|编码|输入法?|字型|码)?[】 ：:&\d]*[A-Za-z]\s?[A-Za-z]"
    r"|(?:四角(?:号码)?|笔顺(?:编号)?)[】 ：:]*\d"
    r"|(?:部外|总|部首|简体|台湾|康熙)?笔[画划]数?[】 ：:]*[\d一二三四五六七八九十]|部首笔[画划]"
    r"|(?:简体|繁体)?部首(?:】[：:]?|[：:])\s*[^\s，,；;]?|Uni[Cc]ode|U\+[0-9A-Fa-f]{4,5}|统一汉字|汉字(?:首尾|部件)分解")
_BEFORE_CODES_RE = re.compile(r"[\s，,；;]*(?:[（(]\d+[）)]|[①-⒛]|\d+[.、．])?\s*[【〖\[]?$")
# What else such a page lists around them
_NOT_A_SENSE_RE = re.compile(r"田字格|(?:中文|英文)读音|姓名学|吉凶寓意|字意五行|分解查字|输入代码")
_LIST_OPENING_RE = re.compile(r"^基本信息\s*")
_RULE_RE = re.compile(r"[-=—_]{6,}")       # a line drawn across the page
_AFTER_CODE_RE = re.compile(r"^[\dA-Za-z+，,；;：:&\s画]*")
# 拼音：bǎo 繁体：保 in front of the codes is more of the same list, not a sense
_LISTED_RE = re.compile(r"[\u4e00-\u9fff]{2,8}[：:]\s*(?:[A-Za-z\u00c0-\u024f\d]+|[\u4e00-\u9fff](?![\u4e00-\u9fff]))")
_SENTENCE_RE = re.compile(r"[。，；,;]")     # 基本信息诚 繁体字：诚 田字格中的“诚”字 is not one
CODES_FIRST_LINES = 3       # a text can open with a few lines of them and go on with the senses (娱)
_BARE_CJK_RE = re.compile(r"^[\u4e00-\u9fff]+$")
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")

# A heading inside the text of a section. On a line of its own (含义, 出处), or
# in front of what it heads: with a colon (示例：…, 【出处】：…), in brackets
# (【出处】…), or a word that is nothing but a heading (基本解释, 近义词).
# Without a colon 出处不详 and 解释说 would be split.
_CJK_RUN = r"[\u4e00-\u9fff]{2,6}"
_GAP = r"[ \t\u00a0\u3000]*"
_BOUNDARY = r"(?:^|(?<=[。！？”’）》；\s]))"
_INLINE = (
    rf"{_BOUNDARY}{_GAP}[【〖\[]?(?P<colon>{_CJK_RUN})[】〗\]]?{_GAP}[：:]{_GAP}"
    rf"|[【〖](?P<bracket>{_CJK_RUN})[】〗]"
    rf"|{_BOUNDARY}{_GAP}(?P<bare>成文用法|运用示例|近义词|反义词|同义词)"
    rf"|(?<![的其之个种])(?P<anywhere>(?:基本|详细)(?:解释|释义|字义)|引证解释)")
_INLINE_RE = re.compile(_INLINE)
# A text that runs a whole entry together opens with one of its headings
# (发音 zhōng shēn dà shì 释义终身：一生。…出处明·凌蒙初…示例但～…). In such
# a text the plain words head what follows them as well, after a sentence or
# a space. 解释为 and 含义是 are prose.
_PLAIN = (r"(?:基本|详细|词语|成语|引证)(?:解释|释义)|(?:基本|详细)字义|基本词义|成语(?:发音|出处|用法|示例|辨析)"
          r"|近义词|反义词|同义词|解释|释义|含义|词义|出处|用法|示例|例句|造句|辨析|拼音|读音|发音|注音")
_NOT_PROSE = r"(?![是为指即有如同的上])"
_PINYIN_LETTER = "A-Za-zɑɡüāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹ"
# ... or right after the reading: 读音èr bǎi wǔ近义词傻头傻脑
_RUN_TOGETHER_RE = re.compile(
    rf"(?:{_BOUNDARY}|(?<=[{_PINYIN_LETTER}])){_GAP}(?P<plain>{_PLAIN}){_NOT_PROSE}|{_INLINE}")
# The 2019 pages often space a heading out to the width of the others: 解 释：, 出\u3000处, 近 义 词
_SPACE = _GAP[:-1]
# 歇后语 烂网打鱼 after the antonyms is left out; 歇后语。袜子上拆下来的线，都是短的 is a meaning
_RUN_TOGETHER_RE = re.compile(
    _RUN_TOGETHER_RE.pattern + rf"|{_BOUNDARY}{_GAP}(?P<leftout>歇后语|灯谜)(?={_SPACE}|[：:])")
_ONLY_HEADINGS_RE = re.compile(rf"^(?:(?:{_PLAIN})[：: ]*)+$")
_SPACED_HEADING_RE = re.compile(
    rf"{_BOUNDARY}{_GAP}((?:[\u4e00-\u9fff]{_SPACE}{{1,3}}){{1,3}}[\u4e00-\u9fff])(?={_SPACE}|[：:])")
_WHOLE_LINE_RE = re.compile(rf"^[【〖\[]?({_CJK_RUN})[】〗\]]?[：:]?$")
# What says nothing in an entry that has the headword and its reading above it.
_STUB_HEADING_RE = re.compile(rf"^(?:(?:{_WORD}|汉语)?(?:拼音|读音|发音|注音|音标)|词目|词语|成语|词条|名称|中文名)$")
_STUB_LEAD_RE = re.compile(rf"^\s*[【〖\[]?({_CJK_RUN})[】〗\]]?{_GAP}[：:]?{_GAP}")
_PINYIN_RUN_RE = re.compile(r"[A-Za-zɑɡüāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹ][A-Za-zɑɡüāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹ '’\-]*")
_NO_MEANING = "无略暂缺"       # what a page writes where it has nothing to say
_PART_OF_SPEECH_RE = re.compile(r"^(?:名词|动词|形容词|副词|代词|量词|数词|介词|连词|助词|叹词|象声词|拟声词|及物动词|不及物动词)$")
# What such an entry goes on with after the antonyms, and what tells a story.
_LEFT_OUT_RE = re.compile(rf"^(?:歇后语|灯谜|谜语|{_WORD}?(?:典故|故事))$")
# Headings that are too common on other pages to be the heading of a section, but head a part inside one.
_INNER_ONLY = {"事例": "示例", "例子": "示例", "词性": "用法"}
# After 词性 in a line: the kind of word (形容词; 叹词，单纯词; 贬义成语；古代成语; 联合式). What follows it is
# the text again: 词性：形容词 痴呆 chīdāi 1．发呆；呆滞. 词性：由两个偏正短语“晨钟”与“暮鼓”组成 is no heading.
_KIND_OF_WORD = r"(?:[\u4e00-\u9fff]{0,4}?(?:词|成语|短语|词组|俗语|谚语)|[\u4e00-\u9fff]{2,3}式|褒义|贬义|中性)"
_KINDS_OF_WORD_RE = re.compile(rf"{_GAP}[：:]?{_GAP}({_KIND_OF_WORD}(?:[，、；,;/和或及 ]{{1,2}}{_KIND_OF_WORD})*)")
_STUB, _PART_OF_SPEECH, _LEFT_OUT = "stub", "part of speech", "left out"
_MEANING = {"释义", "详解"}
INNER_RANK = len(_HEADING_RES) + 1      # a part found inside a section gives way to a section of that name

# 汉典 pages pasted into Baike bring that site's furniture along: its name in
# front of the definition, and after it a pointer to the same word in another
# of its dictionaries (成语词典已有该词条：被褐, usually cut after two characters).
_PASTED_POINTER_RE = re.compile(r"[ \t\u00a0\u3000]*(?:汉\s*典?\s*)?成语词典已有该词条[：:]?[^\s\[\\]{0,10}")
# 汉 in front of a sentence. Not the dynasty of a quoted author (汉 蔡邕 《…》,
# 汉 郑玄 注：), and not a word the corpus spaced apart (汉 制, 汉 朝).
_PASTED_NAME_RE = re.compile(
    r"^\s*汉\s+(?:典\s+|(?=◎)|(?![\u4e00-\u9fff]{2,3}(?:《|注|笺|曰|云|疏|传))"
    r"(?=[^制朝代族人语字书末初时以之兴军廷王室家\s]\S*?[。，；：“（(]))")


# The same name once more after the last sentence of a paragraph (…重来振羽翎。” 汉 典).
_PASTED_NAME_END_RE = re.compile(r"(?<=[。”’）》！？])\s*汉\s*典?[ \t\u00a0\u3000]*(?=\\n|$)", re.M)


def strip_pasted_furniture(text: str | None) -> str:
    """'汉 犹言被褐怀玉。 明 叶宪祖 …  汉 成语词典已有该词条：被褐' without the
    two 汉 and the pointer. For the text of a section as the corpus has it,
    before the spaces between Chinese characters are taken out."""
    if not text or ("汉" not in text and "词典已有该词条" not in text):
        return text or ""
    return _PASTED_NAME_END_RE.sub("", _PASTED_NAME_RE.sub("", _PASTED_POINTER_RE.sub("", text)))


def _heading(heading: str | None, title: str) -> str:
    h = clean_title(heading).strip("：:【】[]〖〗 ")
    if title and h.startswith(title) and len(h) > len(title):   # the overlay runs title and heading together
        h = h[len(title):]
    return h


def _rank(heading: str) -> tuple[str, int] | None:
    for i, (label, pattern) in enumerate(_HEADING_RES):
        if pattern.match(heading):
            return label, i
    return None


def label_of(heading: str | None, title: str = "") -> str | None:
    """The label a section heading goes under, or None: 成语出处 -> 出处,
    基本解释 -> 释义, 详细解释 -> 详解, 成语故事 -> None."""
    found = _rank(_heading(heading, title))
    return found[0] if found else None


def _inner(word: str) -> str | None:
    """What a heading inside a section heads: one of the labels, the
    headword or its pronunciation again (a stub), a part of speech, or None
    when it is no heading."""
    found = _rank(word)
    if found:
        return found[0]
    if word in _INNER_ONLY:
        return _INNER_ONLY[word]
    if _STUB_HEADING_RE.match(word):
        return _STUB
    if _LEFT_OUT_RE.match(word):
        return _LEFT_OUT
    return _PART_OF_SPEECH if _PART_OF_SPEECH_RE.match(word) else None


def _without_stub(text: str, title: str) -> str:
    """'拼音 bái ái ái形容非常洁白。' and '词目：冷汗 指畏寒、肢冷而出汗。'
    without the reading and the headword they open with."""
    m = _STUB_LEAD_RE.match(text)
    if not m or not _STUB_HEADING_RE.match(m.group(1)):
        return text
    rest = text[m.end():]
    if title and rest.startswith(title):
        return rest[len(title):]
    pinyin = _PINYIN_RUN_RE.match(rest)
    return rest[pinyin.end():] if pinyin and has_tone_marks(pinyin.group(0)) else text


def _join_spaced(line: str) -> str:
    """'解 释 付：交给' as '解释 付：交给': a heading that the page spaced out, as one word."""
    def joined(m: re.Match) -> str:
        spaced = m.group(1)
        chars = [ch for ch in spaced if not ch.isspace()]
        for k in range(len(chars), 1, -1):
            if _inner("".join(chars[:k])) is not None:
                seen = end = 0
                for end, ch in enumerate(spaced, 1):
                    seen += not ch.isspace()
                    if seen == k:
                        break
                return m.group(0)[:m.start(1) - m.start()] + "".join(chars[:k]) + spaced[end:]
        return m.group(0)

    return _SPACED_HEADING_RE.sub(joined, line)


def _opens_with_heading(line: str, title: str) -> bool:
    text = line.lstrip()
    m = re.match(rf"{_WORD}?[：:]?\s*{re.escape(title)}\s*", text) if title else None
    text = text[m.end():] if m else text
    m = _RUN_TOGETHER_RE.match(text)
    return bool(m and m.group("plain") and text[m.end():].strip("：: \t\u00a0\u3000"))     # not a line of its own


def _lines_by_label(raw: str, title: str, label: str) -> dict[str, list[str]]:
    """The lines of a section's text under the label each belongs to. They
    start under the section's own label; a heading inside the text moves on to
    another one (see _INLINE_RE)."""
    parts: dict[str, list[str]] = {label: []}
    current = label
    after_stub_heading = False
    lines = [_join_spaced(line) for line in _LINE_SPLIT_RE.split(raw) if clean_text(line, title)]
    if lines:
        lines[0] = _TABLE_HEADER_RE.sub("", lines[0])       # before 释义 and 例句 in it are taken for headings
    # the heading can stand on the second line, after 成语 一无所获
    run_together = any(_opens_with_heading(line, title) for line in lines[:3])
    headings = _RUN_TOGETHER_RE if run_together else _INLINE_RE

    def turn(to: str) -> None:
        nonlocal current
        # 基本解释 on the first line of a 详细解释 section heads the same text as the section, and so
        # does 出处 there: what follows is the senses with their quotations (捎带, 妖娆)
        if to == "释义" and label == "详解":
            to = label      # 基本词义 and 【词义】 in a 详细解释 section head senses of that section (惝, 乖剌)
        if to != current and not ((to in _MEANING or to == "出处") and current in _MEANING and not any(parts.values())):
            current = to
            parts.setdefault(to, [])

    def add(text: str, stub: bool, headword_line: bool = False) -> None:
        text = text.lstrip("：: \t\u00a0\u3000")
        cleaned = clean_text(text, title)
        if not cleaned:
            return
        if headword_line:       # 【头油】tóuyóu goes; 1、见“墨迹”。 says something, little as it is
            stub = not _CJK_CHAR_RE.search(cleaned.replace(title, ""))
        if not (stub and says_nothing(cleaned, title)):     # the entry has that above the text
            parts[current].append(_without_stub(text, title).lstrip("，,；; ") if stub else text)

    for i, line in enumerate(lines):
        whole = _WHOLE_LINE_RE.match(clean_text(line, title))
        kind = _inner(whole.group(1)) if whole else None
        if kind in _MEANING and current in _LIST_LABELS:
            kind = None         # in a list of synonyms, 解释 on a line of its own is one of them
        stub, after_stub_heading = after_stub_heading, kind == _STUB
        if kind == _STUB:
            continue
        if kind == _PART_OF_SPEECH:
            parts[current].append(whole.group(1) + "：")
            continue
        if kind:
            turn(kind)
            continue
        pos = 0
        stub = stub or (i == 0 and run_together)        # 成语一无所获 in front of the first heading
        headword_line = i == 0 and not stub and bool(title and title in line)
        for m in headings.finditer(line):
            groups = m.groupdict()
            word = (groups.get("plain") or groups.get("leftout") or groups["colon"] or groups["bracket"]
                    or groups["bare"] or groups["anywhere"])
            kind = _inner(word)
            if kind is None or kind == _PART_OF_SPEECH or m.start() < pos:
                continue
            if word == "词性":
                kinds = _KINDS_OF_WORD_RE.match(line, m.end())
                if kinds:
                    add(line[pos:m.start()], stub, headword_line)
                    headword_line = stub = False
                    parts.setdefault("用法", []).append(kinds.group(1))
                    pos = kinds.end() + len(line[kinds.end():]) - len(line[kinds.end():].lstrip("。，,；; "))
                continue
            add(line[pos:m.start()], stub, headword_line)
            headword_line, stub = False, kind == _STUB
            if stub:
                pos = m.start()     # 拼音：guò mǐn goes; of 拼音：bái ái ái形容非常洁白 the reading goes
            else:
                turn(kind)
                pos = m.end()
        add(line[pos:], stub, headword_line)
    return parts


def section_parts(content: str | None, title: str, label: str) -> list[list[str]]:
    """[label, text] for the text of a section and for what stands under a
    heading of its own inside it: the 详细解释 section of 插足 is 含义 …, 出处 …,
    示例 …, one to a line, and gives a 详解, a 出处 and a 示例 part. Each text
    is one cleaned line of at most MAX_SECTION_CHARS; a part that says
    nothing (empty, or only the title's pinyin) is left out."""
    raw = strip_pasted_furniture(content)
    parts = [[name, _text(lines, title, name)] for name, lines in _lines_by_label(raw, title, label).items()
             if name != _LEFT_OUT]
    parts = [part for part in parts if part[1] and not _ONLY_HEADINGS_RE.match(part[1])]
    if not parts:
        lines = [line for line in _LINE_SPLIT_RE.split(raw) if clean_text(line, title)]
        whole = _WHOLE_LINE_RE.match(clean_text(lines[0], title)) if len(lines) == 1 else None
        if whole and len(whole.group(1)) == 2:      # 基本解释 by itself is a heading with nothing under it
            text = _text(lines, title, label)       # a section whose whole text is 解释 says that
            parts = [[label, text]] if text else []
    return parts


def section_text(content: str | None, title: str, label: str) -> str:
    """The text of a section under its own label, '' when there is none."""
    return next((text for name, text in section_parts(content, title, label) if name == label), "")


def _text(raw_lines: list[str], title: str, label: str) -> str:
    lines = [p for p in (clean_text(x, title) for x in raw_lines) if p]
    if not lines:
        return ""
    lines[0] = _LIST_OPENING_RE.sub("", _TABLE_HEADER_RE.sub("", lines[0]))
    if label in _LIST_LABELS and not any(ch in line for line in lines for ch in "。：:"):
        # a bare list of words, one to a line or spaced apart, which the cleaning runs together
        words = [clean_text(w, title) for w in _ITEM_SPLIT_RE.split(" ".join(raw_lines))]
        words = [w for w in words if w]
        ends = next((i for i, w in enumerate(words) if i and _inner(w)), len(words))
        words = words[:ends]        # 严于律己、从善如流 用法 联合式；作谓语: the list ends at 用法
        if len(words) == 1 and len(title) == 4 and len(words[0]) >= 8 and len(words[0]) % 4 == 0 \
                and _BARE_CJK_RE.match(words[0]):
            words = [words[0][i:i + 4] for i in range(0, len(words[0]), 4)]     # 成语 with nothing between them
        text = "、".join(dict.fromkeys(words))
    else:
        text = ""
        for i, line in enumerate(lines):
            line = _RULE_RE.sub(" ", line).strip()
            while line:
                codes = _CODES_LINE_RE.search(line)     # how the character is typed and written
                head = _BEFORE_CODES_RE.sub("", line[:codes.start()]) if codes else line
                if head:
                    text += ("" if not text or text[-1] in _NO_GAP_AFTER else " ") + head
                if not codes:
                    break
                said = _LISTED_RE.sub("", text)
                if cjk_len(said.replace(title, "") if title else said) >= MIN_REST_CJK and _SENTENCE_RE.search(said) \
                        and not _NOT_A_SENSE_RE.search(said):
                    break           # 臆: the senses, then 简体部首：月，部外笔画：13 and the codes
                if i >= CODES_FIRST_LINES:
                    return ""       # 保: ten lines of them
                # 娱: 拼音：yú，笔划：10, 部首：女, and then the senses
                text, line = "", _AFTER_CODE_RE.sub("", line[codes.end():])
            else:
                continue
            if codes:
                break
    text = trim_summary(text, MAX_SECTION_CHARS)
    if not _says_something(text, title, label) or _CODES_LINE_RE.search(text) or _NOT_A_SENSE_RE.search(text[:40]):
        return ""
    return text


def _says_something(text: str, title: str, label: str) -> bool:
    han = _CJK_CHAR_RE.findall(text.replace(title, "") if title else text)
    if len(han) == 1:       # one character can be the whole meaning: 姬媵, 1.妾
        return label in _MEANING and han[0] not in _NO_MEANING and not has_tone_marks(text)
    return cjk_len(text) >= MIN_SECTION_CJK and not says_nothing(text, title)


def pick_sections(pairs: Iterable[tuple[str | None, str | None]], title: str, summary: str = "",
                  refuse: Callable[[str], bool] | None = None, proof_within: int | None = None) -> list | None:
    """[label, text] for one section under each label, in ORDER; None when
    the page is not about a word or has no such section. `refuse` is asked
    about every text (the overlay passes its test for injected characters).

    Sections count from the first heading that shows the page to be about a
    word, or from the top when the summary says so. `proof_within`: that
    heading has to be among the first so many. A row of the 2019 corpus can
    end with the sections of another article, and the page of a machine must
    not show the synonyms of the 成语 that follows it in the row."""
    best: dict[str, tuple[int, str]] = {}
    about_word = is_word({"title": title, "summary": summary})
    for i, (heading, content) in enumerate(pairs):
        h = _heading(heading, title)
        found = _rank(h)
        if not about_word:
            if not (_WORD_HEADING_RE.match(h) or (found and found[0] in _PROVES_WORD)):
                continue
            if proof_within is not None and i >= proof_within:
                return None
            about_word = True
        if found is None:
            continue
        for label, text in section_parts(content, title, found[0]):
            rank = found[1] if label == found[0] else INNER_RANK
            prefix = next((p for p in _EXAMPLE_PREFIXES if text.startswith(p)), None) if label == "用法" else None
            if prefix:      # the overlay's 成语用法 section often holds nothing but examples under a heading of its own
                label, rank, text = "示例", len(_HEADING_RES), text[len(prefix):].lstrip(" ：:")
            if label in best and best[label][0] <= rank:
                continue
            if text and not (refuse and refuse(text)):
                best[label] = (rank, text)
    return [[label, best[label][1]] for label in ORDER if label in best] or None


def shown_sections(rec: dict) -> list:
    """The sections of a record that add to its summary. One that the summary
    already says is left out: the summary of 被褐藏辉 is its 释义 section, and an
    abstract often ends with the meaning that the 释义 section repeats."""
    summary, title = rec.get("summary") or "", rec.get("title") or ""
    out, total = [], 0
    for label, text in rec.get("sections") or []:
        if text and summary and text.startswith(summary):
            # the summary is the first paragraph of this section: what follows it is new
            # (发给: 1. […]∶分给, and the section goes on with an example and the second sense)
            text = text[len(summary):].lstrip(" ，；。")
            if cjk_len(text) < MIN_REST_CJK:
                continue
        elif not text or text in summary or any(similarity(text, said, title) >= SAME_ARTICLE
                                                for said in [summary] + [t for _label, t in out]):
            continue
        if total + len(text) > MAX_SHOWN_CHARS:
            break
        total += len(text)
        out.append([label, text])
    return out
