# import sys
# import os

# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import os
from dotenv import load_dotenv
from .test_app import *  # noqa
from flaskr.common.config import get_config

# Load environment variables first
load_dotenv()

# Set Django settings module using get_config
os.environ["DJANGO_SETTINGS_MODULE"] = get_config("DJANGO_SETTINGS_MODULE")
