# baike2yomitan

Build importable [Yomitan](https://github.com/yomidevs/yomitan) dictionaries
(term bank format 3) from offline copies of Baidu Baike.

## Download

Ready-made zips are attached to the
[latest release](https://github.com/Fighter1/Baidu-Baike-Yomitan/releases/latest):

| file | dictionary title | what it is |
|---|---|---|
| `baike-full.zip` | `百度百科 (full)` | every article that survived extraction: 4.9 M senses, 8.8 M entries with the traditional headwords, about 1.4 GB |
| `baike-lexical.zip` | `百度百科 (lexical)` | only titles that are CC-CEDICT headwords, minus people, companies and schools: about 167 k entries, 28 MB |

Import either one in Yomitan → Settings → Dictionaries → *Import*. Both are
self-updating: later releases arrive through *Check for updates*. Entries are
Chinese-Chinese, with pinyin, a traditional and a simplified headword, an
optional infobox table and a link back to the article. The rest of this file
is about building them yourself.

The pipeline is source-agnostic: a thin per-source `extract` step writes a
common JSONL record format, and `merge`, `build` and `validate` know nothing
about where records came from. Adding a new source (Baidu's Baike API, an MDX
file, …) means writing one more extractor that emits the same records.

## Sources

| source | dataset | what we take |
|---|---|---|
| `563w` (primary) | `lars1234/baidu-baike-dataset`, one 16.8 GB JSON Lines file, 5.63 M entries, crawled ~2019 | title, summary (or first paragraph of the first section), tags, `/view/<id>` lemma id |
| `hf` (overlay, optional) | `mohamedah/baidu_baike`, Internet Archive snapshots 2020–2024, 588 k rows, parquet on `refs/convert/parquet` (~2.2 GB) | title, subtitle (= sense label), abstract, lemma id from `/item/<title>/<id>`, archive URL and snapshot date |

Nothing is ever requested from baike.baidu.com. CC-CEDICT (used to pick the
lexical headwords and as the first source of readings) comes from the MDBG
export; the Yomitan JSON schemas come from the yomitan GitHub repo.

## Setup

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux
```

Python 3.11+. On Windows run Python with `-X utf8` (or set `PYTHONUTF8=1`) so
Chinese text prints correctly.

### Downloading the corpora (pinned inputs)

`data/source-inputs.json` pins both datasets to a Hugging Face **commit** and
records every input file's size and SHA-256 (Hugging Face keeps large files in
LFS, whose object id is the file's SHA-256, so the manifest is filled from the
API without downloading). The release tag pins the code; this manifest pins the
data the same way. The 16.8 GB primary cannot be attached to a GitHub release
(2 GiB asset limit), so the pin is a hash, not a copy.

```bash
python -X utf8 -m baike2yomitan inputs download     # fetch exactly the pinned commits into data/raw/ (16.8 GB + 2.2 GB)
```

```bash
python -X utf8 -m baike2yomitan inputs verify       # size + SHA-256 of every local input (~2 min for the primary); --no-hash for size only
```

```bash
python -X utf8 -m baike2yomitan inputs pin          # re-resolve main / refs/convert/parquet to their current commits and rewrite the manifest
```

`extract` (and therefore `all`) verifies its source against the manifest before
streaming it and stops on a mismatch; `--skip-verify` bypasses the check,
`--no-hash` checks sizes only, and a custom `--input` path is never checked.
Run `inputs pin` deliberately when you *want* to move to newer upstream files;
the diff of the manifest then shows what changed. Equivalent manual download:

```python
from huggingface_hub import hf_hub_download
hf_hub_download("lars1234/baidu-baike-dataset", "563w_baidubaike.json", repo_type="dataset",
                revision="<revision from the manifest>", local_dir="data/raw/563w")
```

Do not use `datasets.load_dataset` on the primary file: it would build a second
~17 GB Arrow cache. The extractors stream the raw files.

## Commands

```bash
python -X utf8 -m baike2yomitan extract --source 563w [--limit N] [--max-summary-chars 300]
python -X utf8 -m baike2yomitan extract --source hf   [--limit N]
python -X utf8 -m baike2yomitan merge                 # records.jsonl + records.hf.jsonl → records.merged.jsonl (keyed on title)
python -X utf8 -m baike2yomitan build --records data/records.merged.jsonl --out dist/baike-full.zip [--pinyin] [--traditional s2tw|s2t|s2twp|s2hk] [--infobox] [--sections]
python -X utf8 -m baike2yomitan build --records data/records.merged.jsonl --out dist/baike-lexical.zip --cedict data/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz --exclude-tags 人物,企业,学校
python -X utf8 -m baike2yomitan validate dist/baike-full.zip
python -X utf8 -m baike2yomitan audit dist/baike-full.zip dist/baike-lexical.zip
python -X utf8 -m baike2yomitan smoke dist/baike-full.zip
python -X utf8 -m baike2yomitan sample --records data/records.merged.jsonl -n 20
python -X utf8 -m baike2yomitan all --overlay-hf --pinyin --traditional s2tw --infobox --sections --exclude-tags 人物,企业,学校 --update-url github
python -X utf8 -m baike2yomitan release --dry-run        # upload dist zips as a GitHub release (see below)
```

`all` runs extract (both sources with `--overlay-hf`), merge, both builds,
validation, the smoke test, a 20-record sample and the quality audit; it
downloads CC-CEDICT when the copy on disk is missing or more than a day old,
and exits non-zero when validation,
the smoke test or a golden-word check fails. `--limit N` on `extract` stops
after N input rows for fast iteration. `inputs`, `audit` and `release` are
described in their own sections below.

Leave `--update-url github` off a build you only want to try locally. With it
the zip points at the latest release, and an app that checks for updates
(Hachidori does on import) replaces what you imported with that release
whenever the revisions differ, so a local change never shows. `--no-validate
--no-audit` skip the checks at the end of `all` (about 3 of 40 minutes); keep
them when a rule changed.

### Flags

| flag | step | effect |
|---|---|---|
| `--overlay-hf` | all | also extract the `hf` overlay and merge it into the primary records |
| `--limit N` | extract, all | stop after N input rows (fast iteration) |
| `--skip-verify`, `--no-hash` | extract, all | skip the pinned-input check, or check sizes only |
| `inputs pin\|verify\|download [--source 563w\|hf]` | inputs | maintain `data/source-inputs.json` (see *Downloading the corpora*) |
| `--max-summary-chars N` | extract, all | trim summaries to N chars at the last `。！？；` inside the window (default 300); a hard cut adds `…` |
| `--no-infobox` | extract, all | do not parse `基本信息`/`基本资料` sections into `[key, value]` pairs (they are parsed only at the top of the page, see *Record schema*) |
| `--no-sections` | extract, all | do not keep the `释义`/`出处`/`用法` … sections of pages about words on the record (see *Sections of pages about words*) |
| `--merge-key title\|lemma_id` | merge | how overlay records match primary ones; `title` is the default because the two sources' ids differ (see below) |
| `--pinyin` | build, all | fill Yomitan's reading field (`hóng sè shí pǐn`) from CC-CEDICT, the article's own pinyin, then pypinyin (see *Readings*); off by default, the reading is then empty |
| `--readings-cedict PATH\|none` | build, all | CC-CEDICT export to take readings from; default is the `--cedict` file, else `data/cedict/…` when present |
| `--traditional s2tw\|s2t\|s2twp\|s2hk` | build, all | also emit a traditional-script headword for every entry whose OpenCC conversion differs from the simplified title; same content and sequence number. The modes differ in character forms, see *Showing simplified and traditional together* |
| `--infobox` | build, all | render the extracted infobox pairs (first six) as a two-column table under the summary |
| `--sections` | build, all | show those sections under the summary, each with its label, where they say more than the summary |
| `--cedict PATH` | build, all | `build`: keep only records whose title is a simplified CC-CEDICT headword (the lexical build). `all`: the MDBG export to use instead of `data/cedict/…`; a file named here is downloaded when missing and otherwise used as it is. `all` always builds both zips |
| `--keep-cedict` | all | build with the copy in `data/cedict/` however old it is (to repeat an earlier build, or offline); without it the copy is downloaded again when it is more than a day old |
| `--exclude-tags a,b` | build, all | drop records carrying any of these Baike tags; `all` applies it to the lexical build only. With `--cedict`, a headword CC-CEDICT lists as an ordinary word is only dropped when its text reads as a person, company or school (see *The lexical dictionary's tag filter*) |
| `--title` | build | override the dictionary title stored in `index.json` (default `百度百科 (full)`, or `百度百科 (lexical)` with `--cedict`) |
| `--revision R` | build, all | `index.json` revision; exactly four dot-separated integers (default: today plus `.1`, e.g. `2026.11.09.1`). Anything else is rejected before any work starts |
| `--update-url BASE\|github` | build, all | make the zip self-updating: `index.json` gets `isUpdatable` + `indexUrl`/`downloadUrl` under `BASE`; `github` derives `https://github.com/<owner>/<repo>/releases/latest/download` from the `origin` remote |
| `--repo`, `--tag`, `--target`, `--title`, `--notes-file`, `--draft`, `--dry-run` | release | see *Self-updating dictionaries* below |
| `--no-validate` | build, all | skip the schema check after building |
| `--validate-mode shape\|full` | build, validate, all | `shape` (default) checks each distinct entry structure against the schema once and three whole term banks as a cross-check; `full` runs the schema over every entry (see *Validation*) |
| `--validate-workers N` | build, validate, all | processes for the schema check (default: every core) |
| `--engine auto\|fast\|jsonschema` | validate | fastjsonschema when installed (default), or the reference implementation |
| `--golden PATH`, `--no-golden` | audit | golden words file (default `data/golden_words.tsv`); `--no-golden` reports the rates only |
| `--no-audit`, `--golden PATH` | all | skip the quality audit, or use another golden words file |
| `--schemas-dir` | build, validate, all | where the Yomitan schemas are cached |
| `--seed` | smoke, sample, all | seed for the random smoke/sample picks |
| `--random N` | smoke | how many random headwords to look up besides the fixed ones |

### What gets dropped, and what gets flagged

Every record is either written, or dropped for exactly one reason that is
counted in `data/extract_report.md`. Rules, in the order they are applied:

| reason | source | condition |
|---|---|---|
| `dup_lemma_id` | 563w | a `/view/<id>` that already gave a record (zero padding stripped, so `view/0010` = `view/10`); a row that was dropped does not block a later row with its id |
| `title_empty`, `title_too_long` | both | title empty, or longer than 30 characters. Titles only have their whitespace normalised: the body-text rules below would erase the headwords 编辑, 语音 and 播报 |
| `no_summary_no_sections` | 563w | `summary` is null and the row has no sections |
| `summary_too_short` | 563w | `summary` is present but shorter than 15 characters after cleaning, no section paragraph qualifies as a replacement, and neither keep rule below applies |
| `summary_not_prose` | 563w | `summary` is present and long enough but holds only the title's pinyin or bopomofo, or the title again (`qí fú ㄑㄧˊ ㄈㄨˊ 旗幅`), and the sections have nothing better. A foreign name counts as content: `刺鱼目（Gasterosteiformes）` is kept |
| `summary_too_short_fallback` | 563w | `summary` is null, the first paragraph is under 15 characters, and no paragraph in any section qualifies (the whole page is infobox lines, pinyin or headings) |
| `summary_not_prose_fallback` | 563w | as above, but the first paragraph was long enough and still not usable (an infobox line or no Chinese) |
| `dup_title_summary` | 563w | same title and identical cleaned summary already written |
| `disambiguation_page` | hf | content is a list of at least two different short `<title>：<descriptor>` items (60 characters each at most), not an article. An article whose abstract opens with `<title>：` is not one |
| `summary_too_short[_fallback]` | hf | abstract shorter than 15 characters after cleaning |
| `obfuscated_no_clean_duplicate` | hf | more than 30% of the page's Chinese characters stand alone between spaces (the `总 录 播 报` spacing of the 2023–24 snapshots), the page could not be recovered (see *Letter-spaced snapshots*), and no other snapshot of the same article exists. A run of spaced characters by itself is not enough: tables and name lists have those too |
| `unspaced_title_has_other_snapshot` | hf | a recovered letter-spaced page whose title another snapshot covers |
| `dup:lemma_id` | hf | several snapshots of one article id; the cleanest, then one with a subtitle, then the newest is kept |
| `dup:title_subtitle` | hf | several id-less snapshots with the same title and subtitle |
| `dup:idless_same_summary` | hf | an id-less snapshot (the page `/item/<title>` shows) that has the same subtitle or mostly the same text as an article with an id; the two are folded and that article is marked as the title's default sense |

Overlay articles are told apart by their id. Two articles that share a title
and have no subtitle (亨利五世 the king and 亨利五世 the play) stay two records.

A paragraph *qualifies* as a replacement summary when it is at least 15
characters, says something in Chinese beyond the title and its pinyin, and is
not an infobox line (`作者：…`, `I S B N：…`). A line is not an infobox line
when its colon is inside brackets (`粉虱科（学名：Aleyrodidae）是…`), follows
the title itself (`陈灿：影视演员，…`), separates digits (`下午3:00`) or
introduces speech (`子曰：“…”`). When the first paragraph fails, the extractor
walks the following paragraphs and sections (up to 40) for the first that
qualifies; the record is flagged `summary_from_section` and, if it was not the
first paragraph, `summary_from_later_paragraph`.

A line whose key says it is the definition (`解释：`, `释义：`, `词义：`,
`含义：`, `定义：`, `【解释】`, also `简介：` and `概述：`) is taken for its
value as soon as it is reached, even when the value is short: on
dictionary-style pages the next long paragraph is a source citation
(鱼游濠上: `解释：表示纵情山水、逍遥遨游。`, then `出处：《庄子集释》…`). The
record is flagged `summary_from_definition_line` (16,860 primary records).

Some articles break a line in the middle of a sentence (板儿砖: `…总不能叫“我开你一砖`
on one line, `头”，所以就说…` on the next). When the chosen paragraph stops
without closing punctuation inside a quote or bracket, and the next line of the
same section closes it, that line is joined back on (up to three lines); the
record is flagged `summary_joined_lines` (919 primary records). Lines that do
not qualify as a summary by themselves are never joined, so the rule only
extends a paragraph and does not change which one is chosen.

Two kinds of summary under 15 characters are kept anyway, as a last resort
when nothing longer exists (both sources; in the primary source the first one
found anywhere in the first 40 paragraphs, not only the first paragraph):

- a **complete short sentence**: at least 6 characters, Chinese, ending in
  `。！？；`, not just the title, not an infobox line — `剌桐城 → 泉州市的别称。`,
  `诸葛壹 → 吴国将领，诸葛谨后代。` (flag `kept_short_sentence`);
- a **别称/别名 infobox line** with a non-empty value — `不着四六 → 别称：四六不懂`
  (flag `kept_alias_line`).

Everything else under 15 characters is dropped: headings (`公司简介`),
pinyin-only lines, repeated titles, `【词目】+title`, and other one-line infobox
stubs (`姓名：…`, `型号：…`). A 14-character description without a sentence
mark is still lost.

Cleaning applied to body text before any of the above: literal `\n`
sequences become line breaks; `[1]`/`[2-3]` citation markers, gallery captions
(`剧照(80张)`), the UI labels 播报/编辑/语音 and the overlay's
`zhua曲子白渡白颗` trailer are removed; whitespace (incl. fullwidth and no-break
spaces) is normalised and single spaces between Chinese characters are
dropped. A caption glued into a sentence is cut from the article title onwards
(`塔围长21.6荆山皇帝陵景色(20张)米` → `塔围长21.6米`); when nothing shows where a
caption would start, the text is left alone (`四种花色（52张）`). A UI label that
is part of the article's own title (语音编辑器) is not removed.

Overlay links keep the characters that mean something in a URL encoded
(`/item/C%23/195147`), so they still lead to the article.

Outputs (figures from a local build of 2026-11-11 with the rules described here, `--pinyin --traditional s2tw --infobox --sections`; release `2026.11.11.8` has them all except the labelled sections, the stripped dictionary-site furniture and the decoded HTML entities):

- `data/records.jsonl` (4.67 M records), `data/records.hf.jsonl` (414 k), `data/records.merged.jsonl` (4.88 M) — one JSON record per sense
- `data/extract_report.md` — drop counts by reason, quality flags, merge counts, heuristics notes
- `data/short_summary_examples.md` — sampled analysis of the under-15-character drops that motivated the paragraph-walking fallback
- `dist/baike-full.zip` — everything that survived extraction: 8.8 M entries (incl. 3.9 M traditional headwords), 883 term banks, ~1.4 GB
- `dist/baike-lexical.zip` — only titles that are simplified CC-CEDICT headwords (107 k records), minus `--exclude-tags 人物,企业,学校` (2,167 dropped, 1,663 kept because they are ordinary words): 167 k entries, 36 MB
- `dist/<name>.index.json` — a copy of each zip's `index.json`, written when `--update-url` is given (see *Self-updating dictionaries*)
- `data/stats/*.json` — the counters behind the report and the release notes, including `audit_<zip>.json`

Each zip holds `index.json`, `styles.css` and `term_bank_N.json` files of
10,000 entries; there is no tag bank, because entries carry no tags.

Wall-clock on this machine (24 cores, also busy with other work at the time):
primary extract 12 min, overlay extract 7 min, merge ~2 min, full
build 13 min with `--pinyin`, lexical build ~2 min; validation of both
zips, the smoke test and the audit together about 4½ min; the whole `all` run
43 min. Before the rules described here the extracts took ~8.5 and ~6 min
and the full build ~10.5 min. Validating the full zip by shape replaces a
whole-schema check that took 13 min on 24 processes and 33 min on 4
(`--validate-mode full` still does that); the audit of both zips takes about
1 min on 24 processes and 2 min for the full zip on 4. Extraction, merge and
build use one core; validation and the audit use all of them.

### Letter-spaced snapshots

Of the 587,819 overlay rows, 50,909 are pages archived in 2023 and 2024 that
come with a space after every character (`解 释 播 报 编 辑 五 岳 ： …`).
They used to be dropped unless an earlier, clean snapshot of the article
existed. The text is every other character of the row, so it can be put back
exactly, but two things stand in the way of using it:

- **These pages have no abstract.** The text starts at the first section, each
  section as `<heading>播报编辑<text>`. A summary is taken from the first
  section whose heading promises an introduction: a definition (`解释`, `定义`,
  `释义`, `成语解释` …) or `…简介`, `…介绍`, `概述`, `概况`, except the
  introduction of somebody else (`作者简介`). What a page says under
  `演艺经历` or `历史沿革` does not tell what the thing is, and such a page
  stays dropped (27,487 rows). A page without section headings is its own
  introduction, unless it opens with a heading that pages with sections use
  for something else (`歌曲歌词`, `所获荣誉`).
- **Baidu Baike injects random characters into the text it serves to
  scrapers**, two to six at a time: `在长欢台沙召开` for 在长沙召开. They come
  from a pool of a few hundred mostly ordinary characters. A passage is
  refused (8,019 rows) when it has Chinese characters inside a Latin word or
  a year (`Wor去乌ld`), or two pool characters side by side that the 2019
  corpus, which has no such junk, never has side by side (`颈遥`). On the
  2019 summaries this test raises a false alarm in 0.4% of them; in 280
  recovered summaries read by hand, one still had injected characters.

The pool (237 characters), the 15,086 pairs that real text has and the
section headings of these pages (2,773) are learned from the corpora and kept
in `baike2yomitan/spaced_snapshots.txt`; `python -m baike2yomitan.junk` learns
them again from `data/raw/overlay` and `data/records.jsonl`.

A recovered page gets the flags `unspaced` and `abstract_fallback`. It is
never used to refresh a 2019 record or as a further sense of a title that has
one, and it is dropped when another snapshot covers its title: it is the
first section of an article, not its abstract. 12,343 such records are
written; they add 4,742 headwords to the full dictionary and 199 to the
lexical one (剔透, 报幕, 完婚, 执导, 坊间, 束手就擒, and the proverb
五岳归来不看山，黄山归来不看岳 that prompted this).

### HTML entities

Both sources carry text that was escaped once too often:
`m&eacute;ngt&oacute;u`, `腓特烈&middot;威廉一世`, `&ldquo;…&rdquo;`,
`马茂德&#8226;加万`. Entities are turned into their characters as the first
step of both extractors, in the title, the summary, the section headings and
the section text, before any other rule sees the text. So a citation mark
written `&#91;2&#93;` is removed like `[2]`, and pinyin written with entities
counts as pinyin: a summary that shows the reading no longer gets a second
one in the info table.

- Until nothing changes, for text escaped several times (`&amp;amp;nbsp;`;
  木村井泓 has an `&` escaped seven times).
- Names Python's table lacks (`&amacron;`, `&ndotblw;` and other
  transliteration letters) and names in capitals (`&NBSP;`) are covered. A
  soft hyphen is removed.
- A semicolon that was made full-width counts for the five names of plain
  HTML and for numbers (`&lt；br&gt；`, `五笔86&amp；98`, `&#8226；`).
- Without any semicolon, `&nbsp` is a space unless a letter follows
  (`占地&nbsp11公顷`). `&amp`, `&lt`, `&gt` and `&quot` in that form are what
  the corpus left of an entity it cut off, mostly one escaped twice at the
  end of a picture caption: `Can&amp` was `Can&amp;#39;t`, `Ch&amp奥松酒庄`
  was `Ch&amp;acirc;teau`. They are removed; only an `&amp` between two
  Latin words is an `&` (`Honey &amp Clover`). In front of a letter nothing
  is touched: `AT&T`, `you&me`.
- Seven names damaged in single articles are read as what they stand for:
  `&bsp;` and `&agmp;` (typing mistakes for `&nbsp;` and `&amp;`),
  `Q&subm;` (the source's own mark for a subscript, shown as `Qm`), and
  `&S226;` and `&O1548;`, which stand where `&#8226;` and `&#61548;` would
  (the dot in `《新序》&S226;杂事第四》`, a list bullet). The last two are a
  guess from the position.
- The corpus cuts some texts in the middle of an entity (`也说“走背字儿&rdqu`).
  Such a stump is removed at the end of a summary or section text. Titles are
  left alone: `you&me` and `m&ms` are names.
- An `&` that starts no entity stays (`AT&T`, `R&D`).

6,971 of 4.88 M records had an entity (12,498 entities, 272 different ones;
6,132 in summaries, 695 in info tables, 239 in sections, 144 in titles).
One record still has something of that shape, and it is text: `上海&ALICE;&蓬莱`.
Five records whose whole summary was a cut-off caption (`海贼波琪&amp英文名：Porche`)
are no longer entries.

### Layout tags and private-use characters

Two more things stand in the 2019 text where characters should, and go the
same way as the entities, in the same first step.

**Tags.** The corpus kept some of the page's layout as text:
`…的实力企业。<br> 吉顺号在云南省…`, `<p> 《三国群星传》是…`,
`耕地1241</SPAN>亩`. In body text (summaries, sections, info tables) these
are taken out; a tag that broke a line leaves a space.

- Only layout tags: `br`, `p`, `div`, `li`, `span`, `strong`, `em`, `font`,
  `sup`, `sub`, `wbr`, `iframe`, `noinclude`, and `a` with an attribute.
  `<a>`, `<b>`, `<i>` and `<u>` only as a pair, because `字母<u>` is a letter.
- An attribute has to be `name=value`: `<A Year Without Rain>` is an album and
  `<li quan>` a reading. `<stdio.h>`, `<math>` and the like are text.
- A text about markup keeps its tags (`以<li>开始</li>结束`): one that says
  `HTML`, `标签`, `元素`, `超文本`, `控件` or `字母` is left alone.
- Titles are left alone.

**Private-use characters.** A character from U+E000 to U+F8FF means something
only in the font or encoding it was typed in, and shows as a box or as
nothing.

- GB 18030-2000 had 80 characters there that have code points of their own
  now: `口眼㖞斜`, `奕䜣`, `芎䓖`, `康䶮`, and the parts `⺮`, `𠂇`, `𢦏`, `龹`
  on pages about characters. These are mapped, in titles too.
- Text pasted from a word processor has the letters of its symbol fonts at
  U+F000 plus their place in the font. Most are list bullets and become a
  space. A few are signs, read as such where the text around them says so:
  `DS≥2.75`, `μC/OS-II`, `100）μm`, `聚α烯烃`, `NF-κB`, `ΔIB`, `阿法根®`,
  `约翰斯·霍普金斯`, the font's own comma.
- Any other one is a character the text has and cannot show. It becomes `□`,
  the usual mark for that: `其上独有云气，□兮直上`. A run of them in front of
  a text goes, and so do two code points seen only between sentences.
- A title loses the ones at its ends (`开元十四年碑`, `铁书刀`) and keeps one
  inside it as it is (a name with a rare character).

A letter-spaced overlay snapshot is put back together before either rule
touches it: with one tag or character less it is no longer every other
character.

311 texts had a layout tag, and 274 body texts and 22 titles a private-use
character. No body text has one now; five titles keep one inside them. Of
the layout tags, 11 are left outside texts about markup: 7 unpaired or
broken ones (`</B>`, `<p zdct3">`) and 4 in texts that say `元素` or `标签`
about something else.

### Sections of pages about words

A Baike page about a word or a 成语 is laid out like a dictionary entry, and
the summary names only part of it. With `--sections` an entry shows, under the
summary, the page's dictionary-style sections, each with a label:

| label | headings it stands for |
|---|---|
| 释义 | `基本解释`, `基本释义` first; else `解释`, `释义`, `词语解释`, `成语解释`, `词义`, `含义`, `词语解析` … |
| 详解 | `详细解释`, `详细释义`, `引证解释`: the senses with their quotations |
| 出处 | `出处`, `成语出处`, `典故出处`, `出自`, `词源`, `语源` |
| 用法 | `用法`, `成语用法`, `语法` |
| 示例 | `示例`, `成语示例`, `运用示例`, `例句`, `造句` |
| 近义词, 反义词 | the same, and `同义词` |
| 辨析 | `辨析`, `成语辨析`, `词语辨析` |

Sections that tell a story (`成语故事`, `典故`) are left to the article, as
are the pronunciation sections: the reading field has that.

- **Only pages about words.** `出处`, `用法`, `语法` and `示例` are also
  headings of pages about a character of a novel, a medicine or a programming
  function. Sections count from the first heading that shows the page to be
  about a word: a section for the meaning or for synonyms, or a heading that
  says so (`成语出处`, `词语注音`). When the summary says it (`…，汉语成语，…`)
  they count from the top.
- **Only the page's own article** (2019 corpus). A row can end with the
  sections of another article, as with the info tables: 智能鞋套机, a machine,
  is followed by the 成语 祸福由人 and showed its synonyms. Sections are read
  up to the first heading the page has had before (`简介` a second time), and
  the heading that shows a word has to be among the first three unless the
  summary says so.
- **From both sources.** The 2019 corpus has the sections as such. An ordinary
  overlay snapshot has them as `<title><heading>编辑 <text>`, a letter-spaced
  one as `<heading>播报编辑<text>`. Overlay sections go through the test for
  injected characters (see *Letter-spaced snapshots*), which the body text of
  2023 snapshots has as well; a section that fails is left out. When the merge
  refreshes a 2019 summary, the sections are joined label by label: the
  snapshot's section where it has one, the 2019 section where it has none
  (the 2022 snapshot of 旁门左道 yields only its antonym; the 2019 meaning,
  source and usage stay).
- **Headings inside a section.** Many pages put the whole entry into one
  section: the `详细解释` of 插足 is `含义 …`, `出处 …`, `示例 …`, one to a
  line, and the `释义` of 海角天涯 runs `发音 hǎi jiǎo tiān yá 释义形容极远的地方…出处唐·白居易…示例宋…`
  together. A heading inside the text starts a part of its own, which is
  shown under its label like a section. Recognised are a line that is nothing
  but a heading word, a heading with a colon or in brackets (`示例：`,
  `【出处】`), words that are only ever headings (`基本解释`, `近义词`), and
  headings the page spaced out to one width (`解 释：`, `出　处`, `近 义 词`).
  In a text that opens with a heading word the plain words (`释义`, `出处`,
  `用法`) head what follows them after a sentence, a space or the reading;
  elsewhere `出处不详` and `解释说` are prose. A part found this way gives way
  to a section of the page with the same label. The headword and its reading
  repeated at the top (`词目：冷汗`, `拼音：lěng hàn`) are left out, a part of
  speech stays as `名词：`, and `典故`, `故事`, `歇后语` and `灯谜` parts are
  not shown. `辨析` sections that hold only `【近义词】…【反义词】…` come out
  as those two lists.
- **Headings with nothing to mark them.** `作谓语、定语；多指婚姻示例但～，一生至一死`
  has its heading glued to the text on both sides, and `示例`, `出处` and
  `用法` are ordinary words too (`出处不详`, `用法近似`, `古文示例`). Such a
  word counts as a heading only where the text around it shows one:
  - `示例`, `例句` and `例子` anywhere in a `用法` text, which is a formula
    (`联合式；作谓语；含贬义`), and after the end of a sentence in any text.
    Not after a sentence on the page of a single character, which lists its
    compounds, each with an example and the next compound behind it; and
    `例子；榜样` is a meaning.
  - In a list of synonyms, `反义词` and whatever shows the list is over
    (`阳春白雪反义词下里巴人成语出处战国·楚·宋玉…`). A list of synonyms has
    no brackets and no colons, so anything of that kind ends it:
    `唇枪舌剑 【使用程度】常用成语`, `瞌睡、小憩 【英文】：doze off`,
    `半途而废 英语翻译：…`, and the words `相关词`, `感情色彩`, `常用程度`,
    `同韵词`, `英文翻译` with or without them. What follows is left out, unless
    the heading names a label: `【相反词】明锐、足智多谋` are antonyms. A
    source mark (`近义词[1] 不可名状`) is no heading, and in front of a list
    nothing ends it: `确数：确数就是准确的数…` and
    `霎时：短时间，一会儿。马上：副词…`, which explain each synonym, are left
    as they are.
  - `示例` and `例句` with a colon or in brackets after any character
    (`正确，合适例句：方法对头，效率就高`, `偏正式 [例句] 水珠儿附着在…`),
    and without either in a meaning when the headword or `～` comes after it
    (`强壮而勇猛；强悍示例粗犷彪悍。`). Not `欧洲书牍示例》` (a title),
    `解释与示例` (a heading of the senses) or `提供示例` (a sentence).
  - `出处` after a sentence when a source follows: a `《book》`, an author
    with a dynasty (`清·李宝嘉`), `语出`, or the first of a numbered list.
    `用法` after a sentence when its formula follows.
  - A heading right after the headword (`插入示例插入词语`,
    `言归于好运用示例西晋·陈寿…`); the headword goes with it when it starts
    a sentence. `铸铁管用法兰固定` is `用` and `法兰`: `用法` needs its formula
    here as well.
  - The compounds `成语出处`, `词语示例` and the like.
  - At the start of a text, the headword with the section's own heading
    again (`垃圾释义 “垃”字从土从立`) is dropped.

  A heading the page spaced out inside brackets (`【释 义】`, `【出 处】`) and
  headings in `『…』` or `〔…〕` are read like the others.
- **Nothing twice.** The record keeps one section per label, at most 200
  characters each (`sections`, see *Record format*). The build leaves out a
  section the summary already says (the same text, or half of its character
  pairs in common), shows only what follows when a section starts with the
  summary, and stops at 700 characters per entry.
- **Not text.** The page of a character lists how it is typed and written
  (`简体部首：月，部外笔画：13`, `五笔86&98:EUJN`, `笔顺编号：…`). The text of
  a section ends where such a list starts (臆, 徘); when the list comes first,
  in the first three lines, the text starts after it (娱); a section that is
  only such a list is skipped. 仓颉 the man and 《仓颉篇》 are not codes. The
  caption of a picture of the character, which the corpus left in the text,
  is taken out (`田字格中的“浩”字`, `田字格 长`, `田字格中的简体字‘过’`,
  `“旦”在米字格中的书写`, and on the page of a single character
  `书法“浩”字`). The
  flattened header of a table of senses is cut off, a line drawn across the
  page (`--------`) is dropped, and a list of 成语 written without anything
  between them is split every four characters.

121,077 records carry sections (90,200 of the 2019 corpus, 44,608 of the
overlay before the merge). After leaving out what the summary says, 76,396
senses of the full dictionary (1.6%) and 29,040 of the lexical one (28%) show
some: 释义 43,948, 出处 26,572, 详解 16,460, 示例 13,320, 用法 5,106, 近义词
4,654, 反义词 2,673, 辨析 1,143. The full zip grows by 20 MB (1.4%), the
lexical one from 28 MB to 36 MB.

Not handled: a meaning that follows `例句：` on later lines goes under 示例;
where a page gives its senses with their quotations under `出处`, they are
shown under that label; and a list that explains each of its synonyms
(`内人：屋内之人的意思。…`) is shown with the explanations.

### Furniture of a dictionary site

Some 2019 articles were pasted from the dictionary site 汉典 with its
furniture: the site's name before and after the definition, and a pointer to
the same word in another of its dictionaries, which the corpus cuts after two
characters. 被褐藏辉 read `汉犹言被褐怀玉。…被褐藏辉。”汉成语词典已有该词条：被褐`.
The pointer (34 pages) and the name are stripped from section text before
cleaning: `汉` or `汉 典` in front of a sentence at the start of a section, and
after the last sentence of a paragraph. A `汉` that is the dynasty of a quoted
author (`汉 蔡邕 《…》`, `汉 郑玄 注：`) or half of a word the corpus spaced
apart (`汉 制`, `汉 朝`) stays. 667 summaries change, 27 of them in the lexical
dictionary. The watermark `咟喥咟萪` (百度百科 in look-alike characters) is
removed wherever it stands.

### Merge semantics

The 2019 crawl's `/view/<id>` numbers and the Internet Archive snapshots'
`/item/<title>/<id>` numbers are **different id spaces** (0 of 90k shared ids
named the same article), so `merge` keys on the **title**.
`--merge-key lemma_id` exists for a future source that genuinely shares ids.
`lemma_id` is only meaningful within one `source`.

A title names several articles (时间 is a physical quantity, a word and a
dozen songs), so sharing a title is not enough to replace the 2019 text with a
newer one. For a title with exactly one primary record, `merge` compares the
texts. *Similarity* is the share of the shorter summary's character bigrams
that the other one has, with the title itself left out.

| decision | when | example |
|---|---|---|
| refresh, `same_text` | the most similar overlay sense shares at least 25% | 时间 against its 物理量 sense: 0.45 |
| refresh, `likely_same` | it shares at least 10%, no other sense comes within half of that, and both are the same kind (not a word against a song). Two biographies must also name the same year | 北京 2019 against 2022: 0.16, the song 0.00 |
| refresh, `weak_primary` | nothing reads alike, but the 2019 text is only a fallback paragraph or a stub, and the overlay has one clear candidate (the sense the id-less URL showed, or the only one that is not a work) that is not a person and does not say much less | 说明: `【英译】[Explain;…]` gives way to the 汉语词汇 sense |
| keep the 2019 record | otherwise | 大学 keeps its article; the documentary film 《大学》 becomes a sense of its own |

Every overlay sense that was not used for a refresh is added as its own
record, except when it repeats a sense already written for the title (half of
its text in common), or when the title already has a primary record and the
sense is unclean (obfuscated or a fallback abstract), a stub, or only the
title's pinyin.

The rules prefer showing an article twice to losing it. When the 2019 text
and a later one have little in common they may still be the same article
rewritten (鸬鹚 2019 and 2022 share 5%), and both are then kept.

### Which sense comes first

Senses of one title are ranked, and the rank is the entry's score:

1. the sense Baike itself shows for the bare title, when a snapshot of
   `/item/<title>` (no id) says which one that is. Having no subtitle, or being
   the only sense captured, is not taken as a sign: `/item/时间/58293344` is a
   film song without a subtitle;
2. the word before other articles, and works last. A sense is the word when
   its subtitle says so (汉语词汇, 汉字, 成语, 词语解释 …); it is a work when its
   subtitle names one (张学友演唱歌曲, 央视纪录片) or its summary opens with the
   title in 《》;
3. a real abstract before a fallback paragraph;
4. the lower article id.

### The lexical dictionary's tag filter

The lexical build leaves out people, companies and schools with
`--exclude-tags 人物,企业,学校`. A Baike tag describes a page with every sense
on it, and the tags are from 2019 while the text may be newer: 潇洒 is tagged
人物 because a web novelist uses the name, 证书 is tagged 学校. So a headword
that CC-CEDICT lists with a lower-case reading (an ordinary word) is dropped
only when the text itself reads as a person (`，男，`, a birth year, a
lifespan) or as a company or school (`有限公司`, `…学校创办于`). Headwords
CC-CEDICT only lists as names (北京大学 [Bei3 jing1 Da4 xue2]) go by the tag.

Known gap: only primary (2019) records carry tags. Records that come from the
overlay alone have none, so the filter never sees them, and a person, company
or school whose article exists only there, or was added there as an extra
sense of a CC-CEDICT headword, stays in the lexical dictionary. Nothing in the
overlay marks such articles; telling them apart would have to rely on the
text of the summary, as the rule above does for ordinary words.

### Record format

```json
{"source": "563w", "title": "李永赋", "sense_label": "云南晋宁县公安局副局长", "lemma_id": 10000022,
 "is_default_sense": null, "summary": "…", "tags": ["人物"], "url": "https://baike.baidu.com/view/10000022.htm",
 "archive_url": null, "snapshot_date": null, "quality_flags": [], "infobox": null, "sections": null}
```

`quality_flags` values: `summary_from_section` (primary had no usable summary
field), `summary_from_later_paragraph` (that replacement was not the first
paragraph of the page), `summary_joined_lines` (that paragraph was put back
together from lines the article broke in mid-sentence),
`summary_from_definition_line` (the value of a `解释：`-style line),
`kept_short_sentence` / `kept_alias_line` (summary is
under 15 characters but was kept by the rules above),
`infobox_below_top_skipped` (the page has an info table further down than its
second section, which was not taken), `abstract_fallback`
(overlay content had no repeated abstract), `unspaced` (the summary is the
introductory section of a letter-spaced 2023–24 snapshot, see *Letter-spaced
snapshots*), `summary_refreshed` (merge replaced
the summary with the overlay's; the flags about how the 2019 summary was found
are removed), `no_lemma_id`.
`is_default_sense` is `true` for the overlay sense that the id-less URL
`/item/<title>` showed, `false` for the title's other senses, and `null` when
no such snapshot exists (and on primary records that were not refreshed).
`sections` is an optional list of `[label, text]` pairs rendered by
`build --sections`, see *Sections of pages about words*.
`infobox` is an optional list of `[key, value]` pairs rendered by `build --infobox`:
the first six `key：value` lines of a `基本信息`/`基本资料` section, taken only
when that section is the first of the page or the second. A row of the primary
corpus can hold several articles of one title one after the other, or end with
the sections of an unrelated page, and nothing in the row marks where one
article stops. Release `2026.11.10.6` therefore showed 余华 the writer with the
sex, birth date and height of a rower of the same name, whose article follows
his in the row. In a sample, about six in ten of the tables found further down
belonged to another article than the summary, so they are all dropped (11,008
records, flag `infobox_below_top_skipped`; the full dictionary goes from
485,480 senses with a table to 474,779). Some of those were the page's own
table. Of such a table only a `拼音`/`读音` row that fits the title character
by character is kept, because that reading is right whichever article the row
stands in (307 senses now show the reading alone).
Of the 3,555 tables that come second on a page with a summary field, about
one in eight (some 470) is also another article's and is still shown.

### Validation

The term bank schema is slow on these entries: about 6 s of CPU per
10,000-entry term bank with `fastjsonschema`, nearly all of it in the
recursive structured-content rules (the reference `jsonschema` package takes
hours). Yet the schema only constrains structure: tag names, the enumerated
style and image values, and the scheme of an `href`. The text of an entry is
free. Millions of entries therefore share a few dozen shapes, and an entry is
valid exactly when its shape is.

`--validate-mode shape` (the default) blanks out what the schema does not
look at (text content, the values under `data`, an `href` past its scheme),
validates each distinct shape once, checks the eight fields of every row with
plain code, and puts the first, middle and last term bank through the whole
schema as a cross-check; a disagreement between the two is reported as an
error. `--validate-mode full` runs the schema over every entry.
`validate --engine jsonschema` forces the reference implementation. Either way
the zip's files are spread over one process per core (`--validate-workers N`
to change that), and progress lines and errors keep the zip's order.

## Importing into Yomitan

Yomitan → Settings → Dictionaries → *Import* → pick `dist/baike-full.zip`
(and/or `dist/baike-lexical.zip`), built locally or downloaded from the
release. Each zip is a separate dictionary with a distinct title,
`百度百科 (full)` and `百度百科 (lexical)`; enable whichever you want in the
dictionary list. The lexical one is a subset of the full one, so enabling both
shows those entries twice. Entries carry no term tags; the dictionary-title
chip Yomitan draws already names the source. Headwords are simplified; with
`--traditional` the same entries are also reachable from traditional-script
text.

An entry shows, top to bottom: the traditional and simplified spellings (with
`--traditional`), the sense label when the article has one, the
summary, the labelled sections of a page about a word (with `--sections`:
`释义`, `详解`, `出处`, `用法`, `示例`, `近义词`, `反义词`, `辨析`), the infobox table
(with `--infobox`, first six rows), and a footer
with the article link, the archive snapshot link and date when the text came
from the overlay, and up to five Baike tags.

### Showing simplified and traditional together

With `--traditional`, the traditional headword is a second term-bank entry
that shares the simplified entry's content, reading and **sequence number**.
Whether Yomitan shows them as one card with two headword chips (`遺民` `遗民`)
or as two separate cards depends on its grouping setting:

Yomitan → Settings → General → *Result grouping mode* → **Group related terms**
(the sequence-based merge mode). The default *Group term-reading pairs* shows
only the spelling that was looked up. `index.json` sets `sequenced: true`, which
the merge mode requires.

If a simplified lookup shows two cards in the default mode (板儿砖, then 板兒磚)
while the traditional lookup shows one, another enabled dictionary is
redirecting the word: Wiktionary-based dictionaries carry entries that mark
板儿砖 as a form of 板兒磚, and Yomitan then looks up the traditional spelling
in every dictionary and finds this one's second entry. Words the other
dictionary does not list (不着四六) are unaffected. To stop it, open that
dictionary's details in Yomitan → Settings → Dictionaries and switch off
*Use deinflections*, or use the merge mode above with this dictionary as the
main dictionary.

With `--pinyin` the reading (`yí mín`) is attached to both spellings; the
traditional headword reuses the reading chosen for the simplified title.

Independently of the grouping mode, every entry built with `--traditional`
opens with both spellings in small boxes, traditional (red) then simplified
(blue), the way 汉语大词典 and other dual-script Yomitan dictionaries do. The
boxes are styled by a `styles.css` inside the zip, which Yomitan applies only
to this dictionary's entries; a title that OpenCC leaves unchanged gets a
single simplified box.

The OpenCC mode decides which traditional spelling is stored, and a lookup
only matches the spelling that is stored:

| mode | 不着四六 | 里面 | 为什么 | 软件 |
|---|---|---|---|---|
| `s2tw` (Taiwan character forms; used for releases) | 不著四六 | 裡面 | 為什麼 | 軟件 |
| `s2t` (OpenCC standard) | 不着四六 | 裏面 | 爲什麼 | 軟件 |
| `s2twp` (Taiwan characters and vocabulary) | 不著四六 | 裡面 | 為什麼 | 軟體 |
| `s2hk` (Hong Kong) | 不着四六 | 裏面 | 為什麼 | 軟件 |

Some characters are a surname in their simplified form and at the same
time the simplified form of another word, and OpenCC converts the other word:
于荣海 → 於榮海, 范英 → 範英, 岳敏君 → 嶽敏君. Nothing in a title says whether it
is a name, so a title that starts with one of these characters (于, 范, 余, 岳,
游, 党, 沈, 胡, 姜, 钟 … 27 in `build.SURNAME_FORMS`) is indexed under both
spellings (於榮海 and 于榮海) with the same content and sequence number. The
entry displays the name form when the summary reads as a biography (`，男，`,
a year of birth) and OpenCC's form otherwise; a dictionary word (a CC-CEDICT
headword) that is not a biography gets no name form at all. An ambiguous character
later in a title (子丑寅卯 → 子醜寅卯) is not handled.

