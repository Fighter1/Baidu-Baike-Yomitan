"""Quality audit of a built zip: what a user sees for known words, and how
often the known kinds of bad entry occur.

Two parts:

1. Golden words (``data/golden_words.tsv``): ``headword<TAB>check<TAB>value
   <TAB>scope`` lines, each a fact that once was wrong in a release, e.g.
   ``明朝  reading  míng cháo`` or ``时间  first_not_work``. A failing check
   makes the command exit non-zero.
2. Rates over every entry: summaries that say nothing, works ranked first,
   repeated senses and so on. They are reported and saved, not judged; a
   golden word is what turns one of them into a test.
"""
from __future__ import annotations

import collections
import os
import re
import zipfile
from concurrent.futures import ProcessPoolExecutor

from .cleaning import SAME_ARTICLE, says_nothing, similarity
from .records import loads
from .sense import is_work
from .validate import worker_count

GOLDEN_PATH = os.path.join("data", "golden_words.tsv")
CHECKS = ("present", "absent", "reading", "first_reading", "first", "first_not_work", "any", "ends", "traditional",
          "senses_max")
NEEDS_VALUE = {"reading", "first_reading", "first", "any", "ends", "traditional", "senses_max"}
SCOPES = ("", "full", "lexical")

_LIST_ITEM_RE = re.compile(r"^\s*(?:[2-9]|[1-9]\d)\s*[、.．)）]|^\s*[（(](?:[2-9]|[1-9]\d)[)）]|^\s*[⑵-⒇②-⑳]")
_OPENERS, _CLOSERS = "“（《「『【", "”）》」』】"
_SENTENCE_END = "。！？；…”’」』）》】.!?"
_BANK_RE = re.compile(r"term_bank_(\d+)\.json")


def load_golden(path: str = GOLDEN_PATH) -> list[dict]:
    """Parsed golden lines; blank lines and ``#`` comments are ignored."""
    out: list[dict] = []
    with open(path, encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = [p.strip() for p in line.split("\t")] + ["", ""]
            word, check, value, scope = parts[:4]
            if not word or check not in CHECKS or scope not in SCOPES or (check in NEEDS_VALUE and not value):
                raise ValueError(f"{path}:{n}: expected 'headword<TAB>check[<TAB>value[<TAB>full|lexical]]' with a "
                                 f"check from {', '.join(CHECKS)}; got {line!r}")
            if check == "senses_max" and not value.isdigit():
                raise ValueError(f"{path}:{n}: senses_max needs a number, got {value!r}")
            out.append({"word": word, "check": check, "value": value, "scope": scope, "line": n})
    return out


def _text(node) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_text(n) for n in node)
    if isinstance(node, dict):
        return _text(node.get("content"))
    return ""


def entry_parts(definitions) -> dict[str, str]:
    """The labelled parts of an entry this project builds: summary,
    sense-label, simplified-term, traditional-term, infobox, footer."""
    parts: dict[str, str] = {}

    def walk(node) -> None:
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            name = (node.get("data") or {}).get("baike")
            if name and name != "terms":
                parts.setdefault(name, _text(node))
            else:
                walk(node.get("content"))

    walk(definitions)
    return parts


class Sense:
    """One article as the zip shows it: the rows that share a sequence number."""
    __slots__ = ("title", "seq", "reading", "score", "label", "summary", "terms")

    def __init__(self, title: str, seq: int, reading: str, score, label: str, summary: str, terms=()):
        self.title, self.seq, self.reading, self.score = title, seq, reading, score
        self.label, self.summary = label, summary
        self.terms = {title, *terms}

    def as_record(self) -> dict:
        return {"title": self.title, "sense_label": self.label, "summary": self.summary}


def _bank_names(zf: zipfile.ZipFile) -> list[str]:
    return sorted((n for n in zf.namelist() if _BANK_RE.fullmatch(n)), key=lambda n: int(_BANK_RE.fullmatch(n).group(1)))


def _unfinished(summary: str) -> bool:
    """Stops without closing punctuation inside an open quote or bracket."""
    s = summary.rstrip()
    return bool(s) and s[-1] not in _SENTENCE_END and any(
        s.count(a) > s.count(b) for a, b in zip(_OPENERS, _CLOSERS))


