"""Schema validation and smoke test for a built Yomitan zip."""
from __future__ import annotations

import json
import os
import random
import re
import sys
import urllib.request
import zipfile
from concurrent.futures import ProcessPoolExecutor

SCHEMA_FILES = {
    "index": "dictionary-index-schema.json",
    "term": "dictionary-term-bank-v3-schema.json",
    "tag": "dictionary-tag-bank-v3-schema.json",
}
SCHEMA_BASE = "https://raw.githubusercontent.com/yomidevs/yomitan/master/ext/data/schemas/"
DEFAULT_SCHEMA_DIR = os.path.join("data", "schemas")
SMOKE_TITLES = ["红色食品", "丈夫", "时间", "舍利子", "疝气", "Θ", "小隐于野大隐于市"]


def fetch_schemas(schema_dir: str = DEFAULT_SCHEMA_DIR, force: bool = False) -> dict[str, str]:
    os.makedirs(schema_dir, exist_ok=True)
    paths = {}
    for key, name in SCHEMA_FILES.items():
        p = os.path.join(schema_dir, name)
        if force or not os.path.exists(p):
            with urllib.request.urlopen(SCHEMA_BASE + name, timeout=60) as r, open(p, "wb") as f:
                f.write(r.read())
        paths[key] = p
    return paths


def load_schemas(schema_dir: str = DEFAULT_SCHEMA_DIR) -> dict[str, dict]:
    paths = fetch_schemas(schema_dir)
    return {k: json.load(open(p, encoding="utf-8")) for k, p in paths.items()}


def _make_validators(schemas: dict[str, dict], engine: str) -> dict:
    """Return kind -> callable(data) -> list[str] of error messages.

    'fast' compiles the schemas with fastjsonschema (~100x faster, needed for
    ~5M entries); 'jsonschema' uses the reference implementation and reports
    every error with its path."""
    if engine == "auto":
        try:
            import fastjsonschema  # noqa: F401
            engine = "fast"
        except ImportError:
            engine = "jsonschema"
    if engine == "fast":
        import fastjsonschema

        def mk(schema):
            compiled = fastjsonschema.compile(schema)

            def check(data):
                try:
                    compiled(data)
                    return []
                except fastjsonschema.JsonSchemaException as e:
                    return [f"{e.path if hasattr(e, 'path') else ''}: {e.message[:200]}"]
            return check
    else:
        import jsonschema

        def mk(schema):
            v = jsonschema.Draft7Validator(schema)

            def check(data):
                return [f"{list(err.absolute_path)}: {err.message[:200]}" for err in v.iter_errors(data)]
            return check
    return {k: mk(v) for k, v in schemas.items()}


def _member_kind(name: str) -> str | None:
    """The schema a zip member is checked against: "" when it has none, None when it does not belong."""
    if name == "index.json":
        return "index"
    if re.fullmatch(r"term_bank_\d+\.json", name):
        return "term"
    if re.fullmatch(r"tag_bank_\d+\.json", name):
        return "tag"
    if name == "styles.css":  # dictionary-scoped CSS, no schema
        return ""
    return None


MAX_WORKERS_WINDOWS = 61  # ProcessPoolExecutor raises above this on Windows


def default_workers() -> int:
    """Cores this process may use."""
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:  # Windows and macOS have no affinity call
        return os.cpu_count() or 1


def worker_count(requested: int | None, tasks: int, platform: str = sys.platform) -> int:
    """Processes to start: the request (default: every core), never more than there are
    files to check or than the platform's process pool accepts."""
    n = min(requested or default_workers(), tasks)
    if platform == "win32":
        n = min(n, MAX_WORKERS_WINDOWS)
    return max(1, n)


# --- validating by shape ------------------------------------------------------
#
# The term bank schema is slow on these entries (about 6 s of CPU per 10,000,
# almost all in the recursive structured-content rules), yet it only constrains
# structure: tag names, the enumerated style and image values, and the scheme of
# an href. The text of an entry is free. Millions of entries therefore share a
# few dozen shapes, and an entry is valid exactly when its shape is.

MODES = ("shape", "full")
FULL_SAMPLE = 3  # term banks that shape mode also puts through the whole schema
_HREF_SCHEME_RE = re.compile(r"(?:https?:|\?)")  # the part of an href the schema's pattern looks at


