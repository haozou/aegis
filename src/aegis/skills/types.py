"""Skills type definitions."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SkillTrigger(str, Enum):
    KEYWORD = "keyword"
    ALWAYS = "always"
    NEVER = "never"


class SkillMetadata(BaseModel):
    name: str
    description: str = ""
    version: str = "1.0.0"
    trigger: SkillTrigger = SkillTrigger.KEYWORD
    keywords: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    priority: int = 0
    enabled: bool = True


class Skill(BaseModel):
    metadata: SkillMetadata
    system_prompt: str
    source_path: str = ""
