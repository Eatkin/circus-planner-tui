from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer
from textual.widgets import Header


class BaseScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