def content_shape(node):
    """A definition with everything the schema does not look at blanked out:
    text content, the values under `data`, and an href past its scheme. Tags,
    types, styles and every other attribute are kept as they are."""
    if isinstance(node, str):
        return ""
    if isinstance(node, list):
        return [content_shape(n) for n in node]
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "content":
                out[k] = content_shape(v)
            elif k == "data" and isinstance(v, dict):
                out[k] = {dk: "" if isinstance(dv, str) else dv for dk, dv in v.items()}
            elif k == "href" and isinstance(v, str):
                m = _HREF_SCHEME_RE.match(v)
                out[k] = m.group(0) if m else v
            else:
                out[k] = v
        return out
    return node


def _row_problem(row) -> str | None:
    """The eight fields of a term row, checked without the schema."""
    if not isinstance(row, list) or len(row) != 8:
        return "must be an array of exactly 8 items"
    term, reading, definition_tags, rules, score, definitions, sequence, term_tags = row
    for label, value in (("term", term), ("reading", reading), ("rules", rules), ("term tags", term_tags)):
        if not isinstance(value, str):
            return f"{label} must be a string"
    if definition_tags is not None and not isinstance(definition_tags, str):
        return "definition tags must be a string or null"
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return "score must be a number"
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        return "sequence must be an integer"
    if not isinstance(definitions, list):
        return "definitions must be an array"
    return None


def check_term_bank_by_shape(data, check, shapes: dict, max_errors: int = 20) -> list[str]:
    """Error messages for one term bank. `check` is the schema validator for a
    bank; it is called once per distinct shape, and `shapes` remembers the
    answers for the rest of the process."""
    if not isinstance(data, list):
        return check(data)
    errors: list[str] = []
    for i, row in enumerate(data):
        problem = _row_problem(row)
        if problem is None:
            shape = content_shape(row[5])
            key = json.dumps(shape, ensure_ascii=False, sort_keys=True)
            found = shapes.get(key)
            if found is None:
                found = shapes[key] = check([["", "", None, "", 0, shape, 0, ""]])
            problem = "; ".join(found) if found else None
        if problem:
            errors.append(f"entry {i} ({row[0]!r}): {problem}" if isinstance(row, list) and row else f"entry {i}: {problem}")
            if len(errors) >= max_errors:
                break
    return errors


_worker: dict = {}  # per-process state: the open zip, the compiled schemas, the shapes seen


def _init_worker(zip_path: str, schema_dir: str, engine: str, mode: str = "full", full_names: tuple = ()) -> None:
    _worker["zip"] = zipfile.ZipFile(zip_path)
    _worker["validators"] = _make_validators(load_schemas(schema_dir), engine)
    _worker["mode"], _worker["full_names"], _worker["shapes"] = mode, set(full_names), {}


def _check_member(task: tuple[str, str]) -> tuple[str, str, list[str]]:
    """Check one zip member; returns (name, entry count or 'index', error messages)."""
    name, kind = task
    data = json.loads(_worker["zip"].read(name))
    errors = []
    if kind == "term" and len(data) > 10_000:
        errors.append(f"{len(data)} entries (> 10000)")
    check = _worker["validators"][kind]
    by_shape = kind == "term" and _worker.get("mode") == "shape"
    if by_shape:
        errors.extend(check_term_bank_by_shape(data, check, _worker["shapes"]))
    if not by_shape or name in _worker.get("full_names", ()):
        full = check(data)
        if by_shape and full and not errors:
            full = [f"the whole-schema check disagrees with the shape check: {m}" for m in full]
        errors.extend(m for m in full if not by_shape or not errors or m.startswith("the whole"))
    return name, str(len(data)) if isinstance(data, list) else "index", errors


