"""Password hashing utilities.

Uses pwdlib with PasswordHash.recommended() — currently Argon2id.
All password operations in the application must go through these functions.
"""

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()


def hash_password(plain: str) -> str:
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _password_hash.verify(plain, hashed)
