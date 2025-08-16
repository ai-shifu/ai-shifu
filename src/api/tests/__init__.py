# import sys
# import os

# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from .test_app import *  # noqa


import os
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Import and use get_config to set Django settings module
from flaskr.common.config import get_config

os.environ["DJANGO_SETTINGS_MODULE"] = get_config("DJANGO_SETTINGS_MODULE")
