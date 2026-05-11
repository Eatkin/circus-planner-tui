"""
Tests for exercise retrieval and filtering logic.
All tests use the in-memory toy db from conftest.py.
"""

from circus_planner.engine import exercise_queue
from circus_planner.engine import get_available_exercises
from circus_planner.engine import weighted_shuffle


class TestBasicAvailability:
    def test_returns_list_of_ids(self, conn):
        result = get_available_exercises(conn)
        assert isinstance(result, list)
        assert all(isinstance(x, str) for x in [r[0] for r in result])

    def test_no_duplicates(self, conn):
        result = get_available_exercises(conn)
        assert len(result) == len(set(result))

    def test_standard_exercise_included(self, conn):
        result = get_available_exercises(conn)
        assert "three_ball_cascade" in [r[0] for r in result]

    def test_disabled_equipment_exercise_excluded(self, conn):
        result = get_available_exercises(conn)
        assert "broken_exercise" not in [r[0] for r in result]


class TestQuantityChecks:
    def test_five_ball_available_via_beanbags(self, conn):
        # beanbags have 9, so 5-ball should be available
        result = get_available_exercises(conn)
        assert "five_ball_cascade" in [r[0] for r in result]

    def test_five_ball_excluded_when_no_sufficient_balls(self, conn):
        # disable beanbags - only russians (4) remain, not enough for 5-ball
        conn.execute("UPDATE equipment SET enabled = 0 WHERE id = 'beanbags'")
        conn.commit()
        result = get_available_exercises(conn)
        assert "five_ball_cascade" not in [r[0] for r in result]

    def test_three_ball_still_available_without_beanbags(self, conn):
        conn.execute("UPDATE equipment SET enabled = 0 WHERE id = 'beanbags'")
        conn.commit()
        result = get_available_exercises(conn)
        assert "three_ball_cascade" in [r[0] for r in result]


class TestRequiredEquipment:
    def test_rolla_bolla_exercise_available_when_enabled(self, conn):
        result = get_available_exercises(conn)
        assert "rolla_bolla_endurance" in [r[0] for r in result]

    def test_rolla_bolla_exercise_excluded_when_disabled(self, conn):
        conn.execute("UPDATE equipment SET enabled = 0 WHERE id = 'rolla_bolla'")
        conn.commit()
        result = get_available_exercises(conn)
        assert "rolla_bolla_endurance" not in [r[0] for r in result]

    def test_unicycle_exercise_available(self, conn):
        result = get_available_exercises(conn)
        assert "unicycle_idling" in [r[0] for r in result]

    def test_exercise_with_no_required_equipment_always_available(self, conn):
        # three_ball_cascade has no requires_equipment rows
        result = get_available_exercises(conn)
        assert "three_ball_cascade" in [r[0] for r in result]


class TestPropTypeExclusion:
    def test_excludes_rings_when_windy(self, conn):
        result = get_available_exercises(conn, excluded_prop_types=["ring"])
        assert "three_ring_cascade" not in [r[0] for r in result]

    def test_excludes_clubs_and_rings_when_very_windy(self, conn):
        result = get_available_exercises(conn, excluded_prop_types=["ring", "club"])
        assert "three_ring_cascade" not in [r[0] for r in result]
        assert "three_club_cascade" not in [r[0] for r in result]

    def test_balls_still_available_when_windy(self, conn):
        result = get_available_exercises(conn, excluded_prop_types=["ring"])
        assert "three_ball_cascade" in [r[0] for r in result]


class TestWeightedShuffle:
    def test_returns_all_exercises_exactly_once(self):
        exercises = [("a", 1), ("b", 5), ("c", 10)]
        result = weighted_shuffle(exercises)
        assert sorted(result) == ["a", "b", "c"]

    def test_no_duplicates(self):
        exercises = [(str(i), i + 1) for i in range(20)]
        result = weighted_shuffle(exercises)
        assert len(result) == len(set(result))

    def test_empty_input(self):
        assert weighted_shuffle([]) == []

    def test_single_item(self):
        assert weighted_shuffle([("a", 99)]) == ["a"]

    def test_higher_weight_appears_earlier_on_average(self):
        # run 1000 times, high weight item should have lower mean position
        low = "low_weight"
        high = "high_weight"
        exercises = [(low, 1), (high, 100)]
        positions = []
        for _ in range(1000):
            result = weighted_shuffle(exercises)
            positions.append(result.index(high))
        assert sum(positions) / len(positions) < 0.3  # appears first ~97% of the time


class TestExerciseQueue:
    def test_yields_all_exercises_before_repeating(self, conn):
        available = [ex[0] for ex in get_available_exercises(conn)]
        queue = exercise_queue(conn)
        first_cycle = [next(queue) for _ in range(len(available))]
        assert sorted(first_cycle) == sorted(available)

    def test_reseeds_after_exhaustion(self, conn):
        available = get_available_exercises(conn)
        n = len(available)
        queue = exercise_queue(conn)
        # consume two full cycles
        seen = [next(queue) for _ in range(n * 2)]
        # second cycle should also contain all exercises
        second_cycle = seen[n:]
        assert sorted(second_cycle) == sorted([ex[0] for ex in available])

    def test_is_infinite(self, conn):
        queue = exercise_queue(conn)
        # just assert we can pull a lot without error
        for _ in range(200):
            next(queue)
