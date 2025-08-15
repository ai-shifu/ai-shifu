"""Complete migration for sys_user_language: create system profile and migrate data

Revision ID: sys_user_language_complete_migration
Revises: b6cbcf622c0a
Create Date: 2025-01-24 15:00:00.000000

"""

from datetime import datetime

# revision identifiers, used by Alembic.
revision = "sys_user_language_complete_migration"
down_revision = "b6cbcf622c0a"
branch_labels = None
depends_on = None


def upgrade():
    """
    Complete migration for sys_user_language:
    1. Create system-level profile definitions
    2. Migrate existing user_language data to sys_user_language profiles
    """
    from flask import current_app as app
    from flaskr.service.profile.models import ProfileItem, ProfileItemI18n, UserProfile
    from flaskr.service.user.models import User
    from flaskr.service.profile.models import (
        PROFILE_TYPE_INPUT_TEXT,
        PROFILE_SHOW_TYPE_ALL,
        PROFILE_CONF_TYPE_PROFILE,
    )
    from flaskr.util.uuid import generate_id
    from flaskr.dao import db

    with app.app_context():
        print("=" * 60)
        print("Starting sys_user_language complete migration")
        print("=" * 60)

        # ========================================
        # PART 1: Create System Profile Definitions
        # ========================================
        print("\n[Step 1] Creating system profile definitions...")

        system_profiles = [
            {
                "key": "sys_user_nickname",
                "remark_zh": "用户昵称",
                "remark_en": "User Nickname",
                "index": 100,
            },
            {
                "key": "sys_user_background",
                "remark_zh": "用户背景",
                "remark_en": "User Background",
                "index": 110,
            },
            {
                "key": "sys_user_language",
                "remark_zh": "课程语言",
                "remark_en": "Course Language",
                "index": 200,
            },
            {
                "key": "sys_user_style",
                "remark_zh": "授课风格",
                "remark_en": "Teaching Style",
                "index": 210,
            },
        ]

        created_profiles = {}

        for profile_def in system_profiles:
            # Check if this profile already exists
            existing = ProfileItem.query.filter(
                ProfileItem.profile_key == profile_def["key"],
                ProfileItem.parent_id == "",
                ProfileItem.status == 1,
            ).first()

            if not existing:
                profile_id = generate_id(app)
                profile_item = ProfileItem(
                    profile_id=profile_id,
                    parent_id="",  # System-level (empty string)
                    profile_key=profile_def["key"],
                    profile_type=PROFILE_TYPE_INPUT_TEXT,
                    profile_show_type=PROFILE_SHOW_TYPE_ALL,
                    profile_remark=profile_def["remark_en"],
                    profile_color_setting="0",
                    profile_prompt="",
                    profile_prompt_model="",
                    profile_prompt_model_args="{}",
                    profile_raw_prompt="",
                    profile_index=profile_def["index"],
                    created_by="system",
                    updated_by="system",
                    created=datetime.now(),
                    updated=datetime.now(),
                    status=1,
                )
                db.session.add(profile_item)
                created_profiles[profile_def["key"]] = profile_id

                # Add Chinese translation
                zh_i18n = ProfileItemI18n(
                    parent_id=profile_id,
                    conf_type=PROFILE_CONF_TYPE_PROFILE,
                    language="zh-CN",
                    profile_item_remark=profile_def["remark_zh"],
                    created_by="system",
                    updated_by="system",
                    created=datetime.now(),
                    updated=datetime.now(),
                    status=1,
                )
                db.session.add(zh_i18n)

                # Add English translation
                en_i18n = ProfileItemI18n(
                    parent_id=profile_id,
                    conf_type=PROFILE_CONF_TYPE_PROFILE,
                    language="en-US",
                    profile_item_remark=profile_def["remark_en"],
                    created_by="system",
                    updated_by="system",
                    created=datetime.now(),
                    updated=datetime.now(),
                    status=1,
                )
                db.session.add(en_i18n)

                print(
                    f"  ✓ Created {profile_def['key']} system profile with id: {profile_id}"
                )
            else:
                created_profiles[profile_def["key"]] = existing.profile_id
                print(
                    f"  - {profile_def['key']} already exists (id: {existing.profile_id})"
                )

        # Commit system profiles
        db.session.flush()

        # ========================================
        # PART 2: Migrate User Language Data
        # ========================================
        print("\n[Step 2] Migrating user language data...")

        # Use user_language value directly, default to English if empty
        def get_course_language(lang_code):
            """Get course language from user_language field"""
            if lang_code is None or lang_code == "":
                return "English"
            return lang_code  # Use the original value directly

        # Get the sys_user_language profile_id
        sys_lang_profile_id = created_profiles.get("sys_user_language")
        if not sys_lang_profile_id:
            sys_lang_profile = ProfileItem.query.filter(
                ProfileItem.profile_key == "sys_user_language",
                ProfileItem.parent_id == "",
                ProfileItem.status == 1,
            ).first()
            if sys_lang_profile:
                sys_lang_profile_id = sys_lang_profile.profile_id

        # Get all users who don't already have sys_user_language profile
        users_without_profile = (
            db.session.query(User)
            .outerjoin(
                UserProfile,
                (UserProfile.user_id == User.user_id)
                & (UserProfile.profile_key == "sys_user_language"),
            )
            .filter(
                UserProfile.user_id.is_(
                    None
                ),  # Users without sys_user_language profile
                User.user_language.isnot(None),  # Users with user_language set
            )
            .all()
        )

        print(f"  Found {len(users_without_profile)} users to migrate")

        # Batch process users
        success_count = 0
        fail_count = 0

        for user in users_without_profile:
            course_language = get_course_language(user.user_language)

            try:
                # Create user profile directly (more efficient than using save_user_profiles)
                user_profile = UserProfile(
                    user_id=user.user_id,
                    profile_key="sys_user_language",
                    profile_value=course_language,
                    profile_type=PROFILE_TYPE_INPUT_TEXT,
                    profile_id=sys_lang_profile_id or "",
                    created=datetime.now(),
                    updated=datetime.now(),
                )
                db.session.add(user_profile)
                success_count += 1

                if success_count % 100 == 0:
                    print(f"  ... Migrated {success_count} users")

            except Exception as e:
                fail_count += 1
                print(f"  ✗ Failed to migrate user {user.user_id}: {e}")
                continue

        # ========================================
        # PART 3: Update existing user profiles with correct profile_id
        # ========================================
        print("\n[Step 3] Updating existing user profiles with system profile IDs...")

        if sys_lang_profile_id:
            # Update any existing sys_user_language profiles that don't have profile_id set
            updated = (
                db.session.query(UserProfile)
                .filter(
                    UserProfile.profile_key == "sys_user_language",
                    (UserProfile.profile_id == "") | (UserProfile.profile_id.is_(None)),
                )
                .update({"profile_id": sys_lang_profile_id, "updated": datetime.now()})
            )
            if updated > 0:
                print(f"  ✓ Updated {updated} existing profiles with system profile_id")

        # Commit all changes
        db.session.commit()

        # ========================================
        # Summary
        # ========================================
        print("\n" + "=" * 60)
        print("Migration Summary:")
        print(f"  System profiles created: {len(created_profiles)}")
        print(f"  Users migrated: {success_count}")
        if fail_count > 0:
            print(f"  Failed migrations: {fail_count}")

        # Verification
        total_users_with_lang = (
            db.session.query(UserProfile)
            .filter(UserProfile.profile_key == "sys_user_language")
            .count()
        )
        print(f"  Total users with sys_user_language: {total_users_with_lang}")
        print("=" * 60)
        print("Migration completed successfully!")


