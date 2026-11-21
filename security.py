"""Password security helpers for the class merit tracker."""

from __future__ import annotations

import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Argon2id is intentionally used instead of a fast general-purpose hash.
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


class PasswordPolicyError(ValueError):
    """Raised when a password does not meet the minimum strength policy."""


def validate_password(password: str) -> None:
    """Require a minimum of 8 characters; allow any character combination."""
    if len(password) < 8:
        raise PasswordPolicyError("Mật khẩu phải có ít nhất 8 ký tự.")
    if len(password) > 128:
        raise PasswordPolicyError("Mật khẩu không được dài quá 128 ký tự.")


def hash_password(password: str) -> str:
    validate_password(password)
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def generate_password(length: int = 22) -> str:
    """Generate a strong one-time password for an administrator to share safely."""
    if length < 8:
        raise ValueError("Generated passwords must be at least 8 characters long.")
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(length))
        try:
            validate_password(value)
            return value
        except PasswordPolicyError:
            continue
