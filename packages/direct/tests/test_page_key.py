import pytest

from core.enums import Marketplace
from packages.direct.src.page_key import (
    InvalidPageKeyError,
    decode_page_key,
    derive_page_key_secret,
    encode_page_key,
)

SECRET = derive_page_key_secret('auth-secret')
CURSOR = {'marketplace': 'ozon', 'next_params': '?page=2&page_key=abc'}


def make_key(now: float = 1000.0, subject: str = '123') -> str:
    return encode_page_key(
        SECRET, Marketplace.OZON, subject, CURSOR, ttl_seconds=900, now=now,
    )


def test_roundtrip_returns_cursor():
    key = make_key()
    assert decode_page_key(SECRET, key, Marketplace.OZON, '123', now=1100.0) == CURSOR


def test_other_marketplace_rejected():
    with pytest.raises(InvalidPageKeyError):
        decode_page_key(SECRET, make_key(), Marketplace.WILDBERRIES, '123', now=1100.0)


def test_other_subject_rejected():
    with pytest.raises(InvalidPageKeyError):
        decode_page_key(SECRET, make_key(), Marketplace.OZON, '124', now=1100.0)


def test_forged_signature_rejected():
    body, _, _ = make_key().partition('.')
    with pytest.raises(InvalidPageKeyError):
        decode_page_key(SECRET, f'{body}.AAAA', Marketplace.OZON, '123', now=1100.0)


def test_tampered_body_rejected():
    _, _, signature = make_key().partition('.')
    forged = make_key(subject='999').partition('.')[0]
    with pytest.raises(InvalidPageKeyError):
        decode_page_key(SECRET, f'{forged}.{signature}', Marketplace.OZON, '999', now=1100.0)


def test_signature_with_other_secret_rejected():
    other_secret = derive_page_key_secret('another')
    with pytest.raises(InvalidPageKeyError):
        decode_page_key(other_secret, make_key(), Marketplace.OZON, '123', now=1100.0)


@pytest.mark.parametrize('garbage', ['', 'abc', '.', 'a.b', '....', 'не-ключ', 'x' * 500])
def test_garbage_rejected(garbage):
    with pytest.raises(InvalidPageKeyError):
        decode_page_key(SECRET, garbage, Marketplace.OZON, '123', now=1100.0)


def test_expired_rejected():
    with pytest.raises(InvalidPageKeyError):
        decode_page_key(SECRET, make_key(now=1000.0), Marketplace.OZON, '123', now=1901.0)


def test_valid_until_expiry_boundary():
    key = make_key(now=1000.0)
    assert decode_page_key(SECRET, key, Marketplace.OZON, '123', now=1900.0) == CURSOR
