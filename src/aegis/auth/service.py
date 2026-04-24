"""Authentication service — registration, login, token management."""

from __future__ import annotations

from ..storage.database import Database
from ..storage.repositories.users import UserRepository
from ..utils.errors import AuthError
from ..utils.logging import get_logger
from .jwt import create_token_pair
from .models import TokenPair, User, UserCreate, UserLogin
from .passwords import hash_password, verify_password

logger = get_logger(__name__)


class AuthService:
    """Handles user registration, login, and token management."""

    def __init__(self, user_repo: UserRepository, jwt_secret: str) -> None:
        self._repo = user_repo
        self._jwt_secret = jwt_secret

    async def register(self, data: UserCreate) -> tuple[User, TokenPair]:
        """Register a new user and return user + tokens."""
        # Check for existing email
        existing = await self._repo.get_by_email(data.email)
        if existing:
            raise AuthError("A user with this email already exists")

        # Check for existing username
        existing = await self._repo.get_by_username(data.username)
        if existing:
            raise AuthError("This username is already taken")

        # Hash password and create user
        password_hash = hash_password(data.password)
        user = await self._repo.create(
            email=data.email,
            username=data.username,
            password_hash=password_hash,
            display_name=data.display_name or data.username,
        )

        logger.info("User registered", user_id=user.id, username=user.username)

        # Generate tokens
        token_data = create_token_pair(user.id, self._jwt_secret)
        tokens = TokenPair(**token_data)

        return user, tokens

    async def login(self, data: UserLogin) -> tuple[User, TokenPair]:
        """Authenticate a user and return user + tokens."""
        # Look up user
        user_with_hash = await self._repo.get_by_email_with_password(data.email)
        if not user_with_hash:
            raise AuthError("Invalid email or password")

        user, password_hash = user_with_hash

        # Verify password
        if not verify_password(data.password, password_hash):
            raise AuthError("Invalid email or password")

        if not user.is_active:
            raise AuthError("Account is deactivated")

        logger.info("User logged in", user_id=user.id)

        # Generate tokens
        token_data = create_token_pair(user.id, self._jwt_secret)
        tokens = TokenPair(**token_data)

        return user, tokens

    async def login_oauth(
        self,
        provider: str,
        provider_user_id: str,
        email: str,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> tuple[User, TokenPair]:
        """Authenticate via OAuth — finds/links/creates user, returns tokens."""
        user = await self._repo.get_or_create_by_oauth(
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
            display_name=display_name,
            avatar_url=avatar_url,
        )
        if not user.is_active:
            raise AuthError("Account is deactivated")

        logger.info("OAuth login", user_id=user.id, provider=provider)

        token_data = create_token_pair(user.id, self._jwt_secret)
        tokens = TokenPair(**token_data)
        return user, tokens

    async def refresh_tokens(self, user_id: str) -> TokenPair:
        """Generate a new token pair for a valid user."""
        user = await self._repo.get(user_id)
        if not user:
            raise AuthError("User not found")
        if not user.is_active:
            raise AuthError("Account is deactivated")

        token_data = create_token_pair(user.id, self._jwt_secret)
        return TokenPair(**token_data)

    async def get_user(self, user_id: str) -> User | None:
        """Get a user by ID."""
        return await self._repo.get(user_id)