`s2t` keeps 着 for zháo/zhuó/zhe and writes 裏 and 爲, which Taiwanese text
does not use; `s2twp` rewrites words as well, so its headwords stop matching
the article titles. `s2t` also writes 牀, 峯 and 羣 where `s2tw` keeps 床, 峰
and 群, so `s2tw` gives slightly fewer titles a separate traditional headword
(8,809,667 entries in the full zip against 8,817,011). Releases up to
`2026.11.09.3` were built with `s2t`.

### Readings

Neither corpus has a pinyin field, so `--pinyin` assembles the reading per
record from the best source available (`baike2yomitan/readings.py`):

1. `data/pinyin_overrides.tsv` — hand-checked `title<TAB>reading` lines;
2. **CC-CEDICT**, when the title is a CC-CEDICT headword. With several
   readings, the article decides when it states exactly one of them
   (`朝阳（cháo yáng）是北京的一个区`). An article about the word itself lists
   them all, and an article about a single character always does
   (`了（拼音：liǎo、le）`), so those do not decide. Otherwise the one that
   pypinyin's own phrase list gives is taken (`明朝` míng cháo, `教授`
   jiào shòu), asked before CC-CEDICT's words are loaded into pypinyin:
   CC-CEDICT's first lower-case entry is often the rare reading (míng zhāo
   "tomorrow morning", jiāo shòu "to instruct"). Failing both, the first
   lower-case reading; proper-noun readings (`单 [Shan4]`) come last;
