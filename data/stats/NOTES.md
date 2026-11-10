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
   yield nothing.
9. **Tag bank**: the only tag is `百科` (category `name`). Baike tags are shown
   as muted footer text (first five) and used only for `--exclude-tags`.
10. **Traditional headwords** via OpenCC `s2t` by default (`s2twp` available);
    only emitted when the converted title differs.
