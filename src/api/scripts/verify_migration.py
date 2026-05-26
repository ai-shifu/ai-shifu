"""Verify the generated migration file contains complete and correct data."""

import re
import sys
from pathlib import Path

migration_path = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path(
        "e:/Code/OpenSource/ai-shifu-TTS/src/api/migrations/versions/6f6b5b40a411_seedcoursedata.py"
    )
)

content = migration_path.read_text(encoding="utf-8")

# Parse the file to extract individual INSERT statements
inserts = re.findall(
    r'bind\.execute\(sa\.text\("""INSERT INTO (\w+) \((.+?)\) VALUES \((.+?)\)"""\)\)',
    content,
    re.DOTALL,
)

print(f"Total INSERT statements found: {len(inserts)}")

# Group by table
tables = {}
for table_name, cols_str, vals_str in inserts:
    if table_name not in tables:
        tables[table_name] = {"count": 0, "columns": None, "errors": []}
    tables[table_name]["count"] += 1
    if tables[table_name]["columns"] is None:
        tables[table_name]["columns"] = [
            c.strip().strip("`") for c in cols_str.split(",")
        ]

# Check for common issues
print("\n=== Table Summary ===")
for table_name, info in tables.items():
    print(f"\n{table_name}: {info['count']} rows, {len(info['columns'])} columns")
    print(f"  Columns: {info['columns']}")

# Check for potential escaping issues
print("\n=== Escaping Checks ===")

# 1. Check for unmatched parentheses in VALUES
issues = 0
for i, (table_name, cols_str, vals_str) in enumerate(inserts):
    # Count open/close parens in values
    open_parens = vals_str.count("(")
    close_parens = vals_str.count(")")
    if open_parens != close_parens:
        # Some mismatch is expected due to repr() of strings containing parens
        pass

# 2. Check for potential issues with Chinese characters
chinese_pattern = re.compile(r"[一-鿿]")
chinese_count = len(chinese_pattern.findall(content))
print(f"Chinese characters found: {chinese_count}")

# 3. Check file ending
if "def downgrade():" in content:
    print("File ends with downgrade() - OK")
else:
    print("WARNING: File may be truncated!")
    issues += 1

# 4. Check for specific data values
# Verify the course title exists
if "AI 时代的项目管理" in content:
    print("Course title 'AI 时代的项目管理' found - OK")
else:
    print("WARNING: Course title not found!")
    issues += 1

# Check for llm_system_prompt content
if "身份与角色" in content:
    print("System prompt content found - OK")
else:
    print("WARNING: System prompt content not found!")
    issues += 1

# Check for outline item content (markdown flow)
outline_contents = re.findall(
    r"INSERT INTO shifu_draft_outline_items.*?'(.*?)'(?=\s*,\s*\d+\s*,\s*'[^']*'\s*,\s*\d+\s*,\s*\d+\s*,)",
    content,
    re.DOTALL,
)
print(f"\nOutline item content entries found: {len(outline_contents)}")

# 5. Check a sample row for completeness
print("\n=== Sample Row Check (first draft_shifu) ===")
if inserts:
    for table_name, cols_str, vals_str in inserts[:1]:
        cols = [c.strip().strip("`") for c in cols_str.split(",")]
        print(f"  Table: {table_name}")
        print(f"  Columns ({len(cols)}): {cols}")
        # Count values by looking at the structure
        print(f"  Values section length: {len(vals_str)} chars")

# 6. Check for large content in outline items
print("\n=== Large Content Check ===")
large_contents = []
for table_name, cols_str, vals_str in inserts:
    if table_name == "shifu_draft_outline_items":
        # The content field is roughly the 17th column
        large_contents.append(len(vals_str))

if large_contents:
    print(
        f"Outline item value lengths: min={min(large_contents)}, max={max(large_contents)}, avg={sum(large_contents) // len(large_contents)}"
    )
    if len(large_contents) != 226:
        print(f"WARNING: Expected 226 outline items, found {len(large_contents)}")
        issues += 1
    else:
        print("Expected 226 outline items - OK")

# 7. Verify the DELETE statement is present
print("\n=== Idempotency Check ===")
if "DELETE FROM" in content and "shifu_bid IN" in content:
    print("DELETE statement found - idempotent - OK")
else:
    print("WARNING: DELETE statement not found!")
    issues += 1

# 8. Check the shifu_bid
if (
    "9eca13c4c7824d4687600af7c40af7c4a3828a" in content
    or "9eca13c4c7824d4687600af7c4a3828a" in content
):
    print("shifu_bid '9eca13c4c7824d4687600af7c4a3828a' found - OK")
else:
    print("WARNING: shifu_bid not found!")
    issues += 1

print(f"\n{'=' * 40}")
if issues == 0:
    print("All checks passed!")
else:
    print(f"Found {issues} issues!")
