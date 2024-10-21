# import sys
# import os

# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from .test_app import *


import os

os.environ["DJANGO_SETTINGS_MODULE"] = "api.settings"
