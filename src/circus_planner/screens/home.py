from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import Label
from textual.widgets import ListItem
from textual.widgets import ListView
from textual.widgets import Static

from circus_planner.screens import BaseScreen
from circus_planner.screens.exercise import ExerciseScreen


ASCII_TITLE = """ ▗▄▄▖▄  ▄▄▄ ▗▞▀▘█  ▐▌ ▄▄▄     ▗▄▄▖ █ ▗▞▀▜▌▄▄▄▄  ▄▄▄▄  ▗▞▀▚▖ ▄▄▄ 
▐▌   ▄ █    ▝▚▄▖▀▄▄▞▘▀▄▄      ▐▌ ▐▌█ ▝▚▄▟▌█   █ █   █ ▐▛▀▀▘█    
▐▌   █ █             ▄▄▄▀     ▐▛▀▘ █      █   █ █   █ ▝▚▄▄▖█    
▝▚▄▄▖█                        ▐▌   █                            """  # noqa: W291


class HomeScreen(BaseScreen):
    DEFAULT_CSS = """
    HomeScreen {
        align: center middle;
    }
    #title {
        color: $accent;
        text-align: center;
        width: 100%;
        margin-bottom: 2;
    }
    #subtitle {
        color: $text-muted;
        text-align: center;
        width: 100%;
        margin-bottom: 2;
    }
    #menu {
        width: 40;
        height: auto;
        margin: 2 2;
    }
    #menu ListItem {
        width: 100%;
        padding: 0 2;
    }
    #menu Label {
        width: 100%;
        text-align: center;
    }
    """

    BINDINGS: ClassVar = [
        Binding("s", "start_session", "Start", priority=True),
        Binding("q", "app.exit", "Quit", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(ASCII_TITLE, id="title")
        yield Static("🤹  your personal circus trainer", id="subtitle")
        with Center():
            yield ListView(
                ListItem(Label("Start session"), id="start"),
                ListItem(Label("Quit"), id="quit"),
                id="menu",
            )
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id == "start":
            self.app.push_screen(ExerciseScreen())
        elif event.item.id == "quit":
            self.app.exit()
