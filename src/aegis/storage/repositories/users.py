"""User repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ...utils.ids import new_user_id
from ...utils.logging import get_logger
from ..database import Database

logger = get_logger(__name__)


class UserRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        email: str,
        username: str,
        password_hash: str,
        display_name: str | None = None,
    ) -> Any:
        from ...auth.models import User

        user_id = new_user_id()
        now = datetime.now(timezone.utc).isoformat()

        await self.db.execute(
            """INSERT INTO users (id, email, username, password_hash, display_name, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            (user_id, email, username, password_hash, display_name, now, now),
        )
        await self.db.commit()

        return User(
            id=user_id, email=email, username=username,
            display_name=display_name, created_at=now, updated_at=now,
        )

    async def get(self, user_id: str) -> Any | None:
        row = await self.db.fetchone("SELECT * FROM users WHERE id = $1", (user_id,))
        if row is None:
            return None
        return self._row_to_user(row)

    async def get_by_email(self, email: str) -> Any | None:
        row = await self.db.fetchone("SELECT * FROM users WHERE email = $1", (email,))
        if row is None:
            return None
        return self._row_to_user(row)

    async def get_by_username(self, username: str) -> Any | None:
        row = await self.db.fetchone("SELECT * FROM users WHERE username = $1", (username,))
        if row is None:
            return None
        return self._row_to_user(row)

    async def get_by_email_with_password(self, email: str) -> tuple[Any, str] | None:
        row = await self.db.fetchone("SELECT * FROM users WHERE email = $1", (email,))
        if row is None:
            return None
        user = self._row_to_user(row)
        return user, row["password_hash"]

    async def update(
        self,
        user_id: str,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> Any | None:
        now = datetime.now(timezone.utc).isoformat()
        updates: dict[str, Any] = {"updated_at": now}
        if display_name is not None:
            updates["display_name"] = display_name
        if avatar_url is not None:
            updates["avatar_url"] = avatar_url

        parts = []
        values: list[Any] = []
        for i, (k, v) in enumerate(updates.items(), 1):
            parts.append(f"{k} = ${i}")
            values.append(v)
        values.append(user_id)
        set_clause = ", ".join(parts)
        await self.db.execute(
            f"UPDATE users SET {set_clause} WHERE id = ${len(values)}", tuple(values)
        )
        await self.db.commit()
        return await self.get(user_id)

    async def update_password(self, user_id: str, password_hash: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE users SET password_hash = $1, updated_at = $2 WHERE id = $3",
            (password_hash, now, user_id),
        )
        await self.db.commit()

    async def _update_metadata(self, user_id: str, metadata: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE users SET metadata = $1, updated_at = $2 WHERE id = $3",
            (json.dumps(metadata), now, user_id),
        )
        await self.db.commit()

    async def get_or_create_by_oauth(
        self,
        provider: str,
        provider_user_id: str,
        email: str,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> Any:
        """Look up or create a user from OAuth provider info.

        Resolution order:
        1. Match on metadata.oauth_providers[provider].id
        2. Match on email (link accounts)
        3. Create new user with unusable password
        """
        from ...auth.models import User
        import secrets as _secrets

        # 1. Try to find by (provider, provider_user_id) via metadata
        row = await self.db.fetchone(
            "SELECT * FROM users WHERE metadata -> 'oauth_providers' -> $1 ->> 'id' = $2",
            (provider, str(provider_user_id)),
        )
        if row is not None:
            user = self._row_to_user(row)
            # Optionally refresh display_name/avatar
            return user

        # 2. Try to match by email (link accounts)
        existing = await self.get_by_email(email)
        now = datetime.now(timezone.utc).isoformat()

        if existing is not None:
            # Merge oauth provider info into existing user's metadata
            meta = dict(existing.metadata or {})
            providers = dict(meta.get("oauth_providers") or {})
            providers[provider] = {
                "id": str(provider_user_id),
                "linked_at": now,
            }
            meta["oauth_providers"] = providers
            await self._update_metadata(existing.id, meta)
            logger.info("Linked OAuth provider to existing user",
                        user_id=existing.id, provider=provider)
            return await self.get(existing.id)

        # 3. Create new user
        # Auto-generate username from email local-part (with suffix if taken)
        base_username = email.split("@")[0].lower()
        base_username = "".join(c for c in base_username if c.isalnum() or c in "_-") or "user"
        username = base_username
        suffix = 1
        while await self.get_by_username(username):
            username = f"{base_username}{suffix}"
            suffix += 1
            if suffix > 1000:
                username = f"{base_username}_{_secrets.token_hex(4)}"
                break

        # Unusable password hash (random 64 bytes, never matches any real password)
        unusable_hash = "!" + _secrets.token_urlsafe(64)

        user_id = new_user_id()
        metadata = {
            "oauth_providers": {
                provider: {
                    "id": str(provider_user_id),
                    "linked_at": now,
                }
            },
        }

        await self.db.execute(
            """INSERT INTO users
               (id, email, username, password_hash, display_name, avatar_url, created_at, updated_at, metadata)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
            (user_id, email, username, unusable_hash,
             display_name or username, avatar_url, now, now, json.dumps(metadata)),
        )
        await self.db.commit()

        logger.info("Created new user from OAuth",
                    user_id=user_id, provider=provider, email=email)

        return User(
            id=user_id, email=email, username=username,
            display_name=display_name or username, avatar_url=avatar_url,
            created_at=now, updated_at=now, metadata=metadata,
        )

    def _row_to_user(self, row: Any) -> Any:
        from ...auth.models import User

        metadata = row["metadata"]
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        return User(
            id=row["id"],
            email=row["email"],
            username=row["username"],
            display_name=row["display_name"],
            avatar_url=row["avatar_url"],
            plan=row["plan"],
            is_active=bool(row["is_active"]),
            is_admin=bool(row["is_admin"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            metadata=metadata or {},
        )
