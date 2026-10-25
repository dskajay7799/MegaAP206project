from typing import Literal
from pydantic import BaseModel, Field, field_validator
from . import config


class HistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(max_length=config.MAX_MESSAGE_CHARS)
    history: list[HistoryItem] = Field(default_factory=list, max_length=12)

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message is empty.")
        return v
