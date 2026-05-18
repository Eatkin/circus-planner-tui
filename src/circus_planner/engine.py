import datetime
import random
import sqlite3
from collections.abc import Generator
from typing import Any
from typing import Literal

from circus_planner.config import CONFIG
from circus_planner.models import Exercise
from circus_planner.models import ResolvedExercise


def get_available_exercises(
    conn: sqlite3.Connection,
    excluded_prop_types: list[str] | None = None,
) -> list[tuple[str, int]]:
    """Queries the database for available exercise types with their quantities according to the required equipment.
    Returns exercise id and weight
    """
    excluded_prop_types = excluded_prop_types or []

    with conn:
        # max available quantity per prop type
        max_qty = {
            row[0]: row[1]
            for row in conn.execute("""
                SELECT prop_type, MAX(quantity)
                FROM equipment
                WHERE enabled = 1
                GROUP BY prop_type
            """).fetchall()
        }

        # availability check (required equipment)
        rows = conn.execute("""
            SELECT DISTINCT e.id, e.prop_type, e.quantity_needed, e.priority + (10 - e.comfort) + 20*e.practicing as weight
            FROM exercise e
            LEFT JOIN exercise_required_equipment erq ON e.id = erq.exercise_id
            LEFT JOIN equipment eq ON erq.equipment_id = eq.id AND eq.enabled = 1
            WHERE erq.exercise_id IS NULL
               OR eq.enabled = 1
        """).fetchall()

    return [
        (row[0], row[3])
        for row in rows
        if row[1] not in excluded_prop_types
        and (row[2] == 0 or row[2] <= max_qty.get(row[1], 0))
    ]


def get_exercise(conn: sqlite3.Connection, exercise_id: str) -> dict[str, Any]:
    """Retrieves all exercise information from a given exercise id"""
    exercise = conn.execute(
        "SELECT * FROM exercise WHERE id = ?", (exercise_id,)
    ).fetchone()

    modifiers = conn.execute(
        """
        SELECT m.id, m.name, m.additive, m.requires_equipment_type, m.requires_quantity
        FROM modifier m
        JOIN exercise_modifier em ON m.id = em.modifier_id
        WHERE em.exercise_id = ?
    """,
        (exercise_id,),
    ).fetchall()

    required_equipment = conn.execute(
        """
        SELECT eq.id, eq.name, eq.prop_type, eq.quantity
        FROM equipment eq
        JOIN exercise_required_equipment ere ON eq.id = ere.equipment_id
        WHERE ere.exercise_id = ?
        AND eq.enabled = 1
    """,
        (exercise_id,),
    ).fetchall()

    # all enabled equipment that could be used for this exercise
    available_equipment = conn.execute(
        """
        SELECT id, name, prop_type, quantity, is_default
        FROM equipment
        WHERE prop_type = ? AND enabled = 1 AND quantity >= ?
    """,
        (exercise["prop_type"], exercise["quantity_needed"]),
    ).fetchall()

    return {
        "exercise": dict(exercise),
        "modifiers": [dict(m) for m in modifiers],
        "required_equipment": [dict(e) for e in required_equipment],
        "available_equipment": [dict(e) for e in available_equipment],
    }


def get_drill(conn: sqlite3.Connection, drill_id: str) -> dict[str, Any]:
    """Retrieves drill information, mapped to the same shape as get_exercise."""
    drill = conn.execute("SELECT * FROM drill WHERE id = ?", (drill_id,)).fetchone()
    modifiers = conn.execute(
        """
        SELECT m.id, m.name, m.additive, m.requires_equipment_type, m.requires_quantity
        FROM modifier m
        JOIN drill_modifier dm ON m.id = dm.modifier_id
        WHERE dm.drill_id = ?
        """,
        (drill_id,),
    ).fetchall()
    return {
        "exercise": {
            "id": drill["id"],
            "name": drill["name"],
            "prop_type": "drill",
            "quantity_needed": 0,
            "comfort": 5,
            "priority": 0,
            "practicing": 0,
            "always_modify": drill["always_modify"],
            "description": drill["description"],
        },
        "modifiers": [dict(m) for m in modifiers],
        "required_equipment": [],
        "available_equipment": [],
    }


