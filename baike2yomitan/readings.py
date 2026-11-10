"""Readings (pinyin) for headwords, taken from the best source available.

Neither corpus has a pinyin field, so the reading is assembled per record, in
this order of preference:

1. ``data/pinyin_overrides.tsv`` - hand-checked ``title<TAB>reading`` lines;
2. CC-CEDICT, when the title is a CC-CEDICT headword (several readings: the
   one the article states, when it states exactly one of them and the title
   is not a single character; else the one pypinyin's own phrase list gives;
   else the first lower-case one);
3. the article's own pinyin, when its infobox or summary states one that fits
   the title character by character (``拼音是zì kuài yǐ xià``);
4. the same, borrowed from another sense of the same title;
5. pypinyin - a per-character guess helped by a phrase list. CC-CEDICT's
   words are loaded into that list, so a longer title that contains one
   (``不粘锅炒饭``) inherits its reading (``zhān``, not ``nián``). Latin letters
   and digits in a title are kept as they are (``Linux高级程序设计`` ->
   ``Linux gāo jí …``), the way CC-CEDICT writes ``K jīn`` for K金.

Readings are lower-case, tone-marked syllables separated by spaces.
"""
from __future__ import annotations

import collections
import gzip
import io
import os
import re
import unicodedata

OVERRIDES_PATH = os.path.join("data", "pinyin_overrides.tsv")

_MARKS = {"a": "āáǎà", "e": "ēéěè", "i": "īíǐì", "o": "ōóǒò", "u": "ūúǔù", "ü": "ǖǘǚǜ"}
_TONE_COMBINING = {"̄", "́", "̌", "̀"}  # macron, acute, caron, grave
_NUMBERED = re.compile(r"^([A-Za-zü:]+)([1-5])$")
_CEDICT_LINE = re.compile(r"^(\S+) (\S+) \[([^\]]*)\]")


def is_cjk(text: str) -> bool:
    return bool(text) and all("一" <= ch <= "鿿" for ch in text)


def strip_tones(s: str) -> str:
    """``zháo`` -> ``zhao``; the diaeresis of ü is kept."""
    d = unicodedata.normalize("NFD", s)
    return unicodedata.normalize("NFC", "".join(ch for ch in d if ch not in _TONE_COMBINING))


def syllable_to_marks(token: str) -> str:
    """CC-CEDICT numbered syllable -> tone marks (``zhao2`` -> ``zháo``,
    ``lu:4`` -> ``lǜ``, ``de5`` -> ``de``, ``r5`` -> ``r``). Anything that is
    not a numbered syllable (a Latin letter, punctuation) is returned as is."""
    m = _NUMBERED.match(token)
    if not m:
        return token
    body = m.group(1).lower().replace("u:", "ü").replace("v", "ü")
    tone = int(m.group(2))
    if tone == 5:
        return body
    i = body.find("a")
    if i < 0:
        i = body.find("e")
    if i < 0:
        i = body.find("ou")
    if i < 0:
        vowels = [k for k, ch in enumerate(body) if ch in "iouü"]
        i = vowels[-1] if vowels else -1
    if i < 0:  # syllabic m / n / ng
        return unicodedata.normalize("NFC", body[0] + "̄́̌̀"[tone - 1] + body[1:])
    return body[:i] + _MARKS[body[i]][tone - 1] + body[i + 1:]


def cedict_to_marks(pinyin: str) -> str:
    return " ".join(syllable_to_marks(t) for t in pinyin.split())


