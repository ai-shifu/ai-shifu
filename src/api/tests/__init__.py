"""Backend test suite."""

from pathlib import Path

from dotenv import load_dotenv

from .test_app import *  # noqa: F403

# Load a deterministic, test-only dotenv (skip user/global .env files)
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env.test", override=True)