def get_siteswap(conn: sqlite3.Connection, siteswap_id: str) -> dict[str, Any]:
    """Retrieves siteswap, mapped to the same shape as get_exercise."""
    row = conn.execute("SELECT * FROM siteswap WHERE id = ?", (siteswap_id,)).fetchone()
    # available ball equipment with sufficient quantity
    available_equipment = conn.execute(
        """
        SELECT id, name, prop_type, quantity, is_default
        FROM equipment
        WHERE prop_type = 'ball' AND enabled = 1 AND quantity >= ?
        """,
        (row["balls"],),
    ).fetchall()
    return {
        "exercise": {
            "id": row["id"],
            "name": row["pattern"],
            "prop_type": "siteswap",
            "quantity_needed": row["balls"],
            "comfort": row["comfort"],
            "priority": 0,
            "practicing": 0,
            "always_modify": 0,
            "description": f"Period {row['period']}, max throw {row['max_throw']}"
            + (f", entry {row['entry_throw']}" if row["entry_throw"] else "")
            + (f", exit {row['exit_throw']}" if row["exit_throw"] else ""),
        },
        "modifiers": [],
        "required_equipment": [],
        "available_equipment": [dict(e) for e in available_equipment],
    }


def weighted_shuffle(exercises: list[tuple[str, int]]) -> list[str]:
    remaining = list(exercises)
    result = []
    while remaining:
        ids, weights = zip(*remaining, strict=True)
        pick = random.choices(ids, weights=weights, k=1)[0]
        result.append(pick)
        remaining = [(i, w) for i, w in remaining if i != pick]
    return result


def exercise_queue(conn) -> Generator[str]:
    """Infinite queue of exercises"""
    while True:
        exercises = get_available_exercises(conn)
        shuffled = weighted_shuffle(exercises)
        yield from shuffled


def session_queue(
    conn: sqlite3.Connection,
) -> Generator[tuple[Literal["drill", "siteswap", "exercise"], str]]:
    since_last_drill = 0
    since_last_siteswap = 0

    while True:
        exercises = get_available_exercises(conn, CONFIG.disabled_equipment)
        shuffled = weighted_shuffle(exercises)

        for exercise_id in shuffled:
            since_last_drill += 1
            since_last_siteswap += 1

            # probability ramps up the longer since last injection
            drill_prob = (
                (since_last_drill / (11 - CONFIG.drill_frequency))
                if CONFIG.drill_frequency > 0
                else 0
            )
            siteswap_prob = (
                (since_last_siteswap / (11 - CONFIG.siteswap_frequency))
                if CONFIG.siteswap_frequency > 0
                else 0
            )

            # roll independently, no conflict possible
            if random.random() < drill_prob:
                drill = _get_random_drill(conn)
                if drill:
                    yield ("drill", drill)
                    since_last_drill = 0

            if random.random() < siteswap_prob:
                siteswap = _get_random_siteswap(conn)
                if siteswap:
                    yield ("siteswap", siteswap)
                    since_last_siteswap = 0

            yield ("exercise", exercise_id)


def _get_random_drill(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT id FROM drill WHERE active = 1 ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def _get_random_siteswap(conn: sqlite3.Connection) -> str | None:
    max_balls = _get_max_balls(conn)
    row = conn.execute(
        "SELECT id FROM siteswap WHERE balls <= ? ORDER BY RANDOM() LIMIT 1",
        (max_balls,),
    ).fetchone()
    return row[0] if row else None


def _get_max_balls(conn: sqlite3.Connection) -> int:
    row = conn.execute("""
        SELECT MAX(quantity) FROM equipment
        WHERE prop_type = 'ball' AND enabled = 1
    """).fetchone()
    return row[0] if row and row[0] else 0


def log_exercise(
    conn: sqlite3.Connection,
    session_id: str,
    exercise: Exercise,
    resolved: ResolvedExercise,
    timer_seconds: float,
    catches: list[int],
    comfort: int,
    notes: str,
) -> None:
    catches_granular = "|".join(str(c) for c in catches) if catches else None
    catches_max = max(catches) if catches else None
    modifiers = (
        "|".join(m.id for m in resolved.modifiers) if resolved.modifiers else None
    )

    conn.execute(
        """
        INSERT INTO session_log (
            session_id, logged_at, exercise_id,
            equipment_id, modifiers,
            catches_max, catches_granular,
            timer_seconds, comfort_before, comfort_after,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            session_id,
            datetime.datetime.now(datetime.UTC).isoformat(),
            exercise.id,
            resolved.equipment.id if resolved.equipment else None,
            modifiers,
            catches_max,
            catches_granular,
            round(timer_seconds, 1),
            exercise.comfort,
            comfort or None,
            notes or None,
        ),
    )
    conn.commit()
