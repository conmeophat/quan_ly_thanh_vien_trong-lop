"""Password and bootstrap security helpers for the class merit tracker."""

from __future__ import annotations

import hmac
import secrets
import string
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Argon2id is intentionally used instead of a fast general-purpose hash.
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


class PasswordPolicyError(ValueError):
    """Raised when a password does not meet the minimum strength policy."""


def validate_password(password: str, username: str = "") -> None:
    """Require at least 14 chars and mixed character classes."""
    if len(password) < 14:
        raise PasswordPolicyError("Mật khẩu phải có ít nhất 14 ký tự.")
    if len(password) > 128:
        raise PasswordPolicyError("Mật khẩu không được dài quá 128 ký tự.")
    if not any(ch.islower() for ch in password):
        raise PasswordPolicyError("Mật khẩu phải có ít nhất một chữ thường.")
    if not any(ch.isupper() for ch in password):
        raise PasswordPolicyError("Mật khẩu phải có ít nhất một chữ hoa.")
    if not any(ch.isdigit() for ch in password):
        raise PasswordPolicyError("Mật khẩu phải có ít nhất một chữ số.")
    if not any(not ch.isalnum() for ch in password):
        raise PasswordPolicyError("Mật khẩu phải có ít nhất một ký tự đặc biệt.")
    if username and username.casefold() in password.casefold():
        raise PasswordPolicyError("Không được đưa tên đăng nhập vào mật khẩu.")
    common = {"Password123!", "Admin12345678!", "Qwerty123456!", "Abcd12345678!"}
    if password in common:
        raise PasswordPolicyError("Mật khẩu quá phổ biến. Hãy chọn mật khẩu khác.")


def hash_password(password: str, username: str = "") -> str:
    validate_password(password, username)
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_bootstrap_token(provided: str, configured: Optional[str]) -> bool:
    """Constant-time compare for the one-time founder setup token."""
    if not configured or len(configured) < 32:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), configured.encode("utf-8"))


def generate_password(length: int = 22) -> str:
    """Generate a strong one-time password for an administrator to share safely."""
    if length < 16:
        raise ValueError("Generated passwords must be at least 16 characters long.")
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(length))
        try:
            validate_password(value)
            return value
        except PasswordPolicyError:
            continue
