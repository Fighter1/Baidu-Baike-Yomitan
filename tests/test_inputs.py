"""Pinned-input manifest: verification, download arguments and pinning (HF API stubbed)."""
import datetime
import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from baike2yomitan import inputs

SHA_HELLO = hashlib.sha256(b"hello").hexdigest()


def _manifest(tmp_path, sha=SHA_HELLO, size=5):
    d = tmp_path / "raw"
    d.mkdir(parents=True)
    (d / "a.json").write_bytes(b"hello")
    return {"sources": {"563w": {"repo_id": "o/r", "repo_type": "dataset", "ref": "main", "revision": "abc123",
                                 "local_dir": str(d), "files": [{"path": "a.json", "size": size, "sha256": sha}]}}}


def test_verify_ok_size_and_hash(tmp_path):
    m = _manifest(tmp_path)
    assert inputs.verify_source(m, "563w") == []
    assert inputs.verify_source(m, "563w", hash=False) == []


def test_verify_detects_size_hash_and_missing(tmp_path):
    assert inputs.verify_source(_manifest(tmp_path, size=6), "563w") == [
        f"{os.path.join(str(tmp_path / 'raw'), 'a.json')}: size 5 differs from pinned 6"]
    bad = inputs.verify_source(_manifest(tmp_path.joinpath("x"), sha="0" * 64), "563w")
    assert len(bad) == 1 and "sha256" in bad[0]
    # size-only mode does not notice a content change of equal length
    assert inputs.verify_source(_manifest(tmp_path.joinpath("y"), sha="0" * 64), "563w", hash=False) == []
    m = _manifest(tmp_path.joinpath("z"))
    os.remove(os.path.join(m["sources"]["563w"]["local_dir"], "a.json"))
    assert inputs.verify_source(m, "563w")[0].endswith("missing")
    with pytest.raises(inputs.InputError):
        inputs.verify_source(m, "nope")


def test_verify_or_raise_message(tmp_path):
    m = _manifest(tmp_path, size=99)
    p = tmp_path / "m.json"
    inputs.save_manifest(m, str(p))
    with pytest.raises(inputs.InputError, match="inputs download"):
        inputs.verify_or_raise("563w", str(p))
    with pytest.raises(inputs.InputError, match="not found"):
        inputs.load_manifest(str(tmp_path / "none.json"))


def test_download_uses_pinned_revision(tmp_path, monkeypatch):
    m = _manifest(tmp_path)
    calls = []

    def fake_download(repo_id, filename, repo_type=None, revision=None, local_dir=None):
        calls.append((repo_id, filename, repo_type, revision, local_dir))
        return os.path.join(local_dir, filename)

    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_download)
    inputs.download_source(m, "563w", log=lambda *_: None)
    assert calls == [("o/r", "a.json", "dataset", "abc123", m["sources"]["563w"]["local_dir"])]


class _FakeApi:
    def __init__(self):
        self.calls = []

    def dataset_info(self, repo_id, revision=None, files_metadata=False):
        self.calls.append((repo_id, revision, files_metadata))
        lfs = lambda sha: SimpleNamespace(sha256=sha)  # noqa: E731
        if repo_id == "lars1234/baidu-baike-dataset":
            sib = [SimpleNamespace(rfilename="README.md", size=1523, lfs=None),
                   SimpleNamespace(rfilename="563w_baidubaike.json", size=16833953491, lfs=lfs("8e9f" + "0" * 60))]
            return SimpleNamespace(sha="246e64b6", siblings=sib,
                                   last_modified=datetime.datetime(2025, 5, 6, tzinfo=datetime.timezone.utc))
        sib = [SimpleNamespace(rfilename="default/train/0001.parquet", size=20, lfs=lfs("b" * 64)),
               SimpleNamespace(rfilename="default/train/0000.parquet", size=10, lfs=lfs("a" * 64))]
        return SimpleNamespace(sha="e8eef91f", siblings=sib, last_modified=None)


def test_pin_writes_manifest_from_api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    api = _FakeApi()
    path = str(tmp_path / "data" / "source-inputs.json")
    logs = []
    m = inputs.pin(path, api=api, log=logs.append)
    assert set(api.calls) == {("lars1234/baidu-baike-dataset", "main", True),
                              ("mohamedah/baidu_baike", "refs/convert/parquet", True)}
    assert os.path.exists(path)
    on_disk = json.load(open(path, encoding="utf-8"))
    assert on_disk == m and m["generated"] == datetime.date.today().isoformat()
    p = m["sources"]["563w"]
    assert p["revision"] == "246e64b6" and [f["path"] for f in p["files"]] == ["563w_baidubaike.json"]
    assert p["files"][0]["sha256"].startswith("8e9f")
    h = m["sources"]["hf"]
    assert [f["path"] for f in h["files"]] == ["default/train/0000.parquet", "default/train/0001.parquet"]  # sorted
    # local files do not exist here → reported as notes, not failures
    assert any("missing" in line for line in logs)
    # re-pinning one source keeps the other and its spec
    m2 = inputs.pin(path, ["hf"], api=api, log=lambda *_: None)
    assert m2["sources"]["563w"]["revision"] == "246e64b6"
    with pytest.raises(inputs.InputError):
        inputs.pin(path, ["other"], api=api, log=lambda *_: None)


def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(bytes(range(256)) * 1000)
    assert inputs.sha256_file(str(p), chunk=1000) == hashlib.sha256(p.read_bytes()).hexdigest()