3. **the article's own pinyin** — a `拼音`/`读音` infobox row or a run of
   Latin letters in the summary (`拼音是zì kuài yǐ xià`), accepted only
   when it splits into exactly one syllable per character and every
   syllable is a reading that character really has. Dictionary-style pages
   give the pinyin on a line of its own (`【拼音】pī hè cáng huī`); when the
   summary comes from the sections and does not contain it, the extractor
   stores that line as a `拼音` infobox row so it is not lost (被褐藏辉 would
   otherwise be guessed as bèi…);
4. the same, borrowed from another sense of the same title;
5. **pypinyin**, a per-character guess helped by a phrase list. CC-CEDICT's
   words are added to that list, so a longer title containing one
   (`不粘锅炒饭`) inherits its reading, with the reading chosen in 2 for words
   that have several. Latin letters and digits in a title are kept as they
   are (`Linux高级程序设计` → `Linux gāo jí chéng xù shè jì`), the way
   CC-CEDICT writes `K jīn` for K金; punctuation is dropped.

The build statistics count each source (`reading:cedict`,
`reading:article`, `reading:pypinyin`, …). In the full build that is
107 k from CC-CEDICT, 88 k from the articles' own pinyin
(73,039 primary records carry a pinyin line kept for this purpose) and
4.53 M guessed, with 148 k titles that contain no Chinese
character left without a reading. Measured on the records of 2026-11-09,
CC-CEDICT and the articles' pinyin agreed on 96.5 % of the titles that have
both, and the pypinyin guess they replace differed from them about 6 % of the
time (a wrong syllable in roughly 3 %, for example `不粘锅` read `nián`
instead of `zhān`). The remaining titles, mostly names of people, places and
works, still get the guess, so a polyphonic character in such a title can be
wrong; add the word to the overrides file to pin it.

