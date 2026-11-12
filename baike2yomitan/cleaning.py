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
_ENTITY_RE = re.compile(r"&(?:#\d{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,12});")
_BARE_NBSP_RE = re.compile(r"&nbsp(?![;A-Za-z0-9])", re.I)
# An entity that the corpus cut off with the end of a text: 也说“走背字儿&rdqu. Not you&me, m&ms.
_CUT_ENTITY_RE = re.compile(r"(?<![A-Za-z0-9])&([a-z]{3,8})$")
_ENTITY_NAMES = tuple(name for name in html.entities.html5 if name.endswith(";"))
# Names that no browser knows, from a transliteration scheme for Sanskrit and Pali.
_EXTRA_ENTITIES = {
    "amacron": "ā", "emacron": "ē", "imacron": "ī", "omacron": "ō", "umacron": "ū",
    "Amacron": "Ā", "Emacron": "Ē", "Imacron": "Ī", "Omacron": "Ō", "Umacron": "Ū",
    "ddotblw": "ḍ", "hdotblw": "ḥ", "ldotblw": "ḷ", "mdotblw": "ṃ", "ndotblw": "ṇ", "rdotblw": "ṛ",
    "sdotblw": "ṣ", "tdotblw": "ṭ", "mdotabv": "ṁ", "ndotabv": "ṅ",
}


def _entity(m: re.Match) -> str:
    whole = m.group(0)
    char = html.unescape(whole)
    if char != whole:
        return char
    name = whole[1:-1]
    if name in _EXTRA_ENTITIES:
        return _EXTRA_ENTITIES[name]
    lower = "&" + name.lower() + ";"        # &NBSP;, &DEG;
    char = html.unescape(lower)
    return char if char != lower else whole


def decode_entities(text: str | None, cut_off: bool = False) -> str | None:
    """HTML entities as the characters they stand for, for raw text before any
    other rule sees it: &#91;2&#93; has to be [2] for the citation rule, and
    d&igrave;ngzhǐ has to be dìngzhǐ to be read as pinyin. More than once,
    because some are escaped two or three times (&amp;amp;nbsp;). A name nobody
    knows stays as it is. `cut_off`: the text is body text that the corpus may
    have ended inside an entity; a title can end in &me."""
    if not text or "&" not in text:
        return text
    for _ in range(4):
        decoded = _ENTITY_RE.sub(_entity, text)
        if decoded == text:
            break
        text = decoded
    cut = _CUT_ENTITY_RE.search(text) if cut_off else None
    if cut and any(name.startswith(cut.group(1)) for name in _ENTITY_NAMES):
        text = text[:cut.start()]
    return _BARE_NBSP_RE.sub(" ", text).replace("\u00ad", "")      # the soft hyphen shows nothing


def strip_citations(text: str) -> str:
    return _CITATION_RE.sub("", text)


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
    text = strip_citations(text)
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
