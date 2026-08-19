"""Backend test suite."""

import os
from pathlib import Path

from dotenv import load_dotenv
from flaskr.common.config import get_config

from .test_app import *  # noqa: F403

# Load a deterministic, test-only dotenv (skip user/global .env files)
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env.test", override=True)

# Set Django settings module using get_config
os.environ["DJANGO_SETTINGS_MODULE"] = get_config("DJANGO_SETTINGS_MODULE")
