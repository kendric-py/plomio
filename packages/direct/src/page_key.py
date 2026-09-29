import base64
import hashlib
import hmac
import json
import time
from typing import Any

from core.enums import Marketplace

_SECRET_DERIVATION_PREFIX = b'direct-page-key:'


class InvalidPageKeyError(Exception):
    """Ключ повреждён, подделан, просрочен или выдан для другого товара/запроса/маркетплейса —
    вызывающему это одно и то же, различать причины клиенту незачем."""


def derive_page_key_secret(auth_secret_key: str) -> bytes:
    return hashlib.sha256(_SECRET_DERIVATION_PREFIX + auth_secret_key.encode('utf-8')).digest()


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def _sign(secret: bytes, body: str) -> str:
    return _b64_encode(hmac.new(secret, body.encode('ascii'), hashlib.sha256).digest())


def encode_page_key(
    secret: bytes,
    marketplace: Marketplace,
    subject: str,
    cursor: dict[str, Any],
    ttl_seconds: float,
    now: float | None = None,
) -> str:
    """`subject` — артикул или текст поискового запроса: ключ привязан к нему, чтобы его нельзя
    было приложить к другому товару/запросу. Внутренности курсора клиенту не видны и подделать
    их нельзя — подписывает и проверяет только api."""
    issued_at = time.time() if now is None else now
    body = _b64_encode(
        json.dumps(
            {'m': marketplace.value, 'a': subject, 'e': issued_at + ttl_seconds, 'c': cursor},
            separators=(',', ':'),
            ensure_ascii=False,
        ).encode('utf-8'),
    )
    return f'{body}.{_sign(secret, body)}'


def decode_page_key(
    secret: bytes,
    page_key: str,
    marketplace: Marketplace,
    subject: str,
    now: float | None = None,
) -> dict[str, Any]:
    body, separator, signature = page_key.partition('.')
    if not separator or not hmac.compare_digest(signature, _sign(secret, body)):
        raise InvalidPageKeyError('bad signature')
    try:
        claims = json.loads(_b64_decode(body))
        expires_at = float(claims['e'])
        claims_marketplace, claims_subject, cursor = claims['m'], claims['a'], claims['c']
    except (ValueError, KeyError, TypeError) as error:
        raise InvalidPageKeyError('malformed claims') from error
    if expires_at < (time.time() if now is None else now):
        raise InvalidPageKeyError('expired')
    if claims_marketplace != marketplace.value or claims_subject != subject:
        raise InvalidPageKeyError('issued for another target')
    if not isinstance(cursor, dict):
        raise InvalidPageKeyError('malformed cursor')
    return cursor
