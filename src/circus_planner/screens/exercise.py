import time
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import Label
from textual.widgets import Static

from circus_planner.db import get_conn
from circus_planner.engine import exercise_queue
from circus_planner.engine import get_exercise
from circus_planner.models import Exercise
from circus_planner.screens import BaseScreen


class TimerWidget(Static):
    elapsed: reactive[float] = reactive(0.0)
    running: reactive[bool] = reactive(False)

    def __init__(self, **kwargs):
        super().__init__("⏹️ 00:00", **kwargs)
        self._start: float | None = None
        self._accumulated: float = 0.0

    def on_mount(self) -> None:
        self.set_interval(0.5, self._tick)

    def _tick(self) -> None:
        if self.running and self._start is not None:
            self.elapsed = self._accumulated + (time.monotonic() - self._start)
        emoji = "▶️" if self.running else "⏸️"

        if self.elapsed == 0.0:
            emoji = "⏹️"
        m, s = divmod(int(self.elapsed), 60)
        self.update(f"{emoji} {m:02d}:{s:02d}")

    def toggle(self) -> None:
        if self.running:
            if self._start is not None:
                self._accumulated += time.monotonic() - self._start
                self._start = None
            self.running = False
        else:
            self._start = time.monotonic()
            self.running = True

    def reset(self) -> float:
        if self.running:
            self.toggle()
        total = self._accumulated
        self._accumulated = 0.0
        self.elapsed = 0.0
        self.update("⏹️ 00:00")
        return total


class ExerciseScreen(BaseScreen):
    DEFAULT_CSS = """
    ExerciseScreen {
        align: center top;
        padding: 1 4;
    }
    #app-title {
        text-align: center;
        color: $text-muted;
        width: 100%;
        margin-bottom: 1;
    }
    #exercise-name {
        text-align: center;
        text-style: bold;
        color: $accent;
        width: 100%;
    }
    #meta {
        text-align: center;
        color: $text-muted;
        width: 100%;
    }
    #description {
        text-align: center;
        color: $text-muted;
        text-style: italic;
        width: 100%;
        margin-top: 1;
    }
    #stats {
        text-align: center;
        width: 100%;
        margin-top: 1;
    }
    #equipment {
        text-align: center;
        color: $text-muted;
        width: 100%;
        margin-top: 1;
    }
    #modifiers {
        text-align: center;
        width: 100%;
        margin-top: 1;
    }
    TimerWidget {
        text-align: center;
        text-style: bold;
        color: $accent;
        width: 100%;
        margin-top: 2;
    }
    #timer-status {
        text-align: center;
        color: $text-muted;
        width: 100%;
    }
    #reroll-hint {
        text-align: center;
        color: $text-muted;
        width: 100%;
        margin-top: 1;
    }
    """

    BINDINGS: ClassVar = [
        Binding("space", "toggle_timer", "Start/Pause", priority=True),
        Binding("n", "next_exercise", "Next", priority=True),
        Binding("s", "skip_exercise", "Skip", priority=True),
        Binding("r", "reroll", "Re-roll", priority=True),
        Binding("q", "quit_session", "Quit", priority=True),
    ]

    def on_mount(self) -> None:
        self._conn = get_conn()
        self._queue = exercise_queue(self._conn)
        self._load_next()

    def _load_next(self) -> None:
        self.query_one(TimerWidget).reset()
        exercise_id = next(self._queue)
        raw = get_exercise(self._conn, exercise_id)
        self._exercise = Exercise.from_db(raw)
        self._resolved = self._exercise.resolve()
        self._update_display()

    def _update_display(self) -> None:
        r = self._resolved
        e = r.exercise

        self.query_one("#exercise-name", Label).update(f"✦  {e.name}  ✦")

        meta_parts = [e.prop_type]
        if e.practicing:
            meta_parts.append("practicing")
        self.query_one("#meta", Label).update("  ·  ".join(meta_parts))

        self.query_one("#description", Label).update(e.description or "")

        filled = e.comfort
        bar = "█" * filled + "░" * (10 - filled)
        priority_bar = "■" * e.priority + "□" * (10 - e.priority)
        self.query_one("#stats", Label).update(
            f"comfort  😬 {bar} 😎  {e.comfort}/10\n"
            f"priority  [{priority_bar}]  {e.priority}/10"
        )

        eq = f"🎒  {r.equipment.name}" if r.equipment else ""
        self.query_one("#equipment", Label).update(eq)

        if r.modifiers:
            mods = "  ·  ".join(m.name for m in r.modifiers)
            self.query_one("#modifiers", Label).update(f"🎲  {mods}")
        else:
            self.query_one("#modifiers", Label).update("🎲  no modifiers")

        self.query_one("#timer-status", Label).update("space to start")

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("🤹  circus planner  —  session", id="app-title")
        yield Label("", id="exercise-name")
        yield Label("", id="meta")
        yield Label("", id="description")
        yield Label("", id="stats")
        yield Label("", id="equipment")
        yield Label("", id="modifiers")
        yield TimerWidget(id="main-timer")
        yield Label("", id="timer-status")
        yield Label("r to re-roll modifiers / equipment", id="reroll-hint")
        yield Footer()

    def action_toggle_timer(self) -> None:
        timer = self.query_one(TimerWidget)
        timer.toggle()
        status = (
            "running  —  space to pause"
            if timer.running
            else "paused  —  space to resume"
        )
        self.query_one("#timer-status", Label).update(status)

    def action_next_exercise(self) -> None:
        self._load_next()

    def action_skip_exercise(self) -> None:
        self._load_next()

    def action_reroll(self) -> None:
        self._resolved = self._exercise.resolve()
        self._update_display()

    def action_quit_session(self) -> None:
        self.app.pop_screen()