Readings are lower-case, tone-marked syllables separated by spaces. Those
from CC-CEDICT follow its conventions: citation tones (no sandhi on 一/不),
neutral tones unmarked (`yī tā hú tu`) and erhua as a bare `r` (`rén r`).
Without CC-CEDICT (`--readings-cedict none`, or a plain `build` before the
file has been downloaded) source 2 and the phrase help in 5 are skipped; a
`build` that finds no CC-CEDICT file says so.

## Self-updating dictionaries (GitHub Releases)

Yomitan can update a dictionary by itself when its `index.json` carries
`isUpdatable: true`, an `indexUrl` and a `downloadUrl`. *Settings →
Dictionaries → Check for updates* fetches `indexUrl`, compares its `revision`
with the installed one and offers the `downloadUrl` zip when it is newer.
Revisions are compared numerically only when both are dot-separated integers
with the same number of segments, which is why the builder always writes four:
`Y.M.D.N` (`2026.11.09.1` locally; the GitHub Actions build uses the run number
as `N`). `--revision` overrides it and must also have four segments: Yomitan
falls back to a plain string comparison when the segment counts differ, so an
installed `2026.11.9` would never be offered `2026.11.10.5`. The builder, the
command line and the workflow all reject anything else.

GitHub's `…/releases/latest/download/<asset>` URL always points at the newest
non-draft release, so it is a stable target for both fields. The flow:

