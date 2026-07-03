"""Wire schemas for auth, posts, and watchlist."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Sentiment = Literal["bull", "bear"]

# Lightweight email check (avoids the email-validator dep); the verification email is the real proof.
_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


# --- auth ---
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    contact: str = Field(min_length=3, max_length=255)  # email OR phone — handle auto-generated
    password: str = Field(min_length=8, max_length=128)
    locale: str = "bn"


class LoginIn(BaseModel):
    identifier: str = Field(min_length=2, max_length=255)  # email, phone, or auto-handle
    password: str


class ForgotIn(BaseModel):
    email: str = Field(max_length=255, pattern=_EMAIL)


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class VerifyIn(BaseModel):
    token: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Long-lived rotating refresh token (None only on legacy paths that don't mint sessions).
    refresh_token: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handle: str
    name: str
    locale: str
    role: str = "user"  # 'user' | 'admin' — drives admin-only UI (e.g. delete controls)
    email: str | None = None
    email_verified: bool = False
    phone: str | None = None
    phone_verified: bool = False


class ContactUpdateIn(BaseModel):
    email: str | None = None  # add/change email (re-verifies)
    phone: str | None = None  # add/change phone (BD mobile)


# --- posts ---
ReactionKind = Literal["agree", "disagree"]


class PostCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    sentiment: Sentiment | None = None
    parent_id: int | None = None  # set to reply to another post
    route_code: str | None = Field(default=None, max_length=16, pattern=r"^[A-Za-z0-9]{2,16}$")


class ReactionIn(BaseModel):
    kind: ReactionKind


class AuthorOut(BaseModel):
    handle: str
    name: str


class PostOut(BaseModel):
    id: int
    author: AuthorOut
    body: str
    sentiment: Sentiment | None = None
    cashtags: list[str] = []
    cashtag_changes: dict[str, float] = {}  # code -> latest % change, for the chip's +/- tag
    image_url: str | None = None  # agent-generated card (e.g. Evening Wrap); never user uploads
    created_at: dt.datetime
    kind: str = "user"  # 'user' | 'note' (automated agent desk-note)
    parent_id: int | None = None
    # conviction layer — tallies are non-negative; my_reaction is the caller's stance (if any)
    reply_count: int = 0
    agree: int = 0
    disagree: int = 0
    my_reaction: ReactionKind | None = None
    # Feed moderation: 'published' for everything the feed serves; the create response returns
    # 'pending' (under review) so the author knows, and 'blocked' surfaces via a 422 instead.
    moderation_status: str = "published"
    moderation_reason: str | None = None


# --- watchlist ---
class WatchlistAdd(BaseModel):
    code: str
