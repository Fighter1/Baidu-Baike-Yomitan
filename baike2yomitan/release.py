"""Publish the built zips as a GitHub release so Yomitan can update them itself.

How Yomitan auto-update works (Settings → Dictionaries → *Check for updates*):
the installed dictionary's index.json carries ``isUpdatable``, ``indexUrl`` and
``downloadUrl``. Yomitan fetches ``indexUrl``, compares its ``revision`` with the
installed one (numerically, when both are dot-separated integers with the same
number of segments) and, if newer, offers to download ``downloadUrl``.

GitHub's ``https://github.com/<owner>/<repo>/releases/latest/download/<asset>``
URL always redirects to that asset of the newest non-draft release, so it is a
stable ``indexUrl``/``downloadUrl``. ``build --update-url github`` bakes those
URLs into the zip; this module uploads the zip plus a sidecar
``<stem>.index.json`` (identical to the zip's index.json) with the ``gh`` CLI.

Nothing here talks to GitHub except through ``gh``; nothing is ever requested
from baike.baidu.com.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

GITHUB_ASSET_LIMIT = 2 * 1024 ** 3  # GitHub refuses release assets over 2 GiB
WRITE_PERMISSIONS = {"WRITE", "MAINTAIN", "ADMIN"}
_REMOTE_RES = [
    re.compile(r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"),
    re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"),
    re.compile(r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"),
]


class ReleaseError(Exception):
    pass


# ----------------------------------------------------------------- repository

def repo_from_remote_url(url: str) -> str:
    """'https://github.com/o/r.git' | 'git@github.com:o/r.git' → 'o/r'."""
    for rx in _REMOTE_RES:
        m = rx.match(url.strip())
        if m:
            return f"{m.group('owner')}/{m.group('repo')}"
    raise ReleaseError(f"not a GitHub remote URL: {url!r}")


def repo_from_git_remote(remote: str = "origin", cwd: str | None = None) -> str:
    try:
        url = subprocess.run(["git", "remote", "get-url", remote], cwd=cwd, check=True,
                             capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise ReleaseError(f"cannot read git remote {remote!r}: {e}; pass --repo owner/name") from e
    return repo_from_remote_url(url)


def github_release_base_url(repo: str) -> str:
    return f"https://github.com/{repo}/releases/latest/download"


def expected_urls(repo: str, stem: str) -> tuple[str, str]:
    from .build import update_urls

    return update_urls(github_release_base_url(repo), stem)


# ------------------------------------------------------------------ the zips

def zip_stem(zip_path: str) -> str:
    return os.path.splitext(os.path.basename(zip_path))[0]


def read_zip_index(zip_path: str) -> dict:
    with zipfile.ZipFile(zip_path) as zf:
        return json.loads(zf.read("index.json"))


def check_index_for_release(index: dict, repo: str, stem: str) -> list[str]:
    """Problems that would make Yomitan's update check fail for this zip."""
    problems = []
    index_url, download_url = expected_urls(repo, stem)
    if index.get("isUpdatable") is not True:
        problems.append("index.json has no isUpdatable: true")
    if index.get("indexUrl") != index_url:
        problems.append(f"indexUrl is {index.get('indexUrl')!r}, expected {index_url!r}")
    if index.get("downloadUrl") != download_url:
        problems.append(f"downloadUrl is {index.get('downloadUrl')!r}, expected {download_url!r}")
    from .build import check_revision

    try:
        check_revision(str(index.get("revision", "")))
    except ValueError as e:
        problems.append(str(e))
    return problems


