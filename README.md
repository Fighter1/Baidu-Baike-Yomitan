# baike2yomitan

Build importable [Yomitan](https://github.com/yomidevs/yomitan) dictionaries
(term bank format 3) from offline copies of Baidu Baike.

The pipeline is source-agnostic: a thin per-source `extract` step writes a
common JSONL record format, and `merge`, `build` and `validate` know nothing
about where records came from. Adding a new source (Baidu's Baike API, an MDX
file, …) means writing one more extractor that emits the same records.

## Sources

| source | dataset | what we take |
|---|---|---|
| `563w` (primary) | `lars1234/baidu-baike-dataset`, one 16.8 GB JSON Lines file, 5.63 M entries, crawled ~2019 | title, summary (or first paragraph of the first section), tags, `/view/<id>` lemma id |
| `hf` (overlay, optional) | `mohamedah/baidu_baike`, Internet Archive snapshots 2020–2024, 588 k rows, parquet on `refs/convert/parquet` (~2.2 GB) | title, subtitle (= sense label), abstract, lemma id from `/item/<title>/<id>`, archive URL and snapshot date |

Nothing is ever requested from baike.baidu.com. CC-CEDICT comes from the MDBG
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
python -X utf8 -m baike2yomitan build --records data/records.merged.jsonl --out dist/baike-full.zip [--pinyin] [--traditional s2t|s2twp] [--infobox]
python -X utf8 -m baike2yomitan build --records data/records.merged.jsonl --out dist/baike-lexical.zip --cedict data/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz --exclude-tags 人物,企业,学校
python -X utf8 -m baike2yomitan validate dist/baike-full.zip
python -X utf8 -m baike2yomitan smoke dist/baike-full.zip
python -X utf8 -m baike2yomitan sample --records data/records.merged.jsonl -n 20
python -X utf8 -m baike2yomitan all --overlay-hf --pinyin --traditional s2t --infobox --exclude-tags 人物,企业,学校 --update-url github
python -X utf8 -m baike2yomitan release --dry-run        # upload dist zips as a GitHub release (see below)
```

`all` runs extract (both sources with `--overlay-hf`), merge, both builds,
validation, the smoke test and a 20-record sample. `--limit N` on `extract`
stops after N input rows for fast iteration.

### Flags

| flag | step | effect |
|---|---|---|
| `--limit N` | extract, all | stop after N input rows (fast iteration) |
| `--skip-verify`, `--no-hash` | extract, all | skip the pinned-input check, or check sizes only |
| `inputs pin\|verify\|download [--source 563w\|hf]` | inputs | maintain `data/source-inputs.json` (see *Downloading the corpora*) |
| `--max-summary-chars N` | extract, all | trim summaries to N chars at the last `。！？；` inside the window (default 300); a hard cut adds `…` |
| `--no-infobox` | extract, all | do not parse `基本信息`/`基本资料` sections into `[key, value]` pairs |
| `--merge-key title\|lemma_id` | merge | how overlay records match primary ones; `title` is the default because the two sources' ids differ (see below) |
| `--pinyin` | build, all | fill Yomitan's reading field with pypinyin (`hóng sè shí pǐn`); off by default, the reading is then empty |
| `--traditional s2t\|s2twp\|s2hk` | build, all | also emit a traditional-script headword for every entry whose OpenCC conversion differs from the simplified title; same content and sequence number |
| `--infobox` | build, all | render the extracted infobox pairs (first six) as a two-column table under the summary |
| `--cedict PATH` | build | keep only records whose title is a simplified CC-CEDICT headword (the lexical build); `all` downloads the MDBG export when missing |
| `--exclude-tags a,b` | build, all | drop records carrying any of these Baike tags; `all` applies it to the lexical build only |
| `--title` | build | override the dictionary title stored in `index.json` |
| `--revision R` | build, all | `index.json` revision; dot-separated integers only (default: today as `2026.11.08`) |
| `--update-url BASE\|github` | build, all | make the zip self-updating: `index.json` gets `isUpdatable` + `indexUrl`/`downloadUrl` under `BASE`; `github` derives `https://github.com/<owner>/<repo>/releases/latest/download` from the `origin` remote |
| `--repo`, `--tag`, `--title`, `--notes-file`, `--draft`, `--dry-run` | release | see *Self-updating dictionaries* below |
| `--no-validate` | build | skip the schema check after building |
| `--engine auto\|fast\|jsonschema` | validate | fastjsonschema when installed (default), or the reference implementation |
| `--schemas-dir`, `--seed` | build, validate, smoke, sample | where the Yomitan schemas are cached; seed for the random smoke/sample picks |

### What gets dropped, and what gets flagged

Every record is either written, or dropped for exactly one reason that is
counted in `data/extract_report.md`. Rules, in the order they are applied:

| reason | source | condition |
|---|---|---|
| `dup_lemma_id` | 563w | a `/view/<id>` already seen (zero padding stripped, so `view/0010` = `view/10`) |
| `title_empty`, `title_too_long` | both | title empty after cleaning, or longer than 30 characters |
| `no_summary_no_sections` | 563w | `summary` is null and the row has no sections |
| `summary_too_short` | 563w | `summary` is present but shorter than 15 characters after cleaning, no section paragraph qualifies as a replacement, and neither keep rule below applies |
| `summary_too_short_fallback` | 563w | `summary` is null, the first paragraph is under 15 characters, and no paragraph in any section qualifies (the whole page is infobox lines, pinyin or headings) |
| `summary_not_prose_fallback` | 563w | as above, but the first paragraph was long enough and still not usable (an infobox line or no Chinese) |
| `dup_title_summary` | 563w | same title and identical cleaned summary already written |
| `disambiguation_page` | hf | content is a list of `<title>：<descriptor>` items, not an article |
| `summary_too_short[_fallback]` | hf | abstract shorter than 15 characters after cleaning |
| `obfuscated_no_clean_duplicate` | hf | text is the 2024 anti-scraping `总 录 播 报` spacing and no clean snapshot of the same sense exists |
| `dup:title_subtitle`, `dup:lemma_id`, `dup:idless_same_summary` | hf | several snapshots of one sense; the cleanest, then newest, is kept |

A paragraph *qualifies* as a replacement summary when it is at least 15
characters, contains Chinese, and is not an infobox line (`作者：…`,
`I S B N：…`). When the first paragraph fails, the extractor walks the following
paragraphs and sections (up to 40) for the first that qualifies; the record is
flagged `summary_from_section` and, if it was not the first paragraph,
`summary_from_later_paragraph`.

Two kinds of summary under 15 characters are kept anyway, as a last resort
when nothing longer exists on the page (both sources):

- a **complete short sentence**: at least 6 characters, Chinese, ending in
  `。！？；`, not just the title, not an infobox line — `剌桐城 → 泉州市的别称。`,
  `诸葛壹 → 吴国将领，诸葛谨后代。` (flag `kept_short_sentence`);
- a **别称/别名 infobox line** with a non-empty value — `不着四六 → 别称：四六不懂`
  (flag `kept_alias_line`).

Everything else under 15 characters is dropped: headings (`公司简介`),
pinyin-only lines, repeated titles, `【词目】+title`, and other one-line infobox
stubs (`姓名：…`, `型号：…`). A 14-character description without a sentence
mark is still lost.

Cleaning applied before any of the above: literal `\n` sequences become line
breaks; `[1]`/`[2-3]` citation markers, gallery captions (`剧照(80张)`), the
UI labels 播报/编辑/语音 and the overlay's `zhua曲子白渡白颗` trailer are removed;
whitespace (incl. fullwidth and no-break spaces) is normalised and single spaces
between Chinese characters are dropped.

Outputs (figures from the 2026-11-08 pilot build, `--pinyin --traditional s2t --infobox`):

- `data/records.jsonl` (4.72 M records), `data/records.hf.jsonl` (383 k), `data/records.merged.jsonl` (4.89 M) — one JSON record per sense
- `data/extract_report.md` — drop counts by reason, quality flags, merge counts, heuristics notes
- `data/short_summary_examples.md` — sampled analysis of the under-15-character drops that motivated the paragraph-walking fallback
- `dist/baike-full.zip` — everything that survived extraction: 8.8 M entries (incl. 3.9 M traditional headwords), 882 term banks, ~1.3 GB
- `dist/baike-lexical.zip` — only titles that are simplified CC-CEDICT headwords (103 k records), minus `--exclude-tags 人物,企业,学校`: 160 k entries, 25 MB

Wall-clock on this machine: primary extract ~8.5 min, overlay extract ~6 min,
merge ~2 min, full build ~4 min (~8.5 min with `--pinyin`), full-zip validation
~45 min (fastjsonschema).

### Merge semantics

The 2019 crawl's `/view/<id>` numbers and the Internet Archive snapshots'
`/item/<title>/<id>` numbers are **different id spaces** (0 of 90k shared ids
named the same article), so `merge` keys on the **title**: a primary record is
refreshed from the overlay's default sense of the same title when that is
unambiguous; every other overlay sense is added as an extra record.
`--merge-key lemma_id` exists for a future source that genuinely shares ids.
`lemma_id` is only meaningful within one `source`.

### Record format

```json
{"source": "563w", "title": "李永赋", "sense_label": "云南晋宁县公安局副局长", "lemma_id": 10000022,
 "is_default_sense": null, "summary": "…", "tags": ["人物"], "url": "https://baike.baidu.com/view/10000022.htm",
 "archive_url": null, "snapshot_date": null, "quality_flags": [], "infobox": null}
```

`quality_flags` values: `summary_from_section` (primary had no usable summary
field), `summary_from_later_paragraph` (that replacement was not the first
paragraph of the page), `kept_short_sentence` / `kept_alias_line` (summary is
under 15 characters but was kept by the rules above), `abstract_fallback`
(overlay content had no repeated abstract), `summary_refreshed` (merge replaced
the summary with the overlay's), `no_lemma_id`.
Validation uses `fastjsonschema` when installed (the reference `jsonschema`
package takes hours on ~7 M entries); `validate --engine jsonschema` forces the
reference implementation.
`infobox` is an optional list of `[key, value]` pairs rendered by `build --infobox`.

## Importing into Yomitan

Yomitan → Settings → Dictionaries → *Import* → pick `dist/baike-full.zip`
(and/or `dist/baike-lexical.zip`). Each zip is a separate dictionary with a
distinct title; enable whichever you want in the dictionary list. Entries carry
the single tag `百科`. Headwords are simplified; with `--traditional` the same
entries are also reachable from traditional-script text.

### Showing simplified and traditional together

With `--traditional`, the traditional headword is a second term-bank entry
that shares the simplified entry's content, reading and **sequence number**.
Whether Yomitan shows them as one card with two headword chips (`遺民` `遗民`)
or as two separate cards depends on its grouping setting:

Yomitan → Settings → General → *Result grouping mode* → **Group related terms**
(the sequence-based merge mode). The default *Group term-reading pairs* shows
only the spelling that was looked up. `index.json` sets `sequenced: true`, which
the merge mode requires.

With `--pinyin` the reading (`yí mín`) is attached to both spellings; the
traditional chip reuses the pinyin computed from the simplified title.

## Self-updating dictionaries (GitHub Releases)

Yomitan can update a dictionary by itself when its `index.json` carries
`isUpdatable: true`, an `indexUrl` and a `downloadUrl`. *Settings →
Dictionaries → Check for updates* fetches `indexUrl`, compares its `revision`
with the installed one and offers the `downloadUrl` zip when it is newer.
Revisions are compared numerically only when both are dot-separated integers
with the same number of segments, which is why the builder always writes three
(`2026.11.08`); pass `--revision` for a second build on the same day
(`2026.11.8.2` would *not* compare numerically against `2026.11.08`, so keep
three segments, e.g. bump the day).

GitHub's `…/releases/latest/download/<asset>` URL always points at the newest
non-draft release, so it is a stable target for both fields. The flow:

```bash
python -X utf8 -m baike2yomitan build --records data/records.merged.jsonl --out dist/baike-full.zip --pinyin --traditional s2t --infobox --update-url github
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
   requires that the logged-in `gh` account has write access to it;
3. notes whether the repository is private — Yomitan cannot download assets
   from a private repository (it sends no auth header), so auto-update only
   works from a public one;
4. reads each zip's `index.json`, requires the `isUpdatable`/URL fields to
   match that repository (otherwise it tells you the exact `build` command to
   re-run), and regenerates the sidecar from the zip;
5. writes release notes to `dist/<tag>.notes.md` from `data/stats` (entry
   counts, sizes, record counts) unless `--notes-file` is given;
6. runs `gh release create <tag> <zips> <sidecars> --latest` (tag defaults to
   `v<revision>`, `--draft` for a draft), or `gh release upload --clobber` plus
   `gh release edit --latest` when the tag already exists.

`--dry-run` performs every check, prints the `gh` commands it would run and
reports problems as warnings instead of stopping. Users then import the zip
once; later releases reach them through *Check for updates*. The zips built
without `--update-url` are not self-updating and `release` rejects them.

## Tests

```bash
python -X utf8 -m pytest -q
```

Fixtures under `tests/fixtures/` are real rows copied from both sources.

## License and attribution

The dictionary content is Baidu Baike user-contributed material, taken from the
third-party mirrors `lars1234/baidu-baike-dataset` and `mohamedah/baidu_baike`
on Hugging Face; each entry links back to its Baike article. This repository
contains the converter code and small test fixtures; the built `dist/*.zip`
files are distributed as GitHub release assets. CC-CEDICT is CC BY-SA 4.0
(used here only to select headwords).
