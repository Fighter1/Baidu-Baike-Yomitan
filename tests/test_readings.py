"""Readings: CC-CEDICT conversion, article-stated pinyin, and the order of preference."""
import json
import zipfile

import pytest

from baike2yomitan.build import build
from baike2yomitan.readings import (Readings, cedict_to_marks, fit_pinyin, load_cedict_readings,
                                    load_overrides, stated_pinyin, strip_tones, syllable_to_marks)
from baike2yomitan.records import Record, RecordWriter

CEDICT = """\
# CC-CEDICT test extract
著火 着火 [zhao2 huo3] /to catch fire/
單 单 [Shan4] /surname Shan/
單 单 [dan1] /single/
朝陽 朝阳 [Chao2 yang2] /Chaoyang district/
朝陽 朝阳 [zhao1 yang2] /morning sun/
不粘鍋 不粘锅 [bu4 zhan1 guo1] /non-stick pan/
綠 绿 [lu:4] /green/
糊塗 糊涂 [hu2 tu5] /muddled/
人兒 人儿 [ren2 r5] /figurine/
T恤 T恤 [T xu4] /T-shirt/
"""


@pytest.fixture
def cedict_path(tmp_path):
    p = tmp_path / "cedict.txt"
    p.write_text(CEDICT, encoding="utf-8")
    return str(p)


def test_numbered_syllables_to_tone_marks():
    cases = {"zhao2": "zháo", "liu4": "liù", "gui1": "guī", "xiong2": "xióng", "dou1": "dōu",
             "lu:4": "lǜ", "nu:3": "nǚ", "de5": "de", "r5": "r", "Shan4": "shàn", "T": "T", ",": ","}
    for numbered, marked in cases.items():
        assert syllable_to_marks(numbered) == marked
    assert cedict_to_marks("bu4 zhao2 si4 liu4") == "bù zháo sì liù"
    assert strip_tones("bù zháo lǜ") == "bu zhao lü"


def test_cedict_readings_put_proper_nouns_last(cedict_path):
    r = load_cedict_readings(cedict_path)
    assert r["单"] == ["dān", "shàn"]          # the surname is listed first in the file
    assert r["朝阳"] == ["zhāo yáng", "cháo yáng"]
    assert r["糊涂"] == ["hú tu"] and r["人儿"] == ["rén r"] and r["T恤"] == ["T xù"]


def test_fit_pinyin_is_checked_character_by_character():
    assert fit_pinyin("自郐以下", "zì kuài yǐ xià") == "zì kuài yǐ xià"
    assert fit_pinyin("着火", "zháohuǒ") == "zháo huǒ"                 # no spaces in the article
    assert fit_pinyin("睡着", "Shuì Zháo") == "shuì zháo"
    assert fit_pinyin("孤标傲世", "ɡū biāo ào shì") == "gū biāo ào shì"  # IPA look-alike letters
    assert fit_pinyin("桌子", "zhuō zi") == "zhuō zi"                  # 子 has a neutral reading
    assert fit_pinyin("骖风", "can fēng") is None                      # tone missing, 骖 is never neutral
    assert fit_pinyin("丰颐", "fēng") is None                          # too few syllables
    assert fit_pinyin("丰颐", "fēng yí ba") is None                    # too many
    assert fit_pinyin("丰颐", "hello") is None


def test_stated_pinyin_from_summary_and_infobox():
    assert stated_pinyin({"title": "自郐以下", "summary": "自郐以下，汉语成语，拼音是zì kuài yǐ xià，意思是…"}) == "zì kuài yǐ xià"
    assert stated_pinyin({"title": "黍离之悲", "summary": "黍离之悲( shǔ lí zhī bēi)"}) == "shǔ lí zhī bēi"
    # the infobox row wins over a different run in the summary
    rec = {"title": "朝阳", "summary": "朝阳（cháo yáng）是…", "infobox": [["中文名", "朝阳"], ["拼音", "zhāo yáng"]]}
    assert stated_pinyin(rec) == "zhāo yáng"
    assert stated_pinyin({"title": "不着四六", "summary": "别称：四六不懂"}) is None
    assert stated_pinyin({"title": "AI", "summary": "AI is …"}) is None   # not a Chinese title


