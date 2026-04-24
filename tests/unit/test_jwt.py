"""Unit tests for JWT token creation and validation."""

import time

import pytest

from aegis.auth.jwt import (
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_token,
)
from aegis.utils.errors import AuthError, AuthTokenExpiredError

SECRET = "test-secret-key-that-is-32-chars!!"


def test_create_access_token():
    token = create_access_token("user_123", SECRET)
    assert isinstance(token, str)
    assert len(token) > 0


def test_decode_access_token():
    token = create_access_token("user_123", SECRET)
    payload = decode_token(token, SECRET)
    assert payload["sub"] == "user_123"
    assert payload["type"] == "access"


def test_create_refresh_token():
    token = create_refresh_token("user_123", SECRET)
    payload = decode_token(token, SECRET)
    assert payload["sub"] == "user_123"
    assert payload["type"] == "refresh"


def test_create_token_pair():
    pair = create_token_pair("user_123", SECRET)
    assert "access_token" in pair
    assert "refresh_token" in pair
    assert pair["token_type"] == "bearer"
    assert pair["expires_in"] > 0

    access = decode_token(pair["access_token"], SECRET)
    refresh = decode_token(pair["refresh_token"], SECRET)
    assert access["type"] == "access"
    assert refresh["type"] == "refresh"
    assert access["sub"] == refresh["sub"] == "user_123"


def test_decode_with_wrong_secret():
    token = create_access_token("user_123", SECRET)
    with pytest.raises(AuthError):
        decode_token(token, "wrong-secret-that-is-also-32-ch!!")


def test_expired_token():
    token = create_access_token("user_123", SECRET, expires_in=-1)
    with pytest.raises(AuthTokenExpiredError):
        decode_token(token, SECRET)


def test_decode_garbage_token():
    with pytest.raises(AuthError):
        decode_token("not.a.valid.jwt", SECRET)
