"""Download manager module."""
from dataclasses import dataclass
from typing import List


@dataclass
class DownloadItem:
    """Represents an item to download."""
    url: str
    destination: str


class DownloadTask:
    """A task that performs a download."""

    def __init__(self, item: DownloadItem):
        self.item = item
        self.completed = False

    def run(self) -> None:
        """Simulate performing the download."""
        # Real download code would go here.
        self.completed = True


class DownloadManager:
    """Coordinates download tasks."""

    def __init__(self) -> None:
        self.tasks: List[DownloadTask] = []

    def add_task(self, task: DownloadTask) -> None:
        self.tasks.append(task)

    def run_all(self) -> None:
        for task in self.tasks:
            task.run()
