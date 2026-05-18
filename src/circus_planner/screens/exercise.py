import subprocess
import time
from typing import ClassVar
from uuid import uuid4

from textual.app import ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import Label
from textual.widgets import Static

from circus_planner.common import SKIP_THRESHOLD
from circus_planner.db import get_conn
from circus_planner.engine import get_drill
from circus_planner.engine import get_exercise
from circus_planner.engine import get_siteswap
from circus_planner.engine import log_exercise
from circus_planner.engine import session_queue
from circus_planner.models import Exercise
from circus_planner.screens import BaseScreen
from circus_planner.screens.modals import CatchInputModal
from circus_planner.screens.modals import QuickCatchModal


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
    #juggling-lab-hint {
        text-align: center;
        color: $accent;
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
    #catches-count {
        text-align: center;
        color: $text-muted;
        width: 100%;
        margin-top: 1;
    }
    #reroll-hint {
        text-align: center;
        color: $accent;
        width: 100%;
        margin-top: 1;
    }
    """

    BINDINGS: ClassVar = [
        Binding("space", "toggle_timer", "Start/Pause", priority=True),
        Binding("n", "next_exercise", "Next", priority=True),
        Binding("s", "skip_exercise", "Skip", priority=True),
        Binding("g", "toggle_granular", "Granular", priority=True),
        Binding("r", "reroll", "Re-roll", priority=True),
        Binding("j", "open_juggling_lab", "Quit", priority=True, show=False),
        Binding("q", "quit_session", "Quit", priority=True),
    ]
    granular_catches: reactive[bool] = reactive(False)

    def on_mount(self) -> None:
        self._conn = get_conn()
        self._queue = session_queue(self._conn)
        self._catches: list[int] = []
        self._comfort = 0
        self._notes = ""
        self._session_id = str(uuid4())
        self._load_next()

    def _load_next(self) -> None:
        self.query_one(TimerWidget).reset()
        kind, item_id = next(self._queue)
        if kind == "exercise":
            raw = get_exercise(self._conn, item_id)
            self._exercise = Exercise.from_db(raw)
        elif kind == "drill":
            raw = get_drill(self._conn, item_id)
            self._exercise = Exercise.from_db(raw)
        elif kind == "siteswap":
            raw = get_siteswap(self._conn, item_id)
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

        if "siteswap" in self._exercise.prop_type:
            core = self._exercise.extract_core_pattern()
            self.query_one("#juggling-lab-hint", Label).update(
                f"j to open {core} in JugglingLab"
            )
        else:
            self.query_one("#juggling-lab-hint", Label).update("")

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
        self.query_one("#catches-count", Label).update("")

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("🤹  circus planner  —  session", id="app-title")
        yield Label("", id="exercise-name")
        yield Label("", id="meta")
        yield Label("", id="juggling-lab-hint")
        yield Label("", id="description")
        yield Label("", id="stats")
        yield Label("", id="equipment")
        yield Label("", id="modifiers")
        yield TimerWidget(id="main-timer")
        yield Label("", id="timer-status")
        yield Label("", id="catches-count")
        yield Label(
            "r to re-roll modifiers / equipment • g to enter granular catches",
            id="reroll-hint",
        )
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
        def on_dismiss(row: tuple[int | None, str | None, int | None]) -> None:
            catches, notes, comfort = row
            if catches:
                self._catches.append(catches)
            if notes:
                self._notes = notes
            self._comfort = comfort if comfort is not None else self._exercise.comfort
            self._log_exercise()
            self._load_next()
            self._catches = []
            self._comfort = 0
            self._notes = ""

        self.app.push_screen(  # ty: ignore
            CatchInputModal(
                show_catches=self._exercise.prop_type in ("ball", "club", "ring")
            ),
            callback=on_dismiss,
        )

    def action_skip_exercise(self) -> None:
        self._catches = []
        self._comfort = 0
        self._notes = ""
        if self.query_one(TimerWidget).elapsed > SKIP_THRESHOLD:
            self.action_next_exercise()
        else:
            self._load_next()

    def action_reroll(self) -> None:
        if self.query_one(TimerWidget).elapsed > 0:
            return
        self._resolved = self._exercise.resolve()
        self._update_display()

    def action_quit_session(self) -> None:
        self.app.pop_screen()

    def action_toggle_granular(self) -> None:
        self.query_one(TimerWidget).toggle()  # pause

        def on_dismiss(catch: int | None) -> None:
            self.query_one(TimerWidget).toggle()  # resume
            if catch is not None:
                self._catches.append(catch)
                label = "🖐️ Catches: " + ", ".join(
                    str(t) for t in sorted(self._catches[-5:])
                )
                self.query_one("#catches-count", Label).update(label)

        self.app.push_screen(QuickCatchModal(), on_dismiss)

    def action_open_juggling_lab(self) -> None:
        """Open the siteswap in juggling lab gif server"""
        if "siteswap" not in self._exercise.prop_type:
            return
        core = self._exercise.extract_core_pattern()
        url = f"https://jugglinglab.org/anim?pattern={core};colors=mixed"
        subprocess.Popen(["xdg-open", url])

    def _log_exercise(self) -> None:
        log_exercise(
            self._conn,
            self._session_id,
            self._resolved.exercise,
            self._resolved,
            round(self.query_one(TimerWidget).elapsed, 1),
            self._catches,
            self._comfort,
            self._notes,
        )
