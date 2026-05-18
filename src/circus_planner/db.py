"""
Database module - schema, seeding from YAML, and query helpers.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import yaml


DB_PATH = Path(__file__).parent / "juggling.db"
YAML_PATH = Path(__file__).parent / "data" / "juggling.yaml"
SITESWAPS_DIR = Path(__file__).parent / "data" / "siteswaps"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Schema ────────────────────────────────────────────────────────────────


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS equipment (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            prop_type   TEXT NOT NULL,  -- ball, club, ring, balance, other
            quantity    INTEGER DEFAULT 1,
            is_default  INTEGER DEFAULT 0,  -- bool
            enabled     INTEGER DEFAULT 1   -- bool, toggle at runtime
        );

        CREATE TABLE IF NOT EXISTS modifier (
            id                    TEXT PRIMARY KEY,
            name                  TEXT NOT NULL,
            additive              INTEGER DEFAULT 0,  -- bool: stacks on top of exercise
            requires_equipment_type TEXT,             -- ball/club/ring, any of that type
            requires_quantity     INTEGER DEFAULT 0   -- extra quantity needed
        );

        -- which specific equipment items a modifier requires (any one of these suffices)
        CREATE TABLE IF NOT EXISTS modifier_equipment (
            modifier_id     TEXT NOT NULL REFERENCES modifier(id),
            equipment_id    TEXT NOT NULL REFERENCES equipment(id),
            PRIMARY KEY (modifier_id, equipment_id)
        );

        CREATE TABLE IF NOT EXISTS exercise (
            id                  TEXT PRIMARY KEY,
            name                TEXT NOT NULL,
            prop_type           TEXT NOT NULL,  -- ball, club, ring, balance, flow, drill
            quantity_needed     INTEGER DEFAULT 0,
            comfort             INTEGER DEFAULT 5,
            priority            INTEGER DEFAULT 0,
            practicing          INTEGER DEFAULT 0,  -- bool
            always_modify       INTEGER DEFAULT 0,  -- bool
            description         TEXT DEFAULT ''
        );

        -- which equipment an exercise requires to be doable at all (any one suffices)
        CREATE TABLE IF NOT EXISTS exercise_required_equipment (
            exercise_id     TEXT NOT NULL REFERENCES exercise(id),
            equipment_id    TEXT NOT NULL REFERENCES equipment(id),
            PRIMARY KEY (exercise_id, equipment_id)
        );

        -- which modifiers are available for an exercise
        CREATE TABLE IF NOT EXISTS exercise_modifier (
            exercise_id     TEXT NOT NULL REFERENCES exercise(id),
            modifier_id     TEXT NOT NULL REFERENCES modifier(id),
            PRIMARY KEY (exercise_id, modifier_id)
        );

        CREATE TABLE IF NOT EXISTS drill (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            description     TEXT DEFAULT '',
            always_modify   INTEGER DEFAULT 0,
            active          INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS drill_modifier (
            drill_id        TEXT NOT NULL REFERENCES drill(id),
            modifier_id     TEXT NOT NULL REFERENCES modifier(id),
            PRIMARY KEY (drill_id, modifier_id)
        );

        CREATE TABLE IF NOT EXISTS global_modifier (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS session_log (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id           TEXT NOT NULL,
            logged_at            TEXT NOT NULL,
            exercise_id          TEXT,
            drill_id             TEXT,
            equipment_id         TEXT,
            modifiers            TEXT,          -- pipe-separated modifier ids
            catches_max          INTEGER,
            catches_granular     TEXT,          -- pipe-separated e.g. "5|12|28"
            timer_seconds        REAL,
            comfort_before       INTEGER,
            comfort_after        INTEGER,
            notes                TEXT,
            video_path           TEXT
        );

        CREATE TABLE IF NOT EXISTS siteswap (
            id          TEXT PRIMARY KEY,  -- e.g. "5151" or "4_5151_2"
            pattern     TEXT NOT NULL,     -- raw string "4 5151 2"
            balls       INTEGER NOT NULL,
            period      INTEGER NOT NULL,
            max_throw   INTEGER NOT NULL,  -- derived from pattern itself
            entry_throw INTEGER,           -- 4 in "4 5151 2", null if clean entry
            exit_throw  INTEGER,           -- 2 in "4 5151 2", null if clean exit
            comfort     INTEGER DEFAULT 1  -- all start at 1, update as you practice
        );
    """)
    conn.commit()


