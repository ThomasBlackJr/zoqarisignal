import re
from pydantic import Field, field_validator
from .schemas import StrictModel


class Email(StrictModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def address(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(
            r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+",
            value,
        ):
            raise ValueError("Enter a valid work email")
        return value


class Password(StrictModel):
    password: str = Field(min_length=12, max_length=256)

    @field_validator("password")
    @classmethod
    def strength(cls, value):
        if len(set(value)) < 6 or value.strip().lower() in {
            "password1234",
            "password12345",
            "password123456",
            "123456789012",
        }:
            raise ValueError("Choose a longer, less predictable password")
        return value


class Registration(Email, Password):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Name is required")
        return value.strip()


class Token(StrictModel):
    token: str = Field(min_length=40, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class Reset(Token, Password):
    pass


class OrganizationCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Business name is required")
        return value.strip()


class CompleteSetup(StrictModel):
    skip: bool = False
