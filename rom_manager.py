"""Entry point for the ROM Manager application."""

try:  # pragma: no cover - import fallback logic
    from .database import Database
    from .download_manager import DownloadItem, DownloadManager, DownloadTask
    from .ui_main import MainWindow
except ImportError:  # pragma: no cover - support running as a script
    from database import Database
    from download_manager import DownloadItem, DownloadManager, DownloadTask
    from ui_main import MainWindow


def main() -> None:
    """Run the application."""
    db = Database("sqlite:///roms.db")
    db.connect()

    manager = DownloadManager()
    item = DownloadItem(url="http://example.com/rom.zip", destination="rom.zip")
    task = DownloadTask(item)
    manager.add_task(task)
    manager.run_all()

    window = MainWindow()
    window.build_tabs()

    db.close()


if __name__ == "__main__":
    main()
