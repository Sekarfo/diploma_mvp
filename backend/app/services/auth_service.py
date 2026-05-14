from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.config import Settings, get_settings
from backend.app.services.db_service import db_connection
from backend.app.services.errors import (
    AuthenticationError,
    DatabaseUnavailableError,
)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_MIN_LENGTH = 8
PBKDF2_ITERATIONS = 390000
_BEARER_SCHEME = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str
    full_name: str
    role: str
    is_active: bool


class AuthService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def signup(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> dict:
        normalized_email = str(email).strip().lower()
        normalized_name = str(full_name).strip()
        self._validate_signup_payload(
            email=normalized_email,
            password=password,
            full_name=normalized_name,
        )

        now = datetime.now(timezone.utc)
        user_id = str(uuid.uuid4())
        password_hash = self._hash_password(password)

        token = secrets.token_urlsafe(48)
        token_hash = self._hash_token(token)
        expires_at = now + timedelta(minutes=self.settings.auth_session_ttl_minutes)
        session_id = str(uuid.uuid4())

        # User creation and session creation must succeed or fail together.
        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT id FROM users WHERE email = %s", (normalized_email,))
                    if cursor.fetchone() is not None:
                        raise AuthenticationError("User with this email already exists.")

                    cursor.execute(
                        """
                        INSERT INTO users (id, email, password_hash, full_name, role, is_active, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, 'hr', TRUE, %s, %s)
                        """,
                        (user_id, normalized_email, password_hash, normalized_name, now, now),
                    )
                    cursor.execute(
                        """
                        INSERT INTO user_sessions (
                            id, user_id, refresh_token_hash, user_agent, ip_address, expires_at, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (session_id, user_id, token_hash, user_agent, ip_address, expires_at, now),
                    )
        except AuthenticationError:
            raise
        except Exception as exc:
            raise DatabaseUnavailableError(f"Sign-up failed: {exc}") from exc

        session = {"access_token": token, "expires_at": expires_at.isoformat()}
        return {
            "token_type": "bearer",
            "access_token": session["access_token"],
            "expires_at": session["expires_at"],
            "user": {
                "id": user_id,
                "email": normalized_email,
                "full_name": normalized_name,
                "role": "hr",
                "is_active": True,
            },
        }

    def signin(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> dict:
        normalized_email = str(email).strip().lower()
        if not normalized_email:
            raise AuthenticationError("Email is required.")
        if not password:
            raise AuthenticationError("Password is required.")

        now = datetime.now(timezone.utc)
        token = secrets.token_urlsafe(48)
        token_hash = self._hash_token(token)
        expires_at = now + timedelta(minutes=self.settings.auth_session_ttl_minutes)
        session_id = str(uuid.uuid4())

        
        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, email, full_name, role, is_active, password_hash
                        FROM users
                        WHERE email = %s
                        """,
                        (normalized_email,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise AuthenticationError("Invalid email or password.")

                    user_id, user_email, full_name, role, is_active, password_hash = row
                    if not bool(is_active):
                        raise AuthenticationError("User is deactivated.")
                    if not self._verify_password(password=password, password_hash=str(password_hash)):
                        raise AuthenticationError("Invalid email or password.")

                    cursor.execute(
                        "UPDATE users SET last_login_at = %s, updated_at = %s WHERE id = %s",
                        (now, now, str(user_id)),
                    )
                    # Best-effort cleanup of stale sessions (inside same connection, no extra round-trip)
                    cursor.execute(
                        "DELETE FROM user_sessions WHERE user_id = %s AND expires_at < now() - INTERVAL '7 days'",
                        (str(user_id),),
                    )
                    cursor.execute(
                        """
                        INSERT INTO user_sessions (
                            id, user_id, refresh_token_hash, user_agent, ip_address, expires_at, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (session_id, str(user_id), token_hash, user_agent, ip_address, expires_at, now),
                    )
        except AuthenticationError:
            raise
        except Exception as exc:
            raise DatabaseUnavailableError(f"Sign-in failed: {exc}") from exc

        session = {"access_token": token, "expires_at": expires_at.isoformat()}
        return {
            "token_type": "bearer",
            "access_token": session["access_token"],
            "expires_at": session["expires_at"],
            "user": {
                "id": str(user_id),
                "email": str(user_email),
                "full_name": str(full_name),
                "role": str(role),
                "is_active": bool(is_active),
            },
        }

    def get_user_from_token(self, token: str) -> AuthenticatedUser:
        normalized_token = str(token).strip()
        if not normalized_token:
            raise AuthenticationError("Missing bearer token.")

        token_hash = self._hash_token(normalized_token)
        now = datetime.now(timezone.utc)

        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT u.id, u.email, u.full_name, u.role, u.is_active
                        FROM user_sessions s
                        JOIN users u ON u.id = s.user_id
                        WHERE s.refresh_token_hash = %s
                          AND s.revoked_at IS NULL
                          AND s.expires_at > %s
                        LIMIT 1
                        """,
                        (token_hash, now),
                    )
                    row = cursor.fetchone()
        except Exception as exc:
            raise DatabaseUnavailableError(f"Token validation failed: {exc}") from exc

        if row is None:
            raise AuthenticationError("Invalid or expired token.")

        user_id, email, full_name, role, is_active = row
        if not bool(is_active):
            raise AuthenticationError("User is deactivated.")

        return AuthenticatedUser(
            user_id=str(user_id),
            email=str(email),
            full_name=str(full_name),
            role=str(role),
            is_active=bool(is_active),
        )

    def signout(self, token: str) -> None:
        normalized_token = str(token).strip()
        if not normalized_token:
            raise AuthenticationError("Missing bearer token.")

        token_hash = self._hash_token(normalized_token)
        now = datetime.now(timezone.utc)
        try:
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE user_sessions SET revoked_at = %s WHERE refresh_token_hash = %s",
                        (now, token_hash),
                    )
        except Exception as exc:
            raise DatabaseUnavailableError(f"Sign-out failed: {exc}") from exc

    @staticmethod
    def _validate_signup_payload(*, email: str, password: str, full_name: str) -> None:
        if not full_name:
            raise AuthenticationError("Full name is required.")
        if not email or not EMAIL_PATTERN.match(email):
            raise AuthenticationError("A valid email is required.")
        if len(password) < PASSWORD_MIN_LENGTH:
            raise AuthenticationError(
                f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
            )

    def _hash_password(self, password: str) -> str:
        salt = os.urandom(16)
        payload = f"{password}{self.settings.auth_password_pepper}".encode("utf-8")
        derived = hashlib.pbkdf2_hmac("sha256", payload, salt, PBKDF2_ITERATIONS)
        salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
        hash_b64 = base64.urlsafe_b64encode(derived).decode("ascii")
        return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_b64}${hash_b64}"

    def _verify_password(self, *, password: str, password_hash: str) -> bool:
        try:
            algorithm, iterations_raw, salt_b64, hash_b64 = password_hash.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            iterations = int(iterations_raw)
            salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
            expected = base64.urlsafe_b64decode(hash_b64.encode("ascii"))
        except Exception:
            return False

        payload = f"{password}{self.settings.auth_password_pepper}".encode("utf-8")
        actual = hashlib.pbkdf2_hmac("sha256", payload, salt, iterations)
        return secrets.compare_digest(actual, expected)

    def _hash_token(self, token: str) -> str:
        payload = f"{token}{self.settings.auth_password_pepper}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    return AuthService()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_BEARER_SCHEME),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )
    try:
        return auth_service.get_user_from_token(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
