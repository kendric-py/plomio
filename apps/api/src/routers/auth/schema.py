from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    display_name: str = Field(description='Отображаемое имя пользователя')
    email: str = Field(description='Email пользователя')
    password: str = Field(description='Пароль в открытом виде', min_length=8)


class LoginRequest(BaseModel):
    email: str = Field(description='Email пользователя')
    password: str = Field(description='Пароль в открытом виде')


class TokenResponse(BaseModel):
    access_token: str = Field(description='JWT access-токен')
    token_type: str = Field(default='bearer', description='Тип токена')


class StatusResponse(BaseModel):
    has_users: bool = Field(description='Есть ли хотя бы один зарегистрированный пользователь')