```bash
python -X utf8 -m baike2yomitan build --records data/records.merged.jsonl --out dist/baike-full.zip --pinyin --traditional s2tw --infobox --sections --update-url github
```

```bash
python -X utf8 -m baike2yomitan release --dry-run
```

```bash
python -X utf8 -m baike2yomitan release
```

`build --update-url github` bakes
`https://github.com/<owner>/<repo>/releases/latest/download/baike-full.index.json`
and `…/baike-full.zip` into the zip (owner/repo from the `origin` remote; or give
any base URL for self-hosting) and writes a sidecar `dist/baike-full.index.json`
with the same content. `release` then, through the `gh` CLI:

1. checks the zips exist and are under GitHub's 2 GiB asset limit;
2. resolves the repository (`--repo owner/name`, else the `origin` remote) and
   requires that the logged-in `gh` account has write access to it and that
   the repository has at least one commit (a release needs a tag);
3. notes whether the repository is private — Yomitan cannot download assets
   from a private repository (it sends no auth header), so auto-update only
   works from a public one;
4. reads each zip's `index.json`, requires the `isUpdatable`/URL fields to
   match that repository (otherwise it tells you the exact `build` command to
   re-run), and regenerates the sidecar from the zip;
5. writes release notes to `dist/<tag>.notes.md` from `data/stats` (entry
   counts, sizes, record counts) and the pinned input commits in
   `data/source-inputs.json`, unless `--notes-file` is given. When an earlier
   release exists, the notes end with a *Changes since `<its tag>`* section:
   - a table of entries, traditional headwords and term banks per zip with the
     difference from the numbers in the earlier release's notes;
   - whether the pinned dataset commits moved;
   - the subject line of every commit since the earlier tag, read from
     GitHub's compare API (up to 40 are listed);
   - a **Full Changelog** link to GitHub's comparison of the two tags.

   A part that cannot be worked out is left out, for example the table when
   the earlier notes were written by hand, or the commit list when the
   commit being released has not been pushed;
