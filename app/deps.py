from typing import Annotated

from fastapi import Depends, Security
from pymongo.asynchronous.database import AsyncDatabase

from app.auth import User, current_active_user
from app.database.mongo import get_db

DbDep = Annotated[AsyncDatabase, Depends(get_db)]

# One alias per scope, so every endpoint signature states what it requires.
ProfileUser = Annotated[User, Security(current_active_user, scopes=["profile"])]
ReadUser = Annotated[User, Security(current_active_user, scopes=["read"])]
FieldUser = Annotated[User, Security(current_active_user, scopes=["field"])]
AdminUser = Annotated[User, Security(current_active_user, scopes=["admin"])]
