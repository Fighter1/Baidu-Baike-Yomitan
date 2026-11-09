"""Self-updating index.json fields and the GitHub release driver (gh is stubbed)."""
import json
import os
import zipfile

import pytest

from baike2yomitan import release as rel
from baike2yomitan.build import (build, check_revision, default_revision, make_index,
                                 sidecar_index_path, update_urls)
from baike2yomitan.records import Record, RecordWriter
from baike2yomitan.validate import validate_zip

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "schemas")
REPO = "someone/baike-yomitan"
BASE = "https://github.com/someone/baike-yomitan/releases/latest/download"


def test_repo_from_remote_url_variants():
    for url in ("https://github.com/someone/baike-yomitan.git", "https://github.com/someone/baike-yomitan",
                "git@github.com:someone/baike-yomitan.git", "ssh://git@github.com/someone/baike-yomitan.git\n"):
        assert rel.repo_from_remote_url(url) == REPO
    with pytest.raises(rel.ReleaseError):
        rel.repo_from_remote_url("https://gitlab.com/someone/baike-yomitan.git")


def test_update_urls_and_revision_rules():
    assert rel.github_release_base_url(REPO) == BASE
    assert update_urls(BASE + "/", "baike-full") == (BASE + "/baike-full.index.json", BASE + "/baike-full.zip")
    assert check_revision("2026.11.08") == "2026.11.08"
    assert default_revision(__import__("datetime").date(2026, 11, 8)) == "2026.11.08.1"
    for bad in ("1.0.0-alpha", "v1", "2026.11.", ""):
        with pytest.raises(ValueError):
            check_revision(bad)


def test_make_index_updatable_fields():
    plain = make_index("T", merged=False)
    assert "isUpdatable" not in plain and "indexUrl" not in plain
    idx = make_index("T", merged=True, revision="2026.11.08", update_base_url=BASE, stem="baike-full")
    assert idx["isUpdatable"] is True
    assert idx["indexUrl"] == BASE + "/baike-full.index.json"
    assert idx["downloadUrl"] == BASE + "/baike-full.zip"
    assert idx["revision"] == "2026.11.08"
    with pytest.raises(ValueError):
        make_index("T", merged=False, update_base_url=BASE)  # stem required


def _records(path):
    with RecordWriter(str(path)) as w:
        w.write(Record(source="563w", title="红色食品", summary="红色食品是指颜色为红色的食品，如西红柿、红枣等。",
                       sense_label="", lemma_id=1, tags=[], url="https://baike.baidu.com/view/1.htm", quality_flags=[]))


def test_build_writes_updatable_index_and_sidecar(tmp_path):
    _records(tmp_path / "r.jsonl")
    out = tmp_path / "dist" / "baike-full.zip"
    build(str(tmp_path / "r.jsonl"), str(out), revision="2026.11.08", update_base_url=BASE)
    errors = validate_zip(str(out), SCHEMA_DIR)
    assert errors == []
    with zipfile.ZipFile(out) as zf:
        idx = json.loads(zf.read("index.json"))
        raw = zf.read("index.json")
    assert idx["isUpdatable"] is True and idx["downloadUrl"] == BASE + "/baike-full.zip"
    side = sidecar_index_path(str(out))
    assert os.path.exists(side) and open(side, "rb").read() == raw
    assert rel.check_index_for_release(idx, REPO, "baike-full") == []
    problems = rel.check_index_for_release(idx, "other/repo", "baike-full")
    assert len(problems) == 2 and all("expected" in p for p in problems)


def test_check_index_reports_missing_fields():
    problems = rel.check_index_for_release({"revision": "2026.11.08"}, REPO, "baike-full")
    assert any("isUpdatable" in p for p in problems)
    assert any("indexUrl" in p for p in problems) and any("downloadUrl" in p for p in problems)


def test_release_notes_table(tmp_path):
    (tmp_path / "build_baike-full.json").write_text(json.dumps(
        {"entries": 8817011, "entries_traditional": 3928236, "term_banks": 882, "zip_bytes": 1304878197}), "utf-8")
    (tmp_path / "merge.json").write_text(json.dumps({"records_written": 4888775}), "utf-8")
    notes = rel.release_notes(["dist/baike-full.zip"], [{"title": "T", "revision": "2026.11.08"}],
                              stats_dir=str(tmp_path), today=__import__("datetime").date(2026, 11, 8))
    assert "| `baike-full.zip` | T | 2026.11.08 | 8,817,011 | 3,928,236 | 882 | 1,305 MB |" in notes
    assert "merged 4,888,775" in notes and "personal" not in notes
    assert "source-inputs" not in notes
    (tmp_path.parent / "source-inputs.json").write_text(json.dumps(
        {"sources": {"563w": {"repo_id": "lars1234/baidu-baike-dataset", "revision": "246e64b6c441a7d0"}}}), "utf-8")
    notes = rel.release_notes(["dist/baike-full.zip"], [{"title": "T", "revision": "2026.11.08"}], stats_dir=str(tmp_path))
    assert "`lars1234/baidu-baike-dataset@246e64b6c441`" in notes


