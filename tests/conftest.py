import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@pytest.fixture(scope="session")
def rows_563w() -> list[dict]:
    with open(os.path.join(FIXTURES, "563w_rows.jsonl"), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.fixture(scope="session")
def rows_563w_by_title(rows_563w) -> dict[str, list[dict]]:
    d: dict[str, list[dict]] = {}
    for r in rows_563w:
        d.setdefault(r["title"], []).append(r)
    return d


@pytest.fixture(scope="session")
def overlay_rows() -> list[dict]:
    with open(os.path.join(FIXTURES, "overlay_rows.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def overlay_by_title(overlay_rows) -> dict[str, list[dict]]:
    d: dict[str, list[dict]] = {}
    for r in overlay_rows:
        d.setdefault(r["title"], []).append(r)
    return d


@pytest.fixture
def fixture_563w_path() -> str:
    return os.path.join(FIXTURES, "563w_rows.jsonl")
