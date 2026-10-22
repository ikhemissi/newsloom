"""Strict validation of synthetic platform model contracts."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class Ready(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    ready: Annotated[bool, Field(strict=True)]

    @model_validator(mode="after")
    def affirmative(self) -> Ready:
        if not self.ready:
            raise ValueError("Readiness was not affirmed.")
        return self


class Embedding(BaseModel):
    embedding: Annotated[list[Number], Field(min_length=1536, max_length=1536)]


class EmbeddingResponse(BaseModel):
    data: Annotated[list[Embedding], Field(min_length=1, max_length=1)]


class Message(BaseModel):
    content: str


class Choice(BaseModel):
    message: Message
    finish_reason: Literal["stop"]


class ChatResponse(BaseModel):
    choices: Annotated[list[Choice], Field(min_length=1, max_length=1)]


class Noul(BaseModel):
    type: Literal["noul"]
    noul: Annotated[Number, Field(ge=0, le=1)]


class Answers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ready: Noul


class DecisionResponse(BaseModel):
    answers: Answers


def payloads(
    enrichment: str, embeddings: str, screening: str
) -> dict[str, tuple[str, dict[str, object]]]:
    return {
        "enrichment": (
            "/openai/v1/chat/completions",
            {
                "model": enrichment,
                "messages": [{"role": "user", "content": "Affirm synthetic platform readiness."}],
                "max_completion_tokens": 1024,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "platform_readiness",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {"ready": {"type": "boolean", "enum": [True]}},
                            "required": ["ready"],
                            "additionalProperties": False,
                        },
                    },
                },
            },
        ),
        "embeddings": (
            "/openai/v1/embeddings",
            {"model": embeddings, "input": "Synthetic platform readiness.", "dimensions": 1536},
        ),
        "screening": (
            "/providers/microsoft/v1/systemone",
            {
                "model": screening,
                "state": "This is a synthetic platform readiness check.",
                "questions": {
                    "ready": {
                        "type": "noul",
                        "instructions": "Is the state a synthetic readiness check?",
                    }
                },
            },
        ),
    }


def validate_contract(kind: str, value: object) -> None:
    if kind == "enrichment":
        response = ChatResponse.model_validate(value)
        Ready.model_validate(json.loads(response.choices[0].message.content))
    elif kind == "embeddings":
        EmbeddingResponse.model_validate(value)
    elif kind == "screening":
        DecisionResponse.model_validate(value)
    else:
        raise ValueError("Unknown model contract.")
