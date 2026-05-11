import sqlite3
from pathlib import Path

import pytest

from circus_planner.db import create_schema
from circus_planner.db import seed_from_siteswaps
from circus_planner.db import seed_from_yaml


TOY_YAML = Path(__file__).parent / "fixtures" / "toy.yaml"
TOY_SITESWAPS = Path(__file__).parent / "fixtures" / "siteswaps"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    create_schema(c)
    seed_from_yaml(c, TOY_YAML)
    return c


@pytest.fixture
def conn_with_siteswaps(conn):
    TOY_SITESWAPS.mkdir(exist_ok=True)
    seed_from_siteswaps(conn, TOY_SITESWAPS)
    return conn
