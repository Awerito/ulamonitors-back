from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict, ValidationError
from pymongo.asynchronous.database import AsyncDatabase

from app.config import settings

ALGORITHM = "HS256"
from app.database.mongo import get_db
from app.utils.logger import logger

SCOPES = {
    "admin": "Manage API users.",
    "profile": "Read the current user.",
    "read": "Read sites, sensors, measurements and interventions; open interventions.",
    "field": "Register and configure sites and sensors, close interventions.",
}


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None
    scopes: list[str] = []


class User(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "tech",
                "full_name": "Field Technician",
                "email": "tech@example.local",
                "disabled": False,
                "scopes": ["profile", "read", "field"],
            }
        }
    )

    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool = False
    scopes: list[str] = []


class UserCreate(User):
    password: str


class UserInDB(User):
    hashed_password: str


password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", scopes=SCOPES)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


async def get_user(db: AsyncDatabase, username: str) -> UserInDB | None:
    user = await db.users.find_one({"username": username})
    if not user:
        return None

    return UserInDB(**user)


async def authenticate_user(
    db: AsyncDatabase, username: str, password: str
) -> UserInDB | None:
    user = await get_user(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_duration_minutes
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


async def get_current_user(
    security_scopes: SecurityScopes,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncDatabase, Depends(get_db)],
) -> User:
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        username: str = payload.get("sub", "")
        if username == "":
            raise credentials_exception
        token_scopes = payload.get("scopes", [])
        token_data = TokenData(scopes=token_scopes, username=username)
    except (InvalidTokenError, ValidationError):
        raise credentials_exception
    user = await get_user(db, username=token_data.username or "")
    if user is None:
        raise credentials_exception
    for scope in security_scopes.scopes:
        if scope not in token_data.scopes or scope not in user.scopes:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="not enough permissions",
                headers={"WWW-Authenticate": authenticate_value},
            )

    return user


async def current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="inactive user")
    return current_user


async def create_admin_user(db: AsyncDatabase) -> User | None:
    """Ensure the admin user exists, so the API is usable even without the seed."""
    user = await db.users.find_one({"username": settings.admin_username})
    if user:
        return None

    admin_user = UserInDB(
        username=settings.admin_username,
        hashed_password=get_password_hash(settings.admin_password),
        scopes=list(SCOPES),
        disabled=False,
    )
    await db.users.insert_one(admin_user.model_dump())
    logger.info("[auth] admin user created")
    return User(**admin_user.model_dump())
