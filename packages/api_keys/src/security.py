import hashlib
import secrets

# Префикс значения ключа: по нему авторизация отличает API-ключ от JWT в `Authorization: Bearer`.
API_KEY_PREFIX = 'plm_'
# Сколько первых символов ключа хранится открыто — чтобы пользователь узнавал ключ в списке.
DISPLAY_PREFIX_LENGTH = 12
_SECRET_BYTES = 32


def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(_SECRET_BYTES)


def hash_api_key(raw_key: str) -> str:
    """SHA-256, а не bcrypt: ключ — 256 бит случайности (перебор бессмысленен), а поиск по хэшу
    должен быть детерминированным, чтобы найти ключ одним индексным запросом."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def display_prefix(raw_key: str) -> str:
    return raw_key[:DISPLAY_PREFIX_LENGTH]


def looks_like_api_key(value: str) -> bool:
    return value.startswith(API_KEY_PREFIX)