def load_cedict_readings(path: str) -> dict[str, list[str]]:
    """Simplified headword -> its tone-marked readings. Readings CC-CEDICT
    writes in lower case come first: the capitalised ones are proper nouns and
    surnames (``单 [Shan4]``), rarely what an encyclopedia title means."""
    opener = gzip.open if path.endswith(".gz") else open
    lower: dict[str, list[str]] = collections.defaultdict(list)
    upper: dict[str, list[str]] = collections.defaultdict(list)
    with opener(path, "rb") as raw, io.TextIOWrapper(raw, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _CEDICT_LINE.match(line)
            if not m or line[0] == "#":
                continue
            simp, py = m.group(2), m.group(3)
            reading = cedict_to_marks(py)
            bucket = upper if py[:1].isupper() else lower
            if reading and reading not in bucket[simp]:
                bucket[simp].append(reading)
    out: dict[str, list[str]] = {}
    for simp in set(lower) | set(upper):
        seen = list(lower.get(simp, ()))
        seen += [r for r in upper.get(simp, ()) if r not in seen]
        out[simp] = seen
    return out


def load_overrides(path: str = OVERRIDES_PATH) -> dict[str, str]:
    """``title<TAB>reading`` per line; blank lines and ``#`` comments ignored."""
    out: dict[str, str] = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as f:  # tolerate the BOM some editors add
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                raise ValueError(f"{path}:{n}: expected 'title<TAB>reading', got {line!r}")
            out[parts[0].strip()] = " ".join(parts[1].split())
    return out


# --- the article's own pinyin -------------------------------------------------

_PINYIN_CHARS = "A-Za-zɑɡüÜāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹĀÁǍÀĒÉĚÈĪÍǏÌŌÓǑÒŪÚǓÙ"
_PINYIN_RUN = re.compile(f"[{_PINYIN_CHARS}][{_PINYIN_CHARS} '’\\-·]*")
_SEPARATORS = re.compile(r"[ '’\-·]")
_INFOBOX_KEYS = ("拼音", "读音", "注音", "发音")
_LOOKALIKES = str.maketrans({"ɑ": "a", "ɡ": "g"})  # IPA letters Baike editors type for a and g

_char_cache: dict[str, tuple[frozenset, frozenset]] = {}


def char_readings(ch: str) -> tuple[frozenset, frozenset]:
    """(tone-marked readings, the same without tones) pypinyin knows for one character."""
    hit = _char_cache.get(ch)
    if hit is None:
        from pypinyin.pinyin_dict import pinyin_dict

        toned = frozenset(unicodedata.normalize("NFC", r) for r in pinyin_dict.get(ord(ch), "").split(",") if r)
        hit = _char_cache[ch] = (toned, frozenset(strip_tones(r) for r in toned))
    return hit


def fit_pinyin(title: str, run: str) -> str | None:
    """Split a run of pinyin letters into exactly one syllable per character of
    ``title``, each a reading that character really has; None when it does not
    fit. Works with or without spaces (``zháohuǒ``). A syllable written without
    a tone is accepted only for characters that have a neutral-tone reading, so
    a typo like ``can fēng`` for 骖风 is rejected rather than half-trusted."""
    s = _SEPARATORS.sub("", unicodedata.normalize("NFC", run).translate(_LOOKALIKES).lower())
    if not s or len(s) > 7 * len(title):
        return None
    chars = [char_readings(ch) for ch in title]
    out: list[str] = []

    def walk(k: int, i: int) -> bool:
        if k == len(chars):
            return i == len(s)
        toned, toneless = chars[k]
        for size in range(min(6, len(s) - i), 0, -1):
            piece = s[i:i + size]
            if strip_tones(piece) not in toneless or piece not in toned:
                continue
            out.append(piece)
            if walk(k + 1, i + size):
                return True
            out.pop()
        return False

    return " ".join(out) if walk(0, 0) else None


def stated_pinyins(rec: dict) -> list[str]:
    """Every pinyin the article itself gives for its title, in order of
    appearance: 拼音-like infobox rows first, then runs of Latin letters in the
    summary that fit the title character by character."""
    title = rec.get("title") or ""
    if not is_cjk(title):
        return []
    texts = [str(v) for k, v in (rec.get("infobox") or []) if any(key in str(k) for key in _INFOBOX_KEYS)]
    texts.append((rec.get("summary") or "")[:300])
    found: list[str] = []
    for text in texts:
        for m in _PINYIN_RUN.finditer(unicodedata.normalize("NFC", text)):
            fitted = fit_pinyin(title, m.group(0))
            if fitted and fitted not in found:
                found.append(fitted)
    return found


def stated_pinyin(rec: dict) -> str | None:
    """The first pinyin the article itself gives for its title, if any."""
    found = stated_pinyins(rec)
    return found[0] if found else None


# --- putting it together ------------------------------------------------------

_ASCII_RUN = re.compile(r"[A-Za-z0-9]+")
# word -> what pypinyin says before any CC-CEDICT phrase is loaded into it.
# load_phrases_dict changes pypinyin for the whole process, so the untouched
# answer has to be taken first and remembered across Readings objects.
_pristine_guess: dict[str, str] = {}


def _keep_ascii(chunk: str) -> list[str]:
    """pypinyin `errors` callback: keep letter and digit runs, drop punctuation."""
    return _ASCII_RUN.findall(chunk)


class Readings:
    """Callable: record -> (reading, source). ``source`` is one of ``override``,
    ``cedict``, ``article``, ``article-shared``, ``pypinyin`` or ``none``."""

    def __init__(self, cedict_path: str | None = None, overrides_path: str | None = OVERRIDES_PATH):
        from pypinyin import Style, lazy_pinyin, load_phrases_dict  # optional dependency

        self._lazy, self._style = lazy_pinyin, Style.TONE
        self.overrides = load_overrides(overrides_path) if overrides_path else {}
        self.cedict = load_cedict_readings(cedict_path) if cedict_path else {}
        self._shared: dict[str, collections.Counter] = {}
        # Words with several CC-CEDICT readings: pypinyin's own phrase list
        # usually knows the everyday one (明朝 míng cháo, 教授 jiào shòu), where
        # CC-CEDICT's first lower-case entry is the rare one (míng zhāo
        # "tomorrow morning", jiāo shòu "to instruct"). Ask before the phrases
        # are loaded: afterwards pypinyin only repeats what it was told.
        self._preferred: dict[str, str] = {}
        phrases = {}
        for word, readings in self.cedict.items():
            reading = readings[0]
            if len(readings) > 1 and len(word) > 1 and is_cjk(word):
                if word not in _pristine_guess:
                    _pristine_guess[word] = " ".join(lazy_pinyin(word, style=Style.TONE, errors="ignore"))
                reading = self._preferred[word] = self._closest(readings, _pristine_guess[word])
            self._add_phrase(phrases, word, reading)
        for word, reading in self.overrides.items():
            self._add_phrase(phrases, word, reading)
        if phrases:
            load_phrases_dict(phrases)

    @staticmethod
    def _add_phrase(phrases: dict, word: str, reading: str) -> None:
        syllables = reading.split()
        # Erhua words are left out: CC-CEDICT writes 儿 as a bare "r", which
        # would leak into guesses for unrelated titles (孩儿 -> "hái r").
        if len(word) > 1 and is_cjk(word) and len(syllables) == len(word) and "r" not in syllables:
            phrases[word] = [[s] for s in syllables]

    def guess(self, title: str) -> str:
        if not any("一" <= ch <= "鿿" for ch in title):
            return ""
        return " ".join(self._lazy(title, style=self._style, errors=_keep_ascii))

    def observe(self, rec: dict) -> None:
        """First pass: remember what each title's articles say, so a sense that
        states no pinyin can borrow it from one that does."""
        title = rec.get("title") or ""
        if title in self.overrides or title in self.cedict:
            return
        stated = stated_pinyin(rec)
        if stated:
            self._shared.setdefault(title, collections.Counter())[stated] += 1

    @staticmethod
    def _closest(candidates: list[str], guess: str) -> str:
        """The candidate a guess points at: the same reading, else the same
        syllables with other tones, else the first candidate."""
        if guess in candidates:
            return guess
        bare = strip_tones(guess)
        for c in candidates:
            if strip_tones(c) == bare:
                return c
        return candidates[0]

    def _pick_cedict(self, title: str, candidates: list[str], stated: str | None) -> str:
        if len(candidates) == 1:
            return candidates[0]
        if stated and stated in candidates:
            return stated
        return self._preferred.get(title) or self._closest(candidates, self.guess(title))

    def __call__(self, rec: dict) -> tuple[str, str]:
        title = rec.get("title") or ""
        if title in self.overrides:
            return self.overrides[title], "override"
        candidates = self.cedict.get(title)
        if candidates:
            stated = None
            if len(candidates) > 1 and len(title) > 1:
                # The article's pinyin decides only when it names exactly one of
                # the readings (朝阳（cháo yáng）是北京的一个区). An article about
                # the word itself lists them all (读cháo yáng时…读zhāo yáng时…),
                # and an article about a character always does: 了（拼音：liǎo、le）
                # does not mean that 了 is read liǎo.
                named = [p for p in stated_pinyins(rec) if p in candidates]
                stated = named[0] if len(named) == 1 else None
            return self._pick_cedict(title, candidates, stated), "cedict"
        stated = stated_pinyin(rec)
        if stated:
            return stated, "article"
        shared = self._shared.get(title)
        if shared:
            return shared.most_common(1)[0][0], "article-shared"
        guess = self.guess(title)
        return guess, "pypinyin" if guess else "none"
