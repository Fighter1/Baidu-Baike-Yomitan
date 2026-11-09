"""Pinned source inputs: which exact bytes the dictionaries were built from.

``data/source-inputs.json`` records, for each source, the Hugging Face dataset
commit and every input file's size and SHA-256 (Hugging Face stores large files
in LFS, whose object id *is* the file's SHA-256, so the values can be read from
the API without downloading). ``inputs download`` fetches exactly that commit,
``inputs verify`` checks the local files, and ``extract`` verifies its source
before streaming it unless ``--skip-verify`` is given.

The 16.8 GB primary file cannot live in a GitHub release (2 GiB asset limit),
so the pin is the commit hash + content hash, not a copy of the bytes.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import sys
from typing import Iterable

MANIFEST_PATH = os.path.join("data", "source-inputs.json")

# What `inputs pin` records when no manifest exists yet.
DEFAULT_SOURCES: dict[str, dict] = {
    "563w": {"repo_id": "lars1234/baidu-baike-dataset", "repo_type": "dataset", "ref": "main",
             "local_dir": "data/raw/563w", "patterns": [".json"]},
    "hf": {"repo_id": "mohamedah/baidu_baike", "repo_type": "dataset", "ref": "refs/convert/parquet",
           "local_dir": "data/raw/overlay", "patterns": [".parquet"]},
}


class InputError(Exception):
    pass


# ------------------------------------------------------------------ manifest

def load_manifest(path: str = MANIFEST_PATH) -> dict:
    if not os.path.exists(path):
        raise InputError(f"{path} not found; run `inputs pin` (or download the corpora manually)")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest: dict, path: str = MANIFEST_PATH) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return path


def local_path(source: dict, file: dict) -> str:
    return os.path.join(source["local_dir"], *file["path"].split("/"))


# -------------------------------------------------------------------- hashing

def sha256_file(path: str, chunk: int = 16 * 1024 * 1024, progress=None) -> str:
    h = hashlib.sha256()
    done = 0
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
            done += len(block)
            if progress:
                progress(done)
    return h.hexdigest()


def verify_file(path: str, expected_size: int, expected_sha256: str | None, hash: bool = True) -> list[str]:
    """Problems with one local file (empty list = ok). Size is always checked,
    the hash only when `hash` is true (the primary file takes ~2 min to hash)."""
    if not os.path.exists(path):
        return [f"{path}: missing"]
    size = os.path.getsize(path)
    if size != expected_size:
        return [f"{path}: size {size:,} differs from pinned {expected_size:,}"]
    if hash and expected_sha256:
        actual = sha256_file(path)
        if actual != expected_sha256:
            return [f"{path}: sha256 {actual[:16]}… differs from pinned {expected_sha256[:16]}…"]
    return []


def verify_source(manifest: dict, name: str, hash: bool = True, log=None) -> list[str]:
    src = manifest.get("sources", {}).get(name)
    if src is None:
        raise InputError(f"source {name!r} is not in the manifest")
    problems: list[str] = []
    for file in src["files"]:
        p = local_path(src, file)
        if log:
            log(f"  [inputs] verifying {p} ({file['size'] / 1e9:.2f} GB{', sha256' if hash else ', size only'})")
        problems += verify_file(p, file["size"], file.get("sha256"), hash=hash)
    return problems


def verify_or_raise(name: str, manifest_path: str = MANIFEST_PATH, hash: bool = True) -> None:
    manifest = load_manifest(manifest_path)
    problems = verify_source(manifest, name, hash=hash, log=lambda m: print(m, file=sys.stderr, flush=True))
    if problems:
        raise InputError("pinned input check failed:\n  " + "\n  ".join(problems) +
                         "\nRe-download with `inputs download`, or re-pin with `inputs pin` if the new "
                         "files are intended, or pass --skip-verify.")


# ------------------------------------------------------------------ download

def download_source(manifest: dict, name: str, log=print) -> list[str]:
    """Fetch every pinned file at the pinned commit into local_dir (hf_hub_download
    skips files that are already present and complete)."""
    from huggingface_hub import hf_hub_download

    src = manifest["sources"][name]
    paths = []
    for file in src["files"]:
        log(f"  [inputs] {src['repo_id']}@{src['revision'][:12]} {file['path']} ({file['size'] / 1e9:.2f} GB)")
        paths.append(hf_hub_download(src["repo_id"], file["path"], repo_type=src.get("repo_type", "dataset"),
                                     revision=src["revision"], local_dir=src["local_dir"]))
    return paths


# ----------------------------------------------------------------------- pin

def _pin_source(spec: dict, api) -> dict:
    """Resolve a source's ref to a commit and list its matching files with sizes
    and LFS SHA-256 values from the Hugging Face API."""
    info = api.dataset_info(spec["repo_id"], revision=spec.get("ref") or None, files_metadata=True)
    files = []
    for s in info.siblings:
        if not any(s.rfilename.endswith(ext) for ext in spec.get("patterns", [])):
            continue
        if s.size is None:
            raise InputError(f"{spec['repo_id']}: no size for {s.rfilename}; is the API answering with metadata?")
        files.append({"path": s.rfilename, "size": s.size, "sha256": s.lfs.sha256 if s.lfs else None})
    if not files:
        raise InputError(f"{spec['repo_id']}@{spec.get('ref')}: no files match {spec.get('patterns')}")
    files.sort(key=lambda f: f["path"])
    out = {k: spec[k] for k in ("repo_id", "repo_type", "ref", "local_dir", "patterns") if k in spec}
    out["local_dir"] = out["local_dir"].replace(os.sep, "/")  # portable manifest
    out["revision"] = info.sha
    out["last_modified"] = info.last_modified.isoformat() if getattr(info, "last_modified", None) else None
    out["files"] = files
    return out


def pin(manifest_path: str = MANIFEST_PATH, sources: Iterable[str] | None = None, api=None,
        check_local: bool = True, log=print) -> dict:
    """Write/refresh the manifest from the Hugging Face API. Existing local files
    are compared by size (and reported, not failed) so a stale download shows up."""
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi()
    manifest = load_manifest(manifest_path) if os.path.exists(manifest_path) else {"sources": {}}
    specs = dict(DEFAULT_SOURCES)
    for name, src in manifest.get("sources", {}).items():
        specs[name] = {k: src[k] for k in ("repo_id", "repo_type", "ref", "local_dir", "patterns") if k in src}
    for name in sources or specs:
        if name not in specs:
            raise InputError(f"unknown source {name!r}; known: {', '.join(specs)}")
        pinned = _pin_source(specs[name], api)
        manifest["sources"][name] = pinned
        log(f"{name}: {pinned['repo_id']}@{pinned['ref']} -> {pinned['revision']} ({len(pinned['files'])} files, "
            f"{sum(f['size'] for f in pinned['files']) / 1e9:.2f} GB)")
        if check_local:
            for p in verify_source(manifest, name, hash=False):
                log(f"  note: {p}")
    manifest["generated"] = _dt.date.today().isoformat()
    manifest["note"] = ("Pinned Hugging Face inputs. sha256 values are the LFS object ids (= file SHA-256). "
                        "Regenerate with `python -m baike2yomitan inputs pin`.")
    save_manifest(manifest, manifest_path)
    return manifest
