"""密码工具函数：哈希、验证、强度校验。"""

from __future__ import annotations

import re

import bcrypt


def hash_password(plain_text: str) -> str:
    """对明文密码进行 bcrypt 哈希，cost factor 为 12。"""
    return bcrypt.hashpw(plain_text.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode(
        "utf-8"
    )


def verify_password(plain_text: str, hashed: str) -> bool:
    """验证明文密码与 bcrypt 哈希是否匹配。"""
    try:
        return bcrypt.checkpw(plain_text.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    校验密码强度。

    规则：
    - 最少 8 位
    - 需包含至少一个字母
    - 需包含至少一个数字

    返回 (is_valid, error_message)。
    """
    if len(password) < 8:
        return False, "密码长度至少为 8 位"
    if not re.search(r"[a-zA-Z]", password):
        return False, "密码需包含至少一个字母"
    if not re.search(r"[0-9]", password):
        return False, "密码需包含至少一个数字"
    return True, ""