def test_order_of_preference(cedict_path, tmp_path):
    overrides = tmp_path / "overrides.tsv"
    overrides.write_text("# comment\n\n不着四六\tbù  zháo sì liù\n", encoding="utf-8")
    r = Readings(cedict_path, str(overrides))
    assert r({"title": "不着四六", "summary": "别称：四六不懂"}) == ("bù zháo sì liù", "override")
    assert r({"title": "不粘锅", "summary": "不粘锅是一种锅。"}) == ("bù zhān guō", "cedict")
    # several CC-CEDICT readings: the article's own pinyin picks one …
    assert r({"title": "朝阳", "summary": "朝阳（cháo yáng）是北京的一个区。"}) == ("cháo yáng", "cedict")
    # … otherwise the lower-case (common-noun) reading comes first
    assert r({"title": "单", "summary": "单是一个汉字。"})[0] == "dān"
    assert r({"title": "自郐以下", "summary": "拼音是zì kuài yǐ xià。"}) == ("zì kuài yǐ xià", "article")
    assert r({"title": "红色食品", "summary": "红色食品是指…"}) == ("hóng sè shí pǐn", "pypinyin")
    assert r({"title": "AI", "summary": "x"}) == ("", "none")
    # a CC-CEDICT word inside a longer title lends its reading to the guess
    assert r({"title": "不粘锅炒饭", "summary": "一道菜。"}) == ("bù zhān guō chǎo fàn", "pypinyin")


def test_a_sense_without_pinyin_borrows_it_from_another_sense():
    r = Readings(None, None)
    word = {"title": "解廌冠", "summary": "解廌冠，读音jiě zhì guān，古代法官戴的帽子。"}
    film = {"title": "解廌冠", "summary": "《解廌冠》是一部电影。"}
    assert r(film)[1] == "pypinyin"
    r.observe(word)
    r.observe(film)
    assert r(word) == ("jiě zhì guān", "article")
    assert r(film) == ("jiě zhì guān", "article-shared")


def test_overrides_file_errors(tmp_path):
    assert load_overrides(str(tmp_path / "missing.tsv")) == {}
    bad = tmp_path / "bad.tsv"
    bad.write_text("不着四六 bù zháo sì liù\n", encoding="utf-8")   # a space, not a tab
    with pytest.raises(ValueError, match="title<TAB>reading"):
        load_overrides(str(bad))


def test_build_uses_the_readings(cedict_path, tmp_path):
    with RecordWriter(str(tmp_path / "r.jsonl")) as w:
        for title, summary in (("不粘锅", "不粘锅是一种不会粘底的锅，表面有涂层。"),
                               ("自郐以下", "自郐以下，汉语成语，拼音是zì kuài yǐ xià，比喻其余不值一提。"),
                               ("红色食品", "红色食品是指颜色为红色的食品，如西红柿、红枣等。")):
            w.write(Record(source="563w", title=title, summary=summary, sense_label="", lemma_id=1, tags=[],
                           url="https://baike.baidu.com/view/1.htm", quality_flags=[]))
    out = tmp_path / "d.zip"
    stats = build(str(tmp_path / "r.jsonl"), str(out), pinyin=True, readings_cedict=cedict_path, pinyin_overrides=None)
    with zipfile.ZipFile(out) as zf:
        got = {e[0]: e[1] for e in json.loads(zf.read("term_bank_1.json"))}
    assert got == {"不粘锅": "bù zhān guō", "自郐以下": "zì kuài yǐ xià", "红色食品": "hóng sè shí pǐn"}
    assert (stats["reading:cedict"], stats["reading:article"], stats["reading:pypinyin"]) == (1, 1, 1)