def _full_sample(term_banks: list[str]) -> tuple:
    """First, middle and last term bank: checked both ways in shape mode."""
    if len(term_banks) <= FULL_SAMPLE:
        return tuple(term_banks)
    return (term_banks[0], term_banks[len(term_banks) // 2], term_banks[-1])


def validate_zip(zip_path: str, schema_dir: str = DEFAULT_SCHEMA_DIR, max_errors: int = 20,
                 engine: str = "auto", workers: int | None = None, mode: str = "shape") -> list[str]:
    """Return a list of error strings (empty = valid).

    `mode="shape"` (default) validates each distinct entry shape once, see
    above, and puts three term banks through the whole schema as a cross-check.
    `mode="full"` runs the schema over every entry (~6 s of CPU per
    10,000-entry term bank). Either way the zip members are independent and
    are spread over `workers` processes (default: every core). Progress lines
    and errors keep the zip's order."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
    load_schemas(schema_dir)  # download them once, before any worker looks
    errors: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    if any("/" in n for n in names):
        errors.append("zip contains subfolders: " + ", ".join(n for n in names if "/" in n)[:200])
    if "index.json" not in names:
        errors.append("index.json missing")
    if not any(_member_kind(n) == "term" for n in names):
        errors.append("no term_bank_N.json files")
    tasks = []
    for name in names:
        kind = _member_kind(name)
        if kind is None:
            errors.append(f"unexpected file in zip: {name}")
        elif kind:
            tasks.append((name, kind))

    def collect(results) -> None:
        for name, size, member_errors in results:
            for msg in member_errors:
                errors.append(f"{name}: {msg}")
                if len(errors) >= max_errors:
                    return
            status = f"{len(member_errors)} error(s)" if member_errors else f"ok ({size})"
            print(f"  [validate] {name}: {status}", file=sys.stderr, flush=True)

    full_names = _full_sample([n for n, kind in tasks if kind == "term"]) if mode == "shape" else ()
    workers = worker_count(workers, len(tasks))
    if workers == 1:
        _init_worker(zip_path, schema_dir, engine, mode, full_names)
        try:
            collect(map(_check_member, tasks))
        finally:
            _worker.pop("zip").close()
            _worker.clear()
    else:
        pool = ProcessPoolExecutor(workers, initializer=_init_worker,
                                   initargs=(zip_path, schema_dir, engine, mode, full_names))
        try:
            collect(pool.map(_check_member, tasks))
        finally:
            pool.shutdown(cancel_futures=True)  # after max_errors, drop what has not started
    return errors[:max_errors]


def flatten_content(node) -> str:
    """Structured content → plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(flatten_content(n) for n in node)
    if isinstance(node, dict):
        if node.get("type") == "structured-content":
            return flatten_content(node.get("content"))
        if node.get("type") == "text":
            return node.get("text", "")
        tag = node.get("tag")
        inner = flatten_content(node.get("content"))
        if tag in ("div", "tr", "li"):
            return inner + "\n"
        if tag in ("th", "td"):
            return inner + "\t"
        if tag == "br":
            return "\n"
        return inner
    return str(node)


def smoke(zip_path: str, extra_random: int = 5, seed: int | None = None) -> dict[str, list[str]]:
    """Look up the known titles plus random ones; return title -> definitions."""
    rng = random.Random(seed)
    wanted = set(SMOKE_TITLES)
    found: dict[str, list[str]] = {t: [] for t in SMOKE_TITLES}
    reservoir: list[list] = []
    seen = 0
    with zipfile.ZipFile(zip_path) as zf:
        for name in sorted(zf.namelist()):
            if not name.startswith("term_bank_"):
                continue
            for entry in json.loads(zf.read(name)):
                seen += 1
                if entry[0] in wanted:
                    found[entry[0]].append(flatten_content(entry[5]).strip())
                # reservoir sample for the random picks
                if len(reservoir) < extra_random:
                    reservoir.append(entry)
                else:
                    j = rng.randrange(seen)
                    if j < extra_random:
                        reservoir[j] = entry
    for entry in reservoir:
        found.setdefault(entry[0] + " (random)", []).append(flatten_content(entry[5]).strip())
    return found


def print_smoke(results: dict[str, list[str]]) -> bool:
    ok = True
    for title, defs in results.items():
        print(f"\n### {title}  — {len(defs)} entr{'y' if len(defs)==1 else 'ies'}")
        for d in defs:
            print("  " + d.replace("\n", "\n  ").rstrip())
    n_hong = len(results.get("红色食品", []))
    n_zf = len(results.get("丈夫", []))
    n_sj = len(results.get("时间", []))
    if n_hong != 1:
        print(f"\nSMOKE FAIL: 红色食品 appears {n_hong} times (expected 1)")
        ok = False
    if n_zf < 1:
        print("\nSMOKE FAIL: 丈夫 is missing")
        ok = False
    if n_sj < 2:  # a title with several articles: the word, the physical quantity, songs
        print(f"\nSMOKE WARN: 时间 shows {n_sj} sense(s) (expected > 1)")
    return ok
