"""sys_profile

Revision ID: 2681575163c0
Revises: 7cee4b561f30
Create Date: 2025-07-01 13:56:40.217637

"""

from alembic import op
from sqlalchemy.sql import text
import re

# revision identifiers, used by Alembic.
revision = "2681575163c0"
down_revision = "7cee4b561f30"
branch_labels = None
depends_on = None


def upgrade():
    renames = {
        "nick_name": "sys_user_nickname",
        "nickname": "sys_user_nickname",
        "style": "sys_user_style",
        "userbackground": "sys_user_background",
        "user_background": "sys_user_background",
        "input": "sys_user_input",
    }
    # Update profile_item profile_key field - full table replacement
    for old, new in renames.items():
        op.execute(
            f"UPDATE profile_item SET profile_key = '{new}' WHERE profile_key = '{old}';"
        )
    # Update profile_item profile_prompt field - support multiple formats
    connection = op.get_bind()
    # Pre-compile all regex patterns
    patterns = {}
    for old, new in renames.items():
        patterns[old] = {
            "braces": re.compile(rf"\{{{old}\}}"),
            "parens": re.compile(rf"\({old}\)"),
            "json": re.compile(rf'\{{{{\"{old}\":\s*"([^\"]*)"}}}}'),
            "new": new,
        }

    # Process all profile_item profile_prompt and profile_raw_prompt fields
    results = connection.execute(
        text(
            "SELECT id, profile_prompt, profile_raw_prompt FROM profile_item WHERE profile_prompt IS NOT NULL OR profile_raw_prompt IS NOT NULL"
        )
    ).fetchall()

    for row in results:
        profile_prompt = row[1]
        profile_raw_prompt = row[2]
        new_profile_prompt = profile_prompt if profile_prompt else None
        new_profile_raw_prompt = profile_raw_prompt if profile_raw_prompt else None
        # Replace variable names in multiple formats: {old}, (old), and {{"old": "xxx"}}
        if new_profile_prompt:
            for old, pattern_dict in patterns.items():
                new_profile_prompt = pattern_dict["braces"].sub(
                    f"{{{pattern_dict['new']}}}", new_profile_prompt
                )
                new_profile_prompt = pattern_dict["parens"].sub(
                    f"({pattern_dict['new']})", new_profile_prompt
                )
                new_profile_prompt = pattern_dict["json"].sub(
                    f'{{{{"{pattern_dict["new"]}": "\\1"}}}}', new_profile_prompt
                )
        if new_profile_raw_prompt:
            for old, pattern_dict in patterns.items():
                new_profile_raw_prompt = pattern_dict["braces"].sub(
                    f"{{{pattern_dict['new']}}}", new_profile_raw_prompt
                )
                new_profile_raw_prompt = pattern_dict["parens"].sub(
                    f"({pattern_dict['new']})", new_profile_raw_prompt
                )
                new_profile_raw_prompt = pattern_dict["json"].sub(
                    f'{{{{"{pattern_dict["new"]}": "\\1"}}}}', new_profile_raw_prompt
                )
        # Only update if changed
        if (new_profile_prompt != profile_prompt) or (
            new_profile_raw_prompt != profile_raw_prompt
        ):
            connection.execute(
                text(
                    "UPDATE profile_item SET profile_prompt = :new_prompt, profile_raw_prompt = :new_raw_prompt WHERE id = :id"
                ),
                {
                    "new_prompt": new_profile_prompt,
                    "new_raw_prompt": new_profile_raw_prompt,
                    "id": row[0],
                },
            )

    # Update user_profile profile_key field - all profile_type records
    for old, new in renames.items():
        op.execute(
            f"UPDATE user_profile SET profile_key = '{new}' WHERE profile_key = '{old}';"
        )
    # Update ai_lesson_script fields - batch processing for large dataset
    connection = op.get_bind()
    batch_size = 5000
    # Pre-compile all regex patterns for ai_lesson_script
    patterns = {}
    for old, new in renames.items():
        patterns[old] = {
            "braces": re.compile(rf"\{{{old}\}}"),
            "parens": re.compile(rf"\({old}\)"),
            "json": re.compile(rf'\{{{{\"{old}\":\s*"([^\"]*)"}}}}'),
            "brackets": re.compile(rf"\[{old}\]"),
            "new": new,
        }

    offset = 0
    while True:
        results = connection.execute(
            text(
                "SELECT id, script_check_prompt, script_ui_profile, script_prompt, script_profile "
                "FROM ai_lesson_script "
                "ORDER BY id ASC "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": batch_size, "offset": offset},
        ).fetchall()
        if not results:
            break
        for row in results:
            # Initialize new values
            new_script_prompt = row[3]  # script_prompt is the 4th field
            new_prompt = row[1]  # script_check_prompt is the 2nd field
            new_profile = row[2]  # script_ui_profile is the 3rd field
            new_script_profile = row[4]  # script_profile is the 5th field

            # Replace variable names for each pattern
            for old, pattern_dict in patterns.items():
                new = pattern_dict["new"]

                # script_prompt: only replace {old} with {new}
                if new_script_prompt and pattern_dict["braces"].search(
                    new_script_prompt
                ):
                    new_script_prompt = pattern_dict["braces"].sub(
                        f"{{{new}}}", new_script_prompt
                    )

                # script_check_prompt: replace {old}, (old), and {{"old": "xxx"}}
                if new_prompt:
                    new_prompt = pattern_dict["braces"].sub(f"{{{new}}}", new_prompt)
                    new_prompt = pattern_dict["parens"].sub(f"({new})", new_prompt)
                    new_prompt = pattern_dict["json"].sub(
                        f'{{{{"{new}": "\\1"}}}}', new_prompt
                    )

                # script_ui_profile: replace [old] format
                if new_profile:
                    new_profile = pattern_dict["brackets"].sub(f"[{new}]", new_profile)

                # script_profile: replace [old] format
                if new_script_profile:
                    new_script_profile = pattern_dict["brackets"].sub(
                        f"[{new}]", new_script_profile
                    )

            # Update if any changes detected
            if (
                new_prompt != row[1]
                or new_profile != row[2]
                or new_script_prompt != row[3]
                or new_script_profile != row[4]
            ):
                connection.execute(
                    text(
                        "UPDATE ai_lesson_script SET "
                        "script_check_prompt = :new_prompt, "
                        "script_ui_profile = :new_profile, "
                        "script_prompt = :new_script_prompt, "
                        "script_profile = :new_script_profile "
                        "WHERE id = :id"
                    ),
                    {
                        "new_prompt": new_prompt,
                        "new_profile": new_profile,
                        "new_script_prompt": new_script_prompt,
                        "new_script_profile": new_script_profile,
                        "id": row[0],  # id is the 1st field
                    },
                )
        if len(results) < batch_size:
            break
        offset += batch_size
    # ### end Alembic commands ###


def downgrade():
    renames = {
        "sys_user_nickname": "nick_name",
        "sys_user_style": "style",
        "sys_user_background": "user_background",
        "sys_user_input": "input",
    }
    # Revert profile_item profile_key field - full table replacement
    for old, new in renames.items():
        op.execute(
            f"UPDATE profile_item SET profile_key = '{new}' WHERE profile_key = '{old}';"
        )
    # Revert profile_item profile_prompt field - support multiple formats
    connection = op.get_bind()
    # Pre-compile all regex patterns
    patterns = {}
    for old, new in renames.items():
        patterns[old] = {
            "braces": re.compile(rf"\{{{old}\}}"),
            "parens": re.compile(rf"\({old}\)"),
            "json": re.compile(rf'\{{{{\"{old}\":\s*"([^\"]*)"}}}}'),
            "new": new,
        }

    # Process all profile_item profile_prompt and profile_raw_prompt fields
    results = connection.execute(
        text(
            "SELECT id, profile_prompt, profile_raw_prompt FROM profile_item WHERE profile_prompt IS NOT NULL OR profile_raw_prompt IS NOT NULL"
        )
    ).fetchall()

    for row in results:
        profile_prompt = row[1]
        profile_raw_prompt = row[2]
        new_profile_prompt = profile_prompt if profile_prompt else None
        new_profile_raw_prompt = profile_raw_prompt if profile_raw_prompt else None
        # Replace variable names in multiple formats: {old}, (old), and {{"old": "xxx"}}
        if new_profile_prompt:
            for old, pattern_dict in patterns.items():
                new_profile_prompt = pattern_dict["braces"].sub(
                    f"{{{pattern_dict['new']}}}", new_profile_prompt
                )
                new_profile_prompt = pattern_dict["parens"].sub(
                    f"({pattern_dict['new']})", new_profile_prompt
                )
                new_profile_prompt = pattern_dict["json"].sub(
                    f'{{{{"{pattern_dict["new"]}": "\\1"}}}}', new_profile_prompt
                )
        if new_profile_raw_prompt:
            for old, pattern_dict in patterns.items():
                new_profile_raw_prompt = pattern_dict["braces"].sub(
                    f"{{{pattern_dict['new']}}}", new_profile_raw_prompt
                )
                new_profile_raw_prompt = pattern_dict["parens"].sub(
                    f"({pattern_dict['new']})", new_profile_raw_prompt
                )
                new_profile_raw_prompt = pattern_dict["json"].sub(
                    f'{{{{"{pattern_dict["new"]}": "\\1"}}}}', new_profile_raw_prompt
                )
        # Only update if changed
        if (new_profile_prompt != profile_prompt) or (
            new_profile_raw_prompt != profile_raw_prompt
        ):
            connection.execute(
                text(
                    "UPDATE profile_item SET profile_prompt = :new_prompt, profile_raw_prompt = :new_raw_prompt WHERE id = :id"
                ),
                {
                    "new_prompt": new_profile_prompt,
                    "new_raw_prompt": new_profile_raw_prompt,
                    "id": row[0],
                },
            )

    # Revert user_profile profile_key field - all profile_type records
    for old, new in renames.items():
        op.execute(
            f"UPDATE user_profile SET profile_key = '{new}' WHERE profile_key = '{old}';"
        )
    # Revert ai_lesson_script fields - batch processing for large dataset
    connection = op.get_bind()
    batch_size = 5000
    # Pre-compile all regex patterns for ai_lesson_script
    patterns = {}
    for old, new in renames.items():
        patterns[old] = {
            "braces": re.compile(rf"\{{{old}\}}"),
            "parens": re.compile(rf"\({old}\)"),
            "json": re.compile(rf'\{{{{\"{old}\":\s*"([^\"]*)"}}}}'),
            "brackets": re.compile(rf"\[{old}\]"),
            "new": new,
        }

    offset = 0
    while True:
        results = connection.execute(
            text(
                "SELECT id, script_check_prompt, script_ui_profile, script_prompt, script_profile "
                "FROM ai_lesson_script "
                "ORDER BY id ASC "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": batch_size, "offset": offset},
        ).fetchall()
        if not results:
            break
        for row in results:
            # Initialize new values
            new_script_prompt = row[3]  # script_prompt is the 4th field
            new_prompt = row[1]  # script_check_prompt is the 2nd field
            new_profile = row[2]  # script_ui_profile is the 3rd field
            new_script_profile = row[4]  # script_profile is the 5th field

            # Replace variable names for each pattern
            for old, pattern_dict in patterns.items():
                new = pattern_dict["new"]

                # script_prompt: only replace {old} with {new}
                if new_script_prompt and pattern_dict["braces"].search(
                    new_script_prompt
                ):
                    new_script_prompt = pattern_dict["braces"].sub(
                        f"{{{new}}}", new_script_prompt
                    )

                # script_check_prompt: replace {old}, (old), and {{"old": "xxx"}}
                if new_prompt:
                    new_prompt = pattern_dict["braces"].sub(f"{{{new}}}", new_prompt)
                    new_prompt = pattern_dict["parens"].sub(f"({new})", new_prompt)
                    new_prompt = pattern_dict["json"].sub(
                        f'{{{{"{new}": "\\1"}}}}', new_prompt
                    )

                # script_ui_profile: replace [old] format
                if new_profile:
                    new_profile = pattern_dict["brackets"].sub(f"[{new}]", new_profile)

                # script_profile: replace [old] format
                if new_script_profile:
                    new_script_profile = pattern_dict["brackets"].sub(
                        f"[{new}]", new_script_profile
                    )

            # Update if any changes detected
            if (
                new_prompt != row[1]
                or new_profile != row[2]
                or new_script_prompt != row[3]
                or new_script_profile != row[4]
            ):
                connection.execute(
                    text(
                        "UPDATE ai_lesson_script SET "
                        "script_check_prompt = :new_prompt, "
                        "script_ui_profile = :new_profile, "
                        "script_prompt = :new_script_prompt, "
                        "script_profile = :new_script_profile "
                        "WHERE id = :id"
                    ),
                    {
                        "new_prompt": new_prompt,
                        "new_profile": new_profile,
                        "new_script_prompt": new_script_prompt,
                        "new_script_profile": new_script_profile,
                        "id": row[0],  # id is the 1st field
                    },
                )
        if len(results) < batch_size:
            break
        offset += batch_size
    # ### end Alembic commands ###
