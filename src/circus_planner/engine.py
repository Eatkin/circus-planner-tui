import random
import sqlite3
from collections.abc import Generator


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

def get_exercise(conn: sqlite3.Connection, exercise_id: str) -> dict:
    """Retrieves all exercise information from a given exercise id"""
    exercise = conn.execute(
        "SELECT * FROM exercise WHERE id = ?", (exercise_id,)
    ).fetchone()

    modifiers = conn.execute("""
        SELECT m.id, m.name, m.additive, m.requires_equipment_type, m.requires_quantity
        FROM modifier m
        JOIN exercise_modifier em ON m.id = em.modifier_id
        WHERE em.exercise_id = ?
    """, (exercise_id,)).fetchall()

    required_equipment = conn.execute("""
        SELECT eq.id, eq.name, eq.prop_type, eq.quantity
        FROM equipment eq
        JOIN exercise_required_equipment ere ON eq.id = ere.equipment_id
        WHERE ere.exercise_id = ?
        AND eq.enabled = 1
    """, (exercise_id,)).fetchall()

    # all enabled equipment that could be used for this exercise
    available_equipment = conn.execute("""
        SELECT id, name, prop_type, quantity, is_default
        FROM equipment
        WHERE prop_type = ? AND enabled = 1 AND quantity >= ?
    """, (exercise["prop_type"], exercise["quantity_needed"])).fetchall()

    return {
        "exercise": dict(exercise),
        "modifiers": [dict(m) for m in modifiers],
        "required_equipment": [dict(e) for e in required_equipment],
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