6. runs `gh release create <tag> <zips> <sidecars> --latest` (tag defaults to
   `v<revision>`, `--draft` for a draft), or `gh release upload --clobber` plus
   `gh release edit --latest` when the tag already exists. A new tag points at
   `--target` when given. In GitHub Actions that defaults to `GITHUB_SHA`, the
   commit the workflow built; without it GitHub tags whatever the default
   branch is at publish time, which is another commit when something was
   pushed during the build.

`--dry-run` performs every check, prints the `gh` commands it would run and
reports problems as warnings instead of stopping. Users then import the zip
once; later releases reach them through *Check for updates*. The zips built
without `--update-url` are not self-updating and `release` rejects them.

## GitHub Actions

Three workflows under `.github/workflows/`:

| workflow | trigger | what it does |
|---|---|---|
| `tests.yml` | every push to `main`, every pull request | installs requirements on Python 3.11 and 3.12, runs pytest (fixtures only, no corpus), builds a one-entry zip with this repository's update URLs and runs `release --dry-run` on it |
| `upstream-check.yml` | Mondays 06:00 UTC, or manually | runs `inputs pin`; if a dataset commit changed, pushes branch `upstream-inputs` and opens (or refreshes) a pull request with the manifest diff. Downloads nothing |
| `build-release.yml` | manual only (*Actions → Build and release → Run workflow*) | frees runner disk, downloads the pinned corpora, runs `all` with `--update-url github` and revision `UTC-date.run-number`, uploads the reports as an artifact and publishes the release as *latest*, tagged at the commit that was built. Inputs: `publish` (off keeps the zips as a 7-day artifact instead), `skip_validation`, `revision` (four integers) |

