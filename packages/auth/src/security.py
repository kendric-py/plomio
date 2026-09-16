from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from core.configs import AuthConfig
from packages.auth.src.exceptions import InvalidTokenError

auth_config = AuthConfig()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password=password.encode(), salt=bcrypt.gensalt()).decode()


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password=password.encode(), hashed_password=hashed_password.encode())


def create_access_token(user_id: int) -> str:
    expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=auth_config.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {'sub': str(user_id), 'exp': expires_at}
    return jwt.encode(payload=payload, key=auth_config.SECRET_KEY, algorithm=auth_config.ALGORITHM)


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(jwt=token, key=auth_config.SECRET_KEY, algorithms=[auth_config.ALGORITHM])
    except jwt.PyJWTError as error:
        raise InvalidTokenError from error
    return int(payload['sub'])
