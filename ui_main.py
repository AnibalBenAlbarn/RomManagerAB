"""User interface module."""
from typing import List


class MainWindow:
    """Represents the main application window."""

    def __init__(self) -> None:
        self.tabs: List[str] = []

    def build_tabs(self) -> None:
        """Simulate constructing UI tabs."""
        # In a real GUI application, this would construct the actual tabs.
        self.tabs = ["Downloads", "Database"]
