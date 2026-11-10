import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Limits(StrictModel):
    steps: int = Field(default=30, ge=1, le=500)
    wall_seconds: float = Field(default=300, gt=0, le=3600)
    command_seconds: float = Field(default=20, gt=0, le=120)
    tokens: int = Field(default=50000, ge=1)
    cost_usd: float = Field(default=1, gt=0)
    output_chars: int = Field(default=12000, ge=100, le=100000)


class Task(StrictModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    repository: str
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    issue: str = Field(min_length=1)
    image: str = "harnesslab-task:local"
    visible_command: list[str] = Field(default_factory=lambda: ["python", "-m", "unittest", "discover", "-s", "tests"])
    grade_command: list[str] = Field(default_factory=lambda: ["python", "-I", "-m", "unittest", "discover", "-s", "/grading"])
    grading_dir: str
    reference_patch: str
    split: Literal["development", "held-out"] = "development"
    provenance: str
    limits: Limits = Field(default_factory=Limits)

    @model_validator(mode="after")
    def commands_present(self):
        if not self.visible_command or not self.grade_command:
            raise ValueError("test commands must not be empty")
        return self


class HarnessConfig(StrictModel):
    schema_version: Literal[1] = 1
    name: Literal["baseline", "resilient"] = "baseline"
    model: str = "fake"
    provider: Literal["fake", "local", "openai-compatible", "anthropic"] = "fake"
    input_usd_per_million: float = Field(default=0, ge=0)
    output_usd_per_million: float = Field(default=0, ge=0)
    pricing_date: str = "unpriced"
    max_output_tokens: int = Field(default=2048, ge=1, le=16384)
    context_chars: int = Field(default=60000, ge=2000)
    mcp_transport: Literal["stdio", "in-process"] = "stdio"

    @model_validator(mode="after")
    def require_pricing(self):
        if self.provider not in {"fake", "local"} and (self.pricing_date == "unpriced" or self.output_usd_per_million <= 0 or self.input_usd_per_million <= 0):
            raise ValueError("paid models require explicit positive input/output prices and pricing_date")
        if self.provider == "local" and (self.input_usd_per_million or self.output_usd_per_million):
            raise ValueError("local inference has no provider API charge; set input/output API prices to zero")
        return self

    def digest(self):
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class Outcome(StrEnum):
    SOLVED = "solved"
    UNSOLVED = "unsolved"
    INFRA_ERROR = "infrastructure_error"
    CANCELLED = "cancelled"
    BUDGET = "budget_exceeded"


def read_task(path: Path) -> Task:
    return Task.model_validate(json.loads(path.read_text()))
