"""python -m baike2yomitan extract|merge|build|validate|smoke|sample|release|all"""
from __future__ import annotations

import argparse
import os
import random
import sys

DEFAULT_563W = os.path.join("data", "raw", "563w", "563w_baidubaike.json")
DEFAULT_HF = os.path.join("data", "raw", "overlay")
RECORDS = os.path.join("data", "records.jsonl")
RECORDS_HF = os.path.join("data", "records.hf.jsonl")
RECORDS_MERGED = os.path.join("data", "records.merged.jsonl")
DIST_FULL = os.path.join("dist", "baike-full.zip")
DIST_LEX = os.path.join("dist", "baike-lexical.zip")


def _print_stats(name: str, stats: dict) -> None:
    print(f"\n== {name} ==")
    for k in sorted(stats):
        v = stats[k]
        print(f"  {k:40s} {v:>12,}" if isinstance(v, int) else f"  {k:40s} {v}")


def _verify_input(a) -> None:
    """Check the default input against data/source-inputs.json before extracting."""
    from .inputs import MANIFEST_PATH, InputError, verify_or_raise

    if getattr(a, "skip_verify", False):
        return
    if a.input:
        print(f"  [inputs] custom --input given; not checked against {MANIFEST_PATH}", file=sys.stderr)
        return
    if not os.path.exists(MANIFEST_PATH):
        print(f"  [inputs] {MANIFEST_PATH} missing; inputs not verified (run `inputs pin`)", file=sys.stderr)
        return
    try:
        verify_or_raise(a.source, MANIFEST_PATH, hash=not getattr(a, "no_hash", False))
    except InputError as e:
        raise SystemExit(f"extract: {e}") from e


def cmd_extract(a) -> int:
    from .report import save_stats, write_report

    _verify_input(a)
    if a.source == "563w":
        from .extract_563w import extract

        inp = a.input or DEFAULT_563W
        out = a.out or RECORDS
        stats = extract(inp, out, limit=a.limit, max_summary_chars=a.max_summary_chars,
                        want_infobox=not a.no_infobox)
    else:
        from .extract_hf import extract

        inp = a.input or DEFAULT_HF
        out = a.out or RECORDS_HF
        stats = extract(inp, out, limit=a.limit, max_summary_chars=a.max_summary_chars)
    stats["input"] = inp
    stats["output"] = out
    save_stats(f"extract_{a.source}", stats)
    _print_stats(f"extract {a.source}", stats)
    print("report:", write_report())
    return 0


def cmd_merge(a) -> int:
    from .merge import merge
    from .report import save_stats, write_report

    stats = merge(a.primary, a.overlay, a.out, key=getattr(a, "merge_key", "title"))
    save_stats("merge", stats)
    _print_stats("merge", stats)
    print("report:", write_report())
    return 0


def _readings_cedict(a, fallback=None):
    """CC-CEDICT export to take readings from: --readings-cedict, else the
    given path, else the default download location when it exists."""
    from .cedict import DEFAULT_PATH

    if not a.pinyin:
        return None
    explicit = getattr(a, "readings_cedict", None)
    if explicit == "none":
        return None
    path = explicit or fallback or (DEFAULT_PATH if os.path.exists(DEFAULT_PATH) else None)
    if path is None:
        print("readings: CC-CEDICT not found, using article pinyin and pypinyin only "
              "(pass --readings-cedict PATH, or run `all`, which downloads it)")
    elif not os.path.exists(path):
        raise SystemExit(f"--readings-cedict: {path} does not exist")
    return path


def _build_one(records, out, a, cedict_words=None, exclude_tags=None, readings_cedict=None):
    """Build one zip. The title is --title (build only) or, absent that, derived
    by build() from whether a CC-CEDICT filter is in play."""
    from .build import build
    from .report import save_stats

    update_base_url = a.update_url
    if update_base_url == "github":
        from .release import github_release_base_url, repo_from_git_remote

        update_base_url = github_release_base_url(repo_from_git_remote())
    stats = build(records, out, title=getattr(a, "title", None), pinyin=a.pinyin, traditional=a.traditional,
                  infobox=a.infobox, cedict_words=cedict_words, exclude_tags=exclude_tags,
                  revision=a.revision, update_base_url=update_base_url,
                  readings_cedict=readings_cedict)
    save_stats("build_" + os.path.splitext(os.path.basename(out))[0], stats)
    _print_stats(f"build {out}", stats)
    return stats


