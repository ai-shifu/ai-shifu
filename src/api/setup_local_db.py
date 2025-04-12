import os
import sys
from flask import Flask

os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/test.db"
os.environ["FLASK_APP"] = "app.py"
os.environ["LOGGING_PATH"] = "/tmp/ai-shifu.log"
os.environ["MODE"] = "development"

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print("Environment configured for SQLite database")
print(
    'Run "cd /home/ubuntu/repos/ai-shifu/src/api && flask db migrate -m "rename_course_teacher_avator_to_avatar"" to generate a new migration script'
)