# ── Seeding ───────────────────────────────────────────────────────────────


def seed_from_yaml(conn: sqlite3.Connection, yaml_path: Path = YAML_PATH) -> None:
    """
    Wipe and repopulate all static tables from juggling.yaml.
    session_log is never touched.
    """
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    # Clear static tables in dependency order
    conn.executescript("""
        DELETE FROM drill_modifier;
        DELETE FROM drill;
        DELETE FROM exercise_modifier;
        DELETE FROM exercise_required_equipment;
        DELETE FROM exercise;
        DELETE FROM modifier_equipment;
        DELETE FROM modifier;
        DELETE FROM equipment;
        DELETE FROM global_modifier;
        DELETE FROM siteswap;
    """)

    # Equipment
    for item in data.get("equipment", []):
        conn.execute(
            """
            INSERT INTO equipment (id, name, prop_type, quantity, is_default, enabled)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                item["name"],
                item["prop_type"],
                item.get("quantity", 1),
                int(item.get("default", False)),
                int(item.get("enabled", True)),
            ),
        )

    # Modifiers
    for mod in data.get("modifiers", []):
        conn.execute(
            """
            INSERT INTO modifier (id, name, additive, requires_equipment_type, requires_quantity)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                mod["id"],
                mod["name"],
                int(mod.get("additive", False)),
                mod.get("requires_equipment_type"),
                mod.get("requires_quantity", 0),
            ),
        )
        for eq_id in mod.get("requires_equipment", []):
            conn.execute(
                "INSERT INTO modifier_equipment (modifier_id, equipment_id) VALUES (?, ?)",
                (mod["id"], eq_id),
            )

    # Exercises
    for ex in data.get("exercises", []):
        conn.execute(
            """
            INSERT INTO exercise
                (id, name, prop_type, quantity_needed, comfort, priority,
                 practicing, always_modify, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ex["id"],
                ex["name"],
                ex["prop_type"],
                ex.get("quantity_needed", 0),
                ex.get("comfort", 5),
                ex.get("priority", 0),
                int(ex.get("practicing", False)),
                int(ex.get("always_modify", False)),
                ex.get("description", ""),
            ),
        )
        for eq_id in ex.get("requires_equipment", []):
            conn.execute(
                """
                INSERT INTO exercise_required_equipment (exercise_id, equipment_id)
                VALUES (?, ?)
                """,
                (ex["id"], eq_id),
            )
        for mod_id in ex.get("modifiers", []):
            conn.execute(
                "INSERT INTO exercise_modifier (exercise_id, modifier_id) VALUES (?, ?)",
                (ex["id"], mod_id),
            )

    # Drills
    for drill in data.get("drills", []):
        conn.execute(
            """
            INSERT INTO drill (id, name, description, always_modify, active)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                drill["id"],
                drill["name"],
                drill.get("description", ""),
                int(drill.get("always_modify", False)),
                int(drill.get("active", True)),
            ),
        )
        for mod_id in drill.get("modifiers", []):
            conn.execute(
                "INSERT INTO drill_modifier (drill_id, modifier_id) VALUES (?, ?)",
                (drill["id"], mod_id),
            )

    # Global modifiers
    for gm in data.get("global_modifiers", []):
        conn.execute("INSERT INTO global_modifier (name) VALUES (?)", (gm,))

    conn.commit()
    print(f"Seeded DB from {yaml_path}")


