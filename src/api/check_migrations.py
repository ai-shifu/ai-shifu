from alembic.config import Config
from alembic.script import ScriptDirectory

config = Config('migrations/alembic.ini')
script = ScriptDirectory.from_config(config)

print('Current heads:', script.get_heads())
print('\nMigration branches:')
for head in script.get_heads():
    print(f"\nBranch ending with {head}:")
    revision = head
    branch = []
    while revision:
        script_revision = script.get_revision(revision)
        branch.append(f"{revision} ({script_revision.doc})")
        revision = script_revision.down_revision
    for rev in reversed(branch):
        print(f"  - {rev}")
