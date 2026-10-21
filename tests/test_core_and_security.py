import pytest
import uuid
from decimal import Decimal
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
)
from app.models.user import UserRole
from app.services.catalog_service import slugify


def test_password_hashing():
    raw = "SuperSecretPassword123!"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_token_creation_and_decoding():
    user_id = uuid.uuid4()
    access = create_access_token(user_id=user_id, role=UserRole.CUSTOMER.value, permissions=["read"])
    decoded = decode_token(access)
    assert decoded["sub"] == str(user_id)
    assert decoded["role"] == UserRole.CUSTOMER.value
    assert decoded["type"] == "access"
    assert "read" in decoded["permissions"]


def test_refresh_token_hashing():
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    ref_token = create_refresh_token(user_id=user_id, session_id=session_id)
    h1 = hash_token(ref_token)
    h2 = hash_token(ref_token)
    assert h1 == h2
    assert len(h1) == 64


def test_slugify():
    assert slugify("Heritage Cotton Kurta - Special!") == "heritage-cotton-kurta-special"
    assert slugify("Varanasi Zari Silk Saree") == "varanasi-zari-silk-saree"