class _FakeGh:
    """Stand-in for the gh CLI: records calls, answers repo view / release view."""

    def __init__(self, perm="ADMIN", private=True, existing=(), empty=False):
        self.perm, self.private, self.existing, self.calls = perm, private, set(existing), []
        self.empty = empty

    def __call__(self, args, capture=True):
        self.calls.append(args)
        if args[0] == "api" and "/commits" in args[1]:
            if self.empty:
                raise rel.ReleaseError("gh api failed: gh: Git Repository is empty. (HTTP 409)")
            return "1"
        if args[:2] == ["repo", "view"]:
            return json.dumps({"isPrivate": self.private, "viewerPermission": self.perm, "nameWithOwner": args[2]})
        if args[:2] == ["release", "view"]:
            if args[2] in self.existing:
                return json.dumps({"tagName": args[2]})
            raise rel.ReleaseError("gh release view failed: release not found")
        return ""


@pytest.fixture
def built_zip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _records(tmp_path / "r.jsonl")
    out = tmp_path / "dist" / "baike-lexical.zip"
    build(str(tmp_path / "r.jsonl"), str(out), revision="2026.11.08", update_base_url=BASE)
    monkeypatch.setattr(rel.shutil, "which", lambda name: "/usr/bin/gh")
    return str(out)


def test_release_creates_new_release(built_zip, monkeypatch, capsys):
    gh = _FakeGh()
    monkeypatch.setattr(rel, "_gh", gh)
    rc = rel.release([built_zip], repo=REPO, stats_dir="nowhere")
    assert rc == 0
    create = [c for c in gh.calls if c[:2] == ["release", "create"]]
    assert len(create) == 1
    c = create[0]
    assert c[2] == "v2026.11.08" and "--latest" in c and "--draft" not in c
    assert built_zip in c and sidecar_index_path(built_zip) in c
    notes = c[c.index("--notes-file") + 1]
    assert os.path.exists(notes) and "baike-lexical.zip" in open(notes, encoding="utf-8").read()
    assert "released v2026.11.08" in capsys.readouterr().out


def test_release_uploads_to_existing_tag_with_clobber(built_zip, monkeypatch):
    gh = _FakeGh(existing={"v2026.11.08"})
    monkeypatch.setattr(rel, "_gh", gh)
    rel.release([built_zip], repo=REPO, stats_dir="nowhere")
    kinds = [tuple(c[:2]) for c in gh.calls]
    assert ("release", "upload") in kinds and ("release", "edit") in kinds and ("release", "create") not in kinds
    upload = next(c for c in gh.calls if c[:2] == ["release", "upload"])
    assert "--clobber" in upload


def test_release_refuses_read_access_and_warns_on_private(built_zip, monkeypatch, capsys):
    monkeypatch.setattr(rel, "_gh", _FakeGh(perm="READ"))
    with pytest.raises(rel.ReleaseError, match="READ access"):
        rel.release([built_zip], repo=REPO, stats_dir="nowhere")
    # a public repository needs no acknowledgement; a private one only gets a warning
    gh = _FakeGh(private=False)
    monkeypatch.setattr(rel, "_gh", gh)
    assert rel.release([built_zip], repo=REPO, stats_dir="nowhere") == 0
    assert any(c[:2] == ["release", "create"] for c in gh.calls)
    assert "WARNING" not in capsys.readouterr().out
    monkeypatch.setattr(rel, "_gh", _FakeGh(private=True))
    assert rel.release([built_zip], repo=REPO, stats_dir="nowhere") == 0
    assert "private" in capsys.readouterr().out


def test_release_dry_run_reports_problems_without_uploading(built_zip, monkeypatch, capsys):
    gh = _FakeGh(perm="READ", private=False)
    monkeypatch.setattr(rel, "_gh", gh)
    # wrong repo → the baked-in URLs do not match either
    rc = rel.release([built_zip], repo="other/repo", dry_run=True, stats_dir="nowhere")
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry run" in out and "WARNING" in out and "READ access" in out
    assert "--update-url github" in out
    assert not any(c[:2] in (["release", "create"], ["release", "upload"]) for c in gh.calls)


def test_release_in_github_actions_skips_permission_probe(built_zip, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    gh = _FakeGh(perm=None, private=False)   # the workflow token reports no viewerPermission
    monkeypatch.setattr(rel, "_gh", gh)
    monkeypatch.setattr(rel, "repo_from_git_remote", lambda *a, **k: pytest.fail("git remote should not be read"))
    assert rel.release([built_zip], stats_dir="nowhere") == 0   # repo taken from GITHUB_REPOSITORY
    out = capsys.readouterr().out
    assert "(GitHub Actions)" in out and "permission probe skipped" in out
    assert any(c[:2] == ["release", "create"] and "--repo" in c and c[c.index("--repo") + 1] == REPO
               for c in gh.calls)


def test_release_rejects_zip_without_update_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _records(tmp_path / "r.jsonl")
    out = tmp_path / "dist" / "baike-full.zip"
    build(str(tmp_path / "r.jsonl"), str(out))  # no --update-url
    monkeypatch.setattr(rel.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(rel, "_gh", _FakeGh())
    with pytest.raises(rel.ReleaseError, match="isUpdatable"):
        rel.release([str(out)], repo=REPO, stats_dir="nowhere")


def test_release_refuses_empty_repository(built_zip, monkeypatch):
    gh = _FakeGh(empty=True)
    monkeypatch.setattr(rel, "_gh", gh)
    with pytest.raises(rel.ReleaseError, match="no commits"):
        rel.release([built_zip], repo=REPO, stats_dir="nowhere")
    assert not any(c[:2] == ["release", "create"] for c in gh.calls)