def _check(golden: dict, senses: list[Sense]) -> str | None:
    """None when the check holds, else what was found instead."""
    check, value, word = golden["check"], golden["value"], golden["word"]
    if check == "absent":
        return None if not senses else f"present with {len(senses)} sense(s)"
    if not senses:
        return "not in the dictionary"
    top = max(senses, key=lambda s: s.score)
    if check == "present":
        return None
    if check == "reading":
        got = sorted({s.reading for s in senses})
        return None if value in got else f"readings {got}"
    if check == "first_reading":
        return None if top.reading == value else f"first sense reads {top.reading!r}"
    if check == "first":
        return None if value in top.summary or value in top.label else f"first sense: {top.label!r} {top.summary[:60]!r}"
    if check == "first_not_work":
        return f"first sense is a work: {top.label!r} {top.summary[:60]!r}" if is_work(top.as_record()) else None
    if check == "any":
        return None if any(value in s.summary or value in s.label for s in senses) else \
            f"no sense mentions it; first sense: {top.summary[:60]!r}"
    if check == "ends":
        return None if top.summary.endswith(value) else f"first sense ends {top.summary[-30:]!r}"
    if check == "traditional":
        got = sorted(set().union(*(s.terms for s in senses)) - {word})
        return None if value in got else f"other spellings {got}"
    if check == "senses_max":
        return None if len(senses) <= int(value) else f"{len(senses)} senses"
    raise ValueError(check)


# --- reading the zip, one term bank per task ----------------------------------
#
# A sense is the run of adjacent rows that share a sequence number: the
# simplified headword first, then its traditional spellings. Such a run can
# straddle two term banks, and each bank is read by itself, so a bank may open
# with rows whose simplified row is in the bank before it. They are recognised
# by their term differing from the simplified headword named inside the entry,
# and are handed back as "orphans" for the parent to attach.

_worker: dict = {}


def _init_worker(zip_path: str, keep: frozenset = frozenset()) -> None:
    _worker["zip"] = zipfile.ZipFile(zip_path)
    _worker["keep"] = keep


def _titles_with_lower_senses(name: str) -> set[str]:
    """First pass. The build gives every sense but the first of a headword a
    negative score, so one number per row tells which headwords have several
    senses; the entry itself is only opened for those rows."""
    out: set[str] = set()
    last = None
    for row in loads(_worker["zip"].read(name)):
        if row[4] < 0 and row[6] != last:
            last = row[6]
            out.add(entry_parts(row[5]).get("simplified-term") or row[0])
    return out


def _read_bank(name: str) -> tuple[collections.Counter, list[tuple], list[tuple]]:
    """Second pass: (counts for this bank, senses of the headwords to keep,
    orphan rows of kept headwords as (title, sequence, term))."""
    keep = _worker["keep"]
    stats: collections.Counter = collections.Counter()
    kept: list[tuple] = []
    orphans: list[tuple] = []
    seq_now, terms_now, title_now = None, None, None
    for term, reading, _dt, _rules, score, definitions, seq, _tt in loads(_worker["zip"].read(name)):
        stats["rows"] += 1
        if seq == seq_now:
            if terms_now is not None:
                terms_now.append(term)
            elif title_now in keep:              # still inside the run that opened this bank
                orphans.append((title_now, seq, term))
            continue
        seq_now, terms_now = seq, None
        parts = entry_parts(definitions)
        title = title_now = parts.get("simplified-term") or term
        if term != title:                        # a traditional row whose sense began in the bank before
            if title in keep:
                orphans.append((title, seq, term))
            continue
        summary, label = parts.get("summary", ""), parts.get("sense-label", "")
        stats["senses"] += 1
        if says_nothing(summary, title):
            stats["summaries_that_say_nothing"] += 1
        if _LIST_ITEM_RE.match(summary):
            stats["summaries_starting_mid_list"] += 1
        if _unfinished(summary):
            stats["summaries_cut_inside_a_quote"] += 1
        if not reading:
            stats["senses_without_a_reading"] += 1
        if title in keep:
            terms_now = []
            kept.append((title, seq, reading, score, label, summary, terms_now))
        elif is_work({"title": title, "sense_label": label, "summary": summary}):
            stats["headwords_whose_first_sense_is_a_work"] += 1
    return stats, kept, orphans


def _run(fn, names: list[str], workers: int, zip_path: str, keep: frozenset = frozenset()):
    """fn over every term bank, in this process or in a pool; results in zip order."""
    if workers == 1:
        _init_worker(zip_path, keep)
        try:
            return [fn(n) for n in names]
        finally:
            _worker.pop("zip").close()
            _worker.clear()
    with ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(zip_path, keep)) as pool:
        return list(pool.map(fn, names, chunksize=4))


