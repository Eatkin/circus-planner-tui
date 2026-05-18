from typing import Any
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input
from textual.widgets import Label
from textual.widgets import Static


class CatchInputModal(ModalScreen[list[int] | None]):
    DEFAULT_CSS = """
    CatchInputModal {
        align: center middle;
    }
    #modal-box {
        width: 40;
        height: auto;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }
    #title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #catches-list {
        color: $text-muted;
        margin-bottom: 1;
    }
    #hint {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }
    """

    BINDINGS: ClassVar = [
        Binding("escape", "dismiss_none", "Skip", priority=True),
    ]

    def __init__(self, show_catches: bool = True, **kwargs: Any):
        super().__init__(**kwargs)
        self._show_catches = show_catches

    def compose(self) -> ComposeResult:
        with Static(id="modal-box"):
            yield Label("exercise complete", id="title")
            if self._show_catches:
                yield Input(placeholder="catches (blank to skip)", id="catch-input")
            yield Input(placeholder="comfort level (1-10) (blank to skip)", id="comfort-level-input")
            yield Input(placeholder="notes (blank to skip)", id="notes-input")
            yield Label("enter to confirm  •  esc to skip", id="hint")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "catch-input":
            self.query_one("#notes-input", Input).focus()
            return
        # notes submitted - we're done
        catches_raw = self.query_one("#catch-input", Input).value.strip() if self._show_catches else ""
        notes_raw = event.value.strip()
        comfort = self.query_one("#comfort-level-input", Input).value.strip()
        try:
            catches = int(catches_raw) if catches_raw else None
        except ValueError:
            catches = None
        try:
            comfort = int(comfort)
        except ValueError:
            comfort = None

        self.dismiss((catches, notes_raw or None), comfort) # ty: ignore

    def on_mount(self) -> None:
        if self._show_catches:
            self.query_one(Input).focus()

    def on_key(self, event) -> None:
        if event.key == "enter" and not self._show_catches:
            self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss((None, None, None)) # ty: ignore


class QuickCatchModal(ModalScreen[int | None]):
    DEFAULT_CSS = """
    QuickCatchModal {
        align: center middle;
    }
    #modal-box {
        width: 40;
        height: auto;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }
    #title {
        text-align: center;
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }
    #hint {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS: ClassVar = [
        Binding("escape", "dismiss_none", "Cancel", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Static(id="modal-box"):
            yield Label("catches this run", id="title")
            yield Input(placeholder="e.g. 23", id="catch-input", type="integer")
            yield Label("enter to log  •  esc to cancel", id="hint")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip()
        try:
            self.dismiss(int(val))
        except ValueError:
            self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
