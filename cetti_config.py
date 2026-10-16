from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent


def load_project_environment() -> None:
    """Load the root .env without overriding explicitly configured variables."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
