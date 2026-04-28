"""Browser UI server package."""


def main() -> None:
    """Launch the browser UI server lazily."""

    from src.ui.server import main as server_main

    server_main()


__all__ = ["main"]