def audit(zip_path: str, golden: list[dict] | None = None,
          workers: int | None = None) -> tuple[collections.Counter, list[str]]:
    """(counts, failed golden checks as printable lines).

    Two passes, each spread over `workers` processes (default: every core),
    one term bank per task. The first finds the headwords that have several
    senses. The second counts over every sense and sends back only the senses
    of those headwords and of the golden words, tens of thousands out of
    millions, for the checks that compare senses with each other."""
    with zipfile.ZipFile(zip_path) as zf:
        index = loads(zf.read("index.json"))
        names = _bank_names(zf)
    scope = "lexical" if "lexical" in str(index.get("title", "")) else "full"
    golden = [g for g in (golden or []) if g["scope"] in ("", scope)]
    wanted = {g["word"] for g in golden}
    workers = worker_count(workers, len(names))

    several: set[str] = set()
    for found in _run(_titles_with_lower_senses, names, workers, zip_path):
        several |= found

    stats: collections.Counter = collections.Counter()
    senses: dict[tuple, Sense] = {}
    groups: dict[str, list[Sense]] = collections.defaultdict(list)
    orphans: list[tuple] = []
    for bank_stats, kept, bank_orphans in _run(_read_bank, names, workers, zip_path, frozenset(several | wanted)):
        stats.update(bank_stats)
        orphans.extend(bank_orphans)
        for title, seq, reading, score, label, summary, terms in kept:
            sense = senses[title, seq] = Sense(title, seq, reading, score, label, summary, terms)
            groups[title].append(sense)
    for title, seq, term in orphans:
        if (title, seq) in senses:
            senses[title, seq].terms.add(term)

    extra_senses = 0
    for title, group in groups.items():
        if len(group) < 2:
            if is_work(group[0].as_record()):
                stats["headwords_whose_first_sense_is_a_work"] += 1
            continue
        extra_senses += len(group) - 1
        stats["headwords_with_several_senses"] += 1
        top = max(group, key=lambda s: s.score)
        if is_work(top.as_record()):
            stats["headwords_whose_first_sense_is_a_work"] += 1
            if any(not is_work(s.as_record()) for s in group):
                stats["headwords_with_a_work_above_another_sense"] += 1
        stats["senses_of_headwords_with_several"] += len(group)
        stats["of_those_without_a_label"] += sum(1 for s in group if not s.label)
        if len(group) <= 60 and any(similarity(a.summary, b.summary, title) >= SAME_ARTICLE
                                    for i, a in enumerate(group) for b in group[i + 1:]):
            stats["headwords_with_a_repeated_sense"] += 1
    stats["headwords"] = stats["senses"] - extra_senses

    failures = []
    for g in golden:
        problem = _check(g, groups.get(g["word"], []))
        stats["golden_checks"] += 1
        if problem:
            stats["golden_failures"] += 1
            failures.append(f"{g['word']}  {g['check']}" + (f"  {g['value']}" if g["value"] else "")
                            + f"  (line {g['line']}): {problem}")
    stats["scope"] = scope
    return stats, failures


RATES = (  # (label, numerator, denominator)
    ("summaries that say nothing", "summaries_that_say_nothing", "senses"),
    ("summaries starting mid-list", "summaries_starting_mid_list", "senses"),
    ("summaries cut inside a quote", "summaries_cut_inside_a_quote", "senses"),
    ("senses without a reading", "senses_without_a_reading", "senses"),
    ("headwords whose first sense is a work", "headwords_whose_first_sense_is_a_work", "headwords"),
    ("… with another kind of sense below it", "headwords_with_a_work_above_another_sense", "headwords"),
    ("headwords with several senses", "headwords_with_several_senses", "headwords"),
    ("… with a repeated sense", "headwords_with_a_repeated_sense", "headwords_with_several_senses"),
    ("… senses without a label", "of_those_without_a_label", "senses_of_headwords_with_several"),
)


def format_report(stats: dict, failures: list[str]) -> str:
    lines = [f"{stats.get('headwords', 0):,} headwords, {stats.get('senses', 0):,} senses, "
             f"{stats.get('rows', 0):,} rows ({stats.get('scope')})"]
    for label, num, den in RATES:
        n, d = stats.get(num, 0), stats.get(den, 0)
        lines.append(f"  {label:42s} {n:>10,}  {100 * n / d:6.2f}%" if d else f"  {label:42s} {n:>10,}")
    lines.append(f"golden words: {stats.get('golden_checks', 0) - stats.get('golden_failures', 0)} of "
                 f"{stats.get('golden_checks', 0)} checks hold")
    lines.extend("  FAILED  " + f for f in failures)
    return "\n".join(lines)
