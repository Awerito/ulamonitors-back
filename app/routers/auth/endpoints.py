from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import (
    Token,
    User,
    UserCreate,
    UserInDB,
    authenticate_user,
    create_access_token,
    get_password_hash,
    get_user,
)
from app.deps import AdminUser, DbDep, ProfileUser

router = APIRouter(tags=["Users and Authentication"])


@router.post("/token", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbDep,
) -> dict[str, str]:
    """Validate user credentials and return a JWT."""
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # An empty scope request means the user's stored scopes — a plain fetch()
    # login must yield a usable token. A non-empty request must be a subset of
    # the stored scopes.
    if form_data.scopes:
        if not set(form_data.scopes) <= set(user.scopes):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="requested scopes exceed the user's scopes",
                headers={"WWW-Authenticate": "Bearer"},
            )
        scopes = form_data.scopes
    else:
        scopes = user.scopes
    access_token = create_access_token(data={"sub": user.username, "scopes": scopes})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=User)
async def read_users_me(
    current_user: ProfileUser,
) -> User:
    """Return the authenticated user's profile."""
    return current_user


@router.post("/users", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(
    user: UserCreate,
    _: AdminUser,
    db: DbDep,
) -> User:
    """Create a new API user. Requires the admin scope."""
    if await get_user(db, user.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="username already exists"
        )
    hashed_password = get_password_hash(user.password)
    user_db = UserInDB(**user.model_dump(), hashed_password=hashed_password)
    await db.users.insert_one(user_db.model_dump())
    return User(**user_db.model_dump())


@router.get("/users", response_model=list[User])
async def list_users(
    _: AdminUser,
    db: DbDep,
) -> list[User]:
    """List all API users. Requires the admin scope."""
    users = await db.users.find({}, {"_id": 0, "hashed_password": 0}).to_list()
    return [User(**user) for user in users]