def cmd_build(a) -> int:
    cedict_words = None
    if a.cedict:
        from .cedict import load_simplified_headwords

        cedict_words = load_simplified_headwords(a.cedict)
        print(f"CC-CEDICT simplified headwords: {len(cedict_words):,}")
    exclude = set(t for t in (a.exclude_tags or "").split(",") if t)
    _build_one(a.records, a.out, a, cedict_words, exclude, _readings_cedict(a, fallback=a.cedict))
    if not a.no_validate:
        return cmd_validate(argparse.Namespace(zip=a.out, schemas_dir=a.schemas_dir, engine="auto"))
    return 0


def cmd_validate(a) -> int:
    from .validate import validate_zip

    errors = validate_zip(a.zip, a.schemas_dir, engine=getattr(a, "engine", "auto"))
    if errors:
        print(f"VALIDATION FAILED for {a.zip}: {len(errors)} error(s)")
        for e in errors:
            print("  -", e)
        return 1
    print(f"VALIDATION OK: {a.zip}")
    return 0


def cmd_smoke(a) -> int:
    from .validate import print_smoke, smoke

    ok = print_smoke(smoke(a.zip, extra_random=a.random, seed=a.seed))
    return 0 if ok else 1


def cmd_sample(a) -> int:
    """Random sample of N records for eyeballing (reservoir sampling)."""
    from .records import iter_records

    rng = random.Random(a.seed)
    res: list[dict] = []
    for i, rec in enumerate(iter_records(a.records)):
        if len(res) < a.n:
            res.append(rec)
        else:
            j = rng.randrange(i + 1)
            if j < a.n:
                res[j] = rec
    print(f"\n== random sample of {len(res)} records from {a.records} ==")
    for r in res:
        label = f" [{r['sense_label']}]" if r.get("sense_label") else ""
        flags = ",".join(r.get("quality_flags") or [])
        print(f"\n{r['title']}{label}  ({r['source']}; id={r.get('lemma_id')}; {flags})")
        print("  " + r["summary"])
    return 0


def cmd_inputs(a) -> int:
    from . import inputs

    path = a.manifest or inputs.MANIFEST_PATH
    names = [a.source] if a.source else None
    try:
        if a.action == "pin":
            inputs.pin(path, names)
            print("wrote", path)
            return 0
        manifest = inputs.load_manifest(path)
        rc = 0
        for name in names or manifest["sources"]:
            if a.action == "download":
                inputs.download_source(manifest, name)
            problems = inputs.verify_source(manifest, name, hash=not a.no_hash,
                                            log=lambda m: print(m, file=sys.stderr, flush=True))
            for p in problems:
                print(f"  FAIL {p}")
            print(f"{name}: {'OK' if not problems else f'{len(problems)} problem(s)'}"
                  f" ({manifest['sources'][name]['repo_id']}@{manifest['sources'][name]['revision'][:12]})")
            rc |= 1 if problems else 0
        return rc
    except inputs.InputError as e:
        print(f"inputs: {e}", file=sys.stderr)
        return 2


def cmd_release(a) -> int:
    from .release import ReleaseError, release

    try:
        return release(a.zips, repo=a.repo, tag=a.tag, title=a.title, notes_file=a.notes_file,
                       draft=a.draft, dry_run=a.dry_run)
    except ReleaseError as e:
        print(f"release: {e}", file=sys.stderr)
        return 2


