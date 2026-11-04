import json
import math
import re

from pydantic import BaseModel, JsonValue

from agent_evaluation.policy import EvaluationFailure


def wire_schema(model: type[BaseModel]) -> dict[str, object]:
    schema = model.model_json_schema()
    schema["properties"]["score"] = {"type": "string"}
    return schema


def score_value(row: BaseModel) -> float:
    value = row.model_dump(mode="json").get("score")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationFailure("invalid_publication_score_encoding")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise EvaluationFailure("invalid_publication_score_encoding")
    return float(value)


def wire_row(row: BaseModel) -> dict[str, object]:
    value: dict[str, object] = row.model_dump(mode="json")
    value["score"] = repr(score_value(row))
    return value


def read_row[Model: BaseModel](
    model: type[Model], value: JsonValue, *, canonical_text_only: bool = False
) -> Model:
    if isinstance(value, dict) and "item" in value:
        if set(value) != {"item"} or not isinstance(value["item"], dict):
            raise EvaluationFailure("invalid_publication_datasource_wrapper")
        value = value["item"]
    if isinstance(value, dict):
        raw = value.get("score")
        if isinstance(raw, str):
            try:
                score = float(raw)
            except ValueError:
                raise EvaluationFailure("invalid_publication_score_encoding") from None
            if not math.isfinite(score) or not 0 <= score <= 1 or repr(score) != raw:
                raise EvaluationFailure("invalid_publication_score_encoding")
            value = {**value, "score": score}
        elif canonical_text_only:
            raise EvaluationFailure("invalid_publication_score_encoding")
    return model.model_validate_json(json.dumps(value))


def has_error(value: JsonValue) -> bool:
    if isinstance(value, dict):
        return any(has_error(child) for child in value.values())
    return value is not None


def identifier(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[a-zA-Z0-9_-]{1,256}", value) is None:
        raise EvaluationFailure("invalid_publication_reference")
    return value
