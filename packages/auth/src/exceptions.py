class AuthError(Exception):
    """Базовое исключение доменной области auth."""


class UserAlreadyExistsError(AuthError):
    """Пользователь с таким email уже зарегистрирован."""


class InvalidCredentialsError(AuthError):
    """Неверный email или пароль."""


class InvalidTokenError(AuthError):
    """Токен невалиден, просрочен или подделан."""
