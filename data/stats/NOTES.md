## Source inspection: deviations from the task description

**⚠ The two sources do not share an id space.** The task assumes the overlay's
`/item/<title>/<id>` number equals the primary's `/view/<id>` number. On the
real data **0 of 90,506 shared ids named the same page** (view/153 is 舍利子,
item/…/153 is 头七; view/1000 is 疝气, item/…/1000 is 龙族). A lemma_id merge
would have overwritten ~90k summaries with text about unrelated articles (the
first attempt did: 朱澄 received the summary of 义乌). **The merge therefore
keys on the title** (`merge --merge-key title`, the default; `lemma_id` remains
available for a future source that really shares ids). A primary record is
refreshed only when its title has a single primary sense and the overlay has an
unambiguous default sense (or a single sense) for that title; all other overlay
senses are added as new records. `lemma_id` in a record is only meaningful
within its own `source`.

Checked on the first 1,394 rows of the primary file plus 400 rows at each of six
offsets (5 %, 20 %, 40 %, 60 %, 80 %, 95 %), and on 10,000 + 3,000 overlay rows
from shards 0000 and 0004.

**Primary (`563w_baidubaike.json`)**

- Layout is JSON Lines (one object per line), not an array. The extractor
  detects both and streams either (ijson for an array).
- The file is sorted by the id *as a string*, so all zero-padded ids
  (`view/0010.htm`, `view/006236.htm`, …) sit in the first ~1,400 rows and the
  rest of the file has none. Zero-padding dedupe therefore removes very few rows
  overall (it is still applied).
- `summary` is null for about **half** of all rows (52 % in the mid-file
  samples, 68 % at the head), far more than "nullable" suggests. The
  first-section fallback is the main source of summaries, and those records are
  flagged `summary_from_section`.
- About a third of rows have no `sections` at all; when `summary` is also null
  the row is dropped (`no_summary_no_sections`).
- Many present summaries are not prose: pinyin only (`jī bèi ㄐㄧ ㄅㄟˋ`), the
  title repeated, or a single `key：value` line from a product spec table
  (`连接方式：无线`). These fall under the 15-character rule. **Deviation:** when
  the summary field is present but too short, the extractor looks through the
  sections before dropping (flag `summary_from_section_after_short_summary`).
- **Deviation (second build):** the task's fallback is "first paragraph of
  the first section". On this crawl that paragraph is usually an infobox line
  (`药名：新疆远志`, `I S B N：…`) or a pinyin line, because the first section is
  基本信息/图书信息/重要参数. The extractor now takes the first paragraph anywhere
  on the page (up to 40) that is ≥ 15 chars, contains Chinese and is not a
  `key：value` line (flag `summary_from_later_paragraph`, 1.34 M records). This
  raised the kept primary records from 3.97 M to 4.71 M and replaced ~600 k
  infobox-line summaries that the first build had kept as-is. The 15-char
  `_fallback` drops fell from 941 k to 151 k, plus 70.8 k
  `summary_not_prose_fallback` (first paragraph long enough but infobox/pinyin
  and nothing better on the page). Spot checks: ~70 % of rescued summaries are
  real descriptions; the rest are spec tables without colons
  (`最高车速(km/h)2180-100加速时间7.8`), lyric openings, or stats tables. One
  sampled page (经济法概论) carries the blurb of a different book — a source
  error, not detectable here.
- **Lines broken in mid-sentence (2026-11-10):** section text sometimes has a
  line break inside a sentence (板儿砖: `…总不能叫“我开你一砖` / `头”，所以就说…`),
  so the fallback paragraph stopped in the middle of a quotation. A paragraph
  that qualifies as a summary, stops without closing punctuation inside a
  quote or bracket, and is closed by the next line of the same section now
  gets that line joined on (up to three; flag `summary_joined_lines`, 918
  records, 899 summaries changed and 19 trimmed back to the same text by the
  length cap). No record was gained or lost. A first version also joined lines
  too short to qualify by themselves; that turned dictionary stubs
  (`(2) 〔嗫～〕见“` / `(3) 嗫”。`) and song lines into summaries and was dropped.
  Not covered: breaks outside any quote or bracket, and lines whose
  continuation does not close what was opened. 3,232 section-derived
  summaries ended inside an open quote or bracket before the change.
- Tags are present on only ~6 % of head rows but ~58 % of mid-file rows.
- Summaries contain `[n]` citation markers, non-breaking and fullwidth spaces,
  and occasionally leaked image captions (`钟如标近照钟如标，男…`). Captions of
  the form `…(N张)` are stripped; other caption leaks are not detectable.
- Real sense descriptors as first-section titles (李永赋 → 云南晋宁县公安局副局长)
  are rare: roughly 1–2 % of kept records get a `sense_label`.

**Overlay (`mohamedah/baidu_baike`)**

- Confirmed: `content` = abstract, then the abstract again (the repeat differs
  only in inserted spaces after sentence punctuation), then the body. Found in
  ~80 % of 2020–2023 rows. The detector works on a whitespace-free copy and maps
  the cut back to the original text.
- **Not described in the task:** ~12 % of 2020–2023 rows have *no* abstract at
  all; the content starts directly with a section heading
  (`成龙早年经历编辑 …`, `李佳佳个人经历编辑语音 …`). For these the fallback
  strips the leading `<title><heading>编辑播报|编辑语音|编辑` token and takes text
  up to the first section separator (two spaces) or 400 chars, flagged
  `abstract_fallback`. Such records never refresh a primary summary.
- **Not described in the task:** `语音` is a third UI label (`编辑语音`),
  alongside `播报` and `编辑`. Also a fixed anti-scraping trailer
  `zhua曲子白渡白颗` ends ~26 % of rows; it is stripped.