def downgrade():
    """
    Reverse the migration:
    1. Remove sys_user_language profiles from user_profile table
    2. Remove system profile definitions from profile_item table
    """
    from flask import current_app as app
    from flaskr.service.profile.models import ProfileItem, ProfileItemI18n, UserProfile
    from flaskr.dao import db

    with app.app_context():
        print("=" * 60)
        print("Starting downgrade...")
        print("=" * 60)

        # List of system profile keys to handle
        system_profile_keys = [
            "sys_user_language",
            "sys_user_nickname",
            "sys_user_background",
            "sys_user_style",
        ]

        # Step 1: Remove user profiles
        print("\n[Step 1] Removing user profiles...")
        deleted_profiles = (
            db.session.query(UserProfile)
            .filter(UserProfile.profile_key == "sys_user_language")
            .delete()
        )
        print(f"  ✓ Removed {deleted_profiles} sys_user_language user profiles")

        # Step 2: Remove system profile definitions
        print("\n[Step 2] Removing system profile definitions...")
        for profile_key in system_profile_keys:
            # Find the profile item
            profile_item = ProfileItem.query.filter(
                ProfileItem.profile_key == profile_key,
                ProfileItem.parent_id == "",
                ProfileItem.status == 1,
            ).first()

            if profile_item:
                # Delete associated i18n entries
                deleted_i18n = ProfileItemI18n.query.filter(
                    ProfileItemI18n.parent_id == profile_item.profile_id
                ).delete()

                # Soft delete the profile item
                profile_item.status = 0
                profile_item.updated = datetime.now()
                profile_item.updated_by = "system_downgrade"
                print(
                    f"  ✓ Removed {profile_key} system profile (i18n: {deleted_i18n})"
                )

        db.session.commit()

        print("\n" + "=" * 60)
        print("Downgrade completed successfully!")
        print("=" * 60)