Nothing is published unless the build step succeeds, and it fails when
validation, the smoke test or a golden-word check fails. (Until 2026-11-10 the
step piped `all` into `tee` under a shell without `pipefail`, so its exit
status was lost and a build that failed validation would still have been
published. The job now names its shell, which makes Actions run
`bash -eo pipefail`.)

The full build needs roughly 27 GB of disk (16.8 GB primary, 2.2 GB overlay,
6.6 GB of record files, 1.4 GB zip). The three runs of 2026-11-09 took
2 h 02 min, 2 h 29 min and 3 h 32 min on a standard GitHub-hosted runner.
Schema validation of the full zip, then in a single process, was most of
that: 1 h 20 min, 1 h 46 min and 2 h 30 min. The downloads took 2 to 14 min.
Validation now runs on every core of the runner. The first run to do so
(2026-11-10) took 1 h 32 min: downloads 3 min, extraction and merge 19 min,
both builds 12 min, validation 51 min (50 min of it the full zip) and the
smoke test 3 min. Since then validation checks each distinct entry shape
once and `all` ends with a quality audit. The first run with both
(2026-11-10, release `v2026.11.10.6`) took 1 h 00 min: downloads 2 min,
extraction and merge 27 min, both builds 17 min, validation 3½ min (3 min
10 s of it the full zip), the smoke test and the audit together 7½ min, and
publishing under 1 min. Extraction and the builds are slower than in the
run before because of the rules added since; they use one core.
The runner had 145 GB of disk, so the *Free disk space*
step is a safety margin rather than a requirement; the 16.8 GB file cannot be
cached between runs (10 GB cache limit), so every run downloads it again. All
five runs completed without memory problems.

