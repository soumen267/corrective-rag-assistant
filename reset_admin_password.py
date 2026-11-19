"""
Generate a new RAG_ADMIN_PASSWORD_HASH for the project's .env file.

Run from the project root:
    python reset_admin_password.py

The script does not change .env automatically. Copy the generated value into
.env so you can review the change before restarting the API.
"""

import base64
import getpass
import hashlib
import secrets
import sys

ITERATIONS = 600_000


def b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def make_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${ITERATIONS}"
        f"${b64encode(salt)}${b64encode(digest)}"
    )


def main() -> int:
    password = getpass.getpass("Enter new admin password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm new admin password: ")

    if len(password) < 12:
        print("Password must be at least 12 characters.")
        return 1
    if password != confirmation:
        print("Passwords do not match.")
        return 1

    print("\nAdd this line to your project-root .env file:")
    print(f"RAG_ADMIN_PASSWORD_HASH={make_hash(password)}")
    print("\nKeep the hash private. Do not share it or commit .env to Git.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