def cmd_all(a) -> int:
    from .cedict import DEFAULT_PATH, download, load_simplified_headwords
    from .report import save_stats, write_report
    from .validate import print_smoke, smoke

    a.source = "563w"; a.input = None; a.out = None
    cmd_extract(a)
    records = RECORDS
    if a.overlay_hf:
        a.source = "hf"; a.input = None; a.out = None
        cmd_extract(a)
        a.primary, a.overlay, a.out = RECORDS, RECORDS_HF, RECORDS_MERGED
        a.merge_key = "title"
        cmd_merge(a)
        records = RECORDS_MERGED
    cedict_path = a.cedict or DEFAULT_PATH
    if not os.path.exists(cedict_path):
        print("downloading CC-CEDICT …")
        download(cedict_path)
    words = load_simplified_headwords(cedict_path)
    print(f"CC-CEDICT simplified headwords: {len(words):,}")
    exclude = set(t for t in (a.exclude_tags or "").split(",") if t)
    readings_cedict = _readings_cedict(a, fallback=cedict_path)
    _build_one(records, DIST_FULL, a, readings_cedict=readings_cedict)
    lex = _build_one(records, DIST_LEX, a, words, exclude, readings_cedict)
    rc = 0
    for z in (DIST_FULL, DIST_LEX):
        if getattr(a, "no_validate", False):
            print(f"validation skipped for {z} (--no-validate)")
        else:
            rc |= cmd_validate(argparse.Namespace(zip=z, schemas_dir=a.schemas_dir, engine="auto"))
    inter = lex["records_seen"] - lex.get("skip:not_in_cedict", 0)
    save_stats("cedict", {"cedict_headwords": len(words), "records_with_cedict_title": inter,
                          "lexical_entries_after_tag_exclusion": lex["entries"]})
    print(f"\nCEDICT intersection: {inter:,} records have a CC-CEDICT simplified headword as title")
    print("report:", write_report())
    print("\n== smoke test (full) ==")
    ok = print_smoke(smoke(DIST_FULL, extra_random=5, seed=a.seed))
    cmd_sample(argparse.Namespace(records=records, n=20, seed=a.seed))
    return rc or (0 if ok else 1)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="baike2yomitan", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common_extract(sp):
        sp.add_argument("--limit", type=int, default=None, help="stop after N input rows")
        sp.add_argument("--skip-verify", action="store_true",
                        help="do not check the input files against data/source-inputs.json")
        sp.add_argument("--no-hash", action="store_true",
                        help="verify pinned inputs by size only (skip the SHA-256, ~2 min for the primary)")
        sp.add_argument("--max-summary-chars", type=int, default=300)
        sp.add_argument("--no-infobox", action="store_true", help="do not extract 基本信息 key/value pairs")

    def add_common_build(sp):
        sp.add_argument("--pinyin", action="store_true",
                        help="fill the reading field: CC-CEDICT, then the article's own pinyin, then pypinyin")
        sp.add_argument("--readings-cedict", default=None, metavar="PATH|none",
                        help="CC-CEDICT export to take readings from (default: the --cedict file, else "
                             "data/cedict/… when present); 'none' disables it")
        sp.add_argument("--traditional", choices=["s2t", "s2twp", "s2hk"], default=None,
                        help="also emit traditional-script headwords via OpenCC")
        sp.add_argument("--infobox", action="store_true", help="render 基本信息 pairs below the summary")
        sp.add_argument("--exclude-tags", default="", help="comma-separated Baike tags to drop (lexical build)")
        sp.add_argument("--schemas-dir", default=os.path.join("data", "schemas"))
        sp.add_argument("--seed", type=int, default=None)
        sp.add_argument("--revision", default=None,
                        help="index.json revision, dot-separated integers (default: today as Y.M.D)")
        sp.add_argument("--update-url", default=None, metavar="BASE_URL|github",
                        help="make the dictionary self-updating: index.json gets isUpdatable plus "
                             "indexUrl/downloadUrl under BASE_URL; 'github' derives "
                             "https://github.com/<owner>/<repo>/releases/latest/download from the origin remote")

    sp = sub.add_parser("extract", help="source → data/records*.jsonl")
    sp.add_argument("--source", choices=["563w", "hf"], required=True)
    sp.add_argument("--input", default=None, help="563w json file / overlay parquet dir")
    sp.add_argument("--out", default=None)
    add_common_extract(sp)
    sp.set_defaults(fn=cmd_extract)

    sp = sub.add_parser("merge", help="overlay records into primary records by lemma_id")
    sp.add_argument("--primary", default=RECORDS)
    sp.add_argument("--overlay", default=RECORDS_HF)
    sp.add_argument("--out", default=RECORDS_MERGED)
    sp.add_argument("--merge-key", dest="merge_key", choices=["title", "lemma_id"], default="title",
                    help="title (default; the 563w and IA id spaces differ) or lemma_id for sources that share ids")
    sp.set_defaults(fn=cmd_merge)

    sp = sub.add_parser("build", help="records → Yomitan zip")
    sp.add_argument("--records", default=RECORDS)
    sp.add_argument("--out", default=DIST_FULL)
    sp.add_argument("--title", default=None)
    sp.add_argument("--cedict", default=None, help="restrict to CC-CEDICT simplified headwords (path to MDBG export)")
    sp.add_argument("--no-validate", action="store_true")
    add_common_build(sp)
    sp.set_defaults(fn=cmd_build)

    sp = sub.add_parser("validate", help="schema-check every JSON file in a zip")
    sp.add_argument("zip")
    sp.add_argument("--schemas-dir", default=os.path.join("data", "schemas"))
    sp.add_argument("--engine", choices=["auto", "fast", "jsonschema"], default="auto",
                    help="fastjsonschema (default when installed) or the reference jsonschema package")
    sp.set_defaults(fn=cmd_validate)

    sp = sub.add_parser("smoke", help="look up known titles in a zip")
    sp.add_argument("zip")
    sp.add_argument("--random", type=int, default=5)
    sp.add_argument("--seed", type=int, default=None)
    sp.set_defaults(fn=cmd_smoke)

    sp = sub.add_parser("sample", help="print N random records")
    sp.add_argument("--records", default=RECORDS)
    sp.add_argument("-n", type=int, default=20)
    sp.add_argument("--seed", type=int, default=None)
    sp.set_defaults(fn=cmd_sample)

    sp = sub.add_parser("inputs", help="pin / verify / download the Hugging Face source files (data/source-inputs.json)")
    sp.add_argument("action", choices=["pin", "verify", "download"])
    sp.add_argument("--source", choices=["563w", "hf"], default=None, help="one source (default: all)")
    sp.add_argument("--manifest", default=None)
    sp.add_argument("--no-hash", action="store_true", help="verify: size only, skip SHA-256")
    sp.set_defaults(fn=cmd_inputs)

    sp = sub.add_parser("release", help="upload dist zips (+ sidecar index.json) as a GitHub release via gh")
    sp.add_argument("zips", nargs="*", default=[DIST_FULL, DIST_LEX],
                    help=f"zips to upload (default: {DIST_FULL} {DIST_LEX})")
    sp.add_argument("--repo", default=None, help="owner/name (default: from the origin remote)")
    sp.add_argument("--tag", default=None, help="release tag (default: v<revision of the first zip>)")
    sp.add_argument("--title", default=None, help="release title (default: the tag)")
    sp.add_argument("--notes-file", default=None, help="markdown notes (default: generated from data/stats)")
    sp.add_argument("--draft", action="store_true", help="create the release as a draft")
    sp.add_argument("--dry-run", action="store_true", help="check everything and print the gh commands")
    sp.set_defaults(fn=cmd_release)

    sp = sub.add_parser("all", help="extract (+overlay, merge), build both zips, validate, smoke")
    sp.add_argument("--overlay-hf", action="store_true")
    sp.add_argument("--cedict", default=None)
    sp.add_argument("--no-validate", action="store_true", help="skip the schema check of both zips (~45 min)")
    add_common_extract(sp)
    add_common_build(sp)
    sp.set_defaults(fn=cmd_all)

    a = p.parse_args(argv)
    return a.fn(a)
