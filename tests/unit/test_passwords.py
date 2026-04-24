"""Unit tests for password hashing."""

from aegis.auth.passwords import hash_password, verify_password


def test_hash_password_returns_string():
    h = hash_password("mypassword")
    assert isinstance(h, str)
    assert h != "mypassword"


def test_hash_password_different_each_time():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2  # Different salts


def test_verify_correct_password():
    h = hash_password("correct")
    assert verify_password("correct", h) is True


def test_verify_wrong_password():
    h = hash_password("correct")
    assert verify_password("wrong", h) is False


def test_verify_empty_password():
    h = hash_password("notempty")
    assert verify_password("", h) is False


def test_verify_invalid_hash():
    assert verify_password("anything", "not-a-valid-hash") is False
