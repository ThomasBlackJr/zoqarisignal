from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator
from sqlalchemy import update
from .auth import current_user, get_db
from .models import User, UserPreference
from .schemas import StrictModel

router = APIRouter()
DEFAULT_MODULES = ["metrics", "attention", "issues", "teams", "coaching", "recommendations", "recent"]


class Preferences(StrictModel):
    appearance: Literal["light", "dark", "system"]
    modules: list[
        Literal[
            "metrics", "attention", "recent", "review", "issues", "teams", "coaching", "recommendations", "processing"
        ]
    ] = Field(max_length=9)
    revision: int = Field(ge=0, strict=True)

    @field_validator("modules")
    @classmethod
    def unique(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Dashboard modules must be unique")
        return value


def view(value):
    return (
        {"appearance": value.appearance, "modules": value.modules, "revision": value.revision}
        if value
        else {
            "appearance": "system",
            "modules": DEFAULT_MODULES,
            "revision": 0,
        }
    )


@router.get("/preferences")
def preferences(user=Depends(current_user), db=Depends(get_db)):
    return view(db.get(UserPreference, user.id))


@router.put("/preferences")
def save(body: Preferences, user=Depends(current_user), db=Depends(get_db)):
    # Lock an existing row before the first insert too; never accept a client-supplied user ID.
    db.execute(update(User).where(User.id == user.id).values(active=User.active))
    current = db.get(UserPreference, user.id)
    if body.revision != (current.revision if current else 0):
        raise HTTPException(409, "Preferences changed in another window. Reload before saving.")
    if current is None:
        current = UserPreference(user_id=user.id)
        db.add(current)
    current.appearance = body.appearance
    current.modules = body.modules
    current.revision = body.revision + 1
    db.commit()
    return view(current)
