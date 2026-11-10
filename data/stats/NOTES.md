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
  plus a >30 % lone-character share catches them.
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
