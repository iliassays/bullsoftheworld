"""Wire schemas for auth, posts, and watchlist."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Sentiment = Literal["bull", "bear"]


# --- auth ---
class RegisterIn(BaseModel):
    handle: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    locale: str = "bn"


class LoginIn(BaseModel):
    handle: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handle: str
    name: str
    locale: str


# --- posts ---
class PostCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    sentiment: Sentiment | None = None


class AuthorOut(BaseModel):
    handle: str
    name: str


class PostOut(BaseModel):
    id: int
    author: AuthorOut
    body: str
    sentiment: Sentiment | None = None
    cashtags: list[str] = []
    created_at: dt.datetime


# --- watchlist ---
class WatchlistAdd(BaseModel):
    code: str
