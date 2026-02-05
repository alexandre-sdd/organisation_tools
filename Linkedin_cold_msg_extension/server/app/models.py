from typing import Any

from pydantic import BaseModel


class GenerateRequest(BaseModel):
    my_profile: dict[str, Any]
    target_profile: dict[str, Any]
    hooks: list[str]


class Variant(BaseModel):
    label: str
    text: str
    char_count: int


class GenerateResponse(BaseModel):
    variants: list[Variant]
