import csv
import sys
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CSV_PATH = DATA_DIR / "canonical_fixture.csv"
DB_PATH = DATA_DIR / "games.duckdb"


@pytest.fixture()
def client() -> Iterator[TestClient]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    with CSV_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "DATE OCC",
            "AREA NAME",
            "Crm Cd Desc",
            "Premis Desc",
            "Weapon Desc",
            "DR_NO",
            "Vict Age",
        ])
        writer.writerow([
            "2024-01-01",
            "Downtown",
            "Robbery",
            "Street",
            "None",
            "1",
            "34",
        ])
        writer.writerow([
            "2024-01-02",
            "Hollywood",
            "Burglary",
            "Shop",
            "Knife",
            "2",
            "29",
        ])
    with TestClient(app) as test_client:
        yield test_client
    if CSV_PATH.exists():
        CSV_PATH.unlink()
    if DB_PATH.exists():
        DB_PATH.unlink()


def test_json_search_smoke(client: TestClient) -> None:
    response = client.get("/api/admin/canonical", params={"dim": "area", "q": "holly"})
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload, "expected at least one candidate"
    assert any(item["candidate"] == "Hollywood" for item in payload)


def test_promote_roundtrip(client: TestClient) -> None:
    promote_payload = {
        "dim": "area",
        "synonym": "hollywd",
        "canonical": "Hollywood",
        "score": 0.9,
    }
    response = client.post("/api/admin/canonical/promote", json=promote_payload)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    resolution = app.state.canonicalizer.resolve("area", "hollywd")
    assert resolution.applied is True
    assert resolution.value == "Hollywood"
    search = client.get("/api/admin/canonical", params={"dim": "area", "q": "hollywd"})
    assert search.status_code == 200
    candidates = search.json()
    assert any(item["canonical"] == "Hollywood" for item in candidates)
