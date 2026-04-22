"""Pydantic schemas for users."""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from uuid import UUID


class UserResponse(BaseModel):
    id: UUID
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    language: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