- **Not described in the task:** some id-less URLs are *disambiguation pages*
  whose content is `李伶：重庆医科大学教授 李伶：原第二炮兵… ` — a list of senses
  with descriptors. They are detected and dropped (`disambiguation_page`).
  (They would be a good future source of sense labels for the primary.)
- Body text (not the abstract) in 2021–2023 snapshots has random junk hanzi
  injected mid-sentence (`饰钻迁嘱洒演郭令`). Abstracts look clean; fallback
  abstracts come from body text and may carry this junk. Not detectable by rule.
- 2024 snapshots are almost all obfuscated (`总 录 播 报 编 辑 …`): 837 of 838
  sampled 2024 rows, 10 % of 2023 rows. The regex `(?:[一-鿿] ){4,}`
  plus a >30 % lone-character share catches them. (Since 2026-11-10 some are
  recovered, see the last section of this file.)
- 28 % of rows have an id-less `base_url`. The `url` column often carries
  `?fromModule=…` and leading-space / quoted title variants; `base_url` is clean.
  The `title` column is already normalised (URL path may contain `"直立人"`,
  `\x0b 上海精神`, or Kangxi-radical lookalikes `⾦陵⼗⼆钗`), so the title column
  is used and the URL only as a fallback.
- Dedupe on (title, subtitle) leaves pairs that are the same page captured
  before and after Baike added subtitles: `(东方早报, None, id 6637501)` and
  `(东方早报, "2003年…报刊", id 6637501)`. **Deviation:** a second dedupe on
  lemma_id folds these (keeping the one with a subtitle), and a third folds an
  id-less subtitle-less record into another sense of the same title when the
  first 20 non-punctuation characters of the abstracts match.

## Smoke test (dist/baike-full.zip)

- 红色食品: exactly 1 entry (zero-padding dedupe worked; its summary was
  refreshed from a 2023 snapshot and carries the overlay subtitle 食品分类).
- 丈夫: **only 1 sense**, not >1 as the task expected. The 2019 crawl has a
  single 丈夫 article (view/6236) and the overlay captured only the word sense,
  so after the title-keyed refresh there is nothing else to show. Its tags
  (台湾/文学作品/陈朱煌导演作品) still come from the film sense, as the task warned.
  Unchanged in the second build.
- 舍利子, 疝气 (2 senses), Θ, 小隐于野大隐于市: present.
- 671 overlay records had a subtitle identical to the title (疝气/疝气); the
  builder no longer renders those as sense labels, and the extractor blanks them.

## Heuristics I was not sure about

1. **Sense-label descriptor test** (`sense.is_descriptor`): a first-section
   title counts as a descriptor only if it is 4–24 chars, has no punctuation,
   does not contain / is not contained in the title, shares ≤50 % of its
   characters with the title, is not a generic heading (exact list + suffix list
   such as 简介/信息/参数), does not start with 主要/特色/所属/…, and ends in an
   entity-type word (教授, 演员, 词语, 电影, 城市, 村, …) or starts with a year.
   Still lets through a few odd ones (`配合全国人大教科文卫委员`, `松景集团`).
2. **Minimum summary length 15.** A 360k-row sample (`data/short_summary_examples.md`)
   showed that rows whose `summary` *field* is short are almost all
   section-less stubs (97 %), while rows with a *null* summary usually open
   with an infobox (基本信息/图书信息/重要参数) or a pinyin line and have real
   prose a paragraph or a section later (54 %). The extractor therefore walks
   the page (up to 40 paragraphs) for the first paragraph that is ≥ 15 chars,
   contains Chinese and is not a `key：value` line (flag
   `summary_from_later_paragraph`). Pages that are nothing but spec lines are
   still dropped. The 15-char floor itself remains blunt (it cannot tell a
   14-char description from a heading). **Third build:** two exceptions were
   added at the user's request. A complete short sentence (≥ 6 chars, ends in
   。！？；, not the title, not an infobox line: `泉州市的别称。`) and a
   别称/别名 infobox line (`别称：四六不懂`) are kept when nothing longer exists
   (flags `kept_short_sentence`, `kept_alias_line`). Full run: 11,075 short
   sentences and 154 alias lines kept in the primary, 4,020 short sentences in
   the overlay (`艓，是一个汉语汉字。`). The alias rule also fires on long
   `别名：…` lists that the first-paragraph walk had rejected as infobox lines,
   which is why some kept alias summaries are far longer than 15 chars. Junk
   that slips through: questions (`什么是边码？`) and slogans (`迪诺英语，专业十年！`). Not kept: other infobox keys (`姓名：…`) and
   sentence-less fragments (`中共松阳县委常委、统战部部长`).
3. **Overlay default sense**: an id-less URL marks the default sense; when both
   an id-less row *with* a subtitle and an id'd row *without* one exist
   (`β衰变`), the id-less one wins per the rule, which may be wrong.
4. **Clean = no `obfuscated` and no `abstract_fallback` flag** for merge
   refreshes. Fallback abstracts can carry injected junk hanzi.
5. **Title-keyed refresh assumes the 2019 article of a title is its current
   default sense.** The 2019 crawl has essentially one entry per title
   (232 multi-sense titles out of 3.97 M), so when the overlay's default sense
   has since changed, the refreshed summary describes a different sense than the
   2019 one did. Overlay senses that cannot be matched unambiguously are added
   as extra records, which can leave a 2019 and a 2022 version of one sense side
   by side (`added_extra_sense_of_known_title`).
6. **Sense ranking**: `is_default_sense` (overlay only) first, then "has a real
   summary", then lower lemma_id. Score = −rank, so the top sense of each title
   has score 0 and others are negative.
7. **CJK whitespace**: a single space between two CJK characters, or next to
   CJK punctuation, is removed; spaces around Latin words are kept.
8. **Infobox**: only `基本信息`/`基本资料` sections whose body has ≥2 `key：value`
   lines; many such sections in this crawl are one long `k: v; k: v` line and
   yield nothing. Since 2026-11-10 only when the section is the first or the
   second of the page (see the last section of this file).