CC-CEDICT is not pinned: every build uses the MDBG export of the day, and the
lexical dictionary and a few readings change with it. A release always
downloads it, because the runner starts with an empty disk. A local `all`
downloads it again when its copy is more than a day old and keeps the old copy
when MDBG cannot be reached or answers with something that is not a complete
export; `--keep-cedict` turns that off. Until 2026-11-10 a local copy was kept
for good, which is why the local figures in this file come from an export of
2026-11-07 (121,612 headwords and 167,014 lexical entries, against 121,633 and
167,052 in `v2026.11.10.6`; the full zips differed in two term banks out of
882, and 玳瑁猫 read dài mài locally because that entry was still wrong).

Both workflows that contact Hugging Face pass the repository secret `HF_TOKEN`
to that step when it is set (*Settings → Secrets and variables → Actions*).
The datasets are public, so the secret is optional: it only replaces the
anonymous rate limit with the higher one for signed-in accounts. A read-only
token is enough.

To publish a new release, run the workflow from the Actions tab or with
`gh workflow run build-release.yml`. Nothing rebuilds automatically: not a
push to `main`, and not a merged upstream-inputs pull request.

The release step uses the workflow's `GITHUB_TOKEN` (`permissions: contents:
write`); the `release` command skips its account-permission probe when it
detects GitHub Actions. Pull requests opened by the upstream check come from
the workflow token, so they do not trigger the tests workflow themselves; the
tests run once the branch is pushed by a person or when the PR is merged.
Opening that pull request needs the repository setting *Settings → Actions →
General → Allow GitHub Actions to create and approve pull requests*, which is
on for this repository since 2026-11-10. In a fork where it is off, the
upstream check fails at that step the first time a dataset actually changes.

## Tests

```bash
python -X utf8 -m pytest -q
```

Fixtures under `tests/fixtures/` are real rows copied from both sources. The
tests need neither corpus nor CC-CEDICT, and the Yomitan schemas they
validate against are committed under `data/schemas/`.

## Quality audit and golden words

The unit tests say whether a rule does what it was written to do. They cannot
say what a user sees for 时间. `audit` reads a built zip and answers that:

```bash
python -X utf8 -m baike2yomitan audit dist/baike-full.zip dist/baike-lexical.zip
```

**Golden words.** `data/golden_words.tsv` holds one fact per line that a past
release got wrong, as `headword<TAB>check<TAB>value<TAB>scope`:

| check | holds when |
|---|---|
| `present` / `absent` | the headword is (not) in the dictionary |
| `reading VALUE` | one of its senses has this reading |
| `first_reading VALUE` | the sense shown first has this reading |
| `first VALUE` | the sense shown first mentions VALUE in its summary or sense label |
| `first_not_work` | the sense shown first is not a song, film, book … |
| `any VALUE` | some sense mentions VALUE |
| `ends VALUE` | the first sense's summary ends with VALUE |
| `traditional VALUE` | the headword is also indexed under this spelling |
| `senses_max N` | it has at most N senses |
| `table_lacks VALUE` | no sense's info table mentions VALUE |
| `section_has VALUE` | some sense shows VALUE in its labelled sections (read as one text, `出处…用法…`) |
| `section_lacks VALUE` | no sense shows VALUE in its labelled sections |
| `summary_lacks VALUE` | no sense's summary contains VALUE |

`scope` is `full`, `lexical`, or empty for both. A check that does not hold is
printed with what was found instead (`明朝  reading  míng cháo: readings
['míng zhāo']`) and makes `audit`, and therefore `all` and the release
workflow, exit non-zero: a release that brings an old mistake back is not
published. Add a line whenever a wrong entry is fixed.

**Rates.** The same pass counts, over every sense: summaries that say nothing
beyond the title and its pinyin, summaries that start at item 2 of a list,
summaries cut inside a quote or bracket, senses without a reading, headwords
whose first sense is a work (and those with another kind of sense below it),
headwords where two senses have half their text in common, and senses of
multi-sense headwords that lack a label. They are printed and saved to
`data/stats/audit_<zip>.json`; nothing fails on a rate.

## License and attribution

The dictionary content is Baidu Baike user-contributed material, taken from the
third-party mirrors `lars1234/baidu-baike-dataset` and `mohamedah/baidu_baike`
on Hugging Face; each entry links back to its Baike article. This repository
contains the converter code and small test fixtures; the built `dist/*.zip`
files are distributed as GitHub release assets.

[CC-CEDICT](https://cc-cedict.org/) is licensed CC BY-SA 4.0. It selects the
headwords of the lexical dictionary, and with `--pinyin` its readings are
copied into the reading field of every entry whose title it lists; the
`attribution` field of `index.json` and the release notes say so. No
CC-CEDICT definitions are included.