def seed_from_siteswaps(
    conn: sqlite3.Connection, siteswaps_dir: Path = SITESWAPS_DIR
) -> None:
    """
    Parse all siteswap-*.txt files and populate the siteswap table.
    Filename format: siteswap-{balls}-ball-{period}-period-{max}-max.txt
    Line format: either "5151" (clean) or "4  5151  2" (with entry/exit throws)
    """

    conn.execute("DELETE FROM siteswap")

    filename_re = re.compile(r"siteswap-(\d+)-ball-(\d+)-period-(\d+)-max\.txt")

    total = 0
    for filepath in sorted(siteswaps_dir.glob("siteswap-*.txt")):
        match = filename_re.match(filepath.name)
        if not match:
            continue

        balls = int(match.group(1))
        period = int(match.group(2))
        # max from filename - we'll also derive from pattern as a sanity check

        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Split on whitespace - could be 1, 2, or 3 tokens
                # "5151"       -> ["5151"]
                # "4 5151 2"   -> ["4", "5151", "2"]
                tokens = line.split()

                if len(tokens) == 1:
                    core = tokens[0]
                    entry_throw = None
                    exit_throw = None
                elif len(tokens) == 3:
                    entry_throw = int(tokens[0])
                    core = tokens[1]
                    exit_throw = int(tokens[2])
                else:
                    # Unexpected format, skip
                    continue

                # Only keep lines that are purely numeric
                if not re.fullmatch(r"\d+", core):
                    continue

                max_throw = max(int(d) for d in core)
                pattern = re.sub(
                    r"\s{2,}", " ", line
                )  # store the line with reduced spaces
                pattern_id = pattern.replace(" ", "_")

                conn.execute(
                    """
                    INSERT OR IGNORE INTO siteswap
                        (id, pattern, balls, period, max_throw, entry_throw, exit_throw, comfort)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        pattern_id,
                        pattern,
                        balls,
                        period,
                        max_throw,
                        entry_throw,
                        exit_throw,
                    ),
                )
                total += 1

    conn.commit()
    print(f"Seeded {total} siteswaps from {siteswaps_dir}")


# ── Startup ───────────────────────────────────────────────────────────────


def init_db(
    yaml_path: Path = YAML_PATH, siteswaps_dir: Path = SITESWAPS_DIR
) -> sqlite3.Connection:
    """Create schema and seed from YAML. Call once at startup."""
    conn = get_conn()
    create_schema(conn)
    seed_from_yaml(conn, yaml_path)
    seed_from_siteswaps(conn, siteswaps_dir)
    return conn


# ── Smoke test ────────────────────────────────────────────────────────────


if __name__ == "__main__":
    conn = init_db()

    print("\n-- Equipment --")
    for row in conn.execute("SELECT id, name, prop_type, quantity FROM equipment"):
        print(
            f"  {row['id']:<20} {row['name']:<35} {row['prop_type']:<8} qty={row['quantity']}"
        )

    print("\n-- Modifiers --")
    for row in conn.execute("SELECT id, name, additive FROM modifier"):
        tag = " [additive]" if row["additive"] else ""
        print(f"  {row['id']:<30} {row['name']}{tag}")

    print("\n-- Exercises --")
    for row in conn.execute(
        "SELECT id, name, prop_type, quantity_needed, comfort, priority FROM exercise"
    ):
        print(
            f"  {row['name']:<35} {row['prop_type']:<6} qty={row['quantity_needed']} comfort={row['comfort']} priority={row['priority']}"
        )

    print("\n-- Drills --")
    for row in conn.execute("SELECT id, name, active FROM drill"):
        active = "" if row["active"] else " [inactive]"
        print(f"  {row['name']}{active}")

    print("\n-- Siteswaps --")
    for row in conn.execute("""
        SELECT pattern, balls, period, max_throw, entry_throw, exit_throw
        FROM siteswap
        ORDER BY balls, max_throw, period
    """):
        print(
            f"  {row['pattern']}  ({row['balls']}b period={row['period']} max={row['max_throw']})"
        )

    conn.close()
