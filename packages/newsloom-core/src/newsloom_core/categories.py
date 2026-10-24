"""Stable primary news categories and the approved category catalogue."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class Category(StrEnum):
    REGULATIONS = "regulations"
    MODELS = "models"
    AGENTS_APPLICATIONS = "agents-applications"
    DEVELOPER_TOOLS = "developer-tools"
    INFRASTRUCTURE = "infrastructure"
    RESEARCH_EVALUATIONS = "research-evaluations"
    SECURITY_SAFETY = "security-safety"
    GOVERNANCE = "governance"
    INDUSTRY_BUSINESS = "industry-business"
    SERVICE_PROVIDERS = "service-providers"
    FINOPS = "finops"


class CategoryDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    id: Category
    label: Annotated[str, Field(min_length=1, max_length=80)]
    description: Annotated[str, Field(min_length=1, max_length=512)]


def load_categories(path: Path = Path("config/categories.json")) -> tuple[CategoryDefinition, ...]:
    value = TypeAdapter(tuple[CategoryDefinition, ...]).validate_json(path.read_bytes())
    if len(value) != len(Category) or {item.id for item in value} != set(Category):
        raise ValueError("invalid_category_catalogue")
    return value
