"""Profile service constants used across modules."""

SYS_USER_LANGUAGE = "sys_user_language"
SYS_USER_NICKNAME = "sys_user_nickname"
SYS_USER_BACKGROUND = "sys_user_background"

ACTIVE_SYSTEM_PROFILE_KEYS = frozenset(
    {SYS_USER_NICKNAME, SYS_USER_LANGUAGE, SYS_USER_BACKGROUND}
)
RETIRED_PROFILE_KEYS = frozenset(
    {"sex", "birth", "avatar", "language", "sys_user_style"}
)
