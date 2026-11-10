"""Shared text cleaning and quality rules (source-agnostic)."""
from __future__ import annotations

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
# Gallery captions that leak into scraped text: "剧照(80张)", "合并图册(2张)"
_CAPTION_RE = re.compile(r"[^\s，。；：、！？]{0,12}[（(]\d{1,3}张[)）]")
_WS_RE = re.compile(r"[\s\u00a0\u2000-\u200b\u3000\ufeff]+")
# A single space between two CJK characters/punctuation marks is never
# meaningful in Chinese prose.
_CJK = "\u2e80-\u2fdf\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef"
_CJK_PUNCT = "。！？；，、：“”‘’（）《》【】"
_CJK_SPACE_RE = re.compile(
    rf"(?<=[{_CJK}]) (?=[{_CJK}])|(?<=[{_CJK_PUNCT}]) | (?=[。！？；，、：”’）》】])")
_SENTENCE_END = "。！？；"
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
# Infobox-style lines: "\u4f5c\u8005\uff1a\u5f90\u6c49\u6797\u7f16\u8457", "I S B N\uff1a9787801383617", "\u00b7ISBN\uff1a7532120198"
_KEY_VALUE_LINE_RE = re.compile(r"^\s*[\u00b7\u2022\-\u3010\[]?\s*[^\uff1a:\uff0c\u3002\uff1b\uff01\uff1f\n]{1,12}[\u3011\]]?\s*[\uff1a:]")


def strip_citations(text: str) -> str:
    return _CITATION_RE.sub("", text)


def strip_ui_labels(text: str) -> str:
    text = _TRAILER_RE.sub("", text)
    text = _UI_COMPOUND_RE.sub("", text)
    return _UI_EDGE_RE.sub("", text)


def normalize_whitespace(text: str) -> str:
    text = _WS_RE.sub(" ", text).strip()
    return _CJK_SPACE_RE.sub("", text)


def clean_text(text: str | None) -> str:
    """Full cleaning pass used for summaries, labels and titles."""
    if not text:
        return ""
    text = text.replace("\\n", "\n")  # literal backslash-n sequences in 563w
    text = strip_citations(text)
    text = _CAPTION_RE.sub("", text)
    text = strip_ui_labels(text)
    text = normalize_whitespace(text)
    return strip_ui_labels(text).strip()


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
    colon).  Such lines are never a usable summary even when long enough."""
    return bool(_KEY_VALUE_LINE_RE.match(text))


def is_summary_candidate(text: str) -> bool:
    """A cleaned paragraph that can stand in for a missing summary: long
    enough, contains Chinese, and is not an infobox line."""
    return summary_drop_reason(text) is None and has_cjk(text) and not is_key_value_line(text)


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
