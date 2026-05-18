from circus_planner.engine import log_exercise


class TestLogExercise:
    def _get_exercise_and_resolved(self, conn):
        """Helper - grab a known exercise and resolve it."""
        from circus_planner.engine import get_exercise
        from circus_planner.models import Exercise

        raw = get_exercise(conn, "three_ball_cascade")
        exercise = Exercise.from_db(raw)
        resolved = exercise.resolve(modifier_chance=0.0, equipment_swap_chance=0.0)
        return exercise, resolved

    def test_writes_row_to_db(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        log_exercise(conn, "test123", exercise, resolved, 45.0, [], 0, "")
        rows = conn.execute("SELECT * FROM session_log").fetchall()
        assert len(rows) == 1

    def test_catches_max_derived_from_list(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        log_exercise(conn, "test123", exercise, resolved, 30.0, [5, 12, 25, 18], 0, "")
        row = conn.execute("SELECT * FROM session_log").fetchone()
        assert row["catches_max"] == 25

    def test_catches_granular_pipe_separated(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        log_exercise(conn, "test123", exercise, resolved, 30.0, [5, 12, 25], 0, "")
        row = conn.execute("SELECT * FROM session_log").fetchone()
        assert row["catches_granular"] == "5|12|25"

    def test_empty_catches_logs_null(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        log_exercise(conn, "test123", exercise, resolved, 30.0, [], 0, "")
        row = conn.execute("SELECT * FROM session_log").fetchone()
        assert row["catches_max"] is None
        assert row["catches_granular"] is None

    def test_notes_written(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        log_exercise(conn, "test123", exercise, resolved, 30.0, [], 0, "felt good")
        row = conn.execute("SELECT * FROM session_log").fetchone()
        assert row["notes"] == "felt good"

    def test_empty_notes_logs_null(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        log_exercise(conn, "test123", exercise, resolved, 30.0, [], 0, "")
        row = conn.execute("SELECT * FROM session_log").fetchone()
        assert row["notes"] is None

    def test_comfort_before_is_exercise_comfort(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        log_exercise(conn, "test123", exercise, resolved, 30.0, [], 0, "")
        row = conn.execute("SELECT * FROM session_log").fetchone()
        assert row["comfort_before"] == exercise.comfort

    def test_comfort_after_written(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        log_exercise(conn, "test123", exercise, resolved, 30.0, [], 7, "")
        row = conn.execute("SELECT * FROM session_log").fetchone()
        assert row["comfort_after"] == 7

    def test_zero_comfort_after_logs_null(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        log_exercise(conn, "test123", exercise, resolved, 30.0, [], 0, "")
        row = conn.execute("SELECT * FROM session_log").fetchone()
        assert row["comfort_after"] is None

    def test_timer_seconds_rounded(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        log_exercise(conn, "test123", exercise, resolved, 45.678, [], 0, "")
        row = conn.execute("SELECT * FROM session_log").fetchone()
        assert row["timer_seconds"] == 45.7

    def test_session_id_written(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        log_exercise(conn, "mysession", exercise, resolved, 10.0, [], 0, "")
        row = conn.execute("SELECT * FROM session_log").fetchone()
        assert row["session_id"] == "mysession"

    def test_modifiers_pipe_separated(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        # force a modifier by resolving with high chance
        resolved = exercise.resolve(modifier_chance=1.0, equipment_swap_chance=0.0)
        if resolved.modifiers:
            log_exercise(conn, "test123", exercise, resolved, 10.0, [], 0, "")
            row = conn.execute("SELECT * FROM session_log").fetchone()
            expected = "|".join(m.id for m in resolved.modifiers)
            assert row["modifiers"] == expected

    def test_multiple_sessions_logged_separately(self, conn):
        exercise, resolved = self._get_exercise_and_resolved(conn)
        log_exercise(conn, "sess1", exercise, resolved, 10.0, [5], 0, "")
        log_exercise(conn, "sess2", exercise, resolved, 20.0, [10], 0, "")
        rows = conn.execute("SELECT * FROM session_log").fetchall()
        assert len(rows) == 2
        assert rows[0]["session_id"] == "sess1"
        assert rows[1]["session_id"] == "sess2"