9. **Tag bank**: the only tag is `百科` (category `name`). Baike tags are shown
   as muted footer text (first five) and used only for `--exclude-tags`.
10. **Traditional headwords** via OpenCC `s2t` by default (`s2twp` available);
    only emitted when the converted title differs.


## Review of 2026-11-10: what was wrong in release 2026.11.10.4 and what changed

Four read-only review passes over the code and the published zips found the
problems below; each was reproduced before it was fixed. Counts are from the
local build of 2026-11-10 unless a line says otherwise.

**Extraction, primary**

- A summary field was accepted on length alone. A field that holds only the
  title's pinyin or bopomofo, or the title again, now gives way to the
  sections (2,170 records) or, when the page has nothing else, is dropped
  (`summary_not_prose`, 73,731 records). Those records used to be entries that
  showed the pinyin a second time as their definition. A foreign name counts as
  content (刺鱼目（Gasterosteiformes）), and so do accents in capitalised words
  (José Martí): an earlier version of the rule took those for pinyin.
- Tried and withdrawn: replacing a summary field that looks like one
  `key：value` line by a section paragraph. On real rows it made about as many
  entries worse as better (the abstract 粉虱科（学名：Aleyrodidae）是… was
  thrown away), so such a field is kept as before.
- `解释：`/`释义：`/`【解释】`-style lines are now taken for their value
  (16,860 records; 鱼游濠上, 片刻). They used to be skipped as infobox lines,
  after which the next long paragraph, a source citation, became the summary.
- A colon inside brackets, after the title itself, between digits or before
  reported speech no longer makes a line an infobox line. This alone brought
  back about 20,000 pages whose only prose opens `《X：Y》…`
  (`summary_not_prose_fallback` 50,662, was 70,771).
- The under-15-character keep rules look at the whole page, not only the first
  paragraph (16,262 short sentences kept, was 11,075).
- Titles are no longer cleaned like body text: 编辑, 语音 and 播报 had been
  erased as interface labels, and 语音编辑器 had become 器.
- A gallery caption inside a sentence is cut at the article title instead of
  taking the twelve characters before every `(N张)`.
- The page's own pinyin line is kept as a `拼音` infobox row when the summary
  comes from the sections and does not contain it (73,039 records). Without
  it the definition-line rule above would have cost idioms their stated
  reading (被褐藏辉 guessed as bèi… instead of pī…).

**Extraction, overlay** (401,223 records, was 382,823)

- Snapshots were folded by (title, subtitle), which merged different articles
  that share a title and have no subtitle (亨利五世 the king and the play; two
  people called 李佳军 in the test fixture). They are now folded by article id.
- The four-spaced-characters shortcut flagged tables and name lists as garbled
  text; the test is now the share of lone characters only.
- An article whose abstract opens `<title>：` was dropped as a sense list
  (七十子). `drop:disambiguation_page` 26,779, was 29,741.
- `is_default_sense` used to be true for any sense without a subtitle and for
  any lone sense. That marked new song and film pages as the main sense of
  common words. It is now true only for the sense an id-less snapshot shows
  (142,457 records, was 340,016).
- Links keep `#`, `%`, `?` and `/` percent-encoded.

**Merge** (heuristic 5 below is superseded)

- The refresh compared nothing: the overlay's "default" sense replaced the 2019
  article of the same title. 大学 became a documentary film, 北京 a song. Texts
  are now compared (see README, *Merge semantics*): 178,963 refreshes
  (143,584 same text, 23,525 likely the same article, 11,854 a weak 2019 text
  replaced), 51,944 primary records kept as they were
  (20,485 because the overlay is about something else).
- 2,757 overlay senses that repeat one already written are not added again, and
  20,956 fallback abstracts, stubs and pinyin-only abstracts are not added next to an
  existing article.
- Cost of being careful: an article whose text was rewritten between 2019 and
  2022 beyond recognition is kept in both versions.

**Ranking** (heuristic 6 below is superseded): default sense, then the word
before other articles and works last, then a real abstract, then the lower id.

**Readings**

- CC-CEDICT words with several readings took CC-CEDICT's first lower-case one,
  often the rare one (明朝 míng zhāo, 教授 jiāo shòu), because the pypinyin
  guess that should have chosen had been overwritten by loading that very
  reading as a phrase. The guess is now taken before the phrases are loaded.
- An article that lists several readings of its title, as articles about
  single characters do, no longer decides (了 was read liǎo, 通 tòng).
- Guessed readings keep Latin letters and digits.
- Against release 2026.11.10.4 the first sense's reading changed for 433,960
  of 4.76 M shared headwords; for 416,582 only letters or digits were added.
  The other 17,378 are mostly corrections of the kind above (教学 jiào xué,
  重点 zhòng diǎn, 外传 wài zhuàn); some are debatable, for example 朝阳 in the
  names of companies in 朝阳市 is now zhāo yáng.

**Traditional headwords**: titles that start with a surname character OpenCC
converts (于, 范, 余, 岳 …) are indexed under both spellings.

**Lexical tag filter**: 1,662 records of ordinary words that carry a 人物/企业/学校
tag are kept (2,167 are still dropped).

**Effect on the zips**, against release 2026.11.10.4:

| | full, before | full, now | lexical, before | lexical, now |
|---|---:|---:|---:|---:|
| headwords | 4,832,500 | 4,795,093 | 81,377 | 81,843 |
| senses | 4,888,775 | 4,872,771 | 98,929 | 104,436 |
| entries (rows) | 8,809,667 | 8,813,748 | 159,636 | 167,014 |

Full: 69,446 headwords gone (pinyin-only pages), 32,039 new. Lexical: 1,969
gone, 2,435 new. The lexical headwords that went include common idioms whose
Baike page holds nothing but the pinyin (老调重弹, 有朝一日, 独辟蹊径).

