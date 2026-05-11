from textual.app import App

from circus_planner.db import init_db
from circus_planner.screens.home import HomeScreen


class CircusApp(App):
    def on_mount(self) -> None:
        self.push_screen(HomeScreen())


def tui() -> None:
    init_db()

    app = CircusApp()
    app.run()
