import json
import sys
import types
from pathlib import Path
import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[2]
NL_POC = ROOT / "nl-poc"
if str(NL_POC) not in sys.path:
    sys.path.insert(0, str(NL_POC))

if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")

    def _safe_load(stream):
        if hasattr(stream, "read"):
            text = stream.read()
        else:
            text = stream
        text = (text or "").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    yaml_stub.safe_load = _safe_load  # type: ignore[attr-defined]
    sys.modules["yaml"] = yaml_stub

from app.canonical.store import CanonicalStore
from app.executor import DuckDBExecutor
from app.resolver import SemanticDimension, SemanticMetric, SemanticModel


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "canonical.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        """
        CREATE TABLE games (
            Title TEXT,
            Platform TEXT
        )
        """
    )
    con.execute(
        "INSERT INTO games VALUES (?, ?), (?, ?), (?, ?), (?, ?)",
        [
            "Mortal Kombat 1",
            "Arcade",
            "Mortal Kombat II",
            "Arcade",
            "Street Fighter",
            "Arcade",
            "Mario Kart",
            "Console",
        ],
    )
    con.execute(
        """
        CREATE TABLE "la_crime_raw" (
            "AREA NAME" TEXT,
            "Crm Cd Desc" TEXT,
            "Premis Desc" TEXT,
            "Weapon Desc" TEXT,
            "Vict Age" INTEGER,
            "DATE OCC" DATE
        )
        """
    )
    con.execute(
        "INSERT INTO la_crime_raw VALUES (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?)",
        [
            "Central",
            "Robbery",
            "Street",
            "Firearm",
            32,
            "2024-01-01",
            "Downtown",
            "Robbery",
            "Street",
            "Unknown",
            28,
            "2024-01-02",
            "Harbor",
            "Assault",
            "Store",
            "Knife",
            41,
            "2024-02-10",
            "Mission",
            "Burglary",
            "House",
            "None",
            38,
            "2024-03-12",
        ],
    )
    con.close()
    return path


@pytest.fixture()
def executor(db_path: Path) -> DuckDBExecutor:
    return DuckDBExecutor(db_path)


@pytest.fixture()
def games_semantic() -> SemanticModel:
    dimensions = {
        "title": SemanticDimension(name="title", column="Title"),
    }
    metrics = {
        "count": SemanticMetric(name="count", agg="count", grain=["title"]),
    }
    return SemanticModel(table="games", date_grain="month", dimensions=dimensions, metrics=metrics)


@pytest.fixture()
def crime_semantic() -> SemanticModel:
    dimensions = {
        "area": SemanticDimension(name="area", column="AREA NAME"),
        "weapon": SemanticDimension(name="weapon", column="Weapon Desc"),
    }
    metrics = {
        "count": SemanticMetric(name="count", agg="count", grain=["area"]),
    }
    return SemanticModel(table="la_crime_raw", date_grain="month", dimensions=dimensions, metrics=metrics)


@pytest.fixture()
def make_store(executor: DuckDBExecutor):
    def _make(semantic: SemanticModel) -> CanonicalStore:
        return CanonicalStore(executor, semantic)

    return _make