**Audit of the new zips** (`audit`): headwords with a repeated sense 125 (full)
and 0 (lexical); headwords whose first sense is a work with another kind of
sense below it 2,196 and 62; summaries that say nothing 386 and
71; summaries starting at item 2 of a list 14,403 and 396; summaries cut inside
a quote or bracket 8,149 and 129. The last two are not addressed.

**Not fixed**: an ambiguous character later in a title (子丑寅卯 → 子醜寅卯);
overlay records have no tags, so the lexical tag filter never sees them;
summaries that start in the middle of a numbered list.

## After release 2026.11.10.6: info tables of another article

余华 the writer was shown with 性别 女, 出生日期 1981-01-19, 身高 175cm. The
2019 row for that title has twelve sections: ten of the writer's article, then
`基本信息` and `主要成绩` of a rower of the same name. The extractor took the
first `基本信息` section anywhere on the page. 时间 (the physical quantity with
a film's table) and 张衡 had the same fault.

Where the 432,606 parseable info sections sit, and how often a random sample
of 30 showed a table that does not belong to the summary:

| position of the section | rows | wrong in sample |
|---|---:|---:|
| first | 394,831 | not sampled |
| second, no summary field | 23,141 | 0 of 30 |
| second, with summary field | 3,555 | 4 of 30 |
| third or later, no summary field | 4,411 | 12 of 30 |
| third or later, with summary field | 6,668 | 22 of 30 |

Nothing in a row marks where one article ends, and a rule on the table's name
row did not separate the cases (keys such as 英文名称 look like a different
name). So the rule is positional: a table is taken from the first or second
section only. 11,008 records carry the flag `infobox_below_top_skipped`.

Effect on the full zip, against release 2026.11.10.6: 485,480 senses had a
table, 474,779 have one; 10,701 tables are gone and none was added. Of 40
dropped tables drawn at random, 26 belonged to another article (a housing
estate under a textbook, a mini-game under a village, a film under a word).
The 14 others were the page's own table (book data under a book), which is the
price of the rule.

A dropped table keeps a `拼音`/`读音` row that fits the title character by
character (307 senses now show only that row). Without it five readings became
worse in a first build (黄裳 huáng shang for huáng cháng, 淇奥 qí ào for
qí yù). Keeping every such row was wrong as well: 日本财团 then showed
拼音名 Baihua Huoxue Dieda Gao, from a medicine's page at the end of its row.
`reading:article` is 86,541 (was 86,537) and `pinyin_line_kept` 73,070 (was
73,039), because a page's own pinyin line now takes the place of a dropped
row. Three readings differ from the release: 一咕噜 is yī gū lū, from the
page's pinyin line, where it was yī gū lu; 玳瑁猫 and 英国玳瑁猫 (dài mài)
come from the CC-CEDICT export on this machine, which has that entry wrong,
while the release was built with a newer export.

**Not fixed**: about 470 tables in second place under a summary field that
belong to another article (4 of 30 in the sample); the tags of such a row are
mixed in the same way.

Golden words: 余华 `table_lacks` 1981-01-19 and 175cm, 时间 `table_lacks`
影片名称, 张衡 `table_lacks` 片名. 44 of 44 checks hold on the full zip, 35 of 35
on the lexical one; the audit rates are unchanged.

## After release 2026.11.10.7: letter-spaced snapshots

五岳归来不看山，黄山归来不看岳 is in the overlay, as one snapshot of
2024-01-23, and was not in the dictionary: the snapshot is letter-spaced, no
clean one exists, and the 2019 corpus has no row of that title (its id 9842880
is a laptop there, the two sources not sharing ids).

What the 50,909 letter-spaced rows are (43,618 of 2024, 7,268 of 2023, 53
older):

- All but 30 have a space after every character, a space of the text
  included. Every other character is the text.
- Only 10 have the abstract that other snapshots repeat at the start. The
  rest begin at the first section; 43,547 open with a heading and `播报编辑`.
- About a third have injected characters. They were not detectable "by rule"
  in the first review; they are by where they stand. Inside Latin words and
  years (`Wor去乌ld`, 20,457 characters in these rows) a Chinese character can
  only have been injected, which gives the pool: 237 characters after leaving
  out those that ordinary text between Latin letters explains. Two pool
  characters side by side are then compared with the 2019 summaries, where
  15,086 of the 56,169 possible pairs occur twice or more.

Measured before the rule went into the extractor:

| | |
|---|---:|
| false alarms of the pair test on 467,423 held-out 2019 summaries | 0.28% |
| false alarms of the inside-a-word test on the same | 0.11% |
| first sections refused for injected characters | 16,449 of 47,435 |
| visible junk in 130 + 150 accepted summaries read by hand | 1 (兽人种) |

Tried and dropped: a score over single characters (fooled by a topic word
that repeats, 函数 or 干燥, and blind to a page with one injected run);
counting rare pool characters (too few of them in a short definition).

Which section is used: the first whose heading ends in 解释, 释义, 定义,
含义, 涵义, 词义, 概念, 意思, 简介, 介绍, 概述, 概况, 简述 or 概要, unless it
starts with 作者, 编者, 译者, 主编, 导演, 演员, 主演, 嘉宾, 角色, 主创, 团队,
成员, 选手, 出品 or 制作. First headings of the pages that would add a title:
(none) 3,384, 剧情简介 1,130, 演艺经历 830, 历史沿革 710, 简介 575,
内容简介 504, 人物经历 406, 解释 364, 定义 322. The sections on a career or
a history were left out on purpose: `2023年，出演…` is no definition.

Result of the extraction: 27,487 rows without an introduction, 8,019 with
injected characters, 30 not laid out as every other character; 12,343 records
written with the flag `unspaced`, 1,552 dropped because another snapshot
covers the title; `obfuscated_no_clean_duplicate` 31,627 (was 45,704);
overlay records 413,566 (was 401,223).

Effect on the zips, against release 2026.11.10.7:

| | full, before | full, now | lexical, before | lexical, now |
|---|---:|---:|---:|---:|
| headwords | 4,795,093 | 4,799,835 | 81,861 | 82,060 |
| senses | 4,872,771 | 4,877,527 | 104,457 | 104,656 |
| entries (rows) | 8,813,748 | 8,822,185 | 167,052 | 167,374 |

No headword and no sense of the lexical dictionary changed or went; 199 were
added. Golden words: 48 of 48 (full) and 35 of 35 (lexical). Senses without a
reading 148,266 (was 148,116), summaries cut inside a quote 8,154 (was 8,149).

**Not fixed**: a recovered summary can open with a picture caption that does
not repeat the title (航母庞大的航母是…), or be the plot of a film that
shares its title with a word (三分之一, 白头山); pages whose only sections are
a career or a history are not used although their first sentence often says
who the person is; the injected characters in the body text of ordinary
2021–2023 snapshots (fallback abstracts) are not tested.

## After release 2026.11.11.8: pasted furniture and labelled sections

被褐藏辉 looked cut off: `…被褐藏辉。”汉成语词典已有该词条：被褐`. The article
has no summary field, so the entry is its `词语解析` section, which was pasted
from 汉典 with the site's name (`汉`, `汉 典`) around the definition and a
pointer to its 成语 dictionary that the corpus itself cuts after two characters.

Measured over the 5,634,898 rows of the 2019 corpus:

| | |
|---|---:|
| pages with `成语词典已有该词条` | 34 |
| … of which had it in the summary | 18 |
| sections that open with a lone `汉` before a space | 1,039 |
| pages with a lone `汉` before text anywhere | 10,621 |

Most lone `汉` are the dynasty of a quoted author, so the name is only
stripped at the start of a section in front of a sentence, and at the end of
a paragraph after closing punctuation. The first run left 140 summaries
ending in `。”汉`; the end rule was added for those. Result: 667 summaries
changed (18 pointer, the rest the name), 27 in the lexical dictionary, no
headword gained or lost there.

**Sections.** Headings were counted on all pages and on the 93,907 pages
whose title is a CC-CEDICT headword: 184,236 pages have a heading with 解释,
释义, 出处, 用法, 示例, 近义, 辨析 and the like, 27,542 of the CC-CEDICT pages.
The commonest: 词语解释 26,771, 释义 16,796, 详细解释 10,107, 解释 8,282,
出处 7,699, 基本解释 6,581, 词语释义 5,630, 示例 4,117, 详细释义 3,731,
用法 2,827, 引证解释 2,293, 近义词 2,236, 成语出处 1,730.

Left out on purpose: `来源` (3,514, mostly medicines and plant varieties),
`用法用量` (12,180, medicines), `名词解释` (3,155, concepts, where the summary
says the same), `例子` (957, any kind of page), `典故` and the `…故事`
headings (median length 360 to 1,100 characters).

What reading samples of the first run changed:

- `出处`, `用法`, `语法`, `示例` and `辨析` stand on pages that are not about
  words (古魔塔珈, a character of a novel; glCallList; 虎杖叶胶囊), so a page
  has to show that it is about a word, and sections count from that heading.
- 智能鞋套机 showed the synonyms of 祸福由人, the article that follows it in
  the row. The second article starts with `简介`, a heading the page already
  had; sections stop there, and the proof has to be within the first three
  headings. Records with sections in the 2019 corpus: 93,927 before these two
  rules, 90,404 after.
- A section of input codes under the heading `释义` (砂, 单行道), the header
  `词性释义英译例句例词` of a flattened table (圉, 盾, 伏), a synonym list
  without separators, an overlay `成语用法` section holding only examples.
- The watermark `咟喥咟萪` at the end of an example (赛事).

Effect on the zips, against release 2026.11.11.8:

| | full, before | full, now | lexical, before | lexical, now |
|---|---:|---:|---:|---:|
| headwords | 4,799,835 | 4,799,836 | 82,060 | 82,060 |
| senses | 4,877,527 | 4,877,528 | 104,656 | 104,656 |
| senses showing sections | 0 | 73,169 | 0 | 27,504 |
| zip bytes | 1,412,370,266 | 1,430,709,131 | 28,032,676 | 35,369,154 |

Golden words: 55 of 55 (full) and 35 of 35 (lexical). Senses without a
reading 148,266 and summaries cut inside a quote 8,154, both unchanged.

**Not fixed**: on a page without a summary field whose meaning is under 15
characters, the summary is still the first long paragraph, often an example
or a quotation, and the meaning now stands under 释义 below it (避君三舍,
壁垒森严); a section can be mislabelled by the article itself (老骥伏枥，志在千里
has synonyms under 辨析; the common case, a 辨析 section that holds only
`【近义词】…【反义词】…`, is handled below); a word page whose dictionary
sections come after its third heading, with a summary that does not call it a
word, shows none. Two items that stood here are done in the next section:
sub-headings inside a section (`含义 1. 谓兴建高楼`) and raw HTML entities in
the 2019 text (`m&eacute;ngt&oacute;u`).

## Local build of 2026-11-11: HTML entities, headings inside a section

**Entities.** Measured on the merged records of the build above: 6,971 of
4,877,528 records had an entity (12,498 entities, 272 different names; 6,132
in summaries, 695 in info tables, 239 in sections, 144 in titles), 172 of
them under a CC-CEDICT headword. The 2019 corpus has them as text; the overlay
has almost none. Both extractors now decode them first, up to four passes,
with a table for the transliteration names Python lacks. Decoding first is
what makes the other rules see the text: 42,213 rows of the 2019 corpus had
one somewhere, far more than the records that showed one, because citation
marks (`&#91;2&#93;`) and spaces (`&nbsp;`) are then removed by the rules for
those.

Left: 8 records (`&O1548;`, `&subs;`, `&bsp;`, `&ALICE;`, one text escaped
seven times) and 177 names without a semicolon (`&amp` 135, `&nbsp` before a
digit 29, `&lt`/`&gt`/`&quot` 13). Decoding those would also change `AT&T`-like
text, so they stay.

**Headings inside a section.** Measured on the same records with a list of
heading words (解释, 释义, 出处, 用法, 示例, 例句, 近义词, 反义词, 辨析, 拼音
…): 5,647 section texts started with one and 3,992 had one after a sentence
end, 8,644 records in all. Two layouts make up most of it: one heading to a
line inside a `详细解释` section (插足), and a whole entry run together under
`释义` (海角天涯: `发音 … 释义形容极远的地方…出处唐·白居易…示例宋…`). The
text is now split at such headings and each part shown under its label.

What the first two rebuilds showed, and what changed for it:

- The merge replaced all 2019 sections with the snapshot's whenever a refresh
  had any. That was wrong before this change too, but it became visible when
  snapshots began to yield single parts: 旁门左道 kept only its antonym,
  三令五申 lost five of seven. Sections are now joined label by label.
- The rule for input codes looked at the first 80 characters. Once the
  headword and reading at the top were removed, the codes of many character
  pages moved into that window and the meaning in front of them was dropped
  (臆, 徘, 伪, 媒). The text now ends where the codes begin; when the codes
  come first, within three lines, it starts after them (娱).
- A `【词义】` or `基本词义` heading inside a `详细解释` section moved its text
  to a part that then lost to the page's own 释义 section (惝, 乖剌). Such a
  heading no longer moves text out of 详解.
- A section holding only the words `基本解释` became a part (平手, about 45
  more per 500,000 rows). A lone heading word is used as text only when it
  has two characters.
- `词性：形容词` took the meaning after it along into 用法 (炽痛, 晨钟暮鼓).
  Only the kind of word goes there.

Against the build above (merged records and zips):

| | before | now |
|---|---:|---:|
| records with an entity | 6,971 | 8 |
| … under a CC-CEDICT headword | 172 | 1 |
| section texts with a stray heading word (records) | 8,644 | 3,520 |
| records with sections | 119,788 | 120,991 |
| senses showing sections, full | 73,169 | 76,251 |
| senses showing sections, lexical | 27,504 | 28,971 |
| shown 释义 | 41,580 | 43,951 |
| shown 出处 | 25,596 | 26,448 |
| shown 详解 | 12,649 | 16,461 |
| shown 示例 | 7,279 | 11,447 |
| shown 用法 | 4,117 | 4,968 |
| shown 近义词 | 1,858 | 4,587 |
| shown 反义词 | 754 | 2,597 |
| shown 辨析 | 2,529 | 1,149 |
| headwords, full | 4,799,836 | 4,799,728 |
| senses, full | 4,877,528 | 4,877,418 |
| headwords, lexical | 82,060 | 82,060 |
| senses, lexical | 104,656 | 104,657 |
| zip bytes, full | 1,430,709,131 | 1,432,192,152 |
| zip bytes, lexical | 35,369,154 | 36,412,843 |

In the samples read, the 3,520 that remain are mostly prose (`出处不详`,
`解释说`) and headings glued between two characters. 辨析 fell because most
of the 1,614 sections that lost the label held only synonym and antonym
lists, which now stand under those labels. Sections changed on 25,350
records, 14,594 of them under a CC-CEDICT headword. 250 headwords
went and 142 came, all in the full dictionary but one each way (蒙塾 gone,
栗腹䴓 new): titles whose entity is now a character (140), and summaries that
passed or failed the length rule once `&nbsp;` and citation marks were gone.
6,036 summaries changed, 6,015 of them because of an entity.

Labels lost against the build above, by what happened to the old text:

| label | moved to another label | was not text | gone |
|---|---:|---:|---:|
| 释义 | 38 | 320 | 90 |
| 详解 | 12 | 240 | 27 |
| 用法 | 112 | | 42 |
| 辨析 | 674 | | 940 |
| 出处, 示例, 近义词, 反义词 | 12 | | 14 |

"Was not text" is `词目：仲秋 拼音：zhòngqiū 基本解释` and the like. The 940
辨析 are the synonym lists again, reformatted so the old text is not found
whole. Of the 90 释义 many were lists of strokes and codes; the real
losses are rare characters whose whole meaning is shorter than six characters
or has no punctuation before the codes (僼, 嚠, 嬚), where the summary says
it, and pages where the meaning follows a `田字格中的“长”字` caption (长, 浩,
伍, 娴).

Golden words: 72 of 72 (full) and 50 of 50 (lexical), with 17 lines added
for these rules. Senses without a reading 148,224 (148,266 before),
summaries cut inside a quote 8,160 (8,154).

**Not fixed**: a heading glued between two characters (`多指婚姻示例但～`); a
meaning that follows `例句：` on later lines goes under 示例 (理智); the
`田字格` caption above; the headword and reading at the start of some 详解
texts (`老骥伏枥lǎo jì fú lì …`); a 词性 heading followed by a description
instead of a kind of word stays in the text (晨钟暮鼓); summaries that open
with `释义` or `出处` (海角天涯, 一无所获) — the summary rules were not
touched; and, as before, an example or quotation as the summary where the
meaning is short (about 1,150 entries have the meaning under 释义 instead).
The first and the third of these, and the entities left over above, are done
in the next section.

## Second local build of 2026-11-11: leftover entities, captions, glued headings

**Entities.** The 8 records and 177 bare names left above, looked at one by
one:

- `MM(MCJH&amp;amp;amp;TWJ)` was an `&` escaped seven times; the decoder
  stopped after four passes. It now runs until nothing changes.
- 135 bare `&amp` and 3 `&quot`: read in context, nearly all are what the
  corpus left of an entity it cut off, usually one escaped twice at the end
  of a picture caption that then runs into the summary (`Can&amp` of
  `Can&amp;#39;t`, `Ch&amp奥松酒庄` of `Ch&amp;acirc;teau`, `汤米&amp汤米是一位…`).
  Turning them into `&` would leave a stray `&`, so they are removed; only
  between two Latin words is it an `&` (`Honey &amp Clover`).
- 29 `&nbsp` in front of a digit (`占地&nbsp11公顷`) are spaces now.
- 10 with a full-width semicolon (`&lt；br&gt；`, `五笔86&amp；98`).
- `&bsp;`, `&agmp;`, `&subm;`/`&subs;`/`&sub1;`, `&S226;` (two articles, both
  where a middle dot belongs), `&O1548;`: a small table. The last two are a
  guess.

Applied to the records of the build above, 160 change. After the rebuild one
record has an entity-shaped piece left (`上海&ALICE;&蓬莱`, text) and no bare
name is left. Six 2019 records are gone, five of them headwords: their whole
summary was such a caption stump (`海贼波琪&amp英文名：Porche`); the sixth,
`don't panic`, still has its overlay sense.

Seen while looking, not touched: 315 records have literal tags in the text
(`<br>` 157, `<p>` 131; pages about HTML among them), and 296 have characters
from the private-use area, which show as boxes.

**Captions.** `田字格` was on the list of things that make a section "not a
sense", so 长, 浩, 伍, 娴 lost their 释义. The caption is now taken out
instead. The first rebuild still showed `田字格长汉语拼音：cháng`: the raw text
is `田字格 长`, with a space, and other pages say `田字格里的‘烦’`,
`田字格中的简体字‘过’`, `田字格之宋体字`. After the second rebuild one is left
(`熟，田字格四角号码:`). `书法“浩”字` is only taken out on the page of a single
character: `岳飞草书“还我河山”巨匾` is a sentence.

**Glued headings.** Counted on the records of the build above, by the label
of the section, the heading word inside it and what stands in front of it:
`示例` inside a 用法 text 1,761 times (908 after a sentence, 841 glued to a
character), far ahead of everything else; `出处` after a sentence in a 释义
or 详解 text about 100; `反义词` glued inside a list of synonyms 35. `解释`
inside 释义 (1,287) is prose almost every time and is left alone.

The 500,000-row trial on the 2019 corpus changed only 16 records: the 用法
texts with `示例` come mostly from the overlay. So the old and the new rules
were both run over every section text on the records and the differences
read by kind (2,246 records at first). What that showed and what was changed
for it:

- `铸铁管用法兰固定` split at `用法` after the headword: `用法` now needs
  its formula there (`联合式；`, `作谓语`).
- `例子；榜样` (the meaning of 傍州例) and `更显著的例子了` became examples:
  not in front of punctuation or `了`, not after `的`.
- `宠辱不惊的近义词是置之度外` and `还有一个同义词“假卧”` lost the word:
  not after `的`, `有`, `个` and the like.
- `能做到这个程度,真是不简单出处1.` lost `简单` with the heading: the
  headword goes only when it starts a sentence.
- On the page of a character, `例句` after a sentence took the next
  compound's definition along (迷, 诞): not on pages of a single character.
- `不翼而飞（词语解释：…）` in a list of synonyms became a 释义 of the
  headword: `解释：` does not end a list.
- `【释 义】：`, `【出 处】：` (剖心坼肝) were not read at all, a gap from before:
  spaced-out headings in brackets, and `『…』`, `〔…〕` as brackets.

Against the build above:

| | before | now |
|---|---:|---:|
| records with an entity | 8 | 1 |
| names without a semicolon | 177 | 0 |
| section texts with a heading word after a sentence | 1,565 | 610 |
| records with sections | 120,991 | 121,078 |
| senses showing sections, full | 76,251 | 76,383 |
| senses showing sections, lexical | 28,971 | 29,033 |
| shown 示例 | 11,447 | 13,233 |
| shown 用法 | 4,968 | 5,109 |
| shown 出处 | 26,448 | 26,572 |
| shown 反义词 | 2,597 | 2,627 |
| shown 释义 | 43,951 | 43,955 |
| headwords, full | 4,799,728 | 4,799,723 |
| senses, full | 4,877,418 | 4,877,413 |
| headwords, lexical | 82,060 | 82,060 |
| zip bytes, full | 1,432,192,152 | 1,432,236,261 |
| zip bytes, lexical | 36,412,843 | 36,433,587 |

Sections changed on 2,645 records, 1,474 of them under a CC-CEDICT headword.
Labels gained: 示例 1,602, 用法 263, 出处 146, 反义词 34, 释义 22 (the
character pages), others 15. Labels lost: 11, each because the text moved to
another label (获胜: `〔例句〕中国队获胜了。` from 用法 to 示例; 教授:
`【词性】名词动词` from 释义 to 用法). 132 summaries changed; the entity rules
are the only change that reaches summaries.

Golden words: 84 of 84 (full) and 57 of 57 (lexical), 12 lines added. Senses
without a reading 148,224, summaries cut inside a quote 8,159.

**Not fixed**: `示例` glued between two characters in a 释义 or 详解 text
(`强壮而勇猛；强悍示例粗犷彪悍`), 22 texts, because `欧洲书牍示例` and
`古文示例` have the same shape; 74 of 7,813 lists of synonyms still run on
behind a space or a bracket (`唇枪舌剑 【使用程度】常用成语`) — the rule for
list endings only sees a word glued to the list; senses given under a page's
own `出处` heading are shown under 出处 (三岛, 规模); the rest of the list in
the section above. The first two of these, and the tags and private-use
characters seen in passing, are done in the next section.

## Third local build, 2026-11-12: tags, private-use characters, list tails, glued 示例

**Tags.** A wide pattern (`<word …>`) finds 826 texts with something in
angle brackets, and most of it is text: `<math>`, `<stdio.h>`, `<believes>`,
`<A Year Without Rain>`, and pages about HTML elements. Layout tags proper
(`br`, `p`, `span`, `font`, `strong` …) are in 311 texts, 298 of them
summaries. Those are taken out of body text. Three guards came from reading
them: an attribute must be `name=value`; `<a>`, `<b>`, `<i>`, `<u>` only in
pairs; a text that speaks of `HTML`, `标签`, `元素`, `超文本`, `控件` or
`字母` keeps its tags. The same pattern still finds 30 texts after the
build: 13 are about markup, 6 are not tags (`<A Better Day>`, `<li quan>`),
7 are unpaired or broken (`</B>`, `<p zdct3">`), and 4 are layout tags that
stay because the text says `元素` or `标签` somewhere else, about something
else (后孙家鲍村: `耕地1241</SPAN>亩`). The guard looks at the whole text; a
window around the tag would catch those four.

**Private-use characters.** 472 of them, 179 different code points, in 274
body texts and 22 titles. Three kinds:

- E815–E864: the 80 characters GB 18030-2000 kept there. The table was
  checked two ways: Python's `gb18030` codec gives the same character for 66
  of them (the other 14 it still leaves in the private-use area; those are
  the ones the 2005 edition moved), and the corpus agrees wherever the
  context names the character: `口眼㖞斜`, `奕䜣`, `芎䓖`, `康䶮`, `⺮` on the
  page of 竹, `𠂇` in 左 and 希, `𢦏` in 哉, `龹` in 觠.
- F020–F0FF: letters of the Symbol and Wingdings fonts. By count they are
  bullets (F06C 59, F06E 17, F0D8 15, F075 14). A few are signs, and only
  the text around them tells: F06D is `μ` in `μC/OS-II` and a missing
  character in `移主□（藏）郎中`, so it is `μ` only in front of a Latin
  letter or at the end.
- Everything else belongs to some font nobody has: rare characters in
  quotations (`其上独有云气，□兮直上`), Japanese in three articles. `□`.
  E004 and E5E5 occur only between sentences and in front of a text and are
  dropped.

22 titles had one: 13 lost it from an end, two are the character itself now
(`𠂇`, `龻`), `相对磁导率μ` and `奕䜣` are mapped, and 5 keep one inside
(`赵□庆` would be a headword nobody types).

**Lists of synonyms.** 152 lists had a bracket, a colon heading or one of
the words `相关词`, `感情色彩`, `英文翻译` … somewhere; 8 are left. The
first version of this rule broke 69 lists and was caught by comparing the
build with the one before: a source mark right after the heading
(`近义词[1] 不可名状`) counted as a bracketed heading. That is why the rules
were then run, old against new, over the raw rows themselves (all 587,819
overlay rows and 500,000 rows of the 2019 corpus) and not only over the text
on the records, where the source marks are gone. That comparison found the
rest:

- A letter-spaced snapshot lost its introduction when a tag or a
  private-use character was removed before it was put back together
  (人才培养方案: `简介人才培养…`).
- `四分五裂常用程度：…用法：作谓语` lost its 用法 part once the list ended
  at `常用程度`. A heading that names a label counts after the left-out
  tail too.
- `确数：确数就是准确的数…`, a synonym with its explanation, was dropped
  whole. In front of a list nothing ends it.

**示例 in a meaning.** 41 meaning texts of words (not single characters) had
`示例` or `例句` after a Chinese character; 13 are left, and those are
`欧洲书牍示例》`, `解释与示例`, `…的例句都有不少` and the like. With a
colon or in brackets it is a heading after any character; without, the
headword or `～` has to come after it.

Against the build above:

| | before | now |
|---|---:|---:|
| body texts with a private-use character | 274 | 0 |
| texts with a layout tag | 311 | 30 |
| lists of synonyms with a tail | 152 | 8 |
| `示例`/`例句` glued inside a meaning | 41 | 13 |
| shown 示例 | 13,233 | 13,320 |
| shown 近义词 | 4,588 | 4,654 |
| shown 反义词 | 2,627 | 2,673 |
| shown 辨析 | 1,155 | 1,143 |
| senses showing sections, full | 76,383 | 76,396 |
| senses showing sections, lexical | 29,033 | 29,040 |
| headwords, full | 4,799,723 | 4,799,711 |
| senses, full | 4,877,413 | 4,877,405 |
| headwords, lexical | 82,060 | 82,060 |
| zip bytes, full | 1,432,236,261 | 1,432,224,156 |
| zip bytes, lexical | 36,433,587 | 36,424,312 |

514 summaries changed (9 under a CC-CEDICT headword) and sections on 467
records (287). Labels gained: 示例 97, 近义词 85, 反义词 45. Labels lost: 18;
11 are 辨析 sections that held only lists and show under 近义词 and 反义词
now, 2 are lists that were no lists (`皲 jūn 字义：形声…`), 5 moved.
23 headwords went and 11 came: titles that lost a private-use character at
an end, and records whose whole summary was a tag (`<STRONG id=…>ClockTraySkins`).

Golden words: 95 of 95 (full) and 64 of 64 (lexical), 11 lines added. Senses
without a reading 148,222, summaries cut inside a quote 8,158.

**Not fixed**: a list that explains each synonym (`内人：屋内之人的意思。…`)
is shown with the explanations; `□` stands where the character is unknown,
which is honest and no better to read; the 4 layout tags and 7 broken ones
named above; the rest of the lists in the two sections above.