def write_sidecar_index(zip_path: str, index: dict) -> str:
    """<stem>.index.json next to the zip, byte-for-byte the zip's index.json content."""
    from .build import sidecar_index_path

    path = sidecar_index_path(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        data = zf.read("index.json")
    assert json.loads(data) == index
    with open(path, "wb") as f:
        f.write(data)
    return path


# -------------------------------------------------------------- release notes

def _load_stats(stats_dir: str, name: str) -> dict:
    p = os.path.join(stats_dir, f"{name}.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def release_notes(zips: list[str], indexes: list[dict], stats_dir: str = os.path.join("data", "stats"),
                  today: _dt.date | None = None) -> str:
    today = today or _dt.date.today()
    lines = [f"Baidu Baike → Yomitan dictionaries, built {today.isoformat()}.", "",
             "| file | dictionary | revision | entries | traditional | term banks | size |",
             "|---|---|---|---:|---:|---:|---:|"]
    for z, idx in zip(zips, indexes):
        s = _load_stats(stats_dir, "build_" + zip_stem(z))
        size = s.get("zip_bytes") or (os.path.getsize(z) if os.path.exists(z) else 0)
        lines.append(f"| `{os.path.basename(z)}` | {idx.get('title', '')} | {idx.get('revision', '')} | "
                     f"{s.get('entries', 0):,} | {s.get('entries_traditional', 0):,} | "
                     f"{s.get('term_banks', 0):,} | {size / 1e6:,.0f} MB |")
    p, h, m = (_load_stats(stats_dir, n) for n in ("extract_563w", "extract_hf", "merge"))
    if p or h or m:
        lines += ["", "Records: primary {:,} · overlay {:,} · merged {:,} (see `data/extract_report.md`).".format(
            p.get("records_written", 0), h.get("records_written", 0), m.get("records_written", 0))]
    manifest_path = os.path.join(os.path.dirname(stats_dir.rstrip("/\\")) or ".", "source-inputs.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            srcs = json.load(f).get("sources", {})
        pins = ", ".join(f"`{s['repo_id']}@{s['revision'][:12]}`" for s in srcs.values() if s.get("revision"))
        if pins:
            lines += ["", f"Inputs pinned in `data/source-inputs.json`: {pins}."]
    lines += ["", "**Import:** Yomitan → Settings → Dictionaries → Import → pick the zip. "
              "**Update:** the zips are self-updating; Yomitan → Settings → Dictionaries → *Check for updates*.",
              "", "Content is Baidu Baike user-contributed material mirrored by third parties "
              "(lars1234/baidu-baike-dataset, mohamedah/baidu_baike); each entry links to its Baike article."]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------ gh

def _gh(args: list[str], *, capture: bool = True) -> str:
    """Run a gh command; raise ReleaseError with gh's stderr on failure."""
    try:
        r = subprocess.run(["gh", *args], check=True, capture_output=capture, text=True, encoding="utf-8")
    except FileNotFoundError as e:
        raise ReleaseError("the GitHub CLI `gh` is not installed or not on PATH (https://cli.github.com)") from e
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or "").strip() or "see gh's output above"
        raise ReleaseError(f"gh {' '.join(args[:2])} failed: {detail}") from e
    return r.stdout or ""


def repo_info(repo: str) -> dict:
    out = _gh(["repo", "view", repo, "--json", "isPrivate,viewerPermission,nameWithOwner"])
    return json.loads(out)


def repo_has_commits(repo: str) -> bool:
    """A release is attached to a git tag, so the repository needs at least one
    pushed commit (GitHub answers 409 'Git Repository is empty' otherwise)."""
    try:
        _gh(["api", f"repos/{repo}/commits?per_page=1", "--jq", "length"])
        return True
    except ReleaseError as e:
        if "empty" in str(e).lower() or "409" in str(e):
            return False
        raise


def release_exists(repo: str, tag: str) -> bool:
    try:
        _gh(["release", "view", tag, "--repo", repo, "--json", "tagName"])
        return True
    except ReleaseError as e:
        if "release not found" in str(e).lower() or "not found" in str(e).lower():
            return False
        raise


def _fmt(cmd: list[str]) -> str:
    return "gh " + " ".join(f'"{a}"' if " " in a else a for a in cmd)


# ------------------------------------------------------------------- driver

def release(zips: list[str], *, repo: str | None = None, tag: str | None = None, title: str | None = None,
            notes_file: str | None = None, draft: bool = False,
            dry_run: bool = False, stats_dir: str = os.path.join("data", "stats"),
            out=None) -> int:
    """Upload zips + sidecar index files as one GitHub release. Returns 0 on
    success; raises ReleaseError on any problem (in --dry-run, problems that gh
    would hit later are reported as warnings instead and the commands are printed)."""
    out = out or sys.stdout
    warnings: list[str] = []

    def problem(msg: str) -> None:
        if dry_run:
            warnings.append(msg)
        else:
            raise ReleaseError(msg)

    if not zips:
        raise ReleaseError("no zips given")
    for z in zips:
        if not os.path.exists(z):
            raise ReleaseError(f"{z} does not exist; run `build` first")
        if os.path.getsize(z) > GITHUB_ASSET_LIMIT:
            raise ReleaseError(f"{z} is {os.path.getsize(z) / 2**30:.2f} GiB; GitHub release assets must be ≤ 2 GiB")
    if shutil.which("gh") is None:
        problem("the GitHub CLI `gh` is not on PATH (https://cli.github.com); `gh auth login` after installing")

    repo = repo or repo_from_git_remote()
    print(f"repository: {repo}", file=out)

    info: dict = {}
    if shutil.which("gh"):
        try:
            info = repo_info(repo)
        except ReleaseError as e:
            problem(f"{e} — is `gh auth status` logged in to an account that can see {repo}?")
    if info:
        perm = info.get("viewerPermission")
        if perm not in WRITE_PERMISSIONS:
            problem(f"the gh account has {perm} access to {repo}; creating a release needs write access "
                    "(`gh auth login` / `gh auth switch` to the repository owner, or pass --repo)")
        if info.get("isPrivate"):
            warnings.append(f"{repo} is private: Yomitan cannot download assets from a private repository "
                            "(it sends no auth header), so auto-update will not work until it is public; "
                            "manual downloads still do.")

    if info and not repo_has_commits(repo):
        problem(f"{repo} has no commits. A release is a git tag, so commit and push the source first; "
                "the tag then records exactly which code built these zips.")

    indexes = []
    sidecars = []
    for z in zips:
        idx = read_zip_index(z)
        for p in check_index_for_release(idx, repo, zip_stem(z)):
            problem(f"{z}: {p}. Rebuild with `build --out {z} --update-url github` (or --update-url "
                    f"{github_release_base_url(repo)}) so the installed dictionary knows where to look.")
        indexes.append(idx)
        sidecars.append(write_sidecar_index(z, idx))
        print(f"  {z}: revision {idx.get('revision')}  title {idx.get('title')!r}", file=out)

    revisions = {str(i.get("revision")) for i in indexes}
    if len(revisions) > 1:
        warnings.append(f"zips carry different revisions {sorted(revisions)}; tagging with the first")
    tag = tag or f"v{indexes[0].get('revision')}"
    title = title or tag

    if notes_file is None:
        os.makedirs("dist", exist_ok=True)
        notes_file = os.path.join("dist", f"{tag}.notes.md")
        with open(notes_file, "w", encoding="utf-8") as f:
            f.write(release_notes(zips, indexes, stats_dir))
    assets = [a for pair in zip(zips, sidecars) for a in pair]

    exists = False
    if shutil.which("gh") and info:
        try:
            exists = release_exists(repo, tag)
        except ReleaseError as e:
            problem(str(e))
    if exists:
        cmds = [["release", "upload", tag, *assets, "--repo", repo, "--clobber"]]
        if not draft:
            cmds.append(["release", "edit", tag, "--repo", repo, "--latest", "--notes-file", notes_file])
    else:
        create = ["release", "create", tag, *assets, "--repo", repo, "--title", title, "--notes-file", notes_file]
        create += ["--draft"] if draft else ["--latest"]
        cmds = [create]

    if dry_run:
        print("\ndry run — would run:", file=out)
        for c in cmds:
            print("  " + _fmt(c), file=out)
        for w in warnings:
            print(f"\nWARNING: {w}", file=out)
        print(f"\nnotes written to {notes_file}; sidecar index files: {', '.join(sidecars)}", file=out)
        return 0

    for c in cmds:
        print("$ " + _fmt(c), file=out, flush=True)
        _gh(c, capture=False)
    for w in warnings:
        print(f"WARNING: {w}", file=out)
    index_url, download_url = expected_urls(repo, zip_stem(zips[0]))
    print(f"\nreleased {tag} to https://github.com/{repo}/releases/tag/{tag}", file=out)
    if draft:
        print("draft release: publish it on GitHub before the /releases/latest/download URLs resolve to it", file=out)
    else:
        print(f"check:  curl -L {index_url}", file=out)
        print("then in Yomitan: Settings → Dictionaries → Check for updates", file=out)
    return 0
